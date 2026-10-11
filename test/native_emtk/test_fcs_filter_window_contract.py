"""Declared FCS filter geometry preserves physical results and saved layouts."""

from __future__ import annotations

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.fcs.fcs_filter_calculator.gui.app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Build a real worker with isolated detector and native settings."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    instance = create_app()
    instance.job.future.result(timeout=60)
    instance.job.poll()
    yield instance
    instance.close()


def test_primary_default_reaches_true_factory_and_native_binding(app):
    """The standalone host receives the declared tool size before saved preferences."""
    assert app.window_size == (1100, 720)
    attach_native_state("fcs-filter-calculator", app)
    assert app.window_size == (1100, 720)
    driver = Driver(app, app.window_size)
    driver.draw(3)
    assert "compute" in driver.ids()


def test_primary_declaration_drives_factory(app, monkeypatch):
    """The real constructor reads its primary specification through the shared reader."""
    import chisurf.plugins.fcs.fcs_filter_calculator.gui.app as module

    original = module.window_size
    seen = []

    def declared(spec, default):
        """Record the declaration and exercise a different configured default."""
        seen.append((spec["window"], default))
        return original({**spec, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(module, "window_size", declared)
    other = create_app()
    try:
        assert other.window_size == (1234, 789)
        assert seen == [({"width": 1100, "height": 720}, (1100, 720))]
    finally:
        other.close()


def test_saved_user_geometry_and_docks_override_primary_default(app):
    """An actual close and reopen keeps the user's geometry and dock layout."""
    attach_native_state("fcs-filter-calculator", app)
    Driver(app, app.window_size).draw(3)
    app.docks.selected["controls"] = "instrument"
    app.docks.undock("info", (30, 40, 450, 400))
    saved = app.docks.state()
    app.window_resized(1330, 870)
    app.close()
    reopened = attach_native_state("fcs-filter-calculator", create_app())
    try:
        assert reopened.window_size == (1330, 870)
        assert reopened.docks.state()["layout"] == saved["layout"]
        assert reopened.docks.state()["windows"] == saved["windows"]
        assert reopened.docks.selected["controls"] == "instrument"
    finally:
        reopened.close()


def test_resize_preserves_real_filters_reconstruction_residuals_and_settings(app):
    """Geometry leaves computed physical arrays, detector IRFs and fit definitions intact."""
    state = app.model.export_state()
    fingerprint = app.settings_fingerprint()
    result = app.model.results()[0]["result"]
    arrays = {
        name: np.asarray(getattr(result, name)).copy()
        for name in ("filters", "reconstruction", "weighted_residuals", "total_decay")
    }
    irfs = {name: np.asarray(value).copy() for name, value in app.model._irf_by_detector.items()}
    assert arrays["filters"].shape[0] == 4
    assert int(arrays["total_decay"].sum()) > 90000
    driver = Driver(app, (1100, 720))
    for size in ((1100, 720), (800, 600), (1330, 870)):
        driver = Driver(app, size)
        for tab in ("sources", "setup", "autofit", "instrument", "info"):
            app.docks.selected["controls"] = tab
            driver.draw(3)
    assert app.settings_fingerprint() == fingerprint
    assert app.model.export_state() == state
    for name, expected in arrays.items():
        np.testing.assert_array_equal(getattr(result, name), expected)
    for name, expected in irfs.items():
        np.testing.assert_array_equal(app.model._irf_by_detector[name], expected)


def test_initial_clamped_legend_fits_and_hover_exposes_original_identity(app):
    """Every long legend caption stays visible and offers the full original label on hover."""
    driver = Driver(app, (736, 552))
    painter = driver.draw(3)
    entry = next(
        record for record in painter.texts if "green" in record[5] and "Scatter" in record[5]
    )
    x, y, _, height, _, text, *_ = entry
    assert x + painter.text_width(text) < 736
    import time

    driver.hover((x + 6, y + height / 2))
    driver.draw(2)
    time.sleep(0.65)
    painter = driver.draw(4)
    original = "green  Scatter / IRF (green, detector-IRF) [rejected]"
    assert original in " ".join(painter.strings)


@pytest.mark.parametrize("size", [(736, 552), (800, 600)])
def test_small_hosts_scroll_to_final_component_action_with_fixed_tabs(app, size):
    """The final input action remains reachable on a screen-clamped or narrow host."""
    driver = Driver(app, size)
    driver.draw(3)
    header = app.docks.tab_rect("sources")
    for _ in range(8):
        driver.wheel(-2, at=(150, size[1] - 120))
    _, y, _, height = driver.rect("add_measured")
    assert 0 <= y < y + height <= size[1]
    assert app.docks.tab_rect("sources") == header
    assert app.docks.tab_rect("info")[0] + app.docks.tab_rect("info")[2] < size[0]


def test_legend_visibility_survives_resize_with_complete_original_identity(app):
    """Toggling a shortened legend entry keeps the same curve hidden after resize."""
    driver = Driver(app, (736, 552))
    painter = driver.draw(3)
    entry = next(
        record for record in painter.texts if "green" in record[5] and "Scatter" in record[5]
    )
    x, y, _, height, _, caption, colour, *_ = entry
    driver.click((x - 6, y + height / 2))
    toggled = next(record for record in driver.draw(3).texts if record[5] == caption)
    assert toggled[6] != colour
    resized = driver.draw(3, size=(1330, 870))
    retained = next(record for record in resized.texts if record[5] == caption)
    assert retained[6] == toggled[6]
