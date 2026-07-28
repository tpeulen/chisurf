"""A sub-population of a burst is a column of its row, not a row of its own.

The burst table has one row per burst and every companion is merged onto it by
position, so a variable number of dwells cannot become a variable number of
rows. Splitting the fit by H2MM state therefore widens the row: `Tau S0 (green)`
beside `Tau (green)`. These pin that, and the reason it is worth doing — the
all-photon fit of a dynamic burst is a blend that belongs to neither state.
"""

from __future__ import annotations

from multiprocessing import shared_memory

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.burst.burst_mle_analysis._mp_worker import (  # noqa: E402
    process_one_file_worker,
)

N_BINS, BINNING, PERIOD = 128, 32, 13.5
DT = PERIOD / N_BINS


def _cfg(state_min_photons=20, min_photons=10):
    x = np.arange(N_BINS)
    g = np.exp(-0.5 * ((x - 8) / 1.5) ** 2)
    g /= g.sum()
    return dict(
        sb=0, eb=N_BINS, half_len=N_BINS, dt=DT, period=PERIOD, g_factor=1.0,
        l1=0.0, l2=0.0, p2s_twoIstar=True, BIFL_scatter=False,
        min_photons=min_photons, state_min_photons=state_min_photons,
        x0=np.array([2.0, 0.0, 0.38, 1.22]),
        fixed=np.array([0, 1, 1, 1], dtype=np.int32),
        irf=np.concatenate([g, g]), bg=np.zeros(2 * N_BINS),
        class_lut=np.array([0, 1], dtype=np.int8), model="fit23", method="Fit23",
        param_names=["tau", "gamma", "r0", "rho"],
    )


def _synth(taus=(3.6, 1.0), n_bursts=40, per_state=300, seed=0):
    """Bursts of two states with known lifetimes, as real TCSPC photons.

    Convolved with the same IRF the fit uses and **wrapped** into the excitation
    period — not clipped. Clipping piles every late photon into the last bin,
    and while a 300-photon burst has too much noise to care, a decay pooled over
    forty of them does not: the fit stretches τ to cover that spike (measured:
    3.6 ns → 8.5 ns). The artefact is in the generator, not the estimator.
    """
    rng = np.random.default_rng(seed)
    mt, rc, st = [], [], []
    for _ in range(n_bursts):
        for s, tau in enumerate(taus):
            t = rng.normal(8, 1.5, per_state) + rng.exponential(tau / DT, per_state)
            mt.append(np.rint(t).astype(np.int64) % N_BINS)
            rc.append(rng.integers(0, 2, per_state))
            st.append(np.full(per_state, s))
    width = len(taus) * per_state
    return (
        np.concatenate(mt).astype(np.uint16),
        np.concatenate(rc).astype(np.uint16),
        np.concatenate(st).astype(np.int8),
        [(i * width, (i + 1) * width) for i in range(n_bursts)],
    )


def _in_shared_memory(arrays):
    """Yield shared-memory blocks for ``arrays``, unlinked afterwards."""
    blocks = []
    for a in arrays:
        sh = shared_memory.SharedMemory(create=True, size=a.nbytes)
        np.ndarray(a.shape, dtype=a.dtype, buffer=sh.buf)[:] = a
        blocks.append(sh)
    return blocks


def _run(taus=(3.6, 1.0), n_bursts=40, per_state=300, seed=0, cfg=None, **cfg_kw):
    """Two states per burst with known lifetimes, through the real worker."""
    mt, rc, st, bursts = _synth(taus, n_bursts, per_state, seed)
    blocks = _in_shared_memory([rc, mt, st])
    try:
        rc_sh, mt_sh, st_sh = blocks
        args = ("m000.spc", bursts, rc_sh.name, rc.shape, str(rc.dtype),
                mt_sh.name, mt.shape, str(mt.dtype), ["green"],
                {"green": cfg if cfg is not None else _cfg(**cfg_kw)}, 0,
                (st_sh.name, st.shape, str(st.dtype), len(taus)))
        out, n = process_one_file_worker(args)
    finally:
        for sh in blocks:
            sh.close()
            sh.unlink()
    import pandas as pd

    return pd.DataFrame(out), n


def test_each_state_gets_its_own_lifetime_column():
    df, n = _run()
    assert len(df) == 40 == n, "still one row per burst — the grain is the burst"
    assert {"Tau (green)", "Tau S0 (green)", "Tau S1 (green)"} <= set(df.columns)

    tau0 = df["Tau S0 (green)"].median()
    tau1 = df["Tau S1 (green)"].median()
    assert 2.8 < tau0 < 4.6, tau0
    assert 0.6 < tau1 < 1.5, tau1

    # …and the reason the split exists: the all-photon fit of a dynamic burst
    # lands between the two states and belongs to neither.
    blended = df["Tau (green)"].median()
    assert tau1 < blended < tau0, (tau1, blended, tau0)


