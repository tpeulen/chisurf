"""Save Results pressed with the pointer: the two PNGs of the Qt tool are written again."""

import time
from pathlib import Path

import pytest
from emtk.testing import Driver, RecordingPainter

HERE = Path(__file__).parent
DATA = HERE.parents[3] / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"

pytestmark = pytest.mark.skipif(not DATA.exists(), reason="PCH test data missing")

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _wait(drv, seconds=60.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        drv.draw(1)
        if not drv.app.job.busy:
            return
        time.sleep(0.02)
    raise AssertionError("the job did not finish")


def test_save_results_button_writes_both_pictures(tmp_path):
    from chisurf.plugins.pch.gui.app import make_app

    app = make_app()
    drv = Driver(app, (1200, 800))
    drv.draw(3)
    app.on_paths_dropped([str(DATA)])
    _wait(drv)
    app.model.channels, app.model.bin_time_us = "0,8", 50.0
    drv.click("compute")
    _wait(drv)
    drv.click("fit")
    _wait(drv)
    assert app.model.fit_result is not None

    drv.click("save")
    drv.draw(3)
    assert app.dialog is not None and app.dialog_kind == "save"
    app.dialog.directory = str(tmp_path)
    app.dialog.filename = "run"
    drv.click("Save")
    drv.draw(3)

    assert app.model.status_line().startswith("Saved ") and not app.model.error_text
    for suffix in (".npz", ".csv", ".txt", "_window.png", "_histogram.png"):
        assert (tmp_path / f"run{suffix}").stat().st_size > 0, suffix
    for name in ("run_window.png", "run_histogram.png"):
        assert (tmp_path / name).read_bytes().startswith(PNG_MAGIC)
    window = (tmp_path / "run_window.png").stat().st_size
    assert window > (tmp_path / "run_histogram.png").stat().st_size  # trace + histogram
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
