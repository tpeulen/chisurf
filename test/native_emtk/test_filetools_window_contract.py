"""FileTools declares host geometry without changing its native child routes or state."""

import copy
import json
from pathlib import Path

from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep window, detector and native tool state in scratch storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))


def test_real_factory_reads_host_only_declaration(tmp_path, monkeypatch):
    """The actual manual hub reads composite geometry while its panel routes remain intact."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.filetools.gui.app import SPEC, make_app

    path = Path(__import__(make_app.__module__, fromlist=["__file__"]).__file__).with_name(
        "window.view.json"
    )
    original = path.read_bytes()
    app = make_app()
    try:
        assert json.loads(original) == {"window": {"width": 1100, "height": 720}, "sections": []}
        assert app.window_size == (1100, 720)
        assert app.panels == SPEC["panels"]
        Driver(app, size=(1100, 720)).draw(3)
        assert path.read_bytes() == original
    finally:
        app.close()


def test_saved_resize_and_real_child_preferences_survive_reopen(tmp_path, monkeypatch):
    """Saved host dimensions and native splitter/time-window configuration stay authoritative."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.filetools.gui.app import make_app

    first = attach_native_state("filetools", make_app())
    split = first.select("split_convert")
    split.tool._model.photons_per_file_k = 123
    split.tool._model.reset_macro_times = False
    time = first.select("tttr_time_windows")
    time.tool.time_window_ms = 37.5
    time.tool.output_dir_text = str(tmp_path / "windows")
    first.filter = ""
    first.window_resized(1340, 900)
    state = copy.deepcopy(first.export_settings())
    first.close()
    reopened = attach_native_state("filetools", make_app())
    try:
        assert reopened.window_size == (1340, 900)
        assert reopened.export_settings() == state
        assert reopened.selected == "tttr_time_windows"
        assert reopened.select("split_convert").tool._model.photons_per_file_k == 123
        assert reopened.select("tttr_time_windows").tool.time_window_ms == 37.5
        before = copy.deepcopy(reopened.export_settings())
        reopened.draw(RecordingPainter(), 0, 0, 900, 650)
        assert reopened.window_size == (1340, 900)
        assert reopened.export_settings() == before
    finally:
        reopened.close()


def test_all_actual_children_keep_identity_and_follow_responsive_viewport(tmp_path, monkeypatch):
    """Navigation preserves each real child while the hosted viewport follows the canvas."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.filetools.gui.app import make_app

    app = make_app()
    try:
        drv = Driver(app, size=(1100, 720))
        drv.draw(3)
        for panel in app.panels:
            drv.click("nav_" + panel["role"])
            drv.draw(3)
            child = app.child
            assert child is not None and panel["role"] not in app.errors
            assert app.select(panel["role"]) is child
        assert len(app.children) == 7
        large_box = app.child_box
        app.draw(RecordingPainter(), 0, 0, 900, 650)
        assert app.child_box[2] < large_box[2]
        assert app.child_box[3] < large_box[3]
        assert app.native_layouts
        assert len(app.children) == 7
    finally:
        app.close()
