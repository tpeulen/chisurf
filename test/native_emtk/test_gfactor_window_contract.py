"""G-factor host metadata preserves calibration results and native settings."""

from __future__ import annotations

import json
import time

import numpy as np
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.vv_vh_g_factor.gui import app as owner


def _isolate(tmp_path, monkeypatch):
    """Use scratch state for the actual production in-process client."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb/db.sqlite"))


def _settle(app):
    """Publish the real background job and settle render-triggered computation."""
    end = time.monotonic() + 15
    while app.job.running and time.monotonic() < end:
        app.job.poll()
        time.sleep(0.01)
    assert not app.job.running


def test_raw_primary_dimensions_reach_actual_factory(tmp_path, monkeypatch):
    """The host consumes authored metadata before adapting panel controls."""
    _isolate(tmp_path, monkeypatch)
    app = owner.create_app()
    try:
        assert app.window_size == (1100, 720)
        Driver(app, app.window_size).draw(2)
        assert app.panels["tail"]
    finally:
        app.close()


def test_authored_size_is_consumed_not_hardcoded(tmp_path, monkeypatch):
    """A copied specification drives the real constructor's host dimensions."""
    _isolate(tmp_path, monkeypatch)
    spec = json.loads((owner.HERE / "gfactor_emtk.view.json").read_text())
    spec["window"] = {"width": 980, "height": 680}
    (tmp_path / "gfactor_emtk.view.json").write_text(json.dumps(spec))
    for name in ["help.md", "guide.json"]:
        (tmp_path / name).write_bytes((owner.HERE / name).read_bytes())
    monkeypatch.setattr(owner, "HERE", tmp_path)
    app = owner.create_app()
    try:
        assert app.window_size == (980, 680)
    finally:
        app.close()


def test_real_calibration_is_unchanged_by_default_and_narrow_draws(tmp_path, monkeypatch):
    """Actual job output and channel arrays survive host resizing."""
    _isolate(tmp_path, monkeypatch)
    vh = 500 * np.exp(-np.arange(100) / 20) + 5
    file = tmp_path / "known.dat"
    np.savetxt(file, np.concatenate([2 * vh, vh]))
    app = owner.create_app()
    try:
        assert app.load(str(file))
        _settle(app)
        assert app.model.g_factor == 2
        before = app.model.decay_series()
        settings = app.model.export_settings()
        for size in [(1100, 720), (736, 552)]:
            Driver(app, size).draw(3)
            _settle(app)
            for key, value in before.items():
                np.testing.assert_array_equal(app.model.decay_series()[key], value)
            assert app.model.export_settings() == settings
    finally:
        app.close()


def test_saved_geometry_takes_precedence(tmp_path, monkeypatch):
    """Native preferences use the user's dimensions on a fresh app."""
    _isolate(tmp_path, monkeypatch)
    app = attach_native_state("gfactor-size", owner.create_app())
    app.window_resized(1330, 870)
    app.close()
    second = attach_native_state("gfactor-size", owner.create_app())
    try:
        assert second.window_size == (1330, 870)
    finally:
        second.close()


def test_narrow_batch_table_preserves_readable_identity_and_headers(tmp_path, monkeypatch):
    """A narrow host scrolls measured columns instead of squeezing their contents."""
    _isolate(tmp_path, monkeypatch)
    file = tmp_path / "known-fast.dat"
    vv = 2 * np.exp(-np.arange(100) / 20)
    np.savetxt(file, np.concatenate([vv, vv / 2]))
    app = owner.create_app()
    try:
        app.model.load(file)
        app.model.batch_files = [str(file)]
        app.model.compute_batch()
        app.docks.focus("batch")
        paint = Driver(app, (736, 552)).draw(3)
        assert "known-fast.dat" in paint.strings
        table = app.forms["batch"].tables["batch_rows"].control
        widths = table._column_widths(300)
        assert min(widths) >= 80
        assert sum(widths) > 300
        assert table._hbar_box is not None
        x, y, width, _ = table._body_box
        driver = Driver(app, (736, 552))
        for _ in range(6):
            driver.wheel(0, at=(x + width / 2, y + 10), dx=-1)
        assert "Error" in driver.draw(2).strings
        assert app.model.batch_results[0]["r_inf"] == 0
    finally:
        app.close()
