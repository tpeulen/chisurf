"""Faithful state decoding in the H2MM plugin, and writing it back to photons.

Viterbi answers *"what is the single most likely state sequence"*. An occupancy,
a per-state decay, or a state-labelled photon stream asks *"how do the photons
distribute over the states"*, and the argmax answers that with a one-directional
bias. These tests hold the plugin to offering — and correctly reporting — the
decoders that do not.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest
import tttrlib

from chisurf.plugins.burst.burst_h2mm.core import engines, h2mm
from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze
from chisurf.plugins.burst.burst_h2mm.core.photons import StreamDef, bursts_from_dataframe
from chisurf.plugins.burst.burst_h2mm.core.state_tttr import UNASSIGNED, write_state_tttr

pytestmark = pytest.mark.skipif(
    not engines._use_tttrlib(),
    reason="the faithful decoders live only in the tttrlib C++ engine",
)


def _overlapping_gt():
    """Two states at E = 0.40 / 0.60 with 75/25 occupancy.

    Overlapping emission profiles and an uneven population is the regime where
    winner-takes-all hurts most, so it is the one worth testing in.
    """
    k01, k10 = 3e-4, 9e-4
    return h2mm.H2mmModel(
        np.array([k10 / (k01 + k10), k01 / (k01 + k10)]),
        np.array([[1 - k01, k01], [k10, 1 - k10]]),
        np.array([[0.60, 0.40], [0.40, 0.60]]),
    )


def _simulate(n_bursts=120, burst_len=200, seed=3):
    gt = _overlapping_gt()
    rng = np.random.default_rng(seed)
    times = [
        np.cumsum(rng.integers(1, 60, size=burst_len)).astype(np.int64)
        for _ in range(n_bursts)
    ]
    streams = h2mm.simulate_bursts(gt, times, seed=seed + 7)
    return times, streams


def _dataset(with_background=True, n_bursts=60, burst_len=120, seed=3):
    """Simulate → a real tttrlib.TTTR → the plugin's extraction, with meta."""
    times, streams = _simulate(n_bursts, burst_len, seed)
    rng = np.random.default_rng(seed + 1)

    macro, chan, rows = [], [], []
    off, base = 0, 0
    for t, s in zip(times, streams):
        macro.append((t - t[0] + base).astype(np.uint64))
        chan.append(s.astype(np.int8))
        rows.append(("sim.spc", off, off + len(t) - 1))
        off += len(t)
        base = int(macro[-1][-1])
        if with_background:
            # Photons outside every burst: what a decoder never sees, and what
            # both persistence paths still have to carry.
            n_bg = 15
            bg = base + np.cumsum(rng.integers(1, 500, size=n_bg))
            macro.append(bg.astype(np.uint64))
            chan.append(rng.integers(0, 2, size=n_bg).astype(np.int8))
            off += n_bg
            base = int(bg[-1])
        base += 100000

    macro = np.concatenate(macro).astype(np.uint64)
    chan = np.concatenate(chan).astype(np.int8)
    micro = (np.arange(macro.size) % 4096).astype(np.uint16)
    et = np.zeros(macro.size, dtype=np.int8)
    tttr = tttrlib.TTTR()
    tttr.append_events(macro, micro, chan, et, False, 0)

    df = pd.DataFrame(rows, columns=["First File", "First Photon", "Last Photon"])
    defs = [StreamDef("green", [0]), StreamDef("red", [1])]
    data, meta = bursts_from_dataframe(
        df, {"sim.spc": tttr}, defs, min_photons=3, return_meta=True)
    return data, meta, df, tttr


# ---------------------------------------------------------------------------
# Decoders
# ---------------------------------------------------------------------------

class TestDecoders:
    """The three decoders, and the bias the sampling ones remove."""

    def setup_method(self):
        times, streams = _simulate(n_bursts=60, burst_len=150, seed=5)
        self.data = h2mm.prepare_bursts(times, streams, n_streams=2)
        self.model = engines.fit_one(self.data, 2, "em", n_restarts=1, seed=0)

    def test_posterior_is_a_distribution(self):
        gamma, n_underflow = engines.posterior(self.model, self.data)
        assert gamma.shape == (self.data.n_photons, 2)
        assert n_underflow == 0
        np.testing.assert_allclose(gamma.sum(axis=1), 1.0, atol=1e-5)

    def test_decode_dispatches_all_three(self):
        for decoder in engines.DECODERS:
            path, _ = engines.decode(self.model, self.data, decoder, seed=1)
            assert path.shape == (self.data.n_photons,)
            assert set(np.unique(path)).issubset({0, 1})

    def test_sampling_decoders_are_reproducible(self):
        a, _ = engines.decode(self.model, self.data, "jitter", seed=11)
        b, _ = engines.decode(self.model, self.data, "jitter", seed=11)
        c, _ = engines.decode(self.model, self.data, "jitter", seed=12)
        np.testing.assert_array_equal(a, b)
        assert (a != c).any()

    def test_unknown_decoder_falls_back_to_viterbi(self):
        assert engines.normalize_decoder("nonsense") == "viterbi"
        assert engines.normalize_decoder(None) == "viterbi"
        assert engines.normalize_decoder("FFBS") == "ffbs"

    def test_jitter_reproduces_the_posterior_that_viterbi_biases(self):
        gamma, _ = engines.posterior(self.model, self.data)
        post = gamma.mean(axis=0)
        vpath, _ = engines.decode(self.model, self.data, "viterbi")
        jpath, _ = engines.decode(self.model, self.data, "jitter", seed=0)
        occ_v = np.bincount(vpath, minlength=2) / vpath.size
        occ_j = np.bincount(jpath, minlength=2) / jpath.size
        err_v = np.abs(occ_v - post).max()
        err_j = np.abs(occ_j - post).max()
        assert err_j < err_v / 2, f"jitter {err_j:.4f} vs viterbi {err_v:.4f}"
        assert err_v > 0.01, "the bias should be visible in this regime"


