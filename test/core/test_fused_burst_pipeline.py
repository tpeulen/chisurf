"""The fused tttrlib burst pipeline gives what ChiSurf's Python path gives.

A simulated two-colour stream, three detectors on four channels and two PIE windows (the
RVZMT150 shape), through both paths:

* the search, selection mask and burst table (``apply_photon_filters`` + ``find_bursts`` +
  ``drop_short_bursts`` + ``generate_burst_dataframe`` vs ``fused_pipeline.search_and_summarize``):
  the same bursts and every column of the table bit for bit;
* the strict background selection (``strict_background_mask`` vs
  ``fused_pipeline.strict_background``), with and without tightening, and the ``bg`` patterns of
  ``extract_mle_irf_background`` vs ``fused_pipeline.background_patterns``.

The equivalence on DNA13bp_3 (search, strict background, every fit) is
``build_tools/dev_utils/fused_pipeline_equivalence.py``, run on home; its numbers are in
``okf/architecture/fused-burst-pipeline.md``.
"""

from __future__ import annotations

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.burst import fused_pipeline  # noqa: E402

pytestmark = pytest.mark.skipif(not fused_pipeline.available(), reason="tttrlib without BurstPipeline")

MACRO_RES = 40e-9
MICRO_RES = 80e-12
DETECTORS = {
    "G|G": {"chs": [3, 0], "micro_time_ranges": [[0, 250]]},
    "R|G": {"chs": [2, 1], "micro_time_ranges": [[0, 250]]},
    "R|R": {"chs": [2, 1], "micro_time_ranges": [[250, 500]]},
}
WINDOWS = {"prompt": (10, 250), "delayed": (250, 500)}


def _stream(seed=3, n_bursts=250):
    rng = np.random.default_rng(seed)
    macro, micro, rout = [], [], []
    t = 0.0
    for b in range(n_bursts + 1):
        n_bg = int(rng.poisson(30))
        ts = t + np.cumsum(rng.exponential(7500.0, n_bg))
        macro.append(ts)
        rout.append(rng.integers(0, 4, n_bg))
        micro.append(rng.integers(0, 500, n_bg))
        t = ts[-1] if n_bg else t + 2e5
        if b == n_bursts:
            break
        n = int(rng.integers(30, 260))
        ts = t + np.cumsum(rng.exponential(55.0, n))
        ch = rng.integers(0, 4, n)
        delay = np.where(np.isin(ch, [1, 2]) & (rng.random(n) < 0.3), 250, 12)
        macro.append(ts)
        rout.append(ch)
        micro.append(np.minimum(499, delay + rng.exponential(45.0, n)).astype(int))
        t = ts[-1]
    tttr = tttrlib.TTTR()
    rc = np.concatenate(rout).astype(np.int8)
    tttr.append_events(np.concatenate(macro).astype(np.uint64), np.concatenate(micro).astype(np.uint16),
                       rc, np.zeros_like(rc), False, 0)
    tttr.header.set_macro_time_resolution(MACRO_RES)
    tttr.header.set_micro_time_resolution(MICRO_RES)
    tttr.header.set_number_of_micro_time_channels(500)
    return tttr


def _settings(algorithm="cusum_sprt"):
    from chisurf.plugins.burst.burst_selection.api.models import (
        AnalysisSettings,
        BurstDetectionSettings,
        BurstFilterMode,
        DeltaMacroTimeFilterSettings,
        PhotonFilterSettings,
        TttrlibSearchSettings,
    )

    params = ({"min_photons": 5, "background_cps": 3300.0, "signal_to_background_ratio": 3.3,
               "alpha": 0.05, "beta": 0.05, "_detectors": DETECTORS}
              if algorithm == "cusum_sprt" else {"L": 10, "m": 8, "T": 2e-5})
    return AnalysisSettings(
        photon_filter=PhotonFilterSettings(
            filter_active=True, used_filter=BurstFilterMode.TTTRLIB,
            tttrlib_search=TttrlibSearchSettings(algorithm=algorithm, parameters=params),
            delta_macro_time_filter=DeltaMacroTimeFilterSettings(
                dT_min=0.001, dT_max=0.15, dT_min_active=False, dT_max_active=True),
            max_gap=3, use_gap_fill=True,
        ),
        burst_detection=BurstDetectionSettings(min_photons=30),
    )


