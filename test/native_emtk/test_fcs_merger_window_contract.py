"""FCS Merger consumes primary geometry without changing screening or physical data."""

import copy
import json
from pathlib import Path

import numpy as np
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep window preferences and metadata outside user storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))


def test_primary_default_reaches_factory_and_host(tmp_path, monkeypatch):
    """The family dimensions come from the unchanged raw primary declaration."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fcs.fcs_merger.gui import app as owner

    path = Path(owner.__file__).with_name("fcs_merger_emtk.view.json")
    original = path.read_bytes()
    app = attach_native_state("merger_primary", owner.create_app())
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        Driver(app, size=app.window_size).draw(3)
        assert path.read_bytes() == original
        assert {"files", "curves", "mean"} <= app.item_rects.keys()
    finally:
        app.close()


def test_authored_dimensions_are_read_instead_of_repeated_constants(tmp_path, monkeypatch):
    """Editing a copy of the raw spec changes the real constructor's initial size."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fcs.fcs_merger.gui import app as owner

    spec = json.loads((owner.HERE / "fcs_merger_emtk.view.json").read_text())
    spec["window"] = {"width": 960, "height": 640}
    (tmp_path / "fcs_merger_emtk.view.json").write_text(json.dumps(spec))
    monkeypatch.setattr(owner, "HERE", tmp_path)
    app = owner.create_app()
    try:
        assert app.window_size == (960, 640)
        Driver(app, size=app.window_size).draw(3)
    finally:
        app.close()


def test_absent_primary_declaration_uses_family_fallback(tmp_path, monkeypatch):
    """An older specification still receives the declared FCS family fallback."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fcs.fcs_merger.gui import app as owner

    spec = json.loads((owner.HERE / "fcs_merger_emtk.view.json").read_text())
    spec.pop("window")
    (tmp_path / "fcs_merger_emtk.view.json").write_text(json.dumps(spec))
    monkeypatch.setattr(owner, "HERE", tmp_path)
    app = owner.create_app()
    try:
        assert app.window_size == (1100, 720)
    finally:
        app.close()


def test_saved_geometry_wins_and_rendering_preserves_real_merge(tmp_path, monkeypatch):
    """Resize/reopen retains native dimensions; the explicit state API rebuilds real curves."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fcs.fcs_merger.gui.app import create_app
    from chisurf.plugins.fcs.fcs_merger.test.make_chunks import build

    folder = build(tmp_path / "BH_SPC132")
    first = attach_native_state("merger_saved", create_app())
    try:
        assert first.load_folder(folder)
        first.job.future.result(timeout=60)
        first.job.poll()
        first.use = [True, True, False, True, True, True]
        first.selected = 1
        state = copy.deepcopy(first.export_state())
        mean = copy.deepcopy(first.mean_correlation)
        curves = copy.deepcopy(first.correlations)
        for size in ((1100, 720), (900, 650)):
            driver = Driver(first, size=size)
            for key in ("files", "curves", "mean"):
                first.docks.focus(key)
                driver.draw(2)
            assert first.export_state() == state
            for current, original in zip(first.correlations, curves):
                for key in ("x", "y", "ey"):
                    np.testing.assert_array_equal(current[key], original[key])
            for key in ("x", "y", "ey"):
                np.testing.assert_array_equal(first.mean_correlation[key], mean[key])
        first.window_resized(1330, 870)
    finally:
        first.close()
    other = attach_native_state("merger_saved", create_app())
    try:
        assert other.window_size == (1330, 870)
        # Existing state methods are explicit; native settings hooks are not added here.
        other.restore_state(state)
        other.job.future.result(timeout=60)
        other.job.poll()
        assert other.export_state() == state
        for key in ("x", "y", "ey"):
            np.testing.assert_array_equal(other.mean_correlation[key], mean[key])
        assert other.mean_correlation["duration"] == 50.0
        assert other.mean_correlation["count_rate"] == mean["count_rate"]
    finally:
        other.close()
