"""Tests for the NavigationPanelTool shared status bar, stepper and log routing."""
from __future__ import annotations

import logging
import time
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("qtpy")

from chisurf.gui.widgets.navigation import (
    NavigationPanelTool,
    _StatusTask,
    find_status_reporter,
)


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _panels():
    from qtpy import QtWidgets

    leaf = lambda p: QtWidgets.QLabel("body")  # noqa: E731
    return [
        {"name": "1. A", "role": "a", "factory": leaf},
        {"name": "2. B", "role": "b", "factory": leaf},
        {"name": "sep", "separator": True, "role": "sep"},
        {"name": "C", "role": "c", "factory": leaf},
    ]


def test_status_bar_exists_and_starts_idle(qapp):
    w = NavigationPanelTool(title="t", panels=_panels())
    assert w.statusBar() is not None
    assert w._status_message.text() == "Ready"
    assert w._status_progress.isHidden()


def test_stepper_skips_separators_and_bounds(qapp):
    w = NavigationPanelTool(title="t", panels=_panels())
    assert w.nav_list.currentRow() == 0
    assert w.goto_next_step() and w.nav_list.currentRow() == 1
    # 1 -> 3 skips the separator at row 2
    assert w.goto_next_step() and w.nav_list.currentRow() == 3
    assert not w.goto_next_step()  # already at the last panel
    assert not w._btn_next.isEnabled()
    assert w._btn_prev.isEnabled()
    assert w.goto_prev_step() and w.nav_list.currentRow() == 1


def test_find_status_reporter_from_panel_child(qapp):
    w = NavigationPanelTool(title="t", panels=_panels())
    child = w.stacked_widget.currentWidget()
    assert find_status_reporter(child) is w


def test_begin_task_drives_bar_and_close_keeps_last_message(qapp):
    w = NavigationPanelTool(title="t", panels=_panels())
    task = w.begin_task("Computing…", maximum=10, cancel=lambda: None)
    assert isinstance(task, _StatusTask)
    assert not w._status_progress.isHidden()
    assert not w._status_cancel.isHidden()
    task.label.setText("Phase 2")
    task.progress.setRange(0, 4)
    task.set_value(2)
    assert w._status_message.text() == "Phase 2"
    assert w._status_progress.value() == 2
    task.close()
    # Progress/Cancel hidden, but the last message stays on the bar.
    assert w._status_progress.isHidden()
    assert w._status_cancel.isHidden()
    assert w._status_message.text() == "Phase 2"


def test_cancel_button_fires_callback_and_flag(qapp):
    fired = []
    w = NavigationPanelTool(title="t", panels=_panels())
    task = w.begin_task("Working…", maximum=5, cancel=lambda: fired.append(True))
    w._on_status_cancel()
    assert fired == [True]
    assert task.wasCanceled() is True


def test_scoped_logger_routes_to_status_bar_and_detaches(qapp):
    name = "chisurf.test.navstatus"
    lg = logging.getLogger(name)
    n_before = len(lg.handlers)
    w = NavigationPanelTool(title="t", panels=_panels(), status_logger=name)
    assert len(lg.handlers) == n_before + 1
    lg.info("hello from logging")
    qapp.processEvents()
    assert w._status_message.text() == "hello from logging"
    w.close()
    assert len(lg.handlers) == n_before  # handler removed on close


def test_next_processes_current_step_then_advances(qapp):
    """The Next button runs the current panel's canonical Run, then advances."""
    from qtpy import QtWidgets

    from chisurf.gui.widgets.tool_buttons import action_button

    fired = []

    def factory(parent):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.addWidget(action_button("run", on_click=lambda: fired.append(1)))
        return page

    panels = [
        {"name": "1", "role": "a", "factory": factory},
        {"name": "2", "role": "b", "factory": factory},
    ]
    w = NavigationPanelTool(title="t", panels=panels)
    assert w.nav_list.currentRow() == 0
    w._on_next_clicked()  # process (click Run) + advance
    assert fired == [1]                      # all-loaded processing was triggered
    assert w.nav_list.currentRow() == 1      # and we advanced


def test_process_current_step_without_run_button_is_noop(qapp):
    from qtpy import QtWidgets

    w = NavigationPanelTool(
        title="t",
        panels=[{"name": "x", "role": "x", "factory": lambda p: QtWidgets.QLabel("no run")}],
    )
    assert w.process_current_step() is False  # nothing to run, no crash