@pytest.mark.parametrize("algorithm", ["cusum_sprt", "sliding_window"])
def test_search_and_table_equal_the_python_path(algorithm):
    from chisurf.core.datastore import column_names
    from chisurf.core.fio.fluorescence.burst import generate_burst_dataframe
    from chisurf.plugins.burst.burst_selection.api.selection import (
        apply_photon_filters,
        drop_short_bursts,
        find_bursts,
    )

    tttr = _stream()
    settings = _settings(algorithm)
    selected = apply_photon_filters(tttr, settings.photon_filter, burst_detection=settings.burst_detection)
    ref = drop_short_bursts(find_bursts(selected, max_gap=3), 30)
    table = generate_burst_dataframe(ref, "sim.ptu", tttr, WINDOWS, DETECTORS)

    fused = fused_pipeline.search_and_summarize(tttr, settings, {"detectors": DETECTORS, "windows": WINDOWS},
                                                "sim.ptu")
    assert fused is not None
    start_stop, got, result = fused
    assert len(ref) > 100
    np.testing.assert_array_equal(np.asarray(start_stop), np.asarray(ref, dtype=np.int64).reshape(-1, 2))
    assert int(result.stats()["selected_photons"]) == int(np.count_nonzero(selected))
    assert column_names(got) == column_names(table)
    for name in column_names(table):
        a, b = np.asarray(table[name]), np.asarray(got[name])
        if a.dtype == object:
            assert list(a) == list(b), name
        else:
            assert a.dtype == b.dtype, name
            np.testing.assert_array_equal(a, b, err_msg=name)


def _bursts(tttr):
    settings = _settings()
    result = fused_pipeline.search(tttr, settings, DETECTORS, WINDOWS)
    return result.column_view("first_photon"), result.column_view("last_photon")


@pytest.mark.parametrize("rejections", [0, 2])
def test_strict_background_equals_strict_background_mask(rejections):
    from chisurf.core.fluorescence.burst import extract_mle_irf_background
    from chisurf.core.fluorescence.burst.irf_bg import strict_background_mask

    tttr = _stream(seed=8)
    first, last = _bursts(tttr)
    in_burst = np.zeros(len(tttr), dtype=bool)
    for a, b in zip(first, last):
        in_burst[a:b + 1] = True
    chs = [0, 1, 2, 3]
    calls = {"mask": 0, "hist": 0}

    def accept_mask(mask):
        calls["mask"] += 1
        return calls["mask"] > rejections

    def accept_hist(hist):
        calls["hist"] += 1
        return calls["hist"] > rejections

    ref = strict_background_mask(tttr, in_burst, channels=chs, accept=accept_mask if rejections else None,
                                 min_seconds=0.0)
    got = fused_pipeline.strict_background(tttr, first, last, chs, accept_hist=accept_hist if rejections else None,
                                           min_seconds=0.0)
    assert calls["mask"] == calls["hist"]
    assert got.photons == ref.photons
    assert got.iterations == ref.iterations
    for field in ("seconds", "total_seconds", "rate_khz", "threshold_khz", "rate_scale"):
        assert getattr(got, field) == pytest.approx(getattr(ref, field), rel=1e-7), field
    routing = np.asarray(tttr.routing_channels)
    micro = np.asarray(tttr.micro_times)
    for c in chs:
        expect = np.bincount(micro[ref.mask & (routing == c)], minlength=got.histograms[c].size)
        np.testing.assert_array_equal(got.histograms[c], expect[: got.histograms[c].size])
    for binning in (1, 2):
        patterns = extract_mle_irf_background(tttr, DETECTORS, micro_time_binning=binning, mask=ref.mask,
                                              irf_model="experimental")
        mine = fused_pipeline.background_patterns(tttr, got.histograms, DETECTORS, binning)
        for det in DETECTORS:
            np.testing.assert_array_equal(mine[det], np.asarray(patterns[det]["bg"]), err_msg=f"{det} b={binning}")


def test_outside_patterns_equal_the_mask_path():
    from chisurf.core.fluorescence.burst import extract_mle_irf_background

    tttr = _stream(seed=4)
    first, last = _bursts(tttr)
    inside = np.zeros(len(tttr), dtype=bool)
    for a, b in zip(first, last):
        inside[a:b + 1] = True
    hist = fused_pipeline.outside_histograms(tttr, first, last, [0, 1, 2, 3])
    for model in ("experimental", "gaussian"):
        ref = extract_mle_irf_background(tttr, DETECTORS, micro_time_binning=2, mask=~inside, irf_model=model)
        got = extract_mle_irf_background(tttr, DETECTORS, micro_time_binning=2, histograms=hist, irf_model=model)
        for det in DETECTORS:
            for key in ("bg", "irf"):
                np.testing.assert_array_equal(got[det][key], ref[det][key], err_msg=f"{det} {key} {model}")


def test_unfused_configurations_fall_back():
    from chisurf.plugins.burst.burst_selection.api.models import BurstFilterMode

    tttr = _stream(n_bursts=5)
    settings = _settings()
    settings.photon_filter.tttrlib_search.algorithm = "maxtree"
    assert fused_pipeline.search_config(tttr, settings, DETECTORS, WINDOWS) is None
    settings = _settings()
    settings.photon_filter.used_filter = BurstFilterMode.COUNT_RATE
    assert fused_pipeline.search_config(tttr, settings, DETECTORS, WINDOWS) is None
    settings = _settings()
    settings.photon_filter.channels = [0]
    assert fused_pipeline.search_config(tttr, settings, DETECTORS, WINDOWS) is None
