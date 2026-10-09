"""Primary LLTF geometry preserves real subprocess fits and native preferences."""

import copy
import json
import os
from pathlib import Path

import numpy as np
from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep native preferences and metadata outside user storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))


def test_raw_primary_default_reaches_factory_before_section_slicing(tmp_path, monkeypatch):
    """Initial geometry comes from the raw primary spec, not the controls-only copy."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fluorescence_decay.lltf.gui import app as owner

    path = Path(owner.__file__).with_name("lltf.view.json")
    original = path.read_bytes()
    app = attach_native_state("lltf_primary", owner.make_app())
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        assert "window" not in app.controls_spec
        Driver(app, size=app.window_size).draw(3)
        assert path.read_bytes() == original
        assert {"Fit", "Information", "Analysis Output", "Results"} <= app.item_rects.keys()
    finally:
        app.close()


def test_authored_dimensions_reach_real_constructor(tmp_path, monkeypatch):
    """A copied primary declaration changes the factory's dimensions."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fluorescence_decay.lltf.gui import app as owner

    spec = json.loads(Path(owner.__file__).with_name("lltf.view.json").read_text())
    spec["window"] = {"width": 960, "height": 640}
    (tmp_path / "lltf.view.json").write_text(json.dumps(spec))
    monkeypatch.setattr(owner, "__file__", str(tmp_path / "app.py"))
    app = owner.make_app()
    try:
        assert app.window_size == (960, 640)
        Driver(app, size=app.window_size).draw(3)
    finally:
        app.close()


def test_absent_declaration_uses_family_fallback(tmp_path, monkeypatch):
    """An older primary spec receives the same family fallback."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fluorescence_decay.lltf.gui import app as owner

    spec = json.loads(Path(owner.__file__).with_name("lltf.view.json").read_text())
    spec.pop("window")
    (tmp_path / "lltf.view.json").write_text(json.dumps(spec))
    monkeypatch.setattr(owner, "__file__", str(tmp_path / "app.py"))
    app = owner.make_app()
    try:
        assert app.window_size == (1100, 720)
    finally:
        app.close()


def test_saved_geometry_and_declared_preferences_win(tmp_path, monkeypatch):
    """Custom dimensions and fit inputs reopen; computed results are rebuilt on Fit."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fluorescence_decay.lltf.gui.app import make_app

    first = attach_native_state("lltf_saved", make_app())
    first.model.n_lifetimes = 2
    first.model.find_optimal = True
    first.model.max_lifetimes = 3
    prefs = copy.deepcopy(first.export_settings())
    first.window_resized(1330, 870)
    first.close()
    other = attach_native_state("lltf_saved", make_app())
    try:
        assert other.window_size == (1330, 870)
        assert other.export_settings() == prefs
        assert other.model.result is None
        other.draw(RecordingPainter(), 0, 0, 900, 650)
        assert other.window_size == (1330, 870)
        assert other.export_settings() == prefs
    finally:
        other.close()


def test_actual_measured_cli_fit_survives_tabs_and_narrow_host(tmp_path, monkeypatch):
    """A real CLI subprocess produces measured fit arrays retained by every host viewport."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fluorescence_decay.lltf.gui import app as owner

    root = Path(owner.__file__).resolve().parents[5]
    # The subprocess must use the same complete source tree as the app under verification.
    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", str(root) + os.pathsep + inherited)
    monkeypatch.chdir(tmp_path)
    example = Path(owner.__file__).parents[1] / "example"
    app = owner.make_app()
    try:
        app.model.decay_file = str(example / "5-44_D0.dat")
        app.model.irf_file = str(example / "IRF_D0.dat")
        app.model.load_config(example / "config.yml")
        app.model.output_dir = str(tmp_path)
        app.model.n_lifetimes = 2
        app.model.find_optimal = False
        app.start()
        app.model.process.wait(timeout=120)
        app.draw(RecordingPainter(), 0, 0, 1100, 720)
        assert app.model.returncode == 0, "\n".join(app.model.output)
        assert app.model.result is not None and app.arrays is not None
        result = copy.deepcopy(app.model.result)
        arrays = copy.deepcopy(app.arrays)
        assert result["n_lifetimes"] == 2
        assert result["dof"] > 0
        assert np.isclose(np.sum(arrays["residuals"] ** 2), result["chi_square"])
        for size in ((1100, 720), (900, 650)):
            driver = Driver(app, size=size)
            for key in ("inputs", "details", "plots"):
                app.docks.focus(key)
                driver.draw(3)
            for tab in ("Information", "Analysis Output", "Results"):
                driver.click(tab)
                driver.draw(2)
            assert app.model.result == result
            for key in arrays:
                np.testing.assert_array_equal(app.arrays[key], arrays[key])
            assert app.item_rects["Fit"][1] + app.item_rects["Fit"][3] <= size[1]
        assert Path(app.model.output_file).is_file()
        assert json.loads(Path(app.model.output_file).read_text()) == result
    finally:
        app.close()