def test_the_state_columns_never_collide_with_the_all_photon_ones():
    """A duplicate name is dropped on merge, taking its data with it."""
    df, _ = _run(n_bursts=4)
    assert len(set(df.columns)) == len(df.columns)
    identity = {"First File", "Detector"}
    assert identity <= set(df.columns)
    # The identity columns appear once, not once per state.
    assert sum(c.startswith("First File") for c in df.columns) == 1


def test_a_state_too_thin_to_fit_is_reported_not_dropped():
    """The row must survive: a missing row shifts every later burst."""
    df, _ = _run(per_state=5, n_bursts=6, state_min_photons=1000, min_photons=1)
    assert len(df) == 6
    assert df["Tau S0 (green)"].isna().all()
    assert (df["Ng-p S0"] + df["Ng-s S0"] > 0).all(), "counts are still reported"


def test_without_state_info_the_worker_behaves_exactly_as_before():
    """The split is opt-in; an ordinary run must be untouched."""
    rng = np.random.default_rng(1)
    n = 600
    mt = np.clip(rng.exponential(3.0 / DT, n) + 8, 0, N_BINS - 1).astype(np.uint16)
    rc = rng.integers(0, 2, n).astype(np.uint16)
    blocks = []

    def put(a):
        sh = shared_memory.SharedMemory(create=True, size=a.nbytes)
        np.ndarray(a.shape, dtype=a.dtype, buffer=sh.buf)[:] = a
        blocks.append(sh)
        return sh

    try:
        rc_sh, mt_sh = put(rc), put(mt)
        args = ("m000.spc", [(0, n)], rc_sh.name, rc.shape, str(rc.dtype),
                mt_sh.name, mt.shape, str(mt.dtype), ["green"],
                {"green": _cfg()}, 0, None)
        out, _ = process_one_file_worker(args)
    finally:
        for sh in blocks:
            sh.close()
            sh.unlink()

    assert len(out) == 1
    assert not [c for c in out[0] if " S0" in c or " S1" in c]
    assert "Tau (green)" in out[0]


def _pool(taus=(3.6, 1.0), n_bursts=40, per_state=300, seed=0, **cfg_kw):
    """Pool the same synthetic bursts through the real pooling worker."""
    from chisurf.plugins.burst.burst_mle_analysis._mp_worker import pool_states_worker

    mt, rc, st, bursts = _synth(taus, n_bursts, per_state, seed)
    blocks = _in_shared_memory([rc, mt, st])
    try:
        rc_sh, mt_sh, st_sh = blocks
        args = (bursts, rc_sh.name, rc.shape, str(rc.dtype),
                mt_sh.name, mt.shape, str(mt.dtype), ["green"],
                {"green": _cfg(**cfg_kw)},
                (st_sh.name, st.shape, str(st.dtype), len(taus)))
        return pool_states_worker(args)
    finally:
        for sh in blocks:
            sh.close()
            sh.unlink()


def test_the_pooled_decay_holds_every_burst_photon_of_its_state():
    """The pooled decay is the measurement's photons of a state, not a sample."""
    n_bursts, per_state = 40, 300
    pooled = _pool(n_bursts=n_bursts, per_state=per_state)
    green = pooled["green"]
    assert green.shape == (2, 2, N_BINS)  # (state, P/S, bin)
    for state in (0, 1):
        assert int(green[state].sum()) == n_bursts * per_state, (
            "every photon of the state, from every burst"
        )


def test_the_pooled_fit_is_the_state_lifetime_and_beats_a_single_burst():
    """Pooling is what makes the per-state lifetime a number worth quoting."""
    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard as W,
    )

    pooled = _pool()
    fits = W._fit_pooled_state_decays(pooled, ["green"], {"green": _cfg()}, 0)
    rows = W._state_lifetime_rows(fits, "fit23", ["tau", "gamma", "r0", "rho"])

    by_state = {r["State"]: r for r in rows}
    assert set(by_state) == {0, 1}
    assert abs(by_state[0]["Tau"] - 3.6) < 0.25, by_state[0]["Tau"]
    assert abs(by_state[1]["Tau"] - 1.0) < 0.25, by_state[1]["Tau"]
    assert by_state[0]["Photons"] == 40 * 300
    assert by_state[0]["Colour"] == "green"

    # Tighter than the per-burst fits it seeds, which is the whole point: one
    # burst's state is tens of photons, the pooled state is all of them.
    df, _ = _run()
    per_burst_spread = float(df["Tau S0 (green)"].std())
    pooled_error = abs(by_state[0]["Tau"] - 3.6)
    assert pooled_error < per_burst_spread / 2, (pooled_error, per_burst_spread)


