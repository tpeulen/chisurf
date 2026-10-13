"""PTO Inspector geometry comes from its authored primary specification."""

import copy
import json
from pathlib import Path

from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep viewer preferences and metadata within scratch storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))


def test_real_factory_consumes_primary_window_declaration(tmp_path, monkeypatch):
    """Changing the authored declaration changes actual factory geometry, without writing it."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.core.pto_inspector.gui import app as module

    path = Path(module.__file__).with_name("pto.view.json")
    original = path.read_bytes()
    spec = json.loads(original)
    assert spec["window"] == {"width": 1200, "height": 800}
    spec["window"] = {"width": 960, "height": 640}
    read_text = Path.read_text

    def read(source, *args, **kwargs):
        """Supply a different declared size through the same primary read contract."""
        return json.dumps(spec) if source == path else read_text(source, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    app = module.make_app()
    try:
        assert app.window_size == (960, 640)
        assert module.PtoInspectorApp.window_size == (1200, 800)
        assert path.read_bytes() == original
    finally:
        app.close()


def test_saved_resize_and_viewer_preferences_win_on_reopen(tmp_path, monkeypatch):
    """Saved geometry and graph/filter preferences survive construction and rendering."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.core.pto_inspector.gui.app import make_app

    first = attach_native_state("pto_inspector", make_app())
    first.graph.editor.canvas.zoom = 1.7
    first.artifacts.control.filter.set_text("burst")
    first.window_resized(1340, 900)
    state = copy.deepcopy(first.export_settings())
    first.close()
    reopened = attach_native_state("pto_inspector", make_app())
    try:
        assert reopened.window_size == (1340, 900)
        assert reopened.export_settings() == state
        reopened.draw(RecordingPainter(), 0, 0, 900, 650)
        assert reopened.window_size == (1340, 900)
        assert reopened.export_settings() == state
    finally:
        reopened.close()


def test_viewer_default_retains_all_payload_and_provenance_docks(tmp_path, monkeypatch):
    """The authored default retains every existing viewer panel and primary action."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.core.pto_inspector.gui.app import make_app

    app = make_app()
    try:
        assert app.window_size == (1200, 800)
        drv = Driver(app, size=(1200, 800))
        drv.draw(3)
        for key in (
            "container",
            "provenance",
            "data",
            "curve",
            "details",
            "lineage",
            "parameters",
            "text",
        ):
            assert app.docks.window(key) is not None
            app.docks.focus(key)
            drv.draw(2)
        assert {"open", "Verify", "export", "Fit graph"} <= app.item_rects.keys()
    finally:
        app.close()
