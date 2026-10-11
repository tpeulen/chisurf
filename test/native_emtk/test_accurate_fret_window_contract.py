"""Primary Accurate FRET geometry preserves calibration definitions and native layout."""

from __future__ import annotations

import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.burst.accurate_fret.gui.app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create the actual calibration application with scratch detector and native settings."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    instance = create_app()
    yield instance
    instance.close()


def test_primary_declaration_reaches_actual_app_and_native_binding(app):
    """The true host application receives the declaration, independently of its GUI helper."""
    assert app.window_size == (1100, 720)
    attach_native_state("accurate-fret", app)
    assert app.window_size == (1100, 720)
    Driver(app, app.window_size).draw(3)
    assert "Calibrate" in app.accurate_gui.item_rects


def test_reader_sees_raw_primary_before_gui_adaptation(app, monkeypatch):
    """The constructor consumes raw metadata before the helper selects nested controls."""
    import chisurf.plugins.burst.accurate_fret.gui.app as module

    original = module.window_size
    seen = []

    def declared(spec, default):
        """Exercise a different declaration through the real constructor."""
        seen.append((spec["window"], "sections" in spec, default))
        return original({**spec, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(module, "window_size", declared)
    other = create_app()
    try:
        assert other.window_size == (1234, 789)
        assert seen == [({"width": 1100, "height": 720}, True, (1100, 720))]
    finally:
        other.close()


def test_reopen_restores_geometry_setup_parameters_and_docks_without_results(app):
    """Actual close/reopen retains definitions while inputs and estimates remain explicit."""
    attach_native_state("accurate-fret", app)
    app.model.donor_lifetime = 4.2
    app.model.n_bootstrap = 0
    app.model.use_priors = False
    app.model.background_dd = 0.1
    settings = app.export_settings()
    Driver(app, (1100, 720)).draw(3)
    app.accurate_gui.docks.undock("tau", (20, 30, 420, 360))
    layout = app.accurate_gui.docks.state()
    app.window_resized(1330, 870)
    app.close()
    reopened = attach_native_state("accurate-fret", create_app())
    try:
        assert reopened.window_size == (1330, 870)
        assert reopened.export_settings() == settings
        assert reopened.accurate_gui.docks.state()["windows"] == layout["windows"]
        assert not reopened.model._columns and reopened.model.result is None
    finally:
        reopened.close()


def test_true_known_calibration_and_corrected_bursts_survive_resize(app, tmp_path):
    """Actual file loading and calibration retain physical factors and every burst's values."""
    import time

    import numpy as np

    from chisurf.plugins.burst.accurate_fret.test.test_accurate_fret_plugin import (
        ALPHA,
        BETA,
        DELTA,
        GAMMA,
        _simulate,
    )

    dd, da, aa, tau = _simulate(n=900)
    path = tmp_path / "known-calibration.csv"
    np.savetxt(
        path,
        np.column_stack([dd, da, aa, tau]),
        delimiter=",",
        header="Green Count Rate (KHz),Red Count Rate (KHz),S delayed yellow (kHz),Tau (green)",
        comments="",
        fmt="%.17g",
    )
    app.model.n_bootstrap = 0
    app.model.use_priors = False
    app.controller.load(path)
    app.controller._future.result(timeout=60)
    app.controller.poll()
    app.controller.run()
    deadline = time.monotonic() + 60
    while app.controller.running and time.monotonic() < deadline:
        time.sleep(0.02)
        app.controller.poll()
    assert not app.controller.running
    result = app.model.result
    assert result is not None, app.controller.status
    f = result.factors
    assert f["gamma"] == pytest.approx(GAMMA, rel=0.04)
    assert f["alpha"] == pytest.approx(ALPHA, abs=0.006)
    assert f["beta"] == pytest.approx(BETA, rel=0.04)
    assert f["delta"] == pytest.approx(DELTA, abs=0.006)
    corrected = da - f["alpha"] * dd - f["delta"] * aa
    denominator = corrected + f["gamma"] * dd
    expected_e = np.divide(
        corrected, denominator, out=np.zeros_like(denominator), where=denominator > 0
    )
    expected_s = np.divide(
        denominator,
        denominator + aa / f["beta"],
        out=np.zeros_like(denominator),
        where=(denominator + aa / f["beta"]) != 0,
    )
    np.testing.assert_allclose(result.efficiency, expected_e, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(result.stoichiometry, expected_s, rtol=1e-12, atol=1e-12)
    original = {
        name: np.asarray(getattr(result, name)).copy()
        for name in ("efficiency", "stoichiometry", "labels", "distance")
    }
    settings = app.export_settings()
    driver = Driver(app, (1100, 720))
    for size in ((736, 552), (800, 600), (1330, 870)):
        driver.draw(3, size=size)
        for panel in ("settings", "channels", "es", "tau", "hist"):
            app.accurate_gui.docks.focus(panel)
            driver.draw(3)
    assert app.export_settings() == settings
    assert result.factors == f
    for name, values in original.items():
        np.testing.assert_array_equal(getattr(result, name), values)
