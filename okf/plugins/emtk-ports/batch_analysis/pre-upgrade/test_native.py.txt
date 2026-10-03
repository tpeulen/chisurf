from __future__ import annotations

from emtk.testing import RecordingPainter

from ..gui.app import BatchAnalysisApp
from ..gui.view_model import BatchViewModel


def test_native_batch_selection_and_state_roundtrip():
    app = BatchAnalysisApp(BatchViewModel())
    app.model.files = ["example.dat"]
    app.model.selected_fit_name = "template"
    state = app.export_settings()
    other = BatchAnalysisApp(BatchViewModel())
    other.restore_settings(state)
    assert other.model.files == []
    assert other.model.selected_fit_name == "template"


def test_native_batch_renders_tooltips():
    app = BatchAnalysisApp(BatchViewModel())
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 980, 700)
    assert "Batch Analysis" in painter.strings
    assert "Selection" in painter.strings and "Results" in painter.strings


def test_native_batch_selection_summary_shows_no_markup():
    """The selection summary is HTML from the view model; it must be rendered, not printed."""
    app = BatchAnalysisApp(BatchViewModel())
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 980, 700)
    drawn = " ".join(painter.strings)
    assert "<" not in drawn and "</" not in drawn
    assert "Ready to run" in drawn and "Loaded datasets" in drawn