# ---------------------------------------------------------------------------
# analyze()
# ---------------------------------------------------------------------------

class TestAnalyzeDecoder:
    """What analyze() reports, and which path each product is derived from."""

    def setup_method(self):
        times, streams = _simulate(n_bursts=50, burst_len=150, seed=9)
        self.data = h2mm.prepare_bursts(times, streams, n_streams=2)

    def _run(self, decoder):
        return analyze(self.data, state_counts=(2,), n_restarts=1,
                       decoder=decoder, decoder_seed=4)

    def test_default_is_viterbi_and_records_it(self):
        ana = analyze(self.data, state_counts=(2,), n_restarts=1)
        assert ana.decoder == "viterbi"
        assert ana.dwell_decoder == "viterbi"
        np.testing.assert_array_equal(ana.path, ana.dwell_path)

    def test_posterior_populations_are_reported_and_unbiased(self):
        ana = self._run("viterbi")
        post = np.asarray(ana.posterior_populations)
        assert post.shape == ana.populations.shape
        assert np.isfinite(post).all()
        np.testing.assert_allclose(post.sum(), 1.0, atol=1e-6)
        # The counted Viterbi populations are the biased ones; the two should
        # differ, which is the whole reason both are reported.
        assert np.abs(post - ana.populations).max() > 1e-3

    def test_jitter_populations_track_the_posterior(self):
        ana = self._run("jitter")
        assert ana.decoder == "jitter"
        np.testing.assert_allclose(
            ana.populations, np.asarray(ana.posterior_populations), atol=0.02)

    def test_jitter_dwells_come_from_viterbi_not_the_draw(self):
        # Independent per-photon draws shatter dwells; taking dwell statistics
        # from them would be nonsense, so analyze() must not.
        ana = self._run("jitter")
        assert ana.dwell_decoder == "viterbi"
        assert (ana.path != ana.dwell_path).any()
        vit = analyze(self.data, state_counts=(2,), n_restarts=1)
        np.testing.assert_array_equal(ana.dwell_path, vit.dwell_path)
        assert len(ana.dwells) == len(vit.dwells)

    def test_ffbs_keeps_its_own_dwells(self):
        ana = self._run("ffbs")
        assert ana.decoder == "ffbs"
        assert ana.dwell_decoder == "ffbs"
        np.testing.assert_array_equal(ana.path, ana.dwell_path)

    def test_ffbs_dwells_are_not_shattered(self):
        # The claim the decoder table makes, as an assertion: FFBS dwell counts
        # stay in the same league as Viterbi's, a marginal draw's do not.
        vit = analyze(self.data, state_counts=(2,), n_restarts=1)
        ffbs = self._run("ffbs")
        jitter_path, _ = engines.decode(ffbs.best.model, self.data, "jitter", 4)
        offsets = np.asarray(self.data.burst_offsets)

        def n_dwells(p):
            return sum(1 + int((np.diff(p[a:b]) != 0).sum())
                       for a, b in zip(offsets[:-1], offsets[1:]))

        d_v, d_f, d_j = (n_dwells(vit.path), n_dwells(ffbs.path),
                         n_dwells(jitter_path))
        assert d_j > 2 * d_f, f"jitter {d_j} vs ffbs {d_f}"
        assert d_f < 5 * d_v, f"ffbs {d_f} vs viterbi {d_v}"


# ---------------------------------------------------------------------------
# Writing the assignment back into the photon stream
# ---------------------------------------------------------------------------

