"""Consumed BVA host geometry preserves responsive controls and real variance analysis."""

import copy
import json
from pathlib import Path

import numpy as np
from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep controller defaults and native geometry in scratch storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))


def test_host_only_primary_reaches_real_factory(tmp_path, monkeypatch):
    """The consumed host declaration owns geometry without claiming a control migration."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_bva.gui import app as owner

    path = Path(owner.__file__).with_name("window.view.json")
    original = path.read_bytes()
    spec = json.loads(original)
    app = attach_native_state("bva_primary", owner.create_app())
    try:
        assert spec["window"] == {"width": 1100, "height": 720}
        assert spec["sections"] == []
        assert app.window_size == (1100, 720)
        Driver(app, size=app.window_size).draw(3)
        assert path.read_bytes() == original
        assert {"run", "BVA Settings", "Channel Definitions", "bva_plot"} <= app.item_rects.keys()
    finally:
        app.close()


def test_authored_primary_dimensions_reach_constructor(tmp_path, monkeypatch):
    """A different copied declaration changes initial dimensions through the actual constructor."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_bva.gui import app as owner

    spec = json.loads(Path(owner.__file__).with_name("window.view.json").read_text())
    spec["window"] = {"width": 960, "height": 640}
    (tmp_path / "window.view.json").write_text(json.dumps(spec))
    monkeypatch.setattr(owner, "__file__", str(tmp_path / "app.py"))
    app = owner.create_app()
    try:
        assert app.window_size == (960, 640)
        Driver(app, size=app.window_size).draw(3)
    finally:
        app.close()


def test_absent_declaration_uses_family_fallback(tmp_path, monkeypatch):
    """An older host declaration receives the same deterministic family fallback."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_bva.gui import app as owner

    (tmp_path / "window.view.json").write_text(json.dumps({"sections": []}))
    monkeypatch.setattr(owner, "__file__", str(tmp_path / "app.py"))
    app = owner.create_app()
    try:
        assert app.window_size == (1100, 720)
    finally:
        app.close()


def test_saved_geometry_and_existing_controller_defaults_win(tmp_path, monkeypatch):
    """Custom native dimensions and documented INI defaults reopen without fabricated results."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_bva.gui.app import create_app

    first = attach_native_state("bva_saved", create_app())
    first.model.photons_per_slice = 12
    first.model.bins_x = 31
    first.model.bins_y = 37
    first.controller.save_settings()
    first.window_resized(1330, 870)
    first.close()
    other = attach_native_state("bva_saved", create_app())
    try:
        assert other.window_size == (1330, 870)
        assert (other.model.photons_per_slice, other.model.bins_x, other.model.bins_y) == (
            12,
            31,
            37,
        )
        assert other.model.df is None
        other.draw(RecordingPainter(), 0, 0, 900, 650)
        assert other.window_size == (1330, 870)
    finally:
        other.close()


def test_actual_worker_rows_static_line_and_photons_survive_host_views(tmp_path, monkeypatch):
    """Real static/dynamic SPC photons are computed on the worker and preserved by every tab/resize."""
    isolate(tmp_path, monkeypatch)
    from chisurf.core.datastore import numeric_column
    from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build
    from chisurf.plugins.burst.burst_bva.gui.app import create_app

    folder = build(tmp_path / "measurement", n_bursts=60, photons=120, seed=3)
    app = create_app()
    try:
        app.model.auto_update = False
        app.model.donor_channels_text = "0"
        app.model.acceptor_channels_text = "1"
        assert app.files_dropped([str(folder)])
        app.controller.run()
        app.controller._future.result(timeout=90)
        app.controller.poll()
        assert app.model.df is not None, app.model.status_text
        mean = numeric_column(app.model.df, "Proximity Ratio Mean").copy()
        sd = numeric_column(app.model.df, "Proximity Ratio Std").copy()
        settings = copy.deepcopy(app.model.bva_settings())
        raw = app.model.tttrs["m000.spc"]
        micro = np.asarray(raw.micro_times).copy()
        channels = np.asarray(raw.routing_channels).copy()
        for size in ((1100, 720), (900, 650)):
            driver = Driver(app, size=size)
            for tab in ("BVA Settings", "Channel Definitions", "Plot"):
                driver.draw(3)
                driver.click(tab)
                driver.draw(2)
            np.testing.assert_array_equal(
                numeric_column(app.model.df, "Proximity Ratio Mean"), mean
            )
            np.testing.assert_array_equal(numeric_column(app.model.df, "Proximity Ratio Std"), sd)
            np.testing.assert_array_equal(raw.micro_times, micro)
            np.testing.assert_array_equal(raw.routing_channels, channels)
            assert app.model.bva_settings() == settings
        plot = app.model.get_plot_data()
        np.testing.assert_allclose(
            plot["static_y"], np.sqrt(plot["static_x"] * (1 - plot["static_x"]) / 10)
        )
        assert sd[np.arange(60) % 4 == 3].mean() > sd[np.arange(60) % 4 != 3].mean() + 0.1
    finally:
        app.close()


def test_custom_callback_host_shares_target_rectangles_without_controller(tmp_path, monkeypatch):
    """The optional controller path stays safe and GUI/app target addresses share one dictionary."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_bva.gui.app import create_app

    app = create_app(on_run=lambda: None)
    try:
        assert app.controller is None
        assert app.item_rects is app.bva_gui.item_rects
        Driver(app, size=(1100, 720)).draw(3)
        app.bva_gui.remember("shared_target", (10.0, 20.0, 30.0, 40.0))
        assert app.item_rects["shared_target"] == (10.0, 20.0, 30.0, 40.0)
        assert {"run", "BVA Settings", "bva_plot"} <= app.item_rects.keys()
    finally:
        app.close()
