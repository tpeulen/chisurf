"""Scientific history navigation: a rejected publication keeps the cursor.

The Qt history browser (rows, undo/redo buttons, thread-bound rendering) went with the Qt shell.
Undo/redo with science acknowledgement and compaction are covered Qt-free by
``test/history/test_history_scientific_owner.py``; this keeps the failed-navigation contract.
"""

import pytest

from test.history.test_history_scientific_owner import scientific_owner


def test_failed_navigation_keeps_cursor_and_state(tmp_path):
    """Rejected publication keeps the cursor and the exported history untouched."""
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    history.record("fit.range.set", "Retained event", persist=False)
    saved = history.export_state()

    def reject(project):
        """Reject without publishing science, as an owner RPC would."""
        raise RuntimeError("RPC failed")

    history.configure_science(capture, reject)
    with pytest.raises(RuntimeError, match="RPC failed"):
        history.navigate(-1)
    assert history.cursor_index() == 0
    assert history.export_state() == saved

    history.clear()
    assert history.list_events() == []
    history.import_state(saved)
    assert len(history.list_events()) == 1
    assert history.cursor_index() == 0
