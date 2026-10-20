"""The file picked in the Browser reaches CLSM Draw and the Spot Finder through the hub, and both draw it.

One hand-off contract: the hub hands every step ``{"source": <photon file>, "hdf5": <imaging HDF5>}``
(``ImagingToolsApp.set_pipeline``) and every receiver reads those names. The tools are the real native apps,
driven with pointer presses on the hub at the rectangles the list and the file row were drawn in; each tool is
rendered with a :class:`~emtk.testing.PixelPainter` after the file arrived and saved as a PNG beside the test's
temporary folder (inspect it there when the layout is in question).
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import PixelPainter, save_png

from chisurf.emtk import job_gate
from chisurf.plugins.microscopy.imaging_emtk.testing import hermetic_env
from chisurf.plugins.microscopy.imaging_tools.gui.app import ImagingToolsApp
from chisurf.plugins.tttr.tttr_image_browser.test.conftest import two_detector_setup

from .test_emtk_imaging_tools_clicks import HubDriver
from .test_emtk_imaging_tools_parity import BIG, Client

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
#: 512 x 512 px, two cells: the Leica SP8 scan the Browser's own tests use.
SP8 = REPO / "test/data/clsm/Leica_SP8.ptu"


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


def wait(drv, busy, seconds=180.0):
    end = time.monotonic() + seconds
    drv.draw(2)
    while busy() and time.monotonic() < end:
        time.sleep(0.02)
        drv.draw(1)
    assert not busy(), "a worker did not finish"
    drv.draw(3)


def snap(app, path):
    painter = None
    for _ in range(3):
        painter = PixelPainter(*BIG)
        app.draw(painter, 0, 0, *BIG)
    save_png(path, painter.width, painter.height, painter.px)
    return path


def test_the_browsers_file_opens_in_clsm_draw_and_the_spot_finder(tmp_path):
    scan = tmp_path / "scan"
    scan.mkdir()
    shutil.copy2(SP8, scan / SP8.name)
    source = str(scan / SP8.name)

    app = ImagingToolsApp(client=Client())
    drv = HubDriver(app, BIG)
    try:
        drv.draw(3)
        app.set_setup(two_detector_setup())  # PTU reading, so the Browser lists the scan
        browser = app.children["browser"]

        def browser_busy():
            return bool(
                browser.job.busy
                or browser.load_job.busy
                or browser._queue
                or browser.model.wanted_image()
            )

        assert drv.drop(str(scan))  # the host drops the folder on the hub; the Browser opens it
        wait(drv, browser_busy)
        drv.click_text(SP8.name)  # the file row
        wait(drv, browser_busy)
        assert browser.model.current_file == source
        assert app._pipeline["source"] == source

        # CLSM Draw: the source is loaded on arrival, a CLSM image and its representation draw the cells.
        drv.click(drv.rect("entry:clsm_draw"))
        clsm = app.children["clsm_draw"]
        wait(drv, lambda: clsm.job.busy)
        assert clsm.model.filename == source and clsm.model.tttr_data is not None
        snap(app, tmp_path / "clsm_draw_arrived.png")
        drv.click_text("Build CLSM")
        wait(drv, lambda: clsm.job.busy)
        drv.click_text("Add representation")
        wait(drv, lambda: clsm.job.busy)
        image = np.asarray(clsm.model.current_image)
        assert image.shape == (512, 512) and image.sum() > 0
        snap(app, tmp_path / "clsm_draw_image.png")

        # Spot Finder: the source is its file; a Preview detects on it and draws its intensity.
        drv.click(drv.rect("entry:spot_finder"))
        finder = app.children["spot_finder"]
        assert finder.model.files == [source]
        snap(app, tmp_path / "spot_finder_arrived.png")
        drv.click_text("Preview")
        wait(drv, lambda: finder.job.busy)
        shown = finder.model.detection_image()
        assert shown is not None and shown.shape == (512, 512) and shown.sum() > 0
        assert finder.model.results and "Preview:" in finder.model.status_text
        snap(app, tmp_path / "spot_finder_preview.png")
    finally:
        app.close()


def test_a_source_that_arrives_while_clsm_draw_loads_is_opened_once_the_load_ended(tmp_path):
    """The hub's context is kept while a job runs and applied when it ends, not dropped."""
    first, second = tmp_path / "a.ptu", tmp_path / "b.ptu"
    shutil.copy2(SP8, first)
    shutil.copy2(SP8, second)
    app = ImagingToolsApp(client=Client())
    drv = HubDriver(app, BIG)
    try:
        drv.draw(3)
        app.set_pipeline(source=str(first))
        job_gate.arm()  # the first load is held open until the second source has arrived
        drv.click(drv.rect("entry:clsm_draw"))
        clsm = app.children["clsm_draw"]
        assert clsm.job.busy
        app.set_pipeline(source=str(second))  # arrives mid-load
        job_gate.release()
        wait(drv, lambda: clsm.job.busy or clsm._pending_pipeline is not None)
        assert clsm.model.filename == str(second)
    finally:
        job_gate.disarm()
        app.close()
