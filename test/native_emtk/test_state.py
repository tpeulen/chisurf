from emtk.app import ImApp
from emtk.docking import DockManager, Region

from chisurf.emtk.state import attach_native_state, bind_layout, load_settings, save_settings


def test_native_layout_and_window_size_restore_without_qt(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    docks = DockManager(Region("main"))
    docks.add_window("controls", "Controls", dock="main")
    bind_layout("example", docks)
    docks.hide("controls")
    docks.flush()
    second = DockManager(Region("main"))
    second.add_window("controls", "Controls", dock="main")
    bind_layout("example", second)
    assert not second.window("controls").visible

    app = attach_native_state("window_example", ImApp(lambda: None))
    app.window_resized(900, 650)
    app.close()
    app.close()
    reopened = attach_native_state("window_example", ImApp(lambda: None))
    assert reopened.window_size == (900, 650)
    reopened.close()


def test_native_declared_preferences_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    assert save_settings("example", {"bin_width": 0.032, "mode": "vm"})
    assert load_settings("example") == {"bin_width": 0.032, "mode": "vm"}


def test_native_state_calls_explicit_model_preference_hooks(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    save_settings("preferences", {"zoom": 1.5})
    app = ImApp(lambda: None)
    restored = []
    closed = []
    app.restore_settings = lambda values: restored.append(values)
    app.export_settings = lambda: {"zoom": 2.0}
    app.close = lambda: closed.append(True)
    attach_native_state("preferences", app)
    assert restored == [{"zoom": 1.5}]
    app.close()
    app.close()
    assert closed == [True]
    assert load_settings("preferences") == {"zoom": 2.0}
