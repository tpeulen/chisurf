"""The console runs a cell off the frame: the window keeps drawing, output streams, Ctrl+C stops it.

A cell runs on the console's worker thread (:mod:`chisurf.emtk.console`). These tests drive the
emtk shell with keys and frames as a user would, and measure what the user sees: frames drawn while
``time.sleep(2)`` runs, ``print`` lines arriving one by one, ``while True: pass`` stopped by Ctrl+C
within a second, a second cell queued behind the first, the *Interrupt* button, and a cell that
creates a fit through ``api`` and calls the window through ``gui`` (marshalled to the frame).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest
from emtk.events import CONTROL_MODIFIER
from emtk.keys import KEY_RETURN
from emtk.testing import Driver

from chisurf.emtk.console import FrameProxy, unwrap
from chisurf.emtk.main_app import EmtkShellApp

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))


@pytest.fixture
def shell(tmp_path, monkeypatch):
    import chisurf
    from chisurf.core.project import recent

    monkeypatch.setattr(recent, "recent_projects_file", lambda: tmp_path / "recent_projects.json")
    monkeypatch.setattr(chisurf, "working_path", tmp_path, raising=False)
    monkeypatch.chdir(tmp_path)
    app = EmtkShellApp(
        {}, loader=lambda plugin_id: None, console_history=False, console_session_file=False
    )
    # No frame budget: every cell goes on running behind the frames, as a long one does.
    app.console.frame_budget = 0.0
    yield app
    app.close()


@pytest.fixture
def driver(shell):
    drv = Driver(shell, size=(1400, 900))
    drv.frame(3)
    drv.click(shell.console.item_rects["console.input"])
    return drv


def _submit(driver: Driver, text: str) -> None:
    driver.app.console.set_input("")
    driver.type(text)
    driver.press(KEY_RETURN)


def _frames_until(driver: Driver, predicate, timeout: float = 10.0) -> list[float]:
    """Draw frames until *predicate*; each frame's duration (seconds)."""
    durations = []
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, "timed out"
        t0 = time.monotonic()
        driver.frame(1)
        durations.append(time.monotonic() - t0)
        time.sleep(0.01)
    driver.frame(1)
    return durations


def test_a_sleeping_cell_leaves_the_window_drawing(driver, shell):
    console = shell.console
    console.set_input("")
    driver.type("import time; time.sleep(2)")
    # Only the Enter is timed: typing the cell is frames, and a loaded machine draws them slowly.
    started = time.monotonic()
    driver.press(KEY_RETURN)
    assert time.monotonic() - started < 1.0, "Enter returned while the cell sleeps"
    assert console.busy
    # The worker thread takes the cell when the scheduler runs it, not by the time Enter returns.
    _frames_until(driver, lambda: console.running is not None, timeout=1.0)
    painter = driver.frame(1)
    assert any("Running" in s for s in painter.strings), "the running state is drawn"
    assert "Interrupt" in painter.strings
    durations = _frames_until(driver, lambda: not console.busy)
    assert len(durations) >= 10, f"only {len(durations)} frames drawn in 2 s"
    assert max(durations) < 0.5, f"a frame took {max(durations):.2f} s"
    painter = driver.frame(1)
    assert not any("Running" in s for s in painter.strings)


def test_printed_lines_arrive_while_the_cell_runs(driver, shell):
    console = shell.console
    _submit(driver, "[(print('tick', i), __import__('time').sleep(0.2)) for i in range(5)];")
    seen = []
    ticks = lambda: sum(line.startswith("tick ") for line, _kind in console.transcript.lines)  # noqa: E731
    _frames_until(driver, lambda: seen.append(ticks()) or not console.busy)
    final = ticks()
    assert final == 5, console.transcript.text()[-200:]
    partial = {n for n in seen if 0 < n < 5}
    assert len(partial) >= 2, f"output arrived all at once: {seen}"


def test_ctrl_c_interrupts_a_busy_loop_and_the_console_stays_usable(driver, shell):
    console = shell.console
    _submit(driver, "while True: pass")
    driver.frame(2)
    assert console.busy
    t0 = time.monotonic()
    driver.press(ord("c"), CONTROL_MODIFIER)
    _frames_until(driver, lambda: not console.busy, timeout=5.0)
    assert time.monotonic() - t0 < 1.0
    assert "KeyboardInterrupt" in console.transcript.text()
    _submit(driver, "40 + 2")
    _frames_until(driver, lambda: not console.busy)
    assert "Out[2]: 42" in console.transcript.text()


