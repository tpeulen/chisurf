"""Trace Browser factory geometry is declared while saved sizes remain authoritative."""

import copy
import json

from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep setup, native state and metadata in an isolated settings tree."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))


def test_real_factory_declares_viewer_geometry(tmp_path, monkeypatch):
    """The primary specification controls the host size before persistence binds."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.trace_browser.gui.app import HERE, make_app

    app = make_app(on_request=lambda *_: None)
    try:
        path = HERE / "trace_browser_emtk.view.json"
        original = path.read_bytes()
        spec = json.loads(original)
        assert spec["window"] == {"width": 1200, "height": 800}
        assert app.window_size == (1200, 800)
        Driver(app, size=(1200, 800)).draw()
        assert path.read_bytes() == original
    finally:
        app.close()


def test_saved_size_wins_and_render_preserves_preferences(tmp_path, monkeypatch):
    """Reopening uses saved dimensions and a render cannot overwrite configuration."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.trace_browser.gui.app import TraceBrowserApp

    first = attach_native_state("trace_browser", TraceBrowserApp())
    try:
        first.model.window_ms = 17.0
        first.window_resized(1360, 920)
    finally:
        first.close()
    reopened = attach_native_state("trace_browser", TraceBrowserApp())
    try:
        assert reopened.window_size == (1360, 920)
        assert reopened.model.window_ms == 17.0
        before = copy.deepcopy(reopened.export_settings())
        reopened.draw(RecordingPainter(), 0, 0, 900, 650)
        assert reopened.window_size == (1360, 920)
        assert reopened.export_settings() == before
    finally:
        reopened.close()


def test_both_workspaces_retain_real_controls(tmp_path, monkeypatch):
    """Setup, browser table and trace dock controls stay reachable at the viewer default."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.trace_browser.gui.app import TraceBrowserApp

    app = TraceBrowserApp()
    try:
        app.back_to_setup()
        drv = Driver(app, size=(1200, 800))
        drv.draw()
        assert app.setup_docks.window("setup") is not None
        assert "continue" in app.item_rects
        drv.click("continue")
        drv.draw()
        assert app.model.page == "browser"
        assert all(app.browser_docks.window(key) is not None for key in ("files", "plot"))
        assert {"back_to_setup", "choose_folder", "clear", "clear_caches"} <= app.form.rects.keys()
    finally:
        app.close()