def test_a_states_burst_fits_start_from_that_states_pooled_lifetime():
    """The seam that carries the pooled result into the per-burst pass.

    Pinned with τ *fixed*: the estimator then reports the start value it was
    given, so the assertion reads the seed directly instead of guessing whether
    a converged fit used it.
    """
    cfg = _cfg()
    cfg["fixed"] = np.array([1, 1, 1, 1], dtype=np.int32)
    cfg["state_x0"] = {0: np.array([7.0, 0.0, 0.38, 1.22]),
                       1: np.array([0.5, 0.0, 0.38, 1.22])}

    df, _ = _run(n_bursts=3, per_state=200, seed=3, cfg=cfg)
    assert (df["Tau S0 (green)"] == 7.0).all(), df["Tau S0 (green)"].tolist()
    assert (df["Tau S1 (green)"] == 0.5).all(), df["Tau S1 (green)"].tolist()
    # The all-photon fit keeps the panel's own start value, not a state's.
    assert (df["Tau (green)"] == 2.0).all(), df["Tau (green)"].tolist()


def test_the_pooled_step_fits_writes_and_seeds_in_one_go(qapp, tmp_path):
    """The whole global-lifetime step, over the real process pool.

    Pools across files, fits each state, writes the table beside the analysis,
    and puts each fitted lifetime into the job payloads as that state's start
    value — the piece the per-burst pass then reads.
    """
    import multiprocessing as mp

    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    analysis = tmp_path / "burstwise_All 0.1000#15"
    (analysis / "bi4_bur").mkdir(parents=True)
    bur = analysis / "bi4_bur" / "m000.bur"
    bur.write_text("")

    mt, rc, st, bursts = _synth()
    blocks = _in_shared_memory([rc, mt, st])
    w = MLELifetimeAnalysisWizard()
    try:
        rc_sh, mt_sh, st_sh = blocks
        cfg = _cfg()
        jobs = [("m000.spc", bursts, rc_sh.name, rc.shape, str(rc.dtype),
                 mt_sh.name, mt.shape, str(mt.dtype), ["green"], {"green": cfg}, 0,
                 (st_sh.name, st.shape, str(st.dtype), 2))]
        w.burst_files_list.get_selected_files = lambda: [str(bur)]
        rows = w._apply_pooled_state_fits(
            jobs, ["green"], 2, mp.get_context("spawn"), 2, "fit23",
            ["tau", "gamma", "r0", "rho"],
        )
    finally:
        for sh in blocks:
            sh.close()
            sh.unlink()
        w.close()

    assert [r["State"] for r in rows] == [0, 1]
    assert abs(rows[0]["Tau"] - 3.6) < 0.25, rows[0]["Tau"]
    assert (analysis / "Info" / "state_lifetimes.csv").exists()

    seeds = jobs[0][9]["green"]["state_x0"]
    assert set(seeds) == {0, 1}
    assert seeds[0][0] == rows[0]["Tau"], "the seed is the pooled lifetime itself"
    # ...and only the lifetime is seeded; the rest of the start vector stands.
    assert list(seeds[0][1:]) == list(cfg["x0"][1:])


def test_state_lifetimes_are_written_beside_the_analysis_not_as_a_companion(
    qapp, tmp_path
):
    """One row per *state* — a companion is one row per burst, merged by position.

    Written into a ``b?4`` folder this table would shift every burst after the
    first, which is exactly what the companion contract exists to prevent.
    """
    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    analysis = tmp_path / "burstwise_All 0.1000#15"
    (analysis / "bi4_bur").mkdir(parents=True)
    bur = analysis / "bi4_bur" / "m000.bur"
    bur.write_text("")

    w = MLELifetimeAnalysisWizard()
    try:
        w.burst_files_list.get_selected_files = lambda: [str(bur)]
        rows = [{"Detector": "green", "Colour": "green", "State": 0,
                 "Photons (parallel)": 10, "Photons (perpendicular)": 8,
                 "Photons": 18, "Tau": 3.6, "2I*": 1.0},
                {"Detector": "green", "Colour": "green", "State": 1,
                 "Photons (parallel)": 5, "Photons (perpendicular)": 4,
                 "Photons": 9, "Tau": 1.0, "2I*": 1.1}]
        written = w.write_state_lifetimes(rows)
    finally:
        w.close()

    assert written == [analysis / "Info" / "state_lifetimes.csv"]
    text = written[0].read_text()
    assert text.splitlines()[0].startswith("Detector,Colour,State")
    assert len(text.strip().splitlines()) == 3  # header + one row per state
    assert not list(analysis.glob("b?4")), "not a companion folder"


def test_ticking_the_split_invalidates_the_reuse_gate(qapp):
    """Otherwise Run reports 'Unchanged' and never produces the state columns.

    The export is skipped when the fingerprint matches what is already on disk.
    Splitting by state changes what is fitted *and* what is written, so it must
    move the fingerprint — the whole workflow is walked with Next, and the
    natural order is to fit, run H2MM, then come back and tick the box.
    """
    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    w = MLELifetimeAnalysisWizard()
    try:
        w.checkBox_split_by_state.setChecked(False)
        plain = w.batch_settings()
        w.checkBox_split_by_state.setChecked(True)
        split = w.batch_settings()
        assert plain != split, "the split must be part of the settings fingerprint"
        assert split["split_by_state"] is True

        before = dict(split)
        w.spinBox_state_min_photons.setValue(w.state_min_photons + 5)
        assert w.batch_settings() != before, "the state floor changes the fit too"
    finally:
        w.close()
