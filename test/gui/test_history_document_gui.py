"""Scientific history browser acknowledgement and thread-bound presentation."""

from pathlib import Path

import numpy as np
import pytest

import chisurf as cs
from chisurf.gui.widgets.history_browser import HistoryBrowserWidget
from test.history.test_history_scientific_owner import scientific_owner

ARTIFACTS = Path("/Users/tpeulen/.hermes/cache/scratch")


def test_browser_undo_waits_for_science_ack_and_displays_baseline(qtbot, tmp_path):
    """Actual undo/redo controls restore numeric science and show the real cursor."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    owner.fits[0].model.parameters_all_dict["a"].value = 7
    for fit in owner.fits:
        fit.model.update()
    history.record(
        "parameter.value",
        "Set duplicate-named linked coefficient to 7",
        {"new_value": 7},
        persist=False,
    )
    browser = HistoryBrowserWidget()
    qtbot.addWidget(browser)
    browser.set_history(history)
    browser.resize(950, 500)
    browser.show()
    assert browser.grab().save(str(ARTIFACTS / "chisurf-history-browser-before.png"))
    assert browser.can_undo()
    browser.undo_step()
    assert browser.cursor_index() == -1
    assert history.cursor_index() == -1
    np.testing.assert_array_equal(owner.fits[1].model.y, 4 * np.arange(8.0) + 2)
    browser.redo_step()
    assert browser.cursor_index() == 0
    np.testing.assert_array_equal(owner.fits[1].model.y, 7 * np.arange(8.0) + 2)
    assert "new_value" in browser.details.toPlainText()
    assert browser.grab().save(str(ARTIFACTS / "chisurf-history-browser-after.png"))


def test_browser_failed_navigation_keeps_cursor_and_clear_load_refresh(qtbot, tmp_path):
    """Rejected publication keeps cursor and browser tracks external clear/load."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    history.record("fit.range.set", "Retained event", persist=False)
    browser = HistoryBrowserWidget()
    qtbot.addWidget(browser)
    browser.set_history(history)
    saved = history.export_state()

    def reject(project):
        """Reject without publishing science, as an owner RPC would."""
        raise RuntimeError("RPC failed")

    history.configure_science(capture, reject)
    with pytest.raises(RuntimeError, match="RPC failed"):
        browser.undo_step()
    assert browser.cursor_index() == 0

    assert history.export_state() == saved
    history.clear()
    qtbot.waitUntil(lambda: browser.table.topLevelItemCount() == 0)
    history.import_state(saved)
    qtbot.waitUntil(lambda: browser.table.topLevelItemCount() == 1)
    assert browser.cursor_index() == 0


def test_history_mixin_publishes_through_owner_instead_of_entity_projection(monkeypatch):
    """A cursor notification is acknowledgement, never destructive audit replay."""
    from chisurf.gui.main_helper import HistoryMixin, StateMixin

    class Host(HistoryMixin, StateMixin):
        """Use the production mixin precedence, without constructing Main twice."""

        def _sync_history_navigation_actions(self):
            """No toolbar actions are present in this focused notification probe."""

    def forbidden(*args, **kwargs):
        """Any audit replay is an architectural failure regardless of final dicts."""
        pytest.fail("cursor acknowledgement must not reconstruct or mutate science")

    monkeypatch.setattr("chisurf.history.build_target_state", forbidden)
    monkeypatch.setattr("chisurf.history.replay.sync_domain_entities", forbidden)
    Host()._on_history_cursor_changed({"action_type": "parameter.value"})


def test_browser_worker_notifications_are_queued_and_lifetime_detaches(qtbot):
    """Server-thread records never invoke Qt rendering directly or leak subscribers."""
    import threading

    from qtpy import QtCore

    from chisurf.history.core import OperationHistory

    history = OperationHistory()
    browser = HistoryBrowserWidget()
    browser.set_history(history)
    threads = []
    original = browser._render

    def render():
        """Measure which thread touches the real tree widget."""
        threads.append(QtCore.QThread.currentThread())
        original()

    browser._render = render
    worker = threading.Thread(
        target=lambda: history.record("audit", "server thread", persist=False)
    )
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()
    qtbot.waitUntil(lambda: browser.table.topLevelItemCount() == 1)
    assert threads and all(thread == browser.thread() for thread in threads)
    browser.deleteLater()
    qtbot.waitUntil(lambda: len(history._state_subscribers) == 0)


def test_browser_updates_when_complete_scientific_history_is_compacted(qtbot, tmp_path):
    """Browser rows and cursor follow the acknowledged rebased timeline."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    for n in range(3):
        history.record("audit", str(n), persist=False)
    browser = HistoryBrowserWidget()
    qtbot.addWidget(browser)
    browser.set_history(history)
    assert browser.table.topLevelItemCount() == 3
    assert history.compact_history(keep_recent=1)["compaction_successful"] is True
    assert browser.table.topLevelItemCount() == 1
    assert browser.cursor_index() == 0
