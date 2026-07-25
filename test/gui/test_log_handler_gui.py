"""Offscreen-Qt tests for the QTextEditLogger logging handler.

The handler feeds the status bar and log console. Two properties matter for a
GUI app whose data loads log from background threads:

* thread-safety — records logged off the GUI thread must reach the widget
  without direct cross-thread widget access (which triggers ``QBasicTimer``
  warnings / crashes), and
* the O(rows) log-console filter must be coalesced, not run once per record, so
  a burst of hundreds of records stays O(rows) instead of O(rows^2).
"""
from __future__ import annotations

import logging
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _drain(qapp, seconds=0.4):
    """Pump the event loop so queued records + the debounce timer flush."""
    end = time.time() + seconds
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.005)


def test_worker_thread_logging_is_delivered_and_filter_debounced(qapp):
    from qtpy import QtWidgets
    from chisurf.gui import QTextEditLogger

    class Owner(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.filter_calls = 0

        def update_log_filter(self):
            self.filter_calls += 1

    owner = Owner()
    edit = QtWidgets.QPlainTextEdit(owner)  # parent chain reaches update_log_filter
    handler = QTextEditLogger(edit, "append", level=logging.DEBUG)

    log = logging.getLogger("chisurf.test.qtel")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    log.addHandler(handler)
    try:
        n = 200
        # Log entirely from a non-GUI thread, like a background data load.
        t = threading.Thread(target=lambda: [log.info("msg %d", i) for i in range(n)])
        t.start()
        t.join()

        _drain(qapp)

        lines = [ln for ln in edit.toPlainText().splitlines() if ln.strip()]
        # Every record made it to the widget via the GUI-thread relay.
        assert len(lines) == n
        # The expensive filter ran a handful of times, not once per record.
        assert 1 <= owner.filter_calls <= 5
    finally:
        log.removeHandler(handler)


def test_status_mode_updates_widget(qapp):
    from qtpy import QtWidgets
    from chisurf.gui import QTextEditLogger

    label = QtWidgets.QLabel()
    handler = QTextEditLogger(label, "set", log_string="%(message)s", level=logging.INFO)

    log = logging.getLogger("chisurf.test.qtel.status")
    log.setLevel(logging.INFO)
    log.propagate = False
    log.addHandler(handler)
    try:
        log.info("hello status")
        _drain(qapp, 0.15)
        assert label.text() == "hello status"
    finally:
        log.removeHandler(handler)


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
