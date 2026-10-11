"""TTTR tours wait for real controls while the existing file operations retain events."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import tttrlib
from emtk import i18n
from emtk.testing import Driver


@pytest.fixture
def source(tmp_path, monkeypatch):
    """Use the existing deterministic TTTR fixture with isolated preferences."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setattr(i18n, "_locale", "en")
    from chisurf.plugins.microscopy.imaging_emtk.pixel_testing import flim_ptu

    return Path(flim_ptu(tmp_path / "source.ptu"))


def settle(job, driver):
    """Wait for the real background operation, then publish it on the UI frame."""
    if job.future is not None:
        job.future.result(timeout=30)
    job.poll()
    driver.draw(2)


def choose(owner, path):
    """Confirm a path through the actual controller's file-dialog callback."""
    assert owner.dialog is not None
    callback = owner.dialog_callback
    owner.dialog = None
    callback([str(path)])


def waiting(driver, tour):
    """The visible Next control cannot skip the currently awaited action."""
    before = tour.step_idx
    driver.draw(2)
    assert tour.awaiting
    driver.click("Next ►" if before < len(tour.steps) - 1 else "Finish ✓")
    assert tour.active and tour.step_idx == before and tour.awaiting


def next_step(driver, tour):
    """Advance with the actual tour button after an acknowledged action."""
    assert not tour.awaiting
    driver.click("Next ►" if tour.step_idx < len(tour.steps) - 1 else "Finish ✓")


def assert_events(source, outputs):
    """Compare event arrays independently of the editor and splitter models."""
    original = tttrlib.TTTR(str(source))
    pieces = [tttrlib.TTTR(str(path)) for path in outputs]
    for attr in ("macro_times", "micro_times", "routing_channels", "event_types"):
        np.testing.assert_array_equal(
            np.concatenate([np.asarray(getattr(part, attr)) for part in pieces]),
            np.asarray(getattr(original, attr)),
        )


def test_header_tour_waits_for_open_add_save_and_preserves_photons(source, tmp_path):
    """Real clicks acknowledge the tour; an actual saved PTU retains all source events."""
    from chisurf.plugins.tttr.tttr_header_edit.gui.native import create_app

    app = create_app()
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    try:
        gui = app.header_gui
        driver = Driver(app, (1100, 800))
        driver.draw(2)
        driver.click(gui.item_rects["guide"])
        assert app.dialog is None and not app.job.running
        waiting(driver, gui.tour)
        driver.click(gui.item_rects["open"])
        assert not gui.tour.awaiting
        choose(app, source)
        settle(app.job, driver)
        assert app.model.opened_path == str(source)
        next_step(driver, gui.tour)
        waiting(driver, gui.tour)
        count = len(app.model.tags)
        driver.click(gui.item_rects["add"])
        assert len(app.model.tags) == count + 1 and not gui.tour.awaiting
        next_step(driver, gui.tour)
        waiting(driver, gui.tour)
        driver.click(gui.item_rects["save"])
        assert not gui.tour.awaiting
        target = tmp_path / "edited.ptu"
        choose(app, target)
        settle(app.job, driver)
        assert target.is_file()
        assert_events(source, [target])
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
        next_step(driver, gui.tour)
        assert not gui.tour.active
    finally:
        app.close()


def test_splitter_tour_waits_for_both_pickers_and_run_without_changing_events(source, tmp_path):
    """The tour runs no work itself; actual Run writes unchanged event chunks."""
    from chisurf.plugins.tttr.tttr_splitter.gui.controller import create_app

    app = create_app()
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    try:
        tool, gui = app.tool, app.splitter_gui
        driver = Driver(app, (1100, 800))
        driver.draw(2)
        driver.click(gui.item_rects["guide"])
        assert tool.dialog is None and not tool.job.running
        waiting(driver, gui.tour)
        driver.click(gui.item_rects["input"])
        assert not gui.tour.awaiting
        choose(tool, source)
        settle(tool.job, driver)
        assert tool._model.input_file == str(source)
        next_step(driver, gui.tour)
        waiting(driver, gui.tour)
        driver.click(gui.item_rects["output"])
        assert not gui.tour.awaiting
        destination = tmp_path / "output"
        destination.mkdir()
        choose(tool, destination)
        tool._model.photons_per_file_k = 1
        tool._model.reset_macro_times = False
        next_step(driver, gui.tour)
        driver.draw(2)
        assert (gui.tour.step_idx, gui.tour.awaiting) == (2, False), (
            gui.tour.step_idx,
            gui.tour.awaiting,
        )
        next_step(driver, gui.tour)
        driver.draw(2)
        assert gui.tour.step_idx == 3, gui.tour.step_idx
        waiting(driver, gui.tour)
        driver.click(gui.item_rects["run"])
        assert not gui.tour.awaiting
        settle(tool.job, driver)
        assert tool.run_progress == 100, tool.message
        outputs = sorted(destination.rglob("*.ptu"))
        assert len(outputs) > 1
        assert_events(source, outputs)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
        next_step(driver, gui.tour)
        assert not gui.tour.active
    finally:
        app.close()
