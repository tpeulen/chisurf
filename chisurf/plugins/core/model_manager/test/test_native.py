from __future__ import annotations

from emtk.testing import RecordingPainter

from ..api.records import ModelRow
from ..gui.app import ModelManagerApp
from ..gui.model import ModelManagerModel


def test_native_model_manager_filters_and_persists_selection():
    model = ModelManagerModel(settings_block={"disabled_models": ["Disabled"]})
    model._rows = [
        ModelRow("a", "Active", "exp", "Experiment", "m", "A", ""),
        ModelRow("b", "Disabled", "exp", "Experiment", "m", "B", "", disabled=True),
    ]
    app = ModelManagerApp(model)
    app.model.select_row(0)
    assert app.model.selected.name == "Active"
    app.model.selected_disabled = True
    assert app.model.dirty
    app.model.revert()
    assert app.model.selected_disabled is False


def test_native_model_manager_renders_tooltips():
    model = ModelManagerModel(settings_block={})
    model._rows = [ModelRow("a", "Active", "exp", "Experiment", "m", "A", "documentation")]
    app = ModelManagerApp(model)
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 980, 700)
    assert "Registered models" in painter.strings and "Selected model" in painter.strings
    assert "Active" in painter.strings
