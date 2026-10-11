"""The existing admin handler describes and displays its real synthetic table seed."""

from __future__ import annotations

import copy
import json
import socket
from pathlib import Path

import pytest
from qtpy import QtCore, QtGui, QtWidgets


@pytest.fixture
def demo_widget(tmp_path, monkeypatch, qapp):
    """Construct the real tool over scratch services, replaying only the seed result."""
    from mmfdb.config import configure_runtime, reset_runtime_config

    from chisurf.plugins.core.mmfdb_admin.test import seeded_admin as sa

    sa.use_folder(tmp_path, monkeypatch)
    configure_runtime(
        settings_dir=tmp_path,
        database_path=tmp_path / "mmfdb.db",
        source_database_path=tmp_path / "missing.db",
        object_store_root=tmp_path / "objects",
    )

    def no_connect(*args, **kwargs):
        raise AssertionError("caption test attempted an external socket connection")

    monkeypatch.setattr(socket.socket, "connect", no_connect)
    monkeypatch.setattr(socket, "create_connection", no_connect)
    from chisurf.core.settings import cs_settings
    from chisurf.plugins.core.mmfdb_admin.gui.tool import MMFDBWidget

    monkeypatch.setitem(cs_settings["mmfdb"].setdefault("client", {}), "username", "admin")
    local = sa.admin_client()
    summary = local.populate_mock_data()
    assert Path(summary["database_path"]).resolve() == (tmp_path / "mmfdb.db").resolve()
    assert summary["input_row_counts"] == [50, 38, 32]
    assert summary["output_row_count"] == 63 and summary["synthetic"] is True
    calls = []

    class ReplayClient:
        """Delegate reads locally and return the already verified owned seed on demand."""

        def __getattr__(self, name):
            return getattr(local, name)

        def populate_mock_data(self):
            calls.append("populate")
            return copy.deepcopy(summary)

    widget = MMFDBWidget(client=ReplayClient())
    widget.nav_list.setCurrentRow(widget._row_by_name["Import / Export"])
    pending = []
    monkeypatch.setattr(widget, "_run_background_task", lambda **task: pending.append(task))
    try:
        yield widget, summary, pending, calls
    finally:
        qapp.processEvents()
        widget.close()
        qapp.processEvents()
        reset_runtime_config()


def click_header(widget):
    """Deliver the real handler's ten left-click events without inventing a control."""
    event = QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonPress,
        QtCore.QPointF(1, 1),
        QtCore.Qt.LeftButton,
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
    )
    for _ in range(10):
        widget._on_header_label_clicked(event)


def test_confirmation_describes_packaged_tables_and_declining_starts_nothing(
    demo_widget, monkeypatch
):
    """The actual confirmation describes the dataset, and No still prevents population."""
    from chisurf.gui import dialogs

    widget, _, pending, calls = demo_widget
    questions = []

    def decline(parent, title, message, *args):
        questions.append(message)
        return QtWidgets.QMessageBox.No

    monkeypatch.setattr(dialogs, "question", decline)
    click_header(widget)
    assert len(questions) == 1
    assert "packaged synthetic smFRET burst tables" in questions[0]
    assert "test fixtures" not in questions[0]
    assert not pending and not calls and not widget._mock_data_task_running


def test_translated_running_caption_and_real_result_survive_population(demo_widget, monkeypatch):
    """Both captions use translation; the running and completed handler states remain truthful."""
    from chisurf.gui import dialogs

    widget, summary, pending, calls = demo_widget
    translated = []

    def translate(text):
        translated.append(text)
        return "Translated: " + text

    monkeypatch.setattr(widget, "tr", translate)
    with dialogs.auto_answer(question=QtWidgets.QMessageBox.Yes):
        click_header(widget)
    assert len(translated) == 2
    assert all("packaged synthetic smFRET burst tables" in text for text in translated)
    assert all("test fixtures" not in text for text in translated)
    assert widget.preview_edit.toPlainText().startswith("Translated: Populating")
    assert widget._mock_data_task_running and len(pending) == 1 and not calls
    task = pending.pop()
    task["on_success"](task["fn"]())
    assert calls == ["populate"] and not widget._mock_data_task_running
    assert json.loads(widget.preview_edit.toPlainText()) == summary
    assert sum(summary["input_row_counts"]) == 120 and summary["output_row_count"] == 63
