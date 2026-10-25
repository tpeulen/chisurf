"""The editor's document store, Ruff, assistant file writes and close guard, on the emtk app.

Ported from the retired Qt ``CodeEditor`` tests: the same behaviours, on ``gui/editor_app.py``
(model and emtk ``Driver``) and the Qt-free helpers (``file_writes``, ``validation``).
"""

from __future__ import annotations

import time

import pytest
from emtk.events import CONTROL_MODIFIER
from emtk.testing import Driver

from chisurf.plugins.core.code_editor.file_writes import parse_file_writes
from chisurf.plugins.core.code_editor.gui.editor_app import make_editor_app
from chisurf.plugins.core.code_editor.ruff_runner import RuffRunner
from chisurf.plugins.core.code_editor.validation import validate_writes
from chisurf.plugins.emtk_layout import action_caption

F401 = {
    "ok": True,
    "diagnostics": [
        {"line": 1, "column": 0, "code": "F401", "message": "`os` imported but unused"}
    ],
}


@pytest.fixture
def app(tmp_path):
    application = make_editor_app(str(tmp_path))
    yield application
    application.close()


def _wait(app, predicate, timeout=10.0):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        app.model.process_events()
        app.editor_gui.chat_model.process_events()
        time.sleep(0.01)
    assert predicate()


def test_the_editor_syncs_an_open_document_to_the_store(app, tmp_path) -> None:
    """Open documents are mirrored into the JSON document store, unsaved edits included."""
    path = tmp_path / "sample.py"
    path.write_text("x = 1\n", encoding="utf-8")
    doc = app.model.open_file(path)
    doc.editor.text = "x = 1\ny = 2\n"
    app.model._sync_document_store()
    document = app.model.document_store.get(path=str(path.resolve()))
    assert document is not None
    assert document.content == "x = 1\ny = 2\n"
    assert document.modified is True


def test_run_ruff_checks_the_current_buffer_and_lists_the_diagnostics(app, monkeypatch) -> None:
    """Lint uses the unsaved content of the document in front; Diagnostics shows the result."""
    seen = []

    def fake_check(self, path, content, extra_args, timeout_ms):
        seen.append(content)
        return {**F401, "path": str(path)}

    monkeypatch.setattr(RuffRunner, "check", fake_check)
    app.model.new_document("lint.py", "import os\n")
    result = app.model.run_ruff()
    assert seen == ["import os\n"]
    assert [d["code"] for d in result["diagnostics"]] == ["F401"]
    Driver(app, (1400, 860)).frame(3)
    app.editor_gui.docks.focus("diagnostics")
    drawn_text = " ".join(t[5] for t in Driver(app, (1400, 860)).frame(3).texts)
    assert "F401" in drawn_text


def test_an_answer_writing_current_fills_the_document_in_front(app) -> None:
    """``WRITE_FILE: current`` goes into the open document, which stays in front."""
    doc = app.model.active_doc
    response = (
        "```markdown\n# WRITE_FILE: current\n# Theory of FRET\n\n"
        "Forster resonance energy transfer depends on donor-acceptor distance.\n```"
    )
    writes = app.editor_gui.chat_model.apply_file_writes(response)
    assert writes and writes[0][0] == "current"
    assert doc.text.startswith("# Theory of FRET")
    assert "Forster resonance energy transfer" in doc.text
    assert app.model.active_doc is doc and doc.is_modified


def test_the_write_target_is_only_the_header_line(app) -> None:
    """The content never folds into the file name."""
    doc = app.model.active_doc
    app.editor_gui.chat_model.apply_file_writes(
        '```python\n# WRITE_FILE: untitled document\nprint("written")\n```'
    )
    assert doc.text == 'print("written")'
    assert parse_file_writes('<write_file filename="a.py">x = 1</write_file>') == [("a.py", "x = 1")]


def test_closing_a_modified_document_asks_and_cancel_keeps_it_open(app, tmp_path) -> None:
    """Closing a modified tab asks first and honours Cancel."""
    driver = Driver(app, (1400, 860))
    doc = app.model.active_doc
    doc.editor.text = "changed"
    driver.frame(2)
    driver.key(ord("w"), "w", CONTROL_MODIFIER)  # Ctrl+W, as the user closes a tab
    driver.frame(2)
    assert "Discard changes" in [t[5] for t in driver.frame(2).texts]
    driver.click(action_caption("cancel"))
    driver.frame(2)
    assert app.model.active_doc is doc and doc.is_modified


def test_save_as_cancelled_while_closing_keeps_the_document_open(app) -> None:
    """Choosing Save on an untitled document and then cancelling the dialog does not close it."""
    driver = Driver(app, (1400, 860))
    doc = app.model.new_document("Untitled.py", "")
    doc.editor.text = "changed"
    driver.frame(2)
    driver.key(ord("w"), "w", CONTROL_MODIFIER)
    driver.frame(2)
    driver.click("Save and close")
    driver.frame(2)
    assert app.editor_gui._file_dialog is not None  # Save As opened for the untitled document
    app.editor_gui._file_dialog = None  # the user cancels the dialog
    driver.frame(2)
    assert doc in app.model.documents and doc.is_modified


def test_an_answer_without_a_write_runs_no_validation(app, monkeypatch) -> None:
    """An answer that writes nothing triggers no compile or Ruff check (and stays the last message)."""

    def fail_validate(*_args, **_kwargs):
        raise AssertionError("validate_writes should not be called")

    monkeypatch.setattr("chisurf.plugins.core.code_editor.validation.validate_writes", fail_validate)
    chat = app.editor_gui.chat_model
    chat.history.add_message("assistant", "This is just an explanation.")
    assert chat.apply_file_writes("This is just an explanation.") == []
    assert chat.history.messages[-1].content == "This is just an explanation."


def test_a_written_file_is_validated_and_the_issues_are_reported(app, monkeypatch) -> None:
    monkeypatch.setattr(
        RuffRunner, "check", lambda self, path, content, extra_args, timeout_ms: {**F401, "path": path}
    )
    chat = app.editor_gui.chat_model
    chat.apply_file_writes("```python\n# WRITE_FILE: current\nimport os\n```")
    _wait(app, lambda: "Validation found" in chat.history.messages[-1].content)
    assert "F401" in chat.history.messages[-1].content


def test_validate_writes_detects_py_compile_errors(tmp_path) -> None:
    """Generated code is checked with py_compile."""
    issues = validate_writes([("broken.py", "def broken(:\n    pass\n")], editor=None)
    assert issues
    assert issues[0][0] == "broken.py"
    assert issues[0][1][0]["code"] == "E999"


def test_validate_writes_uses_ruff_diagnostics(app, monkeypatch) -> None:
    """Generated code is checked with the editor's Ruff runner and Ruff settings."""

    def fake_check(self, path, content, extra_args, timeout_ms):
        assert content == "import os\n"
        assert timeout_ms == app.model.ruff_timeout_ms
        return {**F401, "path": str(path)}

    monkeypatch.setattr(RuffRunner, "check", fake_check)
    issues = validate_writes([("sample.py", "import os\n")], editor=app.model)
    assert issues
    assert issues[0][1][0]["code"] == "F401"
