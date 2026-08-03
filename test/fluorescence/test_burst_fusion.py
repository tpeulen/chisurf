"""Core burst-fusion tests: the P_same window, the grouping, the table merge.

These exercise :mod:`chisurf.core.fluorescence.burst.fusion` on synthetic burst
streams whose answer is known by construction, so a regression shows up as a
wrong *number* rather than as a plot that looks different.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from chisurf.core.fluorescence.burst.fusion import (
    fuse_burst_frame,
    fusion_statistics,
    fusion_window,
    group_labels,
    group_slices,
    same_molecule_curve,
)
from chisurf.core.fluorescence.burst.recurrence import (
    pair_statistics,
    same_molecule_probability,
)


def _poisson_stream(rate_hz: float, duration_s: float, seed: int = 0) -> np.ndarray:
    """Uncorrelated burst arrival times — no molecule ever recurs."""
    rng = np.random.default_rng(seed)
    n = rng.poisson(rate_hz * duration_s)
    return np.sort(rng.uniform(0.0, duration_s, size=n))


def _recurring_stream(
    n_molecules: int, duration_s: float, recur: int = 3, spacing_s: float = 2e-3,
    seed: int = 0,
) -> np.ndarray:
    """Each molecule leaves ``recur`` bursts a fixed short time apart."""
    rng = np.random.default_rng(seed)
    starts = np.sort(rng.uniform(0.0, duration_s, size=n_molecules))
    times = [start + i * spacing_s for start in starts for i in range(recur)]
    return np.sort(np.asarray(times))


def test_pair_statistics_reproduces_the_original_estimator():
    """The extracted counter must not have changed ``P_same``'s numbers."""
    times = _recurring_stream(200, 10.0, seed=3)
    edges = np.logspace(-4, 0, 41)
    counts, expected = pair_statistics(times, edges)

    tau, p_same, g = same_molecule_probability(times, 1e-4, 1.0, 40)
    with np.errstate(divide="ignore", invalid="ignore"):
        direct = np.where(expected > 0, counts / np.where(expected > 0, expected, 1.0), np.nan)
    np.testing.assert_allclose(g, direct, equal_nan=True)
    np.testing.assert_allclose(tau, np.sqrt(edges[:-1] * edges[1:]))


def test_uncorrelated_bursts_are_never_the_same_molecule():
    """A Poisson stream has ``G = 1``, so nothing may fuse."""
    times = _poisson_stream(300.0, 60.0, seed=1)
    window = fusion_window([times], threshold=0.5, tau_min_s=1e-3, tau_max_s=0.1)

    determined = np.isfinite(window.p_same)
    assert determined.any()
    assert np.nanmedian(window.p_same[determined]) < 0.25
    assert window.tau_max_s == 0.0
    labels = group_labels(times, window.tau_max_s)
    assert labels.max() + 1 == times.size  # every burst its own group


def test_recurring_bursts_fuse_back_into_their_molecules():
    """Three bursts per molecule, 2 ms apart, must come back as one burst."""
    times = _recurring_stream(300, 30.0, recur=3, spacing_s=2e-3, seed=2)
    window = fusion_window([times], threshold=0.5, tau_min_s=1e-4, tau_max_s=1.0)

    assert window.tau_max_s > 2e-3, "the recurrence window must reach the 2 ms spacing"
    labels = group_labels(times, window.tau_max_s)
    sizes = np.bincount(labels)
    # 900 bursts -> ~300 molecules; the estimate is statistical, so allow slack.
    assert 250 <= sizes.size <= 350
    assert sizes.mean() == pytest.approx(3.0, rel=0.25)


def test_pooling_measurements_beats_one_short_file():
    """Counts add, so ten short files resolve a curve none of them resolves."""
    files = [_recurring_stream(12, 1.0, recur=3, spacing_s=2e-3, seed=s) for s in range(10)]
    pooled = same_molecule_curve(files, 1e-4, 2.0, 40, min_pairs=3)[3]
    single = same_molecule_curve([files[0]], 1e-4, 2.0, 40, min_pairs=3)[3]
    assert pooled.sum() > single.sum()
    # Lags are only ever taken inside a measurement, so a lag longer than the
    # files themselves can hold no pairs however many files are pooled.
    assert pooled[-1] == 0.0


def test_min_pairs_marks_thin_bins_undetermined_rather_than_zero():
    """An empty bin is missing evidence, not evidence of a different molecule."""
    times = _recurring_stream(40, 5.0, recur=2, spacing_s=5e-3, seed=4)
    _, lenient, _, counts, _ = same_molecule_curve(times, 1e-4, 1.0, 60, min_pairs=0)
    _, strict, _, _, _ = same_molecule_curve(times, 1e-4, 1.0, 60, min_pairs=5)

    thin = counts < 5
    assert thin.any()
    assert np.isnan(strict[thin]).all()
    # Where there is evidence, the two agree.
    assert np.allclose(strict[~thin], lenient[~thin], equal_nan=True)


def test_window_is_zero_when_no_lag_reaches_the_threshold():
    tau = np.logspace(-4, 0, 20)
    p_same = np.full(20, 0.1)
    from chisurf.core.fluorescence.burst.fusion import _window_from_curve

    assert _window_from_curve(tau, p_same, 0.5) == (0.0, True)


def test_window_is_unresolved_when_the_curve_never_crosses():
    tau = np.logspace(-4, 0, 20)
    p_same = np.full(20, 0.9)
    from chisurf.core.fluorescence.burst.fusion import _window_from_curve

    window, resolved = _window_from_curve(tau, p_same, 0.5)
    assert window == pytest.approx(tau[-1])
    assert resolved is False


