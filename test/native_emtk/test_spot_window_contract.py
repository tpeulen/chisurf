"""SpotFindergeometry preservesrealphotoninput, detection and savedlayout."""

from __future__ import annotations

import copy

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.microscopy.spot_finder.gui.app import make_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    """BuildrealSpotFinder inisolatedsettings/outputstorage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    instance = make_app()
    yield instance
    attach_native_state("spot_finder", instance).close()


def test_primary_default_is_set_before_native_state_binding(app):
    """Thetruefactoryreadstheprimarywindowbeforeslicingformsections."""
    assert app.window_size == (1100, 720)
    attach_native_state("spot_finder", app)
    assert app.window_size == (1100, 720)
    Driver(app, app.window_size).draw(3)


def test_saved_custom_geometry_and_layout_override_declared_default(app):
    """Actualclose/reopen preservesuserdimensions andcustomdocktree."""
    attach_native_state("spot_finder", app)
    Driver(app, (1100, 720)).draw(3)
    app.docks.undock("controls", (40, 50, 440, 400))
    saved = app.docks.state()
    app.window_resized(1390, 910)
    app.close()
    other = attach_native_state("spot_finder", make_app())
    try:
        assert other.window_size == (1390, 910)
        assert other.docks.state()["layout"] == saved["layout"]
        assert other.docks.state()["windows"] == saved["windows"]
        Driver(other, other.window_size).draw(3)
    finally:
        attach_native_state("spot_finder-probe", other).close()


def test_raw_primary_window_reaches_sharedreader(app, monkeypatch):
    """Theunstrippedprimaryspecdrivesconstructionthroughtheexistingreader."""
    import chisurf.plugins.microscopy.spot_finder.gui.app as module

    original = module.window_size
    seen = []

    def declared(spec, default):
        """Observeactualprimarygeometry andexercisedifferentdeclaredsize."""
        seen.append((spec["window"], default))
        return original({**spec, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(module, "window_size", declared)
    other = make_app()
    try:
        assert other.window_size == (1234, 789)
        assert seen == [({"width": 1100, "height": 720}, (1100, 720))]
    finally:
        attach_native_state("spot_finder-probe", other).close()


def test_real_example_await_preview_detect_and_resize_keep_detection_science(app):
    """Realbuttonsproducefourregions andresizingcannotchangedetectionresults."""
    driver = Driver(app, (1100, 720))
    driver.draw(3)
    app.tour.start(1)
    driver.draw(3)
    assert app.tour.awaiting and not app.model.files
    driver.click("load_example")
    if app.job.thread:
        app.job.thread.join(60)
    app.job.poll()
    assert not app.job.error and not app.tour.awaiting
    assert app.model.files and not app.model.results
    app.tour.stop()
    driver.draw(3)
    driver.click("Preview")
    app.job.thread.join(60)
    app.job.poll()
    assert not app.job.error and app.model.results[0].n_regions == 4
    driver.draw(3)
    driver.click("Detect")
    app.job.thread.join(60)
    app.job.poll()
    assert not app.job.error
    from chisurf.core.fio.staging import open_tttr
    from chisurf.core.fluorescence.imaging.simulate import clsm_from_scan

    stream = open_tttr(app.model.files[0])
    reference = clsm_from_scan(stream, 48, channels=[0, 1])
    wide = np.asarray(reference.get_intensity_u32())
    assert np.asarray(reference.intensity).dtype == np.uint32
    np.testing.assert_array_equal(reference.intensity, wide)
    assert int(wide.sum()) == 390384
    indices = np.concatenate([
        np.asarray(reference[0][row][col].get_tttr_indices(), dtype=np.int64)
        for row in range(48) for col in range(48)
    ])
    assert len(indices) == len(np.unique(indices)) == int(wide.sum())
    assert np.all((indices >= 0) & (indices < len(stream)))
    np.testing.assert_array_equal(app.model.detection_image(), wide.sum(axis=0))
    labels = np.asarray(app.model.results[0].labels).copy()
    intensity = np.asarray(app.model.detection_image()).copy()
    measurements = copy.deepcopy(list(app.measure_rows))
    assert labels.shape == (48, 48)
    assert app.model.results[0].n_regions == 4
    driver.draw(3, size=(1390, 910))
    np.testing.assert_array_equal(labels, app.model.results[0].labels)
    np.testing.assert_array_equal(intensity, app.model.detection_image())
    assert list(app.measure_rows) == measurements