class TestStateTttr:
    """Writing the assignment back into the photon stream, both ways."""

    def setup_method(self):
        self.data, self.meta, self.df, self.tttr = _dataset()
        self.ana = analyze(self.data, state_counts=(2,), n_restarts=1,
                           decoder="jitter", decoder_seed=2)
        self.files = list(self.df["First File"].astype(str))

    def _write(self, tmp_path, **kw):
        return write_state_tttr(
            self.meta, self.ana.path, np.asarray(self.data.streams),
            {"sim.spc": self.tttr}, self.meta.burst_rows, self.files, tmp_path,
            model=self.ana.best.model, decoder=self.ana.decoder,
            seed=self.ana.decoder_seed, n_states=2, **kw)

    def test_writes_both_outputs(self, tmp_path):
        out = self._write(tmp_path)
        assert set(out.tttr_paths) == {"sim"}
        assert set(out.sidecar_paths) == {"sim"}
        assert pathlib.Path(out.tttr_paths["sim"]).exists()
        assert pathlib.Path(out.sidecar_paths["sim"]).exists()
        assert out.n_unassigned["sim"] > 0  # background photons exist

    def test_ptu_keeps_every_photon_and_survives_a_round_trip(self, tmp_path):
        out = self._write(tmp_path, write_sidecar=False)
        back = tttrlib.TTTR(out.tttr_paths["sim"], "PTU")
        assert back.size() == self.tttr.size()
        np.testing.assert_array_equal(
            np.asarray(back.macro_times), np.asarray(self.tttr.macro_times))

    def test_channel_ids_are_compacted(self, tmp_path):
        out = self._write(tmp_path, write_sidecar=False)
        back = tttrlib.TTTR(out.tttr_paths["sim"], "PTU")
        ids = np.unique(np.asarray(back.routing_channels))
        cmap = out.channel_maps["sim"]
        # 2 source channels compressed to 0,1 then 2x2 states at 2..5.
        assert cmap["source"] == {0: 0, 1: 1}
        assert cmap["highest"] == 5
        assert ids.min() >= 0 and ids.max() <= cmap["highest"]

    def test_the_two_outputs_agree_photon_for_photon(self, tmp_path):
        out = self._write(tmp_path)
        back = tttrlib.TTTR(out.tttr_paths["sim"], "PTU")
        sc = tttrlib.H2mmStateSidecar.read(out.sidecar_paths["sim"])
        och = np.asarray(back.routing_channels)
        states = np.asarray(cmap_states := out.channel_maps["sim"]["states"])
        for st in range(2):
            want = [states[s][st] for s in range(2)]
            idx_ptu = np.flatnonzero(np.isin(och, want))
            idx_side = sc.indices_for_state(st)
            np.testing.assert_array_equal(idx_ptu, idx_side)
        assert cmap_states  # the map is what makes either readable

    def test_states_land_on_the_photons_the_path_names(self, tmp_path):
        out = self._write(tmp_path, write_tttr=False)
        sc = tttrlib.H2mmStateSidecar.read(out.sidecar_paths["sim"])
        states = sc.states_np
        idx = np.asarray(self.meta.photon_index, dtype=np.int64)
        np.testing.assert_array_equal(
            states[idx], np.asarray(self.ana.path, dtype=np.uint8))
        # Everything else was never analysed and must say so, not default to 0.
        rest = np.setdiff1d(np.arange(self.tttr.size()), idx)
        assert (states[rest] == UNASSIGNED).all()
        assert rest.size > 0

    def test_sidecar_records_how_the_decode_was_made(self, tmp_path):
        out = self._write(tmp_path, write_tttr=False)
        sc = tttrlib.H2mmStateSidecar.read(out.sidecar_paths["sim"])
        assert sc.decoder == "jitter"
        assert sc.seed == 2
        assert sc.n_states == 2
        assert sc.has_channel_map
        np.testing.assert_allclose(
            sc.model.obs_np, self.ana.best.model.obs, atol=1e-9)

    def test_per_state_decays_can_be_built_from_the_written_file(self, tmp_path):
        # The point of the whole exercise: a per-state decay as an ordinary
        # channel selection, with no H2MM-aware code in the reader.
        out = self._write(tmp_path, write_sidecar=False)
        back = tttrlib.TTTR(out.tttr_paths["sim"], "PTU")
        och = np.asarray(back.routing_channels)
        micro = np.asarray(back.micro_times)
        states = out.channel_maps["sim"]["states"]
        total = 0
        for st in range(2):
            sel = np.isin(och, [states[s][st] for s in range(2)])
            assert sel.any()
            total += int(sel.sum())
            assert np.histogram(micro[sel], bins=16)[0].sum() == sel.sum()
        assert total == self.tttr.size() - out.n_unassigned["sim"]

    def test_refuses_without_a_photon_index(self, tmp_path):
        meta = type(self.meta)(
            macro_time=self.meta.macro_time, micro_time=self.meta.micro_time,
            channel=self.meta.channel, burst_id=self.meta.burst_id,
            photon_index=None,
        )
        with pytest.raises(ValueError, match="photon_index"):
            write_state_tttr(
                meta, self.ana.path, np.asarray(self.data.streams),
                {"sim.spc": self.tttr}, self.meta.burst_rows, self.files, tmp_path)
