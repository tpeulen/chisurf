"""Consumed host geometry leaves burst-wise FCS settings and correlation arrays unchanged."""

from __future__ import annotations

import time

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Construct the actual native analysis with scratch window preferences."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    instance = create_app()
    yield instance
    instance.close()


def test_host_declaration_reaches_real_factory_and_native_binding(app):
    """The real host reads the dedicated geometry metadata before persistence binds."""
    assert app.window_size == (1100, 720)
    attach_native_state("burst-fcs-correlator", app)
    assert app.window_size == (1100, 720)
    driver = Driver(app, app.window_size)
    driver.draw(3)
    assert "run" in driver.ids()


def test_loaded_host_metadata_drives_constructor(app, monkeypatch):
    """Changing the declaration through the common reader changes the true host default."""
    import chisurf.plugins.burst.burst_fcs_correlator.gui.app as module

    original = module.window_size
    seen = []

    def declared(spec, default):
        """Record actual file metadata and exercise a different authored size."""
        seen.append((spec["window"], default, "toolbar" in spec))
        return original({**spec, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(module, "window_size", declared)
    other = create_app()
    try:
        assert other.window_size == (1234, 789)
        assert seen == [({"width": 1100, "height": 720}, (1100, 720), True)]
    finally:
        other.close()


def test_saved_geometry_wins_and_native_has_no_analysis_restore_adapter(app):
    """Close/reopen preserves the user's size without claiming cached input or result restoration."""
    attach_native_state("burst-fcs-correlator", app)
    app.controller._model.padding_ms = 0.0
    app.select_tab("Settings")
    Driver(app, (1100, 720)).draw(3)
    app.window_resized(1330, 870)
    app.close()
    reopened = attach_native_state("burst-fcs-correlator", create_app())
    try:
        assert reopened.window_size == (1330, 870)
        assert reopened.controller.files == []
        assert reopened.controller._curves == []
        assert not callable(getattr(reopened, "restore_settings", None))
    finally:
        reopened.close()


def test_resize_preserves_actual_twenty_four_correlations(app, tmp_path):
    """Real demo photons produce24curves whose declared settings and arrays survive resizing."""
    import json

    from chisurf.plugins.burst.burst_fcs_correlator.demo import make_demo

    table = make_demo(tmp_path / "demo")
    controller = app.controller
    pairs = [
        {"pair_name": "ACF_0", "chs_a": [0], "chs_b": [0]},
        {"pair_name": "ACF_1", "chs_a": [1], "chs_b": [1]},
        {"pair_name": "cross", "chs_a": [0], "chs_b": [1]},
    ]
    assert controller.apply_pairs(json.dumps(pairs))
    controller.add_files([table])
    controller._model.fit_mode = "none"
    controller._on_run()
    deadline = time.monotonic() + 30
    while controller.running and time.monotonic() < deadline:
        controller.poll()
        time.sleep(0.01)
    assert not controller.running
    assert len(controller._curves) == 24, controller.status
    settings = controller._model.to_settings().to_dict()
    recorded_pairs = json.dumps(controller._pair_presets, sort_keys=True)
    arrays = [
        (np.asarray(curve["tau_raw"]).copy(), np.asarray(curve["g_raw"]).copy())
        for curve in controller._curves
    ]
    assert arrays[0][0][1] > 0
    for size in [(736, 552), (1100, 720), (1330, 870)]:
        Driver(app, size).draw(3)
        assert controller._model.to_settings().to_dict() == settings
        assert json.dumps(controller._pair_presets, sort_keys=True) == recorded_pairs
        for curve, (tau, correlation) in zip(controller._curves, arrays):
            np.testing.assert_array_equal(curve["tau_raw"], tau)
            np.testing.assert_array_equal(curve["g_raw"], correlation)


def test_pair_heading_hover_explains_the_actual_gate_contract(app):
    """Existing heading delivers the primary description through the actual native tooltip."""
    import chisurf.plugins.burst.burst_fcs_correlator.gui.app as module

    driver = Driver(app, (1100, 720))
    driver.draw(3)
    heading = driver.rect("pair_heading")
    driver.hover("pair_heading")
    time.sleep(0.55)  # The public toolkit hover delay is0.5s.
    painter = driver.draw(3)
    text = "".join("".join(painter.strings).split())
    description = module.SPEC["pairs"]["sections"][0]["description"]
    assert "".join(description.split()) in text
    assert driver.rect("pair_heading") == heading
