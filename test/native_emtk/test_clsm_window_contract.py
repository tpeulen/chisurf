"""Declared host defaults retain native saved geometry and scientific preferences."""

import copy
import json
from pathlib import Path

from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Redirect preferences and metadata to temporary storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))


def test_raw_primary_geometry_reaches_the_real_factory(tmp_path, monkeypatch):
    """The host consumes composite dimensions before preparing dock controls."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.microscopy.clsm.gui import app as owner

    path = Path(owner.__file__).with_name("clsm.view.json")
    original = path.read_bytes()
    app = attach_native_state("clsm_geometry", owner.make_app())
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        Driver(app, size=(1100, 720)).draw(3)
        assert path.read_bytes() == original
    finally:
        app.close()


def test_saved_size_and_scientific_preferences_win_on_reopen(tmp_path, monkeypatch):
    """Reopening restores the existing state contract together with user dimensions."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.microscopy.clsm.gui.app import make_app

    first = attach_native_state("clsm_saved", make_app())
    first.model.setup.channels_text = "0,1"
    first.model.brush.size = 9
    first.model.decay.tac_coarsening = 4
    state = copy.deepcopy(first.state_dict())
    first.window_resized(1330, 870)
    first.close()
    reopened = attach_native_state("clsm_saved", make_app())
    try:
        assert reopened.window_size == (1330, 870)
        assert reopened.state_dict() == state
        reopened.draw(RecordingPainter(), 0, 0, 900, 650)
        assert reopened.window_size == (1330, 870)
        assert reopened.state_dict() == state
    finally:
        reopened.close()


def test_real_dock_addresses_remain_reachable(tmp_path, monkeypatch):
    """Every scientific dock keeps its real address and can be focused at the default."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.microscopy.clsm.gui.app import make_app

    app = attach_native_state("clsm_docks", make_app())
    try:
        driver = Driver(app, size=(1100, 720))
        for key in ('controls', 'image', 'decay'):
            assert app.docks.window(key) is not None
            app.docks.focus(key)
            driver.draw(2)
    finally:
        app.close()


def test_save_painted_mask_button_and_native_preferences_preserve_pixels(tmp_path, monkeypatch):
    """Saving a declared mask fixture retains its exact pixels through native reopen."""
    import numpy as np

    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.microscopy.clsm.gui.app import make_app

    app = attach_native_state("clsm_mask", make_app())
    mask = np.zeros((8, 8), dtype=bool)
    mask[2:6, 3:7] = True
    app.model.current_image = np.arange(64, dtype=float).reshape(8, 8)
    app.model.selection_mask = mask.astype(float) * 30000
    app.model.brush.live_update = False
    app._roi_name = "painted fixture"
    try:
        driver = Driver(app, size=(1100, 720))
        driver.draw(3)
        driver.click("Save painted region")
        region = app.model.regions.roi("painted fixture")
        assert region is not None
        np.testing.assert_array_equal(region.mask, mask)
    finally:
        app.close()
    reopened = attach_native_state("clsm_mask", make_app())
    try:
        region = reopened.model.regions.roi("painted fixture")
        assert region is not None
        np.testing.assert_array_equal(region.mask, mask)
    finally:
        reopened.close()
