"""The wizard consumes native host metadata without altering IRFs or fit links."""

import json

import numpy as np
from emtk.testing import Driver

from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui import app as owner
from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.model import NativeAnisotropyModel


def _isolate(tmp_path, monkeypatch):
    """Use scratch defaults before constructing the native wizard."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))


def test_native_primary_dimensions_reach_constructor(tmp_path, monkeypatch):
    """Native dimensions come from the panel spec, not the Qt step metadata."""
    _isolate(tmp_path, monkeypatch)
    app = owner.AnisotropyApp(model=NativeAnisotropyModel())
    assert app.window_size == (1100, 720)
    Driver(app, app.window_size).draw(2)


def test_authored_primary_dimensions_are_read(tmp_path, monkeypatch):
    """The common size reader receives the authored native metadata."""
    _isolate(tmp_path, monkeypatch)
    original = owner.window_size
    received = []

    def authored(spec, fallback):
        """Exercise the real constructor with another valid authored size."""
        received.append(spec["window"])
        return original({**spec, "window": {"width": 960, "height": 680}}, fallback)

    monkeypatch.setattr(owner, "window_size", authored)
    app = owner.AnisotropyApp(model=NativeAnisotropyModel())
    assert app.window_size == (960, 680)
    assert received == [{"width": 1100, "height": 720}]


def test_normalized_irfs_preserved_across_default_and_narrow(tmp_path, monkeypatch):
    """Adaptive component panels do not mutate loaded counts or spectra."""
    _isolate(tmp_path, monkeypatch)
    model = NativeAnisotropyModel()
    model.first_column_is_time = True
    model.bin_width = 0.1
    x = np.arange(128) * 0.1
    values = {
        "irf_vv": np.exp(-0.5 * ((x - 2) / 0.3) ** 2) * 100 + 2,
        "irf_vh": np.exp(-0.5 * ((x - 2) / 0.3) ** 2) * 60 + 3,
        "data_vv": np.exp(-x / 4) * 1000 + 5,
        "data_vh": np.exp(-x / 4) * 500 + 5,
    }
    for key, data in values.items():
        file = tmp_path / f"{key}.txt"
        np.savetxt(file, np.column_stack([x, data]), header="time_ns counts")
        setattr(model, key + "_path", str(file))
    assert model.load_data()
    model.apply_region(50, 100)
    before = {key: data.y.copy() for key, data in model.data.items()}
    preferences = model.export_preferences()
    app = owner.AnisotropyApp(model=model)
    app.select_step(4)
    for size in [(1100, 720), (736, 552)]:
        Driver(app, size).draw(3)
        for key, expected in before.items():
            np.testing.assert_array_equal(model.data[key].y, expected)
        assert model.export_preferences() == preferences
        assert {"lifetime.add", "rotation.add"} <= app.item_rects.keys()
