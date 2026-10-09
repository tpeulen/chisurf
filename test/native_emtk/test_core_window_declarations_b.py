"""Core host declarations preserve actual defaults and saved user geometry."""

import copy
import importlib
import json
from pathlib import Path

import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state

CASES = [
    ("plot_settings", "gui.app", "make_app", "plot_settings_emtk.view.json"),
    ("plugin_check", "gui.app", "make_app", "plugin_check_emtk.view.json"),
    ("plugin_manager", "gui.app", "make_app", "plugins_emtk.view.json"),
    ("setup", "gui.app", "make_app", "app.view.json"),
    ("setup_channel_definition", "gui.app", "make_app", "app.view.json"),
    ("style_manager", "gui.app", "make_style_manager_app", "app.view.json"),
    ("switch_user", "app", "make_app", "switch_user_emtk.view.json"),
    ("tttr_to_pto", "gui.app", "create_app", "tttr_to_pto_emtk.view.json"),
    ("updater", "gui.app", "make_app", "updater.view.json"),
    ("user_editor", "gui.app", "make_app", "users_emtk.view.json"),
]


@pytest.fixture(params=CASES, ids=[case[0] for case in CASES])
def host(request, tmp_path, monkeypatch):
    """Use real factories and private settings, without starting remote workflows."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))
    key, suffix, factory_name, spec_name = request.param
    module = importlib.import_module(f"chisurf.plugins.core.{key}.{suffix}")

    def create():
        """Keep production construction and disable only first-frame service work."""
        app = getattr(module, factory_name)()
        if key == "updater":
            app.auto_check = False
        if key in {"user_editor", "setup_channel_definition"}:
            app.autoload = False
        return app

    return key, create, Path(module.__file__).with_name(spec_name)


def close(app):
    """Close production apps that expose a lifecycle hook."""
    callback = getattr(app, "close", None)
    if callable(callback):
        callback()


def test_declared_default_preserves_real_controls_and_preferences(host):
    """The existing 1200×800 host still paints its real UI and round-trips preferences."""
    _, create, path = host
    assert json.loads(path.read_text())["window"] == {"width": 1200, "height": 800}
    app = create()
    try:
        assert app.window_size == (1200, 800)
        painter = Driver(app, size=app.window_size).draw(2)
        assert painter.strings
        state = copy.deepcopy(app.export_settings())
        app.restore_settings(state)
        assert app.export_settings() == state
        assert app.window_size == (1200, 800)
    finally:
        close(app)


def test_authored_size_reaches_the_real_constructor(host, monkeypatch):
    """The normal specification loader supplies host size without modifying authored bytes."""
    _, create, path = host
    original = path.read_bytes()
    spec = json.loads(original)
    spec["window"] = {"width": 1040, "height": 740}
    read_text = Path.read_text

    def read(source, *args, **kwargs):
        """Supply changed metadata through the same production read boundary."""
        return json.dumps(spec) if source == path else read_text(source, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    app = create()
    try:
        assert app.window_size == (1040, 740)
        Driver(app, size=app.window_size).draw(2)
        assert app.window_size == (1040, 740)
        assert path.read_bytes() == original
    finally:
        close(app)


def test_fresh_native_state_then_saved_resize_wins(host):
    """Fresh attachment works, and later saved geometry overrides the declared default."""
    key, create, _ = host
    app = attach_native_state(key, create())
    assert app.window_size == (1200, 800)
    app.window_resized(1380, 920)
    app.close()
    reopened = attach_native_state(key, create())
    try:
        assert reopened.window_size == (1380, 920)
        Driver(reopened, size=reopened.window_size).draw(2)
        assert reopened.window_size == (1380, 920)
    finally:
        reopened.close()
