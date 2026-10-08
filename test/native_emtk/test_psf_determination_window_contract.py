"""PSF determination geometry is read from the composite specification before slicing."""

import copy
import json

from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Redirect native geometry and scientific preferences to scratch storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))


def test_primary_geometry_survives_panel_slicing(tmp_path, monkeypatch):
    """The real factory adopts composite geometry independently of its prepared panels."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.microscopy.psf_determination.gui.app import HERE, make_app

    original = (HERE / "psf.view.json").read_bytes()
    app = make_app()
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        assert set(app.panels) == {"psf", "detection", "beads"}
        Driver(app, size=(1100, 720)).draw()
        assert (HERE / "psf.view.json").read_bytes() == original
    finally:
        close = getattr(app, "close", None)
        if close:
            close()


def test_saved_resize_and_physical_settings_win_on_reopen(tmp_path, monkeypatch):
    """Stored user geometry and calibration survive construction and a render."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.microscopy.psf_determination.gui.app import make_app

    first = attach_native_state("psf_determination", make_app())
    first.model.pixel_size_nm = 123.0
    first.model.z_step_nm = 321.0
    first.window_resized(1340, 900)
    state = copy.deepcopy(first.export_settings())
    first.close()
    reopened = attach_native_state("psf_determination", make_app())
    try:
        assert reopened.window_size == (1340, 900)
        assert reopened.export_settings() == state
        reopened.draw(RecordingPainter(), 0, 0, 900, 650)
        assert reopened.window_size == (1340, 900)
        assert reopened.export_settings() == state
    finally:
        reopened.close()


def test_default_retains_docks_and_actual_demo_control(tmp_path, monkeypatch):
    """All four docks and the real demonstration action stay available at the default."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.microscopy.psf_determination.gui.app import make_app

    app = make_app()
    try:
        drv = Driver(app, size=(1100, 720))
        drv.draw(3)
        assert all(
            app.docks.window(k) is not None for k in ("controls", "stack", "profiles", "results")
        )
        assert {
            "demo",
            "detect_beads",
            "fit_selected",
            "fit_all",
            "export_csv",
        } <= app.item_rects.keys()
        drv.click("demo")
        drv.draw(3)
        assert app.model.stack.shape == (21, 110, 100)
        assert app.model.pixel_size_nm == 100.0
        assert app.model.z_step_nm == 300.0
    finally:
        close = getattr(app, "close", None)
        if close:
            close()
