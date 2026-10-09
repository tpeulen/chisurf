from __future__ import annotations

import numpy as np
from emtk.testing import RecordingPainter

from ..gui.app import HmmApp
from ..gui.view_model import HmmViewModel


def test_native_hmm_model_renders_trace_and_fit_controls():
    model = HmmViewModel()
    model.set_traces(
        [np.column_stack((np.sin(np.linspace(0, 8, 120)), np.cos(np.linspace(0, 8, 120))))]
    )
    app = HmmApp(model)
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 980, 760)
    # the window titles of the docked layout (the one-column page of the first stream is gone)
    assert (
        "Model" in painter.strings
        and "Trace" in painter.strings
        and "Fitted states" in painter.strings
    )
    assert "Fit" in painter.strings and "Scan states" in painter.strings


def test_native_hmm_settings_roundtrip():
    app = HmmApp()
    app.model.n_states = 4
    app.model.n_iter = 17
    state = app.export_settings()
    other = HmmApp()
    other.restore_settings(state)
    assert other.model.n_states == 4
    assert other.model.n_iter == 17
