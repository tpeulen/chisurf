"""Consumed host geometry leaves background fit settings and photon diagnostics unchanged."""

from __future__ import annotations

import time

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.burst.burst_background.gui.app import create_app


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
    attach_native_state("burst-background", app)
    assert app.window_size == (1100, 720)
    driver = Driver(app, app.window_size)
    driver.draw(3)
    assert "bg_run" in driver.ids()


def test_loaded_host_metadata_drives_constructor(app, monkeypatch):
    """Changing the declaration through the common reader changes the true host default."""
    import chisurf.plugins.burst.burst_background.gui.app as module

    original = module.window_size
    seen = []

    def declared(spec, default):
        """Record actual file metadata and exercise a different authored size."""
        seen.append((spec["window"], default))
        return original({**spec, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(module, "window_size", declared)
    other = create_app()
    try:
        assert other.window_size == (1234, 789)
        assert seen == [({"width": 1100, "height": 720}, (1100, 720))]
    finally:
        other.close()


def test_saved_geometry_wins_and_native_has_no_analysis_restore_adapter(app):
    """Close/reopen preserves the user's size without claiming cached input or result restoration."""
    attach_native_state("burst-background", app)
    app.model.binsize_ms = 0.2
    Driver(app, (1100, 720)).draw(3)
    app.window_resized(1330, 870)
    app.close()
    reopened = attach_native_state("burst-background", create_app())
    try:
        assert reopened.window_size == (1330, 870)
        assert reopened.model.files == []
        assert not reopened.model.has_results()
        assert not callable(getattr(reopened, "restore_settings", None))
    finally:
        reopened.close()


def test_resize_preserves_real_background_worker_physics(app, tmp_path):
    """Measured photon intervals, tail-fit results and detector settings survive redraws."""
    from chisurf.plugins.burst.burst_background.test.demo_data import build

    source = build(tmp_path / "measurement", seed=5)
    app.controller.add_files([source])
    app.controller.run()
    deadline = time.monotonic() + 20
    while app.controller.running and time.monotonic() < deadline:
        app.controller.poll()
        time.sleep(0.01)
    assert not app.controller.running
    assert app.model.has_results(), app.controller.status
    rates = dict(app.model.backgrounds[str(source)])
    intervals = {key: value.copy() for key, value in app.model._interphoton[str(source)].items()}
    detectors = app.model._channels()
    window = app.model.fit_range()
    assert set(rates) == {"green", "red"}
    assert all(value > 0 for value in rates.values())
    for size in [(736, 552), (1100, 720), (1330, 870)]:
        Driver(app, size).draw(3)
        assert app.model.backgrounds[str(source)] == rates
        assert app.model._channels() == detectors
        assert app.model.fit_range() == window
        for key, value in intervals.items():
            np.testing.assert_array_equal(app.model._interphoton[str(source)][key], value)


@pytest.mark.parametrize("enabled", [False, True])
def test_channel_button_uses_declared_optional_callback(app, enabled):
    """The real button tolerates no callback and focuses the detector dock when connected."""
    app.bg_gui.docks.focus("controls")
    seen = []
    original = app.controller.on_show_channels
    assert callable(original)

    def show_channels():
        """Preserve the real dock action and record its actual native delivery."""
        seen.append(True)
        original()

    app.controller.on_show_channels = show_channels if enabled else None
    driver = Driver(app, (1100, 720))
    driver.draw(3)
    driver.click("bg_channels")
    driver.draw(3)
    assert seen == ([True] if enabled else [])
    assert app.bg_gui.docks.is_shown("channels") == enabled