def test_logged_line_survives_active_task(qapp):
    """A message logged during a task updates the caption; close keeps it."""
    name = "chisurf.test.navstatus2"
    lg = logging.getLogger(name)
    w = NavigationPanelTool(title="t", panels=_panels(), status_logger=name)
    task = w.begin_task("Reading…", maximum=0)
    assert not w._status_progress.isHidden()
    lg.info("Done – 42 items")  # logged while the task is active
    qapp.processEvents()
    assert w._status_message.text() == "Done – 42 items"
    assert not w._status_progress.isHidden()  # bar untouched by the logged line
    task.close()
    assert w._status_message.text() == "Done – 42 items"
    w.close()


def test_status_updates_never_re_enter_the_event_loop(qapp, monkeypatch):
    """A status write must not pump while a pump is already running.

    Every writer here can be reached *from* a pump: a worker thread's log record
    arrives as a queued signal that the previous update's ``processEvents``
    delivers. Unguarded, each line pushed another Python-slot frame onto the C
    stack — the reported crash showed five nested
    ``PyQtSlotProxy::qt_metacall`` → Python → ``notifyInternal2`` levels before
    ``QCoreApplication::postEvent`` died with SIGBUS.
    """
    from qtpy import QtCore

    name = "chisurf.test.navstatus_reentrancy"
    lg = logging.getLogger(name)
    w = NavigationPanelTool(title="t", panels=_panels(), status_logger=name)

    depth = 0
    max_depth = 0

    def _fake_process_events(*_args):
        # Stand in for the real loop: while it runs, more status traffic
        # arrives — exactly what a logging worker thread and a progress loop do.
        nonlocal depth, max_depth
        depth += 1
        max_depth = max(max_depth, depth)
        try:
            if depth < 6:
                lg.info(f"nested line {depth}")
                w.report_progress(depth, 10, f"step {depth}")
        finally:
            depth -= 1

    monkeypatch.setattr(
        QtCore.QCoreApplication, "processEvents", _fake_process_events
    )
    lg.info("first line")

    assert max_depth == 1, f"status updates nested {max_depth} deep"
    w.close()


def test_log_driven_status_pump_excludes_user_input(qapp, monkeypatch):
    """A logged caption update must not deliver clicks into a running operation.

    A click delivered mid-analysis switches panel or closes the window, deleting
    the widgets the operation is still writing to. Task progress keeps input —
    its Cancel button has to stay clickable — but a passive caption repaint does
    not need it.
    """
    from qtpy import QtCore

    name = "chisurf.test.navstatus_input"
    lg = logging.getLogger(name)
    seen = []
    monkeypatch.setattr(
        QtCore.QCoreApplication, "processEvents", lambda *a: seen.append(a)
    )

    w = NavigationPanelTool(title="t", panels=_panels(), status_logger=name)

    lg.info("working")
    assert seen, "the status bar no longer repaints mid-operation"
    assert all(
        args and args[0] == QtCore.QEventLoop.ExcludeUserInputEvents for args in seen
    ), seen

    seen.clear()
    w.report_progress(1, 10, "step")
    assert seen == [()], f"task progress must stay clickable (Cancel): {seen}"
    w.close()


