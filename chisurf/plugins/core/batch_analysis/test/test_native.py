"""Smoke tests of the native Batch Analysis app (the stream's three, kept and moved to the wizard's model).

The app now takes the wizard model :class:`~..gui.model.BatchModel` (steps, tables, threaded run) instead of the bare Qt
view model; the intent of each test is unchanged.
"""

from __future__ import annotations

from emtk.testing import RecordingPainter

from chisurf.plugins.emtk_hermetic import hermetic, real_chisurf_untouched  # noqa: F401  (autouse fixtures)

from ..gui.app import BatchAnalysisApp
from ..gui.model import BatchModel
from .fakes import FakeSession


def test_native_batch_selection_and_state_roundtrip():
    app = BatchAnalysisApp(BatchModel(session=FakeSession()))
    app.model.files = ["example.dat"]
    app.model.selected_fit_name = "Template fit"
    state = app.export_settings()
    other = BatchAnalysisApp(BatchModel(session=FakeSession()))
    other.restore_settings(state)
    assert other.model.files == []
    assert other.model.selected_fit_name == "Template fit"


def test_native_batch_renders_the_welcome_step_and_the_step_list():
    app = BatchAnalysisApp(BatchModel(session=FakeSession()))
    painter = RecordingPainter()
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 980, 700)
    for title in ("Welcome", "Loaded data", "Files & fit", "Run", "Results"):
        assert any(title in s for s in painter.strings), title


def test_native_batch_selection_summary_shows_no_markup():
    """The selection summary is Markdown from the model; it must be rendered, not printed."""
    app = BatchAnalysisApp(BatchModel(session=FakeSession()))
    app.model.go_to(3)
    painter = RecordingPainter()
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 980, 700)
    drawn = " ".join(painter.strings)
    assert "<" not in drawn and "####" not in drawn and "**" not in drawn
    assert "Ready to run" in drawn and "Loaded datasets" in drawn
