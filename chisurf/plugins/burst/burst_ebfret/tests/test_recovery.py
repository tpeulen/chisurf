"""Recovery on ebFRET's own simulated-K04-N350 dataset.

The traces are read the way ebFRET's ``load_raw`` reads a stacked ``.dat``
(the first row of each trace is its label) and the signal is ebFRET's
``(acceptor + eps) / (acceptor + donor + eps)``, so the numbers are comparable
with the analysis ebFRET's GUI saved for the same dataset
(``reference.json``).
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from chisurf.plugins.burst.burst_ebfret.core import ebayes, hmm
from chisurf.plugins.burst.burst_ebfret.core.model import Analysis

DATA_DIR = pathlib.Path(__file__).parent / "data" / "simulated-K04-N350"
EPS = np.finfo(float).eps


def _reference():
    return json.loads((DATA_DIR / "reference.json").read_text())


def _signals(limit=None):
    """ebFRET signals of the vendored stacked file, label rows stripped."""
    raw = np.loadtxt(DATA_DIR / "raw-stacked.dat")
    ids = np.unique(raw[:, 0])
    if limit is not None:
        ids = ids[:limit]
    out = []
    for trace_id in ids:
        rows = raw[raw[:, 0] == trace_id, 1:3][1:]
        out.append((rows[:, 1] + EPS) / (rows[:, 1] + rows[:, 0] + EPS))
    return out


def _fit(signals, K, seed=0, restarts=2):
    analysis = Analysis(states=K, prior=hmm.guess_prior(signals, K))
    run = ebayes.run_ebayes(
        analysis, signals, restarts=restarts, precision=1e-3, rng=np.random.default_rng(seed)
    )
    while True:
        try:
            next(run)
        except StopIteration as stop:
            return analysis, stop.value


def test_fixture_loads():
    signals = _signals()
    ref = _reference()
    assert len(signals) == ref["n_traces"]
    # one label row per trace is not a frame
    assert sum(s.size for s in signals) == ref["n_frames"] - ref["n_traces"]


def test_k2_on_a_subset_lands_near_ebfret():
    analysis, history = _fit(_signals(40), 2, restarts=1)
    ref = _reference()["ebfret_session_means"]["K2"]
    np.testing.assert_allclose(np.sort(analysis.prior.mu), ref, atol=0.05)
    assert history[-1] >= history[0]


@pytest.mark.slow
def test_k2_on_the_full_dataset_matches_ebfret():
    """All 350 traces, the GUI's defaults: ebFRET's session gives [0.30, 0.55]."""
    analysis, _ = _fit(_signals(), 2)
    ref = _reference()["ebfret_session_means"]["K2"]
    np.testing.assert_allclose(np.sort(analysis.prior.mu), ref, atol=0.01)
