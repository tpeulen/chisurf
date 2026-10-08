"""Real viewer/tool factories honor primary declarations and saved geometry."""

import copy
import importlib
import json
from pathlib import Path

import pytest
from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state

CASES = [
    (
        "project_browser",
        "chisurf.plugins.core.project_browser.gui.app",
        "project_browser_emtk.view.json",
        (1200, 800),
    ),
    (
        "burst_selection",
        "chisurf.plugins.burst.burst_selection.gui.native",
        "native.view.json",
        (1100, 720),
    ),
]


def construct(module):
    """Construct the real app without database auto-load or session preference import."""
    if module.__name__.endswith("project_browser.gui.app"):
        from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

        return module.ProjectBrowserApp(ProjectBrowserModel(client=object()), autoload=False)
    return module.create_app(restore=False)


@pytest.mark.parametrize("plugin_id,module_name,spec_name,expected", CASES)
def test_declared_factory_size_and_saved_resize_win(
    plugin_id, module_name, spec_name, expected, tmp_path, monkeypatch
):
    """A saved host resize wins on reopen and drawing cannot reset it."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))
    module = importlib.import_module(module_name)
    path = Path(module.__file__).with_name(spec_name)
    before = path.read_bytes()
    spec = json.loads(before)
    assert spec["window"] == dict(zip(("width", "height"), expected))
    first = construct(module)
    try:
        assert first.window_size == expected
        attach_native_state(plugin_id, first)
        first.window_resized(1370, 910)
        Driver(first, size=(1370, 910)).draw()
        assert first.window_size == (1370, 910)
    finally:
        first.close()
    reopened = attach_native_state(plugin_id, construct(module))
    try:
        assert reopened.window_size == (1370, 910)
        state = copy.deepcopy(reopened.export_settings())
        reopened.draw(RecordingPainter(), 0, 0, 900, 650)
        assert reopened.window_size == (1370, 910)
        assert reopened.export_settings() == state
        assert path.read_bytes() == before
    finally:
        reopened.close()


@pytest.mark.parametrize("plugin_id,module_name,spec_name,expected", CASES)
def test_native_docks_and_controls_survive_declaration(
    plugin_id, module_name, spec_name, expected, tmp_path, monkeypatch
):
    """Changing the host default retains every dock and reachable primary action."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))
    app = construct(importlib.import_module(module_name))
    try:
        drv = Driver(app, size=expected)
        drv.draw()
        if plugin_id == "project_browser":
            assert all(app.docks.window(key) is not None for key in ("browser", "details"))
            assert {
                "open",
                "save",
                "export",
                "import_project",
                "refresh",
                "help",
                "guide",
            } <= app.item_rects.keys()
        else:
            for key in (
                "files",
                "settings",
                "detectors",
                "summary",
                "trace",
                "dt",
                "decay",
                "duration",
                "histogram",
                "scatter",
                "table",
            ):
                assert app.docks.window(key) is not None
                app.docks.focus(key)
                drv.draw()
            app.docks.focus("files")
            drv.draw()
            assert {
                "toolAction_run",
                "toolAction_restart",
                "add_files",
                "add_folder",
            } <= app.item_rects.keys()
    finally:
        app.close()


def test_selection_narrow_default_reveals_detector_actions(tmp_path, monkeypatch):
    """The existing sideways table scrollbar reveals row actions at the tool default."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))
    module = importlib.import_module("chisurf.plugins.burst.burst_selection.gui.native")
    app = module.create_app(restore=False)
    try:
        app.apply_setup(
            {
                "detectors": {
                    "green": {"chs": [0], "micro_time_ranges": []},
                    "red": {"chs": [1], "micro_time_ranges": []},
                },
                "windows": {},
                "tttr_reading": {"file_type": "SPC-130"},
            }
        )
        app.docks.focus("detectors")
        drv = Driver(app, size=(1100, 720))
        drv.draw()
        control = app.editor._detector_table.control
        x, y, width, height = control._hbar_box
        drv.click((x + width * 0.9, y + height * 0.5))
        assert control.first_column > 0
        assert any(cell[2] == "delete" for cell in app.editor._detector_buttons.cells())
    finally:
        app.close()
