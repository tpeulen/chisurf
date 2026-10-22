"""The HMM tool's example: a seeded two-state trace the fit must resolve."""

import numpy as np

from chisurf.plugins.core.hmm.demo import N_BINS, STATE_MEANS, demo_folder, make_demo
from chisurf.plugins.core.hmm.gui.app import make_app


def test_make_demo_writes_a_two_state_trace():
    """The trace file clusters around the two declared state means."""
    path = make_demo()
    trace = np.load(path)
    assert trace.shape == (N_BINS, 1)
    for mean in STATE_MEANS:
        near = np.abs(trace[:, 0] - mean) < 3 * 0.05
        assert near.sum() > N_BINS / 10


def test_load_example_loads_and_fits():
    """The affordance loads the trace into the tool and fits it."""
    app = make_app()
    model = app.model
    model.load_example()
    traces = model.traces
    assert traces and len(traces[0]) == N_BINS
    assert model.status
    assert demo_folder() / "hmm_demo_trace.npy" == make_demo()
