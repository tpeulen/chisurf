"""Calibration geometry keeps actualphotonhistograms andpublishedsnapshots intact."""

from __future__ import annotations

import copy
import time

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.microscopy.img_calibration.gui.app import make_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Use private settings and closeactualpickerresources."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    instance = make_app()
    yield instance
    instance.close()


def test_declared_primary_default_is_bound_before_controls_spec_is_stripped(app):
    """The rawprimarywindow survives throughhostinit, whileformskeepsections only."""
    assert app.window_size == (1100, 720)
    assert "window" not in app.spec
    attach_native_state("img_calibration", app)
    assert app.window_size == (1100, 720)
    Driver(app, app.window_size).draw(3)


def test_saved_custom_geometry_and_docks_override_primary_default(app):
    """Realclose/reopen restoresusergeometry and meaningfulfloatingpane state."""
    attach_native_state("img_calibration", app)
    Driver(app, (1100, 720)).draw(3)
    app.docks.undock("controls", (40, 50, 440, 400))
    saved = app.docks.state()
    app.window_resized(1390, 910)
    app.close()
    reopened = attach_native_state("img_calibration", make_app())
    try:
        assert reopened.window_size == (1390, 910)
        assert reopened.docks.state()["layout"] == saved["layout"]
        assert reopened.docks.state()["windows"] == saved["windows"]
        Driver(reopened, reopened.window_size).draw(3)
    finally:
        reopened.close()


def test_raw_primary_declaration_reaches_sharedreader(app, monkeypatch):
    """The appreadsthesharedspecbefore_controls_spec discardsitstop-levelgeometry."""
    import chisurf.plugins.microscopy.img_calibration.gui.app as module

    original = module.window_size
    seen = []

    def reader(spec, default):
        """Recordrawgeometry andexercise anotherdeclaredsize."""
        seen.append((spec["window"], default))
        return original({**spec, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(module, "window_size", reader)
    other = make_app()
    try:
        assert other.window_size == (1234, 789)
        assert "window" not in other.spec
        assert seen == [({"width": 1100, "height": 720}, (1100, 720))]
    finally:
        other.close()


def test_real_histograms_background_apply_and_resize_preserve_data(app, tmp_path):
    """Actualworker andApply retain measuredhistograms and deep calibration snapshots."""
    import tttrlib

    stream = tttrlib.TTTR()
    rng = np.random.default_rng(7)
    micro = rng.integers(0, 4096, 4000, dtype=np.uint16)
    routing = np.resize(np.array([0, 8], dtype=np.int8), len(micro))
    stream.append_events(
        np.arange(1, len(micro) + 1, dtype=np.uint64),
        micro,
        routing,
        np.zeros(len(micro), dtype=np.int8),
        False,
        0,
    )
    stream.header.set_macro_time_resolution(12.5e-9)
    stream.header.set_micro_time_resolution(12.5e-9 / 4096)
    sample = tmp_path / "calibration.spc"
    stream.write(str(sample))
    parsed = tttrlib.TTTR(str(sample))
    app.apply_setup_settings({"detectors": {"green": {"chs": [0, 8], "ch_p": [0], "ch_s": [8]}}})
    app.apply_pipeline_context({"source": str(sample)})
    app.add_irfs([str(sample)])
    driver = Driver(app, (1100, 720))
    deadline = time.monotonic() + 30
    while True:
        driver.draw(1)
        if not app.busy and not app.model.needs_histograms():
            break
        assert time.monotonic() < deadline
        time.sleep(0.01)
    app.model.set_conv_range(500, 3000)
    app.model.set_irf_range(550, 700)
    app.model.set_bg_range(0, 400)
    data = {
        key: value.copy() if isinstance(value, np.ndarray) else value
        for key, value in app.model.decay_data().items()
    }
    for channel, actual in ((0, app.model.sel_bg_vv), (8, app.model.sel_bg_vh)):
        bins = np.asarray(parsed.micro_times)[np.asarray(parsed.routing_channels) == channel]
        assert actual == np.bincount(bins, minlength=4096)[:400].mean()
    snapshots = []
    app.model.publish = snapshots.append
    driver.draw(3)
    driver.click("apply")
    assert len(snapshots) == 1
    snapshot = copy.deepcopy(snapshots[0])
    driver.draw(3, size=(1390, 910))
    for key, value in data.items():
        actual = app.model.decay_data()[key]
        if isinstance(value, np.ndarray):
            np.testing.assert_array_equal(value, actual)
        else:
            assert value == actual
    app.model.sel_irf_files = []
    assert snapshots[0] == snapshot
    assert snapshot["green"]["irf"] == [str(sample)]


@pytest.mark.parametrize("size", [(736, 552), (1100, 720)])
def test_empty_irf_note_is_visible_after_real_clear_action(app, tmp_path, size):
    """The actualinitialscreenclamp retains readablefallbacktext andreachablecontrols."""
    app.apply_setup_settings({"detectors": {"green": {"chs": [0, 8], "ch_p": [0], "ch_s": [8]}}})
    app.add_irfs([str(tmp_path / "reference.spc")])
    driver = Driver(app, size)
    driver.draw(3)
    driver.click("clear_irf")
    assert app.model.sel_irf_files == []
    index = next(
        i for i, text in enumerate(driver.painter.texts) if text[5] == "No IRF: using raw data"
    )
    metrics = driver.painter.text_metadata[index]
    assert metrics["visible_bounds"] == metrics["measured_bounds"]
    for key in ("open_source", "add_irf", "clear_irf", "apply"):
        x, y, width, height = driver.rect(key)
        assert width > 0 and height > 0
        assert 0 <= x <= x + width <= size[0]
        assert 0 <= y <= y + height <= size[1]
