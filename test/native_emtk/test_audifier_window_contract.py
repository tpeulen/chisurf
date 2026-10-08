"""Declared TTTR host geometry preserves native scientific preferences."""

import copy
import json
from pathlib import Path

from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep native preferences and metadata in scratch storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))


def test_raw_primary_default_reaches_the_real_factory(tmp_path, monkeypatch):
    """Primary dimensions are consumed before rendering prepared control specs."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.audifier.gui import app as owner

    original = Path(owner.__file__).with_name("audifier.view.json").read_bytes()
    app = attach_native_state("audifier_primary", owner.create_app())
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        Driver(app, size=(1100, 720)).draw(3)
        assert Path(owner.__file__).with_name("audifier.view.json").read_bytes() == original
    finally:
        app.close()


def test_saved_dimensions_and_scientific_settings_win(tmp_path, monkeypatch):
    """Reopening and rendering retain custom dimensions and the existing settings contract."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.audifier.gui.app import create_app

    first = attach_native_state("audifier_saved", create_app())
    first.model.sample_rate = 22050
    first.model.master_gain = 1.25
    state = copy.deepcopy(first.export_settings())
    first.window_resized(1330, 870)
    first.close()
    other = attach_native_state("audifier_saved", create_app())
    try:
        assert other.window_size == (1330, 870)
        assert other.export_settings() == state
        other.draw(RecordingPainter(), 0, 0, 900, 650)
        assert other.window_size == (1330, 870)
        assert other.export_settings() == state
    finally:
        other.close()


def test_dock_addresses_remain_available(tmp_path, monkeypatch):
    """Every real scientific panel stays reachable at the declared initial dimensions."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.audifier.gui.app import create_app

    app = attach_native_state("audifier_docks", create_app())
    try:
        driver = Driver(app, size=(1100, 720))
        for key in ('setup', 'audio', 'waterfall_parameters', 'waterfall', 'mixer', 'notes'):
            assert app.docks.window(key) is not None
            app.docks.focus(key)
            driver.draw(2)
    finally:
        app.close()
