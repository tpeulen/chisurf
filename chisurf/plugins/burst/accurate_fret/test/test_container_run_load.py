"""A burst run inside a .pto container is a valid table to load, although it is not a file on disk.

A burst search over a container keeps its bursts there and writes no .bur; the workflow hubs hand that run
(``m000.pto/sliding_window_All 0.1500#60``) on, and the controller used to answer "Burst table does not exist".
"""

from __future__ import annotations

from chisurf.plugins.burst.accurate_fret.gui.controller import AccurateFretController, _is_container_run


def test_a_container_run_is_loaded_and_a_missing_file_is_not(tmp_path):
    run = tmp_path / "m000.pto" / "sliding_window_All 0.1500#60"
    assert _is_container_run(run)
    assert not _is_container_run(tmp_path / "m000.pto"), "the container itself is not a run"
    assert not _is_container_run(tmp_path / "missing.bur")

    started = []
    controller = AccurateFretController.__new__(AccurateFretController)
    controller.running = False
    controller.status = ""
    controller._snapshot = lambda: None
    controller._start = lambda action, snapshot=None, path=None: started.append((action, path))
    controller.load(str(run))
    assert started == [("load", str(run))]
    controller.load(str(tmp_path / "missing.bur"))
    assert started == [("load", str(run))] and controller.status.startswith("Burst table does not exist")
