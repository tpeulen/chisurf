"""The compute dispatcher: UI answers the mouse, work lands one frame later.

The contract (`chimol.compute_dispatch`):

* a drag's ticks are **immediate** -- the calling thread only moves UI state
  and bumps the chrome revision; the worst tick measured well under a
  millisecond while contours ran;
* contour compute runs **off the UI thread** and applies at the frame's
  `poll`, warming the per-level isosurface memo so the apply is an upload;
* a new job for the same key **supersedes** a pending one -- thirty drag
  ticks queue at most one stale contour, not thirty;
* the status line narrates start and finish;
* where there is no worker (Pyodide), the same jobs run one-per-frame at
  `poll` -- after the UI has already answered.
"""

from __future__ import annotations

import time

import pytest

from chimol import compute_dispatch


@pytest.fixture(autouse=True)
def _seen(monkeypatch):
    """Every test on a quiet dispatcher, with the status line captured."""
    seen: list[str] = []
    monkeypatch.setattr(compute_dispatch, "set_status", seen.append)
    with compute_dispatch._lock:
        compute_dispatch._pending.clear()
        compute_dispatch._ready.clear()
    yield seen
    with compute_dispatch._lock:
        compute_dispatch._pending.clear()
        compute_dispatch._ready.clear()


def test_supersede_replaces_the_pending_job(monkeypatch):
    monkeypatch.setattr(compute_dispatch, "has_worker", False)  # deterministic
    ran = []
    compute_dispatch.dispatch("k", lambda: 1, ran.append)
    compute_dispatch.dispatch("k", lambda: 2, ran.append)
    assert compute_dispatch.pending() == 1, "two jobs queued for one key"
    compute_dispatch.poll()
    assert ran == [2], f"the newest job must win, ran {ran}"


def test_sync_mode_runs_one_job_per_frame(_seen, monkeypatch):
    monkeypatch.setattr(compute_dispatch, "has_worker", False)
    ran = []
    for value in range(3):
        compute_dispatch.dispatch("k", lambda v=value: v, ran.append)
    compute_dispatch.poll()
    assert ran == [2], "a frame runs the newest job, not the backlog"


def test_the_status_line_narrates(_seen, monkeypatch):
    monkeypatch.setattr(compute_dispatch, "has_worker", False)
    compute_dispatch.dispatch("contour:obj1", lambda: None, note="contouring x ...")
    assert _seen[-1] == "contouring x ..."
    compute_dispatch.poll()
    assert _seen[-1].startswith("contour done in "), _seen[-1]


def test_a_failed_job_reports_and_never_raises(_seen, monkeypatch):
    monkeypatch.setattr(compute_dispatch, "has_worker", False)

    def _boom():
        raise RuntimeError("nope")

    compute_dispatch.dispatch("k", _boom)
    compute_dispatch.poll()  # must not raise
    assert any("failed" in line for line in _seen)


def test_the_worker_lands_on_the_ui_thread_at_poll():
    if not compute_dispatch.has_worker:
        pytest.skip("no worker thread here")
    import threading

    thread_of_job: list[int] = []
    applied_on: list[int] = []

    def _job():
        thread_of_job.append(threading.get_ident())
        return 41

    compute_dispatch.dispatch("k", _job, lambda result: applied_on.append(
        (threading.get_ident(), result)
    ))
    deadline = time.time() + 2.0
    while not applied_on and time.time() < deadline:
        compute_dispatch.poll()
        time.sleep(0.01)
    compute_dispatch.poll()
    assert applied_on, "the job never landed"
    job_thread, _ = thread_of_job[0], applied_on[0]
    assert job_thread != threading.get_ident(), "the job ran on the UI thread"
    assert applied_on[0][0] == threading.get_ident(), (
        "the apply did not run on the UI thread"
    )
    assert applied_on[0][1] == 41


@pytest.fixture(scope="module")
def driven_window():
    """A window with one dye and the density panel open, driven headlessly."""
    pytest.importorskip("qtpy")
    from qtpy import QtWidgets

    from chimol.app.molview_main_window import MolViewPluginWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MolViewPluginWindow()
    win.resize(900, 700)
    win.show()
    for _ in range(4):
        app.processEvents()
    yield win
    win.close()


def test_the_drag_tick_is_immediate_and_the_contour_lands_later(driven_window):
    """The whole point: the marker answers the mouse with no compute behind it.

    Thirty drag ticks at mouse cadence; the worst single tick must stay
    cheaper than a frame, and the released contour must land through the
    dispatcher at the level the mouse ended on.
    """
    win = driven_window
    from chimol.cmd import cmd as shared

    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)

    import pathlib

    pdb = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    if not pdb.is_file():
        pytest.skip("missing 148l fixture")
    shared.do(f"load {pdb}")
    shared.do("add_dye resi 119 and name CB, Cy5")
    shared.do("density_panel on")

    viewer = win.viewer
    panel = getattr(viewer, "_density_controls", None)
    assert panel is not None, "the density panel did not open"
    gui = viewer._renderer._internal_gui
    rect = gui.window_body(gui.window("density"))

    class _Quiet:
        CHAR_W = 7.0

        def fill_rect(self, *a, **k): pass
        def stroke_rect(self, *a, **k): pass
        def text(self, *a, **k): pass
        def push_clip(self, *a, **k): pass
        def pop_clip(self, *a, **k): pass
        def text_width(self, s): return len(str(s)) * self.CHAR_W
        def line_height(self): return 16.0

    panel.draw(_Quiet(), rect)
    oid = panel._row_boxes[0][1]
    hist = panel._plot_boxes[0][0]
    low, high = panel.model.range_for(oid)

    panel.press(hist.x + (0.5 - low) / (high - low) * hist.w, hist.y + hist.h / 2, rect)
    worst = 0.0
    for step in range(30):
        started = time.perf_counter()
        panel.drag(hist.x + (0.5 + 0.008 * step) * hist.w, hist.y + hist.h / 2, rect)
        worst = max(worst, time.perf_counter() - started)
        time.sleep(0.008)
    panel.release()

    assert worst < 0.002, f"a drag tick cost {worst * 1000:.2f} ms -- compute leaked onto the mouse"
    assert errors == [], errors[:2]

    # The released contour lands through the frame's poll.
    deadline = time.time() + 2.0
    landed = None
    while time.time() < deadline:
        compute_dispatch.poll()
        landed = float(viewer.get_volume_levels(oid)[0]["level"])
        if abs(landed - 0.732) < 0.02:
            break
        time.sleep(0.02)
    assert landed is not None and abs(landed - 0.732) < 0.02, (
        f"the contour never landed at the released level (got {landed})"
    )
