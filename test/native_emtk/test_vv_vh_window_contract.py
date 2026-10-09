"""VV/VH host metadata preserves the anisotropy and existing restoration path."""

import json

import numpy as np
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.vv_vh_anisotropy.gui import app as owner


def _isolate(tmp_path, monkeypatch):
    """Keep actual native state away from user settings."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))


def test_raw_primary_reaches_factory(tmp_path, monkeypatch):
    """The host reads dimensions before translating/adapting controls."""
    _isolate(tmp_path, monkeypatch)
    app = owner.create_app()
    try:
        assert app.window_size == (1100, 720)
        Driver(app, app.window_size).draw(2)
    finally:
        app.close()


def test_authored_dimensions_are_consumed(tmp_path, monkeypatch):
    """A copied specification drives the constructor instead of a fixed size."""
    _isolate(tmp_path, monkeypatch)
    spec = json.loads((owner.HERE / "vv_vh_emtk.view.json").read_text())
    spec["window"] = {"width": 980, "height": 640}
    (tmp_path / "vv_vh_emtk.view.json").write_text(json.dumps(spec))
    for name in ["help.md", "guide.json"]:
        (tmp_path / name).write_bytes((owner.HERE / name).read_bytes())
    monkeypatch.setattr(owner, "HERE", tmp_path)
    app = owner.create_app()
    try:
        assert app.window_size == (980, 640)
    finally:
        app.close()


def test_known_anisotropy_survives_default_narrow_and_native_restore(tmp_path, monkeypatch):
    """Resizing and reload preserve the physical ratio and saved region."""
    _isolate(tmp_path, monkeypatch)
    time = np.arange(120)
    intensity = 1000 * np.exp(-time / 30)
    expected = 0.3 * np.exp(-time / 50)
    file = tmp_path / "known.dat"
    np.savetxt(
        file, np.concatenate([intensity * (1 + 2 * expected), intensity * (1 - expected) / 2])
    )
    app = attach_native_state("vv-vh-host", owner.create_app())
    app.model.g_factor = 2
    assert app.load_file(file)
    np.testing.assert_allclose(app.model.r_t, expected, atol=1e-14)
    settings = app.export_settings()
    for size in [(1100, 720), (736, 552)]:
        Driver(app, size).draw(2)
        np.testing.assert_allclose(app.model.r_t, expected, atol=1e-14)
        assert app.export_settings() == settings
    app.window_resized(1330, 870)
    app.close()
    restored = attach_native_state("vv-vh-host", owner.create_app())
    try:
        assert restored.window_size == (1330, 870)
        np.testing.assert_allclose(restored.model.r_t, expected, atol=1e-14)
    finally:
        restored.close()


def test_picker_callback_queues_paths_without_a_result(tmp_path, monkeypatch):
    """The actual picker boundary preserves queue behavior with a None result."""
    _isolate(tmp_path, monkeypatch)
    file = tmp_path / "queued.dat"
    np.savetxt(file, np.ones(20))
    app = owner.create_app()
    try:
        assert app.picker.on_paths([file]) is None
        assert str(file) in app.model.batch_files
    finally:
        app.close()