def test_a_second_cell_queues_behind_the_first(driver, shell):
    console = shell.console
    # The first cell holds until the test lets it go: a fixed sleep raced the typing of the second
    # cell, which on a loaded machine outlasted it (the first had finished, nothing was queued).
    gate = threading.Event()
    console.engine.user_ns["gate"] = gate
    _submit(driver, "gate.wait(30); order = ['first']")
    _submit(driver, "order.append('second')")
    _frames_until(driver, lambda: console.running is not None, timeout=5.0)
    assert console.queued == 1
    painter = driver.frame(1)
    assert any("1 queued" in s for s in painter.strings)
    gate.set()
    _frames_until(driver, lambda: not console.busy)
    assert console.engine.user_ns["order"] == ["first", "second"]


def test_the_interrupt_button_stops_the_cell_and_drops_the_queue(driver, shell):
    console = shell.console
    _submit(driver, "while True: pass")
    _submit(driver, "never_ran = 1")
    driver.frame(2)
    driver.click(console.item_rects["console.interrupt"])
    _frames_until(driver, lambda: not console.busy, timeout=5.0)
    text = console.transcript.text()
    assert "KeyboardInterrupt" in text and "1 queued cell(s) dropped" in text
    assert "never_ran" not in console.engine.user_ns


def test_gui_calls_from_a_cell_run_on_the_frame_thread(driver, shell):
    console = shell.console
    frame_thread = threading.get_ident()
    shell.probe_thread = lambda: threading.get_ident()
    assert isinstance(console.engine.user_ns["gui"], FrameProxy)
    assert unwrap(console.engine.user_ns["gui"]) is shell
    _submit(
        driver,
        "import threading; cell_thread = threading.get_ident(); "
        "probe = gui.probe_thread(); gui.docks.focus('console')",
    )
    _frames_until(driver, lambda: not console.busy)
    ns = console.engine.user_ns
    assert ns["cell_thread"] != frame_thread, "the cell ran on the worker"
    assert ns["probe"] == frame_thread, "gui's method ran on the frame"


def test_a_cell_creates_a_fit_through_the_api(tmp_path, monkeypatch):
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState
    from test.native_emtk.test_emtk_shell_session import _demo_fit, _idle, _settle

    monkeypatch.chdir(tmp_path)
    session = start_session(state=SessionState())
    app = EmtkShellApp(
        {}, loader=lambda plugin_id: None, console_history=False, console_session_file=False
    )
    app.data.adopt(session)
    try:
        driver = Driver(app, size=(1500, 950))
        driver.frame(2)
        _demo_fit(driver, app)
        driver.frame(2)
        console = app.console
        console.frame_budget = 0.0
        before = len(session.api.list_fits())
        console.execute(
            "idx = [i for i, d in enumerate(api.list_datasets()) if d.get('name') == 'fcs_demo']\n"
            "created = api.add_fit(idx[:1], model_name='FCS (general: diffusion + bunching/anticorr)')\n"
            "n_fits = len(api.list_fits())\n"
            "gui.request_frame()",
            wait=False,
        )
        _settle(driver, lambda: not console.busy, "the cell")
        ns = console.engine.user_ns
        assert "Traceback" not in console.transcript.text(), console.transcript.text().split(
            "Traceback"
        )[-1][-1500:]
        assert ns["n_fits"] == before + 1
        _settle(
            driver,
            lambda: _idle(app) and len(app.data.session.api.list_fits()) == before + 1,
            "the new fit in the shell",
        )
    finally:
        app.close()
        session.close()


def test_the_running_console_screenshot(driver, shell):
    """The Console dock while a cell runs and one waits, written for inspection."""
    console = shell.console
    _submit(driver, "for k in range(3): print('step', k)")
    _frames_until(driver, lambda: not console.busy)
    _submit(driver, "while True: pass")
    _submit(driver, "after = 1")
    driver.type("print('typed while it runs')")
    driver.frame(2)
    assert console.busy and console.queued == 1
    driver.screenshot(SHOTS / "emtk_console_running.png")
    assert console.busy, "the cell was still running when the screenshot was taken"
    console.interrupt()
    _frames_until(driver, lambda: not console.busy, timeout=5.0)
    assert console.input_text == "print('typed while it runs')"
