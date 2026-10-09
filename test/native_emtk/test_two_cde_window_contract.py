"""Consumed host geometry leaves two-channel KDE settings and results unchanged."""

from __future__ import annotations

import time

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.burst.burst_2cde.gui.app import create_app


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
    attach_native_state("burst-2cde", app)
    assert app.window_size == (1100, 720)
    driver = Driver(app, app.window_size)
    driver.draw(3)
    assert "run" in driver.ids()


def test_loaded_host_metadata_drives_constructor(app, monkeypatch):
    """Changing the declaration through the common reader changes the true host default."""
    import chisurf.plugins.burst.burst_2cde.gui.app as module

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
    attach_native_state("burst-2cde", app)
    app.model.tau_us = 50.0
    app.model.variant = "alex"
    Driver(app, (1100, 720)).draw(3)
    app.window_resized(1330, 870)
    app.close()
    reopened = attach_native_state("burst-2cde", create_app())
    try:
        assert reopened.window_size == (1330, 870)
        assert reopened.model.folder == ""
        assert reopened.model.df is None
        assert not callable(getattr(reopened, "restore_settings", None))
    finally:
        reopened.close()


@pytest.mark.parametrize("variant", ["fret", "alex"])
def test_resizing_preserves_real_worker_result_and_declared_settings(app, tmp_path, variant):
    """Actual photon-stream analysis survives narrow/default/custom host redraws."""
    from chisurf.core.datastore import numeric_column
    from chisurf.plugins.burst.burst_2cde.core import computation as core
    from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build

    app.model.folder = str(build(tmp_path / "measurement", n_bursts=12, photons=80, seed=3))
    app.model.donor_channels_text = "0"
    app.model.acceptor_channels_text = "1"
    app.model.variant = variant
    app.model.tau_us = 50.0
    app.controller.run(force=True)
    deadline = time.monotonic() + 15
    while app.controller.running and time.monotonic() < deadline:
        app.controller.poll()
        time.sleep(0.01)
    assert not app.controller.running
    assert app.model.df is not None
    column = core.column_for_variant(variant)
    values = numeric_column(app.model.df, column).copy()
    assert values.shape == (12,)
    assert np.isfinite(values).all()
    settings = app.model.settings()
    for size in [(736, 552), (1100, 720), (1330, 870)]:
        Driver(app, size).draw(3)
        np.testing.assert_array_equal(numeric_column(app.model.df, column), values)
        assert app.model.settings() == settings
