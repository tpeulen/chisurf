from __future__ import annotations

from emtk.testing import RecordingPainter

from ..gui.app import WizardHubApp


def test_native_wizard_hub_lists_registry_and_preserves_selection():
    app = WizardHubApp()
    assert app.entries
    selected = app.selected
    app.selected = app.entries[-1].id
    state = app.export_settings()
    other = WizardHubApp()
    other.restore_settings(state)
    assert other.selected == app.entries[-1].id
    assert selected != ""


def test_native_wizard_hub_renders_tooltips():
    app = WizardHubApp()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 980, 640)
    assert (
        "Anisotropy" in painter.strings and "Batch analysis" in painter.strings
    )  # the list header is the window title now
