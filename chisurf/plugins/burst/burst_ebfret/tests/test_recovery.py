"""Recovery test against ebFRET's own simulated-K04-N350 reference dataset.

This is the cross-tool validation of the port: fit the vendored ebFRET fixture
and assert that the two well-separated interior FRET states match ebFRET's own
fitted means. Marked ``slow`` because it fits a subset of the real dataset.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from chisurf.plugins.burst.burst_ebfret.core.analysis import analyse
from chisurf.plugins.burst.burst_ebfret.core.ebayes import ebayes
from chisurf.plugins.burst.burst_ebfret.io import load_stacked_dat

DATA_DIR = pathlib.Path(__file__).parent / "data" / "simulated-K04-N350"


def _load_reference():
    with open(DATA_DIR / "reference.json") as handle:
        return json.load(handle)


def test_fixture_loads():
    """The vendored stacked .dat parses into the expected number of traces."""
    traces = load_stacked_dat(str(DATA_DIR / "raw-stacked.dat"))
    ref = _load_reference()
    assert len(traces) == ref["n_traces"]
    assert sum(t.size for t in traces) == ref["n_frames"]
    # The ebFRET simulated counts are background-subtracted and may go slightly
    # negative, so FRET can fall just outside [0, 1]; the bulk must be sane.
    pooled = np.concatenate(traces)
    assert np.mean((pooled >= -0.3) & (pooled <= 1.3)) > 0.99


@pytest.mark.slow
def test_k4_recovers_ebfret_interior_states():
    """K=4 empirical Bayes recovers ebFRET's two well-separated interior states."""
    traces = load_stacked_dat(str(DATA_DIR / "raw-stacked.dat"))[:80]
    fit = ebayes(traces, 4, max_iter=15, threshold=1e-4)
    means = fit.state_means
    assert means.size == 4
    assert np.all(np.diff(means) > 0)

    ref_k4 = _load_reference()["ebfret_session_means"]["K4"]
    # The two interior states (~0.33 and ~0.516) are the stable cross-tool
    # target; the donor-only and high-FRET extremes differ because this port
    # fits the uncorrected proximity ratio.
    assert abs(means[1] - ref_k4[1]) < 0.05
    assert abs(means[2] - ref_k4[2]) < 0.05


@pytest.mark.slow
def test_k2_matches_ebfret():
    """K=2 empirical Bayes matches ebFRET's coarse two-state means."""
    traces = load_stacked_dat(str(DATA_DIR / "raw-stacked.dat"))[:80]
    fit = ebayes(traces, 2, max_iter=15, threshold=1e-4)
    means = fit.state_means
    ref_k2 = _load_reference()["ebfret_session_means"]["K2"]
    assert abs(means[0] - ref_k2[0]) < 0.06
    assert abs(means[1] - ref_k2[1]) < 0.06


@pytest.mark.slow
def test_analyse_selects_and_decodes():
    """The high-level analyse() scan returns a decoded, self-consistent model."""
    traces = load_stacked_dat(str(DATA_DIR / "raw-stacked.dat"))[:60]
    analysis = analyse(traces, min_states=2, max_states=3, max_iter=12)
    assert analysis.n_states in (2, 3)
    assert len(analysis.states) == analysis.n_states
    assert analysis.transition_counts.shape == (analysis.n_states, analysis.n_states)
    assert sum(s.occupancy for s in analysis.states) == pytest.approx(1.0, abs=1e-6)
    assert len(analysis.dwells) > 0
