"""Calibrate pressed while a read is running is not dropped, and the Report says its text once.

The window reads the dye catalogue and the optical priors on its own when it opens, and a dropped
burst table is read off the GUI thread; a Calibrate press in that time returned without a word.
"""

import threading

import numpy as np
from emtk.testing import RecordingPainter

from chisurf.plugins.burst.accurate_fret.gui.app import create_app

from .test_accurate_fret_plugin import TAU_D0, _simulate


def _table(path):
    dd, da, aa, tau = _simulate(n=100)
    np.savetxt(
        path,
        np.column_stack([dd, da, aa, tau]),
        delimiter=",",
        comments="",
        header="Green Count Rate (KHz),Red Count Rate (KHz),S delayed yellow (kHz),Tau (green)",
    )
    return path


def test_calibrate_pressed_during_the_read_runs_after_it(tmp_path, monkeypatch):
    app = create_app()
    app.model.n_bootstrap = 0
    app.model.donor_lifetime = TAU_D0
    ctrl = app.controller
    try:
        # finish whatever the window started on its own
        while ctrl.running:
            ctrl._future.result(timeout=30)
            ctrl.poll()
        release = threading.Event()
        original = ctrl._execute

        def slow(action, snapshot, path):
            assert release.wait(30)
            return original(action, snapshot, path)

        monkeypatch.setattr(ctrl, "_execute", slow)
        ctrl.load(_table(tmp_path / "bursts.csv"))
        assert ctrl.running and ctrl._action == "load"
        ctrl.run()  # the press while the table is still being read
        assert "when the current read has finished" in ctrl.status
        release.set()
        ctrl._future.result(timeout=30)
        ctrl.poll()  # the read lands and the calibration starts
        assert ctrl.running and ctrl._action == "calibrate"
        ctrl._future.result(timeout=60)
        ctrl.poll()
        assert app.model.result is not None and ctrl.status == "Accurate FRET calibrated."
    finally:
        ctrl.close()


def test_the_report_tab_shows_the_message_once(tmp_path):
    app = create_app()
    ctrl = app.controller
    try:
        while ctrl.running:
            ctrl._future.result(timeout=30)
            ctrl.poll()
        ctrl.load(_table(tmp_path / "bursts.csv"))
        ctrl._future.result(timeout=30)
        ctrl.poll()
        text = app.model.results_text
        assert text.endswith("Press Calibrate.")
        from emtk.testing import Driver

        driver = Driver(app, (1200, 800))
        driver.frame(3)
        driver.click("Report")
        painter = driver.frame(3)
        assert sum(1 for s in painter.strings if "Press Calibrate." in s) == 1
    finally:
        ctrl.close()
