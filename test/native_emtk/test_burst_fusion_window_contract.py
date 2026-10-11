"""Burst Fusion consumes primary geometry without changing genuine worker results."""

import copy
import json
from pathlib import Path

import numpy as np
from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep native geometry, generated photons and metadata in scratch storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))


def test_raw_primary_default_reaches_true_app_before_gui_loader(tmp_path, monkeypatch):
    """The host reads initial dimensions before the GUI adapts the primary sections."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_fusion.gui import app as owner

    path = Path(owner.__file__).with_name("fusion.view.json")
    original = path.read_bytes()
    app = attach_native_state("fusion_primary", owner.create_app())
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        Driver(app, size=app.window_size).draw(3)
        assert path.read_bytes() == original
        assert {"toolAction_run", "toolAction_refresh", "load_example"} <= app.item_rects.keys()
    finally:
        app.close()


def test_authored_primary_dimensions_reach_constructor(tmp_path, monkeypatch):
    """A copied primary declaration changes real factory dimensions."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_fusion.gui import app as owner

    primary = json.loads(Path(owner.__file__).with_name("fusion.view.json").read_text())
    primary["window"] = {"width": 960, "height": 640}
    (tmp_path / "fusion.view.json").write_text(json.dumps(primary))
    monkeypatch.setattr(owner, "__file__", str(tmp_path / "app.py"))
    app = owner.create_app()
    try:
        assert app.window_size == (960, 640)
        Driver(app, size=app.window_size).draw(3)
    finally:
        app.close()


def test_missing_declaration_uses_family_fallback(tmp_path, monkeypatch):
    """The primary sections remain usable when host metadata is absent."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_fusion.gui import app as owner

    primary = json.loads(Path(owner.__file__).with_name("fusion.view.json").read_text())
    primary.pop("window")
    (tmp_path / "fusion.view.json").write_text(json.dumps(primary))
    monkeypatch.setattr(owner, "__file__", str(tmp_path / "app.py"))
    app = owner.create_app()
    try:
        assert app.window_size == (1100, 720)
    finally:
        app.close()


def test_saved_geometry_wins_and_explicit_settings_preserve_parameters(tmp_path, monkeypatch):
    """Reopen restores native dimensions; settings JSON remains the explicit analysis contract."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_fusion.gui.app import create_app

    first = attach_native_state("fusion_saved", create_app())
    first.model.threshold = 0.7
    first.model.max_group = 3
    path = tmp_path / "fusion.json"
    first.controller.save_settings(path)
    params = copy.deepcopy(first.model.settings.to_dict())
    first.window_resized(1330, 870)
    first.close()
    other = attach_native_state("fusion_saved", create_app())
    try:
        assert other.window_size == (1330, 870)
        assert other.model.analysis is None
        other.controller.load_settings(path)
        assert other.model.settings.to_dict() == params
        other.draw(RecordingPainter(), 0, 0, 900, 650)
        assert other.window_size == (1330, 870)
    finally:
        other.close()


def test_real_fragment_demo_worker_maps_and_curves_survive_views(tmp_path, monkeypatch):
    """The actual photon search and Estimate worker publish results preserved by all view sizes."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_fusion.gui.app import create_app

    app = create_app()
    try:
        app.controller.demo()
        app.controller._future.result(timeout=120)
        app.controller.poll()
        assert app.model.demo is not None
        app.model.threshold = 0.7
        app.controller.estimate()
        app.controller._future.result(timeout=120)
        app.controller.poll()
        analysis = app.model.analysis
        assert analysis is not None
        assert analysis.statistics["n_bursts_before"] > 360
        assert abs(analysis.statistics["n_bursts_after"] - 300) < 30
        curve = analysis.window.p_same.copy()
        labels = [m.labels.copy() for m in analysis.measurements]
        settings = copy.deepcopy(app.model.settings.to_dict())
        statistics = copy.deepcopy(analysis.statistics)
        for size in ((1100, 720), (900, 650)):
            driver = Driver(app, size=size)
            for tab in (
                "P(same)",
                "Proximity ratio",
                "Photons",
                "Duration",
                "Fragments",
                "All plots",
            ):
                driver.draw(3)
                driver.click(tab)
                driver.draw(2)
            assert app.model.settings.to_dict() == settings
            assert app.model.analysis.statistics == statistics
            np.testing.assert_array_equal(app.model.analysis.window.p_same, curve)
            for current, original in zip(app.model.analysis.measurements, labels):
                np.testing.assert_array_equal(current.labels, original)
    finally:
        app.close()