def test_next_advances_only_when_the_step_has_finished(qapp):
    """Next arms the advance; the shell performs it when the run ends.

    Advancing mid-run left the finished analysis plotting into a panel the shell
    had already switched away from, while the next panel was being constructed —
    a reproducible SIGSEGV inside ``QCoreApplication::postEvent``. The click must
    not block the GUI either: it returns immediately, and the step changes only
    once the work is done.
    """
    from qtpy import QtWidgets

    from chisurf.gui.task import run_in_background

    order: list[str] = []

    class _Step(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.button = QtWidgets.QToolButton(self)
            self.button.setObjectName("toolAction_run")
            self.button.clicked.connect(self._run)

        def _run(self):
            def work(task):
                time.sleep(0.05)  # still running when _on_next_clicked returns
                order.append("work")
                return "done"

            run_in_background(self, "Working", work,
                              on_result=lambda v: order.append("result"))

    step = _Step()
    w = NavigationPanelTool(
        title="t",
        panels=[
            {"name": "one", "role": "one", "factory": lambda p: step},
            {"name": "two", "role": "two", "factory": lambda p: QtWidgets.QLabel("2")},
        ],
    )
    w.nav_list.setCurrentRow(0)
    qapp.processEvents()
    w.nav_list.currentRowChanged.connect(lambda *_: order.append("advanced"))

    w._on_next_clicked()
    assert "advanced" not in order, "the shell advanced while the step was running"
    assert not w.nav_list.isEnabled(), "step changes must be blocked while working"

    deadline = time.monotonic() + 5.0
    while "advanced" not in order and time.monotonic() < deadline:
        qapp.processEvents()

    assert order.index("result") < order.index("advanced"), order
    assert w.nav_list.isEnabled(), "the selector must unlock when the work ends"
    assert w.nav_list.currentRow() == 1
    w.close()


def test_a_second_next_click_while_working_is_ignored(qapp):
    """The button is inert during the run — no double-advance, no second run."""
    from qtpy import QtWidgets

    from chisurf.gui.task import run_in_background

    runs: list[int] = []

    class _Step(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.button = QtWidgets.QToolButton(self)
            self.button.setObjectName("toolAction_run")
            self.button.clicked.connect(self._run)

        def _run(self):
            runs.append(1)

            def work(task):
                time.sleep(0.05)
                return None

            run_in_background(self, "Working", work)

    step = _Step()
    w = NavigationPanelTool(
        title="t",
        panels=[
            {"name": "one", "role": "one", "factory": lambda p: step},
            {"name": "two", "role": "two", "factory": lambda p: QtWidgets.QLabel("2")},
        ],
    )
    w.nav_list.setCurrentRow(0)
    qapp.processEvents()

    w._on_next_clicked()
    w._on_next_clicked()          # ignored: the first run is still going
    assert runs == [1]

    deadline = time.monotonic() + 5.0
    while w.nav_list.currentRow() != 1 and time.monotonic() < deadline:
        qapp.processEvents()
    assert w.nav_list.currentRow() == 1
    assert runs == [1], "the ignored click must not have started a second run"
    w.close()


def test_next_clicked_while_already_working_still_advances(qapp):
    """A click during a run means "go on when this finishes", not nothing.

    Panels re-compute on their own when a setting or the folder changes, so a
    quick Next lands while the step is already busy. Dropping the click there
    made the button look dead; it now arms the same pending advance without
    starting a second run on top of the first.
    """
    from qtpy import QtWidgets

    from chisurf.gui.task import run_in_background

    runs: list[int] = []

    class _Step(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.button = QtWidgets.QToolButton(self)
            self.button.setObjectName("toolAction_run")
            self.button.clicked.connect(self.start)

        def start(self):
            runs.append(1)

            def work(task):
                time.sleep(0.05)
                return None

            run_in_background(self, "Working", work)

    step = _Step()
    w = NavigationPanelTool(
        title="t",
        panels=[
            {"name": "one", "role": "one", "factory": lambda p: step},
            {"name": "two", "role": "two", "factory": lambda p: QtWidgets.QLabel("2")},
        ],
    )
    w.nav_list.setCurrentRow(0)
    qapp.processEvents()

    step.start()                 # the panel starts its own recompute
    qapp.processEvents()
    assert w._step_is_busy()

    w._on_next_clicked()         # clicked while that run is in flight
    assert runs == [1], "a second run must not be started on top of the first"

    deadline = time.monotonic() + 5.0
    while w.nav_list.currentRow() != 1 and time.monotonic() < deadline:
        qapp.processEvents()
    assert w.nav_list.currentRow() == 1, "the armed advance never fired"
    w.close()


def test_the_step_selector_refuses_to_switch_while_working(qapp):
    """Switching step mid-run is the crash; a programmatic switch is refused too.

    Disabling the widgets is not enough — the stepper and workflow handoffs call
    ``setCurrentRow`` directly, and that path reached the crash just as well.
    """
    from qtpy import QtWidgets

    from chisurf.gui.task import run_in_background

    class _Step(QtWidgets.QWidget):
        def start(self):
            def work(task):
                time.sleep(0.05)
                return None

            run_in_background(self, "Working", work)

    step = _Step()
    w = NavigationPanelTool(
        title="t",
        panels=[
            {"name": "one", "role": "one", "factory": lambda p: step},
            {"name": "two", "role": "two", "factory": lambda p: QtWidgets.QLabel("2")},
        ],
    )
    w.nav_list.setCurrentRow(0)
    qapp.processEvents()

    step.start()
    qapp.processEvents()

    w.nav_list.setCurrentRow(1)          # what a click (or a handoff) does
    qapp.processEvents()
    assert w.nav_list.currentRow() == 0, "the shell switched step mid-run"
    assert w.goto_next_step() is False

    deadline = time.monotonic() + 5.0
    while w._step_is_busy() and time.monotonic() < deadline:
        qapp.processEvents()
    qapp.processEvents()
    assert w.goto_next_step() is True, "the selector must unlock when work ends"
    w.close()
