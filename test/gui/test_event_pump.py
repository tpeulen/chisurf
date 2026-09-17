"""The shared UI pump: one guard for every mid-operation repaint.

A bare ``processEvents()`` inside a status update dispatches the queued signal
that calls the same update again; each round adds a Python-slot frame to the C
stack, and a deep enough chain crashed inside ``QCoreApplication::postEvent``
(SIGBUS) during a burst run.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("qtpy")

from qtpy import QtCore, QtWidgets  # noqa: E402

from chisurf.gui.event_pump import is_pumping, pump_ui  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_pump_runs_and_reports(qapp):
    assert pump_ui() is True
    assert is_pumping() is False


def test_pump_never_nests(qapp, monkeypatch):
    """A pump started from inside a pump is skipped, not stacked."""
    depth = 0
    max_depth = 0
    skipped = []

    def _fake_process_events(*_args):
        nonlocal depth, max_depth
        depth += 1
        max_depth = max(max_depth, depth)
        try:
            if depth < 5:  # re-entrant callers: queued slots doing their own repaint
                skipped.append(pump_ui())
        finally:
            depth -= 1

    monkeypatch.setattr(QtCore.QCoreApplication, "processEvents", _fake_process_events)
    try:
        assert pump_ui() is True
        assert max_depth == 1
        assert skipped == [False], "a nested pump must be skipped"
        assert is_pumping() is False, "the guard must be released"
    finally:
        monkeypatch.undo()


def test_guard_is_released_when_qt_raises(qapp, monkeypatch):
    def _boom(*_args):
        raise RuntimeError("event loop exploded")

    monkeypatch.setattr(QtCore.QCoreApplication, "processEvents", _boom)
    try:
        assert pump_ui() is False
        assert is_pumping() is False
    finally:
        # Restore before leaving: pytest-qt drains events during teardown, and a
        # raising processEvents would take the teardown down with it.
        monkeypatch.undo()


def test_input_can_be_excluded(qapp, monkeypatch):
    """Passive repaints must not deliver clicks into a running operation."""
    seen = []
    monkeypatch.setattr(QtCore.QCoreApplication, "processEvents", lambda *a: seen.append(a))

    try:
        pump_ui()
        pump_ui(allow_input=False)
        assert seen == [(), (QtCore.QEventLoop.ExcludeUserInputEvents,)]
    finally:
        monkeypatch.undo()
