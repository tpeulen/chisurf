"""PCH primary geometry is explicit and stored user dimensions retain precedence."""

import copy
import json

from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Redirect window and metadata storage to the temporary test tree."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))


def test_real_factory_reads_primary_default_without_mutating_spec(tmp_path, monkeypatch):
    """The primary PCH form sets the host dimensions before any host is created."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.pch.gui.app import HERE, make_app

    original = (HERE / "pch.view.json").read_bytes()
    app = make_app()
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        Driver(app, size=(1100, 720)).draw()
        assert (HERE / "pch.view.json").read_bytes() == original
    finally:
        app.close()


def test_saved_resize_and_species_preferences_win_on_reopen(tmp_path, monkeypatch):
    """Stored size and species configuration survive factory and renderer setup."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.pch.gui.app import make_app

    first = attach_native_state("pch", make_app())
    first.model.channels = "0,8"
    first.model.bin_time_us = 50.0
    first.model.set_n_components(2)
    first.model.species[1].update(epsilon=7.5, n_mean=0.25)
    first.window_resized(1340, 900)
    state = copy.deepcopy(first.export_settings())
    first.close()
    reopened = attach_native_state("pch", make_app())
    try:
        assert reopened.window_size == (1340, 900)
        assert reopened.export_settings() == state
        reopened.draw(RecordingPainter(), 0, 0, 900, 650)
        assert reopened.window_size == (1340, 900)
        assert reopened.export_settings() == state
    finally:
        reopened.close()


def test_default_retains_plots_settings_and_primary_action_addresses(tmp_path, monkeypatch):
    """The two docks and four workflow actions retain their real addresses."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.pch.gui.app import make_app

    app = make_app()
    try:
        drv = Driver(app, size=(1100, 720))
        drv.draw()
        assert all(app.docks.window(key) is not None for key in ("plots", "settings"))
        assert {"load", "compute", "fit", "save"} <= app.form.rects.keys()
        assert {"trace_plot", "region", "help", "guide"} <= app.item_rects.keys()
        drv.click("load")
        drv.draw(3)
        assert app.dialog is not None and app.dialog_kind == "open"
    finally:
        app.close()
