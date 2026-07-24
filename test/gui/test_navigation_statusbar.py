"""Tests for the NavigationPanelTool shared status bar, stepper and log routing."""
from __future__ import annotations

import logging
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
