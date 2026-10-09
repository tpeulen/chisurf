"""Spectra host dimensions preserve real staging data and native preferences."""

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.spectra_downloader.gui import app as owner
from chisurf.plugins.spectra_downloader.mmfdb_adapter import FluorophoreDatabase


@pytest.fixture
def database(tmp_path, monkeypatch):
    """Create actual local staging data, independent of user settings and databases."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "live.sqlite"))
    db = FluorophoreDatabase(tmp_path / "staging.sqlite")
    db.connect()
    db.register_component(
        name="Analytic spectrum fixture",
        source="fpbase",
        kind="fluorescent_protein",
        spectra={"emission": (np.array([400., 500., 600.]), np.array([0., 1., 0.]))},
    )
    yield db
    db.close()


def test_primary_dimensions_reach_constructor(database):
    """The native primary declares the tool-family host dimensions."""
    app = owner.create_app(database)
    try:
        assert app.window_size == (1100, 720)
    finally:
        app.close()


def test_authored_dimensions_are_read(database, monkeypatch):
    """Metadata reaches the common reader before panel adaptation."""
    read = owner.window_size
    received = []

    def authored(spec, fallback):
        """Validate another authored size with the production reader."""
        received.append(spec["window"])
        return read({**spec, "window": {"width": 960, "height": 680}}, fallback)

    monkeypatch.setattr(owner, "window_size", authored)
    app = owner.create_app(database)
    try:
        assert app.window_size == (960, 680)
        assert received == [{"width": 1100, "height": 720}]
    finally:
        app.close()


def test_default_and_narrow_preserve_spectra_selection(database):
    """Rendering all existing panels leaves counts, spectra and chosen IDs intact."""
    app = owner.create_app(database)
    try:
        app.model.select(app.model.rows[0]["probe_id"])
        spectrum = app.model.detail["spectra"][0]
        selected = set(app.model.selected)
        for size in [(1100, 720), (736, 552)]:
            for panel in owner.PANELS:
                app.select_panel(panel)
                Driver(app, size).draw(3)
                assert app.model.selected == selected
                assert app.model.overview()["total"] == 1
                assert app.model.detail["spectra"][0] == spectrum
                assert {"nav." + name for name in owner.PANELS} <= app.item_rects.keys()
    finally:
        app.close()


def test_saved_geometry_and_filters_restore(database):
    """The existing preference seam retains dimensions, IDs, filters and panel."""
    first = attach_native_state("spectra_window_contract", owner.create_app(database))
    first.select_panel("Browse")
    first.model.search = "fixture"
    first.model.select(first.model.rows[0]["probe_id"])
    expected = first.export_settings()
    first.window_resized(1330, 870)
    first.close()
    reopened = attach_native_state("spectra_window_contract", owner.create_app(database))
    try:
        assert reopened.window_size == (1330, 870)
        assert reopened.export_settings() == expected
    finally:
        reopened.close()


def test_stacked_spectrum_is_reachable_with_wheel(database):
    """Stacked Browse content scrolls its plotted spectrum above the fixed footer."""
    for size in [(1100, 720), (736, 552)]:
        app = owner.create_app(database)
        try:
            app.select_panel("Browse")
            app.model.select(app.model.rows[0]["probe_id"])
            driver = Driver(app, size)
            driver.draw(3)
            before = app.item_rects["plot"]
            driver.wheel(-20, at=(size[0] - 15, size[1] * 0.6))
            driver.draw(3)
            after = app.item_rects["plot"]
            assert after[1] < before[1]
            assert after[1] >= 0
            assert after[1] + after[3] <= size[1] - 30
            assert app.model.detail["spectra"][0]["intensity"] == [0., 1., 0.]
        finally:
            app.close()