def test_window_interpolates_the_crossing_logarithmically():
    """The lag axis is logarithmic; a linear interpolation lands short."""
    tau = np.array([1e-3, 1e-2, 1e-1])
    p_same = np.array([0.9, 0.6, 0.4])
    from chisurf.core.fluorescence.burst.fusion import _window_from_curve

    window, resolved = _window_from_curve(tau, p_same, 0.5)
    assert resolved is True
    # Halfway (in p) between 1e-2 and 1e-1 -> 10^(-2 + 0.5) ~ 3.16e-2.
    assert window == pytest.approx(10 ** (-2 + 0.5), rel=1e-6)
    assert window < 5.5e-2, "a linear interpolation would land here instead"


def test_grouping_is_transitive_but_capped():
    """A chain merges end to end; ``max_group`` is what stops it."""
    times = np.array([0.0, 0.001, 0.002, 0.003, 0.004])
    assert group_labels(times, 2e-3).tolist() == [0, 0, 0, 0, 0]
    assert group_labels(times, 2e-3, max_group=2).tolist() == [0, 0, 1, 1, 2]
    # A gap wider than the window always splits.
    times = np.array([0.0, 0.001, 0.010, 0.011])
    assert group_labels(times, 2e-3).tolist() == [0, 0, 1, 1]


def test_group_slices_are_contiguous_runs():
    labels = np.array([0, 0, 1, 2, 2, 2])
    assert [s.tolist() for s in group_slices(labels)] == [[0, 1], [2], [3, 4, 5]]


def _burst_frame() -> pd.DataFrame:
    """Two fragments of one passage plus a lone burst, in .bur column names."""
    return pd.DataFrame(
        {
            "First Photon": [100, 200, 900],
            "Last Photon": [149, 249, 999],
            "Duration (ms)": [1.0, 1.0, 2.0],
            "Mean Macro Time (ms)": [10.5, 13.5, 100.0],
            "Number of Photons": [50, 50, 100],
            "Count Rate (KHz)": [50.0, 50.0, 50.0],
            "Confidence (sigma)": [3.0, 5.0, 8.0],
            "First File": ["m000.spc"] * 3,
            "Last File": ["m000.spc"] * 3,
            "First Photon (green)": [100, 200, 900],
            "Last Photon (green)": [148, 248, 998],
            "Duration (green) (ms)": [1.0, 1.0, 2.0],
            "Mean Macrotime (green) (ms)": [10.5, 13.5, 100.0],
            "Number of Photons (green)": [30, 10, 60],
            "Green Count Rate (KHz)": [30.0, 10.0, 30.0],
            "First Photon (red)": [101, -1, 901],
            "Last Photon (red)": [149, -1, 999],
            "Duration (red) (ms)": [1.0, -1.0, 2.0],
            "Mean Macrotime (red) (ms)": [10.5, -1.0, 100.0],
            "Number of Photons (red)": [20, 0, 40],
            "Red Count Rate (KHz)": [20.0, -1.0, 20.0],
            "Mean Microtime (green) (ns)": [2.0, 4.0, 3.0],
            "Mean Microtime (red) (ns)": [1.0, 0.0, 1.5],
        }
    )


def test_fuse_burst_frame_merges_indices_span_and_counts():
    frame = _burst_frame()
    labels = np.array([0, 0, 1])
    fused = fuse_burst_frame(frame, labels)

    assert len(fused) == 2
    first = fused.iloc[0]
    assert first["First Photon"] == 100
    assert first["Last Photon"] == 249
    assert first["Number of Photons"] == 100  # signal photons of both fragments
    # Span: from the start of the first fragment (10.0 ms) to the end of the
    # second (14.0 ms) — including the 2 ms gap the search cut.
    assert first["Duration (ms)"] == pytest.approx(4.0)
    assert first["Mean Macro Time (ms)"] == pytest.approx(12.0)
    assert first["Fusion Size"] == 2
    assert first["Fusion Gap (ms)"] == pytest.approx(2.0)
    # The untouched burst keeps its own numbers.
    assert fused.iloc[1]["Number of Photons"] == 100
    assert fused.iloc[1]["Fusion Size"] == 1
    assert fused.iloc[1]["Fusion Gap (ms)"] == pytest.approx(0.0)


def test_fuse_burst_frame_handles_a_detector_that_saw_nothing():
    """``-1`` means "this detector saw no photon", not "photon minus one"."""
    frame = _burst_frame()
    fused = fuse_burst_frame(frame, np.array([0, 0, 1]))
    first = fused.iloc[0]

    # Red saw photons in the first fragment only: the sentinel row must not drag
    # the fused first/last photon to -1, nor the counts.
    assert first["First Photon (red)"] == 101
    assert first["Last Photon (red)"] == 149
    assert first["Number of Photons (red)"] == 20
    assert first["Number of Photons (green)"] == 40


def test_fused_mean_micro_time_is_photon_weighted():
    """30 photons at 2 ns and 10 at 4 ns average to 2.5 ns, not 3 ns."""
    frame = _burst_frame()
    fused = fuse_burst_frame(frame, np.array([0, 0, 1]))
    assert fused.iloc[0]["Mean Microtime (green) (ns)"] == pytest.approx(2.5)


def test_fusion_statistics_counts_what_was_fused():
    frame = _burst_frame()
    labels = np.array([0, 0, 1])
    stats = fusion_statistics(frame, fuse_burst_frame(frame, labels), labels)

    assert stats["n_bursts_before"] == 3
    assert stats["n_bursts_after"] == 2
    assert stats["n_fused_groups"] == 1
    assert stats["largest_group"] == 2
    assert stats["fused_fraction"] == pytest.approx(2 / 3)
    assert stats["photons"]["after"]["mean"] > stats["photons"]["before"]["mean"]
