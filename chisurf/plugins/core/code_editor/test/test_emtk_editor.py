"""Test suite for the EMTK Code Editor and AI Chat components."""

from __future__ import annotations

import pathlib
import tempfile

import pytest
from emtk import im
from emtk.testing import RecordingPainter

from chisurf.plugins.core.code_editor.gui.chat_app import ChatApp, ChatGui, ChatModel
from chisurf.plugins.core.code_editor.gui.editor_app import (
    CodeEditorApp,
    CodeEditorGui,
    EditorModel,
)


def test_chat_model_and_gui():
    model = ChatModel()
    model.history.add_message("user", "Hello assistant!")
    model._handle_chunk("Hello from ")
    model._handle_chunk("EMTK!")
    model._handle_finished()

    assert len(model.history.messages) == 2
    assert model.history.messages[1].content == "Hello from EMTK!"
    assert model.history.messages[1].status == "complete"

    # Test immediate mode rendering
    p = RecordingPainter()
    gui = ChatGui(model=model)
    with im.frame(p, (0, 0, 400, 600)):
        gui.draw(400, 600)

    assert len(p.texts) > 0


def test_editor_model_operations():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        test_file = root / "script.py"
        test_file.write_text("print('hello')", encoding="utf-8")

        model = EditorModel(project_root=root)
        assert len(model.documents) == 1
        assert model.documents[0].name == "main.py"

        # Open file
        doc = model.open_file(test_file)
        assert doc is not None
        assert doc.name == "script.py"
        assert doc.text == "print('hello')"
        assert len(model.documents) == 2

        # Edit text and save
        doc.text = "print('updated')"
        assert doc.is_modified
        saved = model.save_document()
        assert saved
        assert test_file.read_text(encoding="utf-8") == "print('updated')"

        # Close doc
        model.close_document(model.active_index)
        assert len(model.documents) == 1


def test_editor_gui_rendering():
    p = RecordingPainter()
    app = CodeEditorApp()
    with im.frame(p, (0, 0, 1000, 700)):
        app.editor_gui.draw(1000, 700)

    assert len(p.texts) > 0


def test_new_and_open_documents_stay_active_after_render(tmp_path):
    model = EditorModel(tmp_path)
    gui = CodeEditorGui(model)
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 1100, 720)):
        gui.draw(1100, 720)
    new = model.new_document("second.py")
    with im.frame(painter, (0, 0, 1100, 720)):
        gui.draw(1100, 720)
    assert model.active_doc is new
    path = tmp_path / "opened.py"
    path.write_text("value = 1\n")
    opened = model.open_file(path)
    with im.frame(painter, (0, 0, 1100, 720)):
        gui.draw(1100, 720)
    assert model.active_doc is opened
    model.open_file(path)
    assert len(model.documents) == 3


def test_closing_earlier_document_preserves_active_buffer(tmp_path):
    model = EditorModel(tmp_path)
    active = model.new_document("second.py")
    model.new_document("third.py")
    model.active_index = 1
    model.close_document(0)
    assert model.active_doc is active


def test_duplicate_names_and_modified_labels_keep_active_document(tmp_path):
    model = EditorModel(tmp_path)
    gui = CodeEditorGui(model)
    active = model.new_document("main.py")
    painter = RecordingPainter()
    storage = {}
    for content in ("", "edited"):
        active.text = content
        with im.frame(painter, (0, 0, 1100, 720), storage=storage):
            gui.draw(1100, 720)
        assert model.active_doc is active


def test_recursive_project_filter_keeps_matching_descendants(tmp_path):
    nested = tmp_path / "package" / "deep"
    nested.mkdir(parents=True)
    target = nested / "target.py"
    target.write_text("pass\n")
    (nested / "other.py").write_text("pass\n")
    gui = CodeEditorGui(EditorModel(tmp_path))
    gui.file_filter = "target"
    assert gui._project_entries(tmp_path) == [tmp_path / "package"]
    assert gui._project_entries(nested) == [target]


def test_project_file_right_click_exposes_actions(tmp_path):
    from emtk.im_core import IO

    (tmp_path / "script.py").write_text("pass\n")
    gui = CodeEditorGui(EditorModel(tmp_path))
    painter = RecordingPainter()
    storage = {}
    with im.frame(painter, (0, 0, 320, 500), storage=storage):
        gui._draw_file_tree((0, 0, 320, 500))
    file_text = next(text for text in painter.texts if "script.py" in text[5])
    io = IO(
        mouse_pos=(file_text[0] + 8, file_text[1] + 8),
        mouse_clicked=[False, True, False],
        mouse_down=[False, True, False],
    )
    painter.texts.clear()
    with im.frame(painter, (0, 0, 320, 500), io=io, storage=storage):
        gui._draw_file_tree((0, 0, 320, 500))
    labels = "\n".join(text[5] for text in painter.texts)
    assert "Open in editor" in labels
    assert "Copy path" in labels and "Copy file name" in labels
    assert "Copy relative path" in labels


@pytest.mark.parametrize("action", ["Cancel", "Discard changes", "Save and close"])
def test_modified_close_requires_choice(tmp_path, monkeypatch, action):
    model = EditorModel(tmp_path)
    active = model.active_doc
    active.text = "unsaved work\n"
    gui = CodeEditorGui(model)
    painter = RecordingPainter()
    storage = {}
    # The toolbar's Close is a regular-height labelled button; pressing it is
    # simulated by answering button the way the click would. The popup's own
    # buttons have distinct labels, so the patch cannot hit them.
    monkeypatch.setattr(
        im,
        "button",
        lambda label, size=None, role=None: "Close" in label and "Save and close" not in label,
    )
    with im.frame(painter, (0, 0, 900, 600), storage=storage):
        gui._draw_editor_tabs((0, 0, 900, 600))
    assert active in model.documents
    assert any("Save changes to main.py" in text[5] for text in painter.texts)

    if action == "Save and close":
        monkeypatch.setattr(model, "save_document", lambda index=None: False)
    monkeypatch.setattr(
        im,
        "button",
        lambda label, size=None, role=None: label.split("###")[0].split("  ")[-1] == action,
    )
    with im.frame(painter, (0, 0, 900, 600), storage=storage):
        gui._draw_editor_tabs((0, 0, 900, 600))
    if action == "Discard changes":
        assert active not in model.documents
    else:
        assert model.active_doc is active
        assert active.text == "unsaved work\n"

    if action == "Cancel":
        painter.texts.clear()
        monkeypatch.setattr(im, "button", lambda label, size=None, role=None: False)
        monkeypatch.setattr(im, "small_button", lambda label, size=None: False)
        with im.frame(painter, (0, 0, 900, 600), storage=storage):
            gui._draw_editor_tabs((0, 0, 900, 600))
        assert not any("Save changes to main.py" in text[5] for text in painter.texts)


def test_pure_emtk_no_qt():
    """Verify code editor and chat widgets operate in pure EMTK without any Qt."""
    import sys

    from chisurf.plugins.core.code_editor.gui.chat_app import make_chat_app
    from chisurf.plugins.core.code_editor.gui.editor_app import make_editor_app

    # Ensure acp_client does not import qtpy or PyQt5/PySide
    assert (
        "qtpy" not in sys.modules
        or "QtCore" not in sys.modules["chisurf.plugins.core.code_editor.acp_client"].__dict__
    )

    # Pure EMTK apps construct and draw without Qt
    p = RecordingPainter()
    editor_app = make_editor_app()
    with im.frame(p, (0, 0, 800, 600)):
        editor_app.editor_gui.draw(800, 600)

    chat_app = make_chat_app()
    with im.frame(p, (0, 0, 400, 500)):
        chat_app.chat_gui.draw(400, 500)

    assert len(p.texts) > 0


def test_document_tab_close_and_context_menu(tmp_path):
    from emtk.im_core import IO

    model = EditorModel(tmp_path)
    active = model.new_document("second.py")
    gui = CodeEditorGui(model)
    storage = {}

    def draw(io=None):
        painter = RecordingPainter()
        with im.frame(painter, (0, 0, 1100, 720), storage=storage, io=io):
            gui.draw(1100, 720)
        return painter

    painter = draw()
    tab_y = next(t[1] for t in painter.texts if t[5].strip() == "second.py")
    crosses = [t for t in painter.texts if t[5] == "×" and abs(t[1] - tab_y) < 4]
    assert len(crosses) == 2
    cross = crosses[0]
    position = (cross[0] + 3, cross[1] + 6)
    draw(
        IO(mouse_pos=position, mouse_clicked=[True, False, False], mouse_down=[True, False, False])
    )
    draw(IO(mouse_pos=position, mouse_released=[True, False, False]))
    assert [doc.name for doc in model.documents] == ["second.py"]
    assert model.active_doc is active

    painter = draw()
    tab = next(t for t in painter.texts if t[5].strip() == "second.py")
    position = (tab[0] + 12, tab[1] + 6)
    painter = draw(IO(mouse_pos=position, mouse_clicked=[False, True, False]))
    assert "Close document" in "\n".join(painter.strings)
    item = next(t for t in painter.texts if t[5].strip() == "Close document")
    position = (item[0] + 12, item[1] + 6)
    draw(IO(mouse_pos=position))
    draw(
        IO(mouse_pos=position, mouse_clicked=[True, False, False], mouse_down=[True, False, False])
    )
    draw(IO(mouse_pos=position, mouse_released=[True, False, False]))
    assert not model.documents


def test_acp_read_file_supports_line_and_limit(tmp_path):
    path = tmp_path / "context.py"
    path.write_text("first\nsecond\nthird\n")
    model = ChatModel()
    assert model._handle_read_file(str(path), 2, 1) == "second\n"
    editor = EditorModel(tmp_path)
    editor.open_file(path).text = "unsaved\ncontext\n"
    model.editor_ref = editor
    assert model._handle_read_file(str(path), 2, 1) == "context\n"


def test_chat_failure_survives_delayed_event_processing(monkeypatch):
    import sys
    import types

    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setitem(
        sys.modules,
        "chisurf.core.agent",
        types.SimpleNamespace(
            AgentConfig=fail,
            AgentSession=fail,
            LLMClient=fail,
            AgentContext=fail,
            ToolRegistry=fail,
            LLMSettings=types.SimpleNamespace(from_provider=fail),
        ),
    )
    model = ChatModel()
    model._run_in_process_prompt("Hello")
    model.process_events()
    assert "provider unavailable" in model.history.messages[0].content
    assert not model.is_generating


def test_native_core_factories_do_not_import_qt():
    import subprocess
    import sys

    script = """
import importlib.abc
import sys
class NoQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
            raise RuntimeError('Qt runtime import: ' + fullname)
sys.meta_path.insert(0, NoQt())
from emtk import im
from emtk.testing import RecordingPainter
from chisurf.plugins.core.code_editor.gui.editor_app import make_editor_app
from chisurf.plugins.core.code_editor.gui.chat_app import make_chat_app
from chisurf.plugins.core.help.gui.help_app import make_help_app
from chisurf.plugins.ai_settings.gui.app import make_ai_settings_app
for factory in (make_editor_app, make_chat_app, make_help_app, make_ai_settings_app):
    app = factory()
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 1000, 720)):
        if hasattr(app, "_render"):
            app._render()
        elif hasattr(app, "render"):
            app.render()
        elif callable(app):
            app()
    assert painter.texts
editor = make_editor_app().model
editor.run_endpoint = 'console'
editor.active_doc.text = "print('pure console execution')"
editor.run_active_script()
editor.process_events()
assert not editor.is_running_script
notebook = editor.new_document('pure.ipynb').notebook
notebook.active_cell.editor.set_text('value = 3; print(value)')
notebook.run_cell(0)
assert notebook.active_cell.execution_count == 1
assert not any(name.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'} for name in sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_chat_permission_requires_ui_choice():
    import threading
    import time

    model = ChatModel()
    responses = []
    thread = threading.Thread(
        target=lambda: responses.append(
            model._handle_permission_request(
                {"title": "Write a file"}, [{"optionId": "allow_once", "name": "Allow once"}]
            )
        ),
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 2
    while model.event_queue.empty() and time.monotonic() < deadline:
        time.sleep(0.01)
    model.process_events()
    assert thread.is_alive()
    assert model.pending_permission["title"] == "Write a file"
    model.respond_permission("allow_once")
    thread.join(timeout=2)
    assert responses == ["allow_once"]
    assert model.pending_permission is None


def test_unnamed_save_requires_destination_and_unique_names(tmp_path):
    model = EditorModel(tmp_path)
    first = model.new_document()
    second = model.new_document()
    assert first.name != second.name
    assert not model.save_document()
    assert second.path is None
    assert not (tmp_path / second.name).exists()
    destination = tmp_path / "saved.py"
    assert model.save_document(path=destination)
    assert second.path == str(destination)
    assert second.name == "saved.py"


def test_save_as_failure_retains_original_document_identity(tmp_path):
    path = tmp_path / "original.py"
    path.write_text("old")
    model = EditorModel(tmp_path)
    doc = model.open_file(path)
    doc.text = "new"
    assert not model.save_document(path=tmp_path / "missing" / "new.py")
    assert doc.path == str(path)
    assert doc.name == "original.py"
    assert doc.is_modified
    assert path.read_text() == "old"


def test_file_chooser_cancel_preserves_unsaved_buffer(tmp_path, monkeypatch):
    model = EditorModel(tmp_path)
    gui = CodeEditorGui(model)
    doc = model.active_doc
    gui._request_save(doc, close_after=True)
    monkeypatch.setattr(gui._file_dialog, "draw", lambda: False)
    with im.frame(RecordingPainter(), (0, 0, 1000, 700)):
        gui._draw_file_dialog()
    assert gui._file_dialog is None
    assert doc in model.documents
    assert doc.path is None


def test_script_stop_finishes_process(tmp_path):
    import time

    model = EditorModel(tmp_path)
    model.active_doc.text = "import time\nprint('started', flush=True)\ntime.sleep(60)"
    model.run_active_script()
    deadline = time.monotonic() + 5
    while model._script_process is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert model._script_process is not None
    model.stop_active_script()
    model._script_thread.join(timeout=5)
    assert not model.is_running_script
    assert model._script_process is None
    assert any("exit code" in line for line in model.output_logs)


def test_save_chooser_requires_confirmation_before_overwrite(tmp_path, monkeypatch):
    path = tmp_path / "existing.py"
    path.write_text("original")
    model = EditorModel(tmp_path)
    doc = model.active_doc
    doc.text = "replacement"
    gui = CodeEditorGui(model)
    gui._request_save(doc)
    monkeypatch.setattr(gui._file_dialog, "draw", lambda: [str(path)])
    with im.frame(RecordingPainter(), (0, 0, 1000, 700)):
        gui._draw_file_dialog()
    assert gui._overwrite_path == path
    assert path.read_text() == "original"
    gui._finish_save(path)
    assert path.read_text() == "replacement"
    assert gui._file_dialog is None


def test_open_chooser_activates_last_selected_document(tmp_path, monkeypatch):
    paths = [tmp_path / "first.py", tmp_path / "second.py"]
    for path in paths:
        path.write_text(path.stem)
    model = EditorModel(tmp_path)
    gui = CodeEditorGui(model)
    gui._request_open()
    monkeypatch.setattr(gui._file_dialog, "draw", lambda: [str(path) for path in paths])
    with im.frame(RecordingPainter(), (0, 0, 1000, 700)):
        gui._draw_file_dialog()
    assert model.active_doc.path == str(paths[-1])
    assert gui._file_dialog is None


def test_native_symbols_follow_unsaved_source_and_jump(tmp_path):
    model = EditorModel(tmp_path)
    model.active_doc.text = "class Model:\n    def execute(self):\n        pass\n"
    symbols = model.document_symbols()
    assert [symbol.display_name for symbol in symbols] == ["Model", "Model.execute"]
    model.goto_line(symbols[-1].line, symbols[-1].column)
    assert model.active_doc.editor.cursors.main.end.line == 1
    model.active_doc.text = "def replacement():\n    pass\n"
    assert [symbol.name for symbol in model.document_symbols()] == ["replacement"]


def test_native_ruff_uses_unsaved_source_and_reports_errors(tmp_path, monkeypatch):
    from chisurf.plugins.core.code_editor.ruff_runner import RuffRunner

    seen = {}

    def check(self, path, content, **kwargs):
        seen.update(path=path, content=content)
        return {"ok": False, "error": "Ruff executable unavailable", "diagnostics": []}

    monkeypatch.setattr(RuffRunner, "check", check)
    model = EditorModel(tmp_path)
    model.active_doc.text = "import os\n"
    result = model.run_ruff()
    assert not result["ok"]
    assert seen["content"] == "import os\n"
    assert seen["path"] == str(tmp_path / "main.py")
    assert "Ruff executable unavailable" in model.output_logs[-1]


def test_native_ruff_fix_preserves_unsaved_modification(tmp_path, monkeypatch):
    from chisurf.plugins.core.code_editor.ruff_runner import RuffRunner

    monkeypatch.setattr(
        RuffRunner,
        "fix",
        lambda *args, **kwargs: {"ok": True, "fixed_content": "value = 1\n", "diagnostics": []},
    )
    model = EditorModel(tmp_path)
    model.active_doc.text = "import os\nvalue = 1\n"
    result = model.run_ruff(fix=True)
    assert result["ok"]
    assert model.active_doc.text == "value = 1\n"
    assert model.active_doc.is_modified
    assert model.active_doc.path is None


def test_native_console_mode_runs_in_chisurf_namespace(tmp_path):
    import chisurf

    model = EditorModel(tmp_path)
    model.run_endpoint = "console"
    model.active_doc.text = "print('console output')\nchisurf._emtk_editor_marker = 27\n"
    model.run_active_script()
    assert model.is_running_script
    model.process_events()
    assert not model.is_running_script
    assert chisurf._emtk_editor_marker == 27
    del chisurf._emtk_editor_marker
    assert any("console output" in line for line in model.output_logs)


def test_native_console_shebang_preselects_endpoint(tmp_path):
    path = tmp_path / "macro.py"
    path.write_text("# !chisurf: ipython\nprint('macro')\n")
    model = EditorModel(tmp_path)
    model.open_file(path)
    assert model.run_endpoint == "console"


def test_native_ruff_does_not_apply_stale_fixes(tmp_path):
    model = EditorModel(tmp_path)
    doc = model.active_doc
    doc.text = "changed during check"
    model._apply_ruff(
        doc, "before check", {"ok": True, "fixed_content": "fixed", "diagnostics": []}, True
    )
    assert doc.text == "changed during check"
    assert any("changed during" in line for line in model.output_logs)


def test_native_ruff_async_error_returns_to_ui(tmp_path, monkeypatch):
    import time

    from chisurf.plugins.core.code_editor.ruff_runner import RuffRunner

    def fail(*args, **kwargs):
        raise RuntimeError("runner failed")

    monkeypatch.setattr(RuffRunner, "check", fail)
    model = EditorModel(tmp_path)
    model.start_ruff()
    deadline = time.monotonic() + 2
    while model.event_queue.empty() and time.monotonic() < deadline:
        time.sleep(0.01)
    model.process_events()
    assert not model._ruff_running
    assert "runner failed" in model.output_logs[-1]


def test_native_apps_keep_frames_running_during_background_work():
    editor = CodeEditorApp()
    editor.model._ruff_running = True
    assert editor.animating()
    editor.model._ruff_running = False
    editor.model.is_running_script = True
    assert editor.animating()
    chat = ChatApp()
    chat.chat_gui.model.is_generating = True
    assert chat.animating()
    from chisurf.plugins.core.help.gui.help_app import make_help_app

    help_app = make_help_app()
    help_app.model.is_asking = True
    assert help_app.animating()


def _write_native_notebook(path):
    import json

    data = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"custom": {"keep": 1}},
        "cells": [
            {
                "id": "code-one",
                "cell_type": "code",
                "metadata": {"tags": ["keep"]},
                "source": ["value = 21\n", "print(value)\n"],
                "outputs": [],
                "execution_count": None,
            },
            {
                "id": "code-two",
                "cell_type": "code",
                "metadata": {},
                "source": "value + 1",
                "outputs": [],
                "execution_count": None,
            },
            {
                "id": "markdown",
                "cell_type": "markdown",
                "metadata": {},
                "source": "# Heading",
                "attachments": {"keep": {"text/plain": "attached"}},
            },
        ],
    }
    path.write_text(json.dumps(data))
    return data


def test_native_notebook_roundtrip_preserves_metadata_and_cells(tmp_path):
    import json

    path = tmp_path / "example.ipynb"
    original = _write_native_notebook(path)
    model = EditorModel(tmp_path)
    doc = model.open_file(path)
    assert doc.notebook is not None
    assert not doc.is_modified
    assert [cell.cell_type for cell in doc.notebook.cells] == ["code", "code", "markdown"]
    doc.notebook.cells[0].editor.set_text("value = 42")
    assert doc.is_modified
    assert model.save_document()
    saved = json.loads(path.read_text())
    assert saved["metadata"] == original["metadata"]
    assert saved["cells"][0]["metadata"] == original["cells"][0]["metadata"]
    assert saved["cells"][2]["attachments"] == original["cells"][2]["attachments"]
    assert saved["cells"][0]["source"] == "value = 42"
    assert not doc.is_modified


def test_native_notebook_shared_shell_execution_restart_and_errors(tmp_path):
    path = tmp_path / "example.ipynb"
    _write_native_notebook(path)
    notebook = EditorModel(tmp_path).open_file(path).notebook
    notebook.run_cell(0)
    notebook.run_cell(1)
    first, second = notebook.cells[:2]
    assert first.execution_count == 1
    assert second.execution_count == 2
    assert any("21" in output.get("text", "") for output in first.outputs)
    assert any("22" in output.get("data", {}).get("text/plain", "") for output in second.outputs)
    notebook.restart_shell()
    notebook.run_cell(1)
    assert any(
        output.get("output_type") == "error" and output["ename"] == "NameError"
        for output in second.outputs
    )
    notebook.clear_outputs()
    assert not any(cell.outputs for cell in notebook.cells)


def test_native_notebook_cell_add_move_delete_and_terminal(tmp_path):
    from chisurf.plugins.core.code_editor.gui.notebook_app import NativeNotebook

    notebook = NativeNotebook.new()
    code = notebook.add_cell("code", "x = 5")
    markdown = notebook.add_cell("markdown", "# Last")
    notebook.move_cell(2, -1)
    assert notebook.cells[1] is markdown
    notebook.remove_cell(1)
    assert markdown not in notebook.cells
    notebook.run_cell(notebook.cells.index(code))
    notebook.run_terminal("print(x + 1)")
    assert any("6" in line for line in notebook.terminal_output)
    notebook.remove_cell(0)
    notebook.remove_cell(0)
    assert notebook.cells  # Editing always retains one cell.


def test_native_notebook_render_has_cell_controls(tmp_path):
    path = tmp_path / "example.ipynb"
    _write_native_notebook(path)
    model = EditorModel(tmp_path)
    model.open_file(path)
    painter = RecordingPainter()
    gui = CodeEditorGui(model)
    with im.frame(painter, (0, 0, 1100, 720)):
        gui.draw(1100, 720)
    labels = "\n".join(painter.strings)
    assert "Run all" in labels
    assert "Code cell" in labels
    assert "Heading" in labels


def test_invalid_native_notebook_falls_back_to_raw_editor(tmp_path):
    path = tmp_path / "broken.ipynb"
    path.write_text("{broken JSON")
    doc = EditorModel(tmp_path).open_file(path)
    assert doc is not None
    assert doc.notebook is None
    assert doc.text == "{broken JSON"


def test_native_app_close_releases_registries_and_background_state(tmp_path):
    from chisurf.emtk.code_links import _ACTIVE_EMTK_EDITORS
    from chisurf.plugins.core.help.gui.help_app import _ACTIVE_HELP_INSTANCES, make_help_app

    editor = CodeEditorApp(tmp_path)
    chat = ChatApp()
    help_app = make_help_app()
    for app in (editor, chat, help_app):
        with im.frame(RecordingPainter(), (0, 0, 1000, 720)):
            app._render()
    assert editor.model in _ACTIVE_EMTK_EDITORS
    assert help_app.model in _ACTIVE_HELP_INSTANCES
    editor.close()
    editor.close()
    chat.close()
    help_app.close()
    assert editor.model not in _ACTIVE_EMTK_EDITORS
    assert help_app.model not in _ACTIVE_HELP_INSTANCES
    assert not editor.animating()
    assert not chat.animating()
    assert not help_app.animating()


def test_native_chat_provider_uses_real_session_contract(monkeypatch):
    import types

    import chisurf.core.agent as agent

    calls = []
    settings = types.SimpleNamespace(validate=lambda: None)
    monkeypatch.setattr(agent.LLMSettings, "from_provider", lambda *args, **kwargs: settings)
    monkeypatch.setattr(agent, "LLMClient", lambda value: value)

    class Session:
        def __init__(self, llm, **kwargs):
            assert llm is settings
            self.context = kwargs["context"]
            calls.append(self)

        def ask(self, prompt):
            self.context.emit("message.completed", {"content": "response to " + prompt})
            return types.SimpleNamespace(stop_reason="answer", error=None)

        def cancel(self):
            pass

    monkeypatch.setattr(agent, "AgentSession", Session)
    model = ChatModel()
    model.provider = "openai"
    model._run_in_process_prompt("first")
    model.process_events()
    model._run_in_process_prompt("second")
    model.process_events()
    assert len(calls) == 1
    assert [message.content for message in model.history.messages] == [
        "response to first",
        "response to second",
    ]
    model.close()


def test_native_notebook_saved_images_render_and_remain_roundtrippable():
    import base64
    import io

    from PIL import Image

    from chisurf.plugins.core.code_editor.gui.notebook_app import NativeNotebook

    buffer = io.BytesIO()
    Image.new("RGBA", (8, 4), "blue").save(buffer, format="PNG")
    payload = base64.b64encode(buffer.getvalue()).decode()
    notebook = NativeNotebook.new()
    output = {
        "output_type": "display_data",
        "data": {"image/png": payload, "text/plain": "figure"},
        "metadata": {"image/png": {"width": 8}},
    }
    notebook.active_cell.outputs.append(output)
    with im.frame(RecordingPainter(), (0, 0, 900, 600)):
        notebook.draw(900, 600)
    assert notebook.active_cell._textures
    assert notebook.to_dict()["cells"][0]["outputs"] == [output]
    notebook.close()


def test_native_notebook_inline_figure_is_saved_as_image():
    import json

    from chisurf.plugins.core.code_editor.gui.notebook_app import NativeNotebook

    notebook = NativeNotebook.new()
    notebook.active_cell.editor.set_text(
        "import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\nfig, ax = plt.subplots()\nax.plot([1, 2], [3, 4])\nfig"
    )
    notebook.run_cell(0)
    outputs = notebook.active_cell.outputs
    assert any("image/png" in output.get("data", {}) for output in outputs)
    assert notebook.to_dict()["cells"][0]["outputs"] == outputs
    assert json.loads(notebook.dumps())["cells"][0]["outputs"] == outputs
    notebook.close()


def test_native_notebook_binary_display_payload_is_json_serializable():
    import base64
    import io
    import json

    from PIL import Image

    from chisurf.plugins.core.code_editor.gui.notebook_app import NativeNotebook

    buffer = io.BytesIO()
    Image.new("RGBA", (8, 4), "blue").save(buffer, format="PNG")
    raw_png = buffer.getvalue()
    notebook = NativeNotebook.new()
    notebook._active_cell = notebook.active_cell
    notebook._display(
        {"image/png": raw_png, "text/plain": b"binary figure"},
        {},
        "display_data",
        None,
    )
    output = notebook.active_cell.outputs[0]
    assert output["data"]["image/png"] == base64.b64encode(raw_png).decode("ascii")
    assert output["data"]["text/plain"] == "binary figure"
    with im.frame(RecordingPainter(), (0, 0, 900, 600)):
        notebook.draw(900, 600)
    assert notebook.active_cell._textures, "the normalized image must remain renderable"
    assert json.loads(notebook.dumps())["cells"][0]["outputs"] == [output]
    notebook.close()


def test_native_editor_process_sets_file_and_import_path(tmp_path):
    model = EditorModel(tmp_path)
    model.active_doc.text = (
        "import os\nprint(os.path.basename(__file__))\nprint(len(__import__('sys').argv))"
    )
    model.run_active_script()
    model._script_thread.join(timeout=5)
    assert not model.is_running_script
    assert "main.py" in model.output_logs
    assert "1" in model.output_logs


def test_native_notebook_svg_uses_existing_qt_free_renderer():
    import shutil

    from chisurf.plugins.core.code_editor.gui.notebook_app import NativeNotebook

    if not shutil.which("rsvg-convert"):
        pytest.skip("Qt-free SVG renderer is not installed")
    notebook = NativeNotebook.new()
    payload = '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="8"><rect width="12" height="8" fill="red"/></svg>'
    output = {"output_type": "display_data", "data": {"image/svg+xml": payload}, "metadata": {}}
    notebook.active_cell.outputs.append(output)
    with im.frame(RecordingPainter(), (0, 0, 900, 600)):
        notebook.draw(900, 600)
    texture = notebook.active_cell._textures[payload]
    assert (texture.width, texture.height) == (12, 8)
    assert notebook.to_dict()["cells"][0]["outputs"] == [output]
    notebook.close()


def _fake_native_lsp_server(path):
    path.write_text("""import json, sys

def send(value):
    body = json.dumps(value).encode()
    data = ("Content-Length: %d\\r\\n\\r\\n" % len(body)).encode() + body
    sys.stdout.buffer.write(data[:7]); sys.stdout.buffer.flush()
    sys.stdout.buffer.write(data[7:]); sys.stdout.buffer.flush()

while True:
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            sys.exit()
        if line == b"\\r\\n":
            break
        key, value = line.decode().split(":", 1)
        headers[key.lower()] = value.strip()
    message = json.loads(sys.stdin.buffer.read(int(headers["content-length"])))
    method = message.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": message["id"], "result": {"capabilities": {}}})
    elif method in ("textDocument/didOpen", "textDocument/didChange"):
        uri = message["params"]["textDocument"]["uri"]
        send({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics", "params": {"uri": uri, "diagnostics": [{"message": "fake diagnostic", "code": "TEST", "range": {"start": {"line": 0, "character": 1}, "end": {"line": 0, "character": 2}}}]}})
    elif method == "textDocument/completion":
        send({"jsonrpc": "2.0", "id": message["id"], "result": [{"label": "print", "textEdit": {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 3}}, "newText": "print"}}]})
    elif method == "textDocument/hover":
        send({"jsonrpc": "2.0", "id": message["id"], "result": {"contents": {"kind": "markdown", "value": "**Function documentation**"}}})
    elif method == "textDocument/definition":
        send({"jsonrpc": "2.0", "id": message["id"], "result": [{"uri": message["params"]["textDocument"]["uri"], "range": {"start": {"line": 0, "character": 1}, "end": {"line": 0, "character": 2}}}]})
    elif "id" in message:
        send({"jsonrpc": "2.0", "id": message["id"], "result": None})
""")


def test_native_lsp_frames_fragmentation_unicode_and_invalid_headers(tmp_path):
    import json

    from chisurf.plugins.core.code_editor.gui.native_lsp import NativeLspClient

    client = NativeLspClient(tmp_path)
    seen = []
    client.diagnostics_received.connect(lambda uri, values: seen.append((uri, values)))
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": "file:///é.py", "diagnostics": [{"message": "é"}]},
        },
        ensure_ascii=False,
    ).encode()
    frame = f"Content-Length: {len(body)}\r\n\r\n".encode() + body
    client.feed_data(frame[:11])
    assert not seen
    client.feed_data(frame[11:] + frame)
    assert len(seen) == 2
    assert seen[0][1][0]["message"] == "é"
    with pytest.raises(ValueError):
        client.feed_data(b"Content-Length: -1\r\n\r\n")
    client.stop()


def test_native_lsp_server_completions_diagnostics_and_draw(tmp_path):
    import sys
    import time

    server = tmp_path / "fake_lsp.py"
    _fake_native_lsp_server(server)
    app = CodeEditorApp(tmp_path)
    model = app.model
    model.active_doc.text = "pri"
    assert model.start_lsp([sys.executable, str(server)])
    deadline = time.monotonic() + 5
    while not model.lsp_client.is_ready and time.monotonic() < deadline:
        model.process_events()
        time.sleep(0.01)
    assert model.lsp_client.is_ready
    model.process_events()
    model.request_lsp("completion")
    while not model.completions and time.monotonic() < deadline:
        model.process_events()
        time.sleep(0.01)
    assert model.completions[0]["label"] == "print"
    model.apply_completion(model.completions[0])
    assert model.active_doc.text == "print"
    model.active_doc.editor.undo()
    assert model.active_doc.text == "pri"
    model.process_events()
    assert model.active_doc.lsp_diagnostics[0]["message"] == "fake diagnostic"
    model.request_lsp("hover")
    while not model.hover_text and time.monotonic() < deadline:
        model.process_events()
        time.sleep(0.01)
    assert "Function documentation" in model.hover_text
    model.request_lsp("definition")
    while model.active_doc.editor.cursors.main.end.index != 1 and time.monotonic() < deadline:
        model.process_events()
        time.sleep(0.01)
    assert model.active_doc.editor.cursors.main.end.index == 1
    with im.frame(RecordingPainter(), (0, 0, 1000, 720)):
        app._render()
    assert app.next_frame_in() is not None
    app.close()
    assert model.lsp_client is None


def test_native_lsp_missing_server_explains_optional_dependency(tmp_path, monkeypatch):
    import importlib.util
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    original = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name: None if name == "pylsp" else original(name)
    )
    model = EditorModel(tmp_path)
    assert not model.start_lsp()
    model.process_events()
    assert "not installed" in model.lsp_status
    model.close()


def test_native_notebook_reload_and_python_export_preserve_tab(tmp_path):
    path = tmp_path / "example.ipynb"
    _write_native_notebook(path)
    model = EditorModel(tmp_path)
    doc = model.open_file(path)
    doc.notebook.cells[0].editor.set_text("unsaved = 1")
    assert not model.reload_document()
    assert doc.notebook.cells[0].editor.text == "unsaved = 1"
    assert model.reload_document(discard_changes=True)
    assert model.active_doc is doc
    assert "value = 21" in doc.notebook.cells[0].editor.text
    export = tmp_path / "example.py"
    assert model.export_notebook(export)
    assert "# %% [markdown]" in export.read_text()
    assert "# # Heading" in export.read_text()
    assert doc.path == str(path)
    assert not doc.is_modified


def test_native_notebook_background_input_prompt_resumes_execution():
    import time

    from chisurf.plugins.core.code_editor.gui.notebook_app import NativeNotebook

    notebook = NativeNotebook.new()
    notebook.active_cell.editor.set_text("name = input('Your name: ')\nprint('Hello ' + name)")
    assert notebook.start_cell(0)
    deadline = time.monotonic() + 3
    while notebook.pending_input is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert notebook.pending_input["prompt"] == "Your name: "
    with im.frame(RecordingPainter(), (0, 0, 1000, 720)):
        notebook.draw(1000, 720)
    notebook.respond_input("Ada")
    notebook._execution_thread.join(timeout=3)
    assert not notebook.is_running
    assert any("Hello Ada" in output.get("text", "") for output in notebook.active_cell.outputs)
    notebook.close()


def test_native_notebook_close_cancels_waiting_input():
    import time

    from chisurf.plugins.core.code_editor.gui.notebook_app import NativeNotebook

    notebook = NativeNotebook.new()
    notebook.active_cell.editor.set_text("input('Waiting: ')")
    notebook.start_cell(0)
    deadline = time.monotonic() + 3
    while notebook.pending_input is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert notebook.pending_input is not None
    notebook.close()
    notebook._execution_thread.join(timeout=3)
    assert not notebook.is_running
    assert notebook.pending_input is None


def test_native_completion_utf16_ranges_additional_edits_and_snippets(tmp_path):
    model = EditorModel(tmp_path)
    doc = model.active_doc
    doc.text = "😀foo\n"
    item = {
        "label": "foobar",
        "insertTextFormat": 2,
        "textEdit": {
            "range": {"start": {"line": 0, "character": 2}, "end": {"line": 0, "character": 5}},
            "newText": "foobar(${1:x})$0",
        },
        "additionalTextEdits": [
            {
                "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
                "newText": "import thing\n",
            }
        ],
    }
    assert model.apply_completion(item)
    assert doc.text == "import thing\n😀foobar(x)\n"
    assert doc.editor.cursors.main.end.line == 1
    assert doc.editor.cursors.main.end.index == 10
    doc.editor.undo()
    assert doc.text == "😀foo\n"
    model.close()


def test_native_save_as_direct_call_does_not_overwrite_existing_file(tmp_path):
    path = tmp_path / "existing.py"
    path.write_text("original")
    model = EditorModel(tmp_path)
    assert not model.save_document(path=path)
    assert path.read_text() == "original"
    assert model.active_doc.path is None
    assert model.save_document(path=path, overwrite=True)
    model.close()


def test_native_save_as_reuses_chooser_overwrite_confirmation(tmp_path, monkeypatch):
    path = tmp_path / "existing.py"
    path.write_text("original")
    model = EditorModel(tmp_path)
    doc = model.active_doc
    doc.text = "confirmed replacement"
    gui = CodeEditorGui(model)
    gui._request_save(doc)
    gui._file_dialog.overwrite_confirmed = True
    monkeypatch.setattr(gui._file_dialog, "draw", lambda: [str(path)])
    with im.frame(RecordingPainter(), (0, 0, 1000, 700)):
        gui._draw_file_dialog()
    assert gui._overwrite_path is None
    assert gui._file_dialog is None
    assert path.read_text() == "confirmed replacement"
    model.close()


def test_native_notebook_rich_html_tables_render_instead_of_plain_fallback():
    from chisurf.plugins.core.code_editor.gui.notebook_app import NativeNotebook

    notebook = NativeNotebook.new()
    output = {
        "output_type": "display_data",
        "metadata": {},
        "data": {
            "text/plain": "PLAIN FALLBACK",
            "text/html": "<style>hidden css</style><h2>Measurements</h2><table><tr><th>State</th><th>Value</th></tr><tr><td>Open</td><td><b>42</b></td></tr></table>",
        },
    }
    notebook.active_cell.outputs.append(output)
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 1000, 720)):
        notebook.draw(1000, 720)
    rendered = "\n".join(painter.strings)
    assert "Measurements" in rendered
    assert "State" in rendered
    assert "Open" in rendered
    assert "42" in rendered
    assert "PLAIN FALLBACK" not in rendered
    assert "hidden css" not in rendered
    assert notebook.to_dict()["cells"][0]["outputs"] == [output]
    notebook.close()


def test_acp_buffer_operations_are_queued_to_native_render_thread(tmp_path):
    import threading
    import time

    model = EditorModel(tmp_path)
    path = tmp_path / "buffer.py"
    path.write_text("disk content")
    model.open_file(path)
    chat = ChatModel(editor_ref=model)
    main_thread = threading.get_ident()
    threads = []
    original = model.set_file_content

    def write(path, content):
        threads.append(threading.get_ident())
        return original(path, content)

    model.set_file_content = write
    result = []
    worker = threading.Thread(
        target=lambda: (
            chat._handle_write_file(str(path), "unsaved RPC content"),
            result.append(chat._handle_read_file(str(path))),
        )
    )
    worker.start()
    deadline = time.monotonic() + 3
    while worker.is_alive() and time.monotonic() < deadline:
        model.process_events()
        time.sleep(0.01)
    worker.join(timeout=1)
    assert result == ["unsaved RPC content"]
    assert threads == [main_thread]
    assert path.read_text() == "disk content"
    chat.close()
    model.close()


def test_native_editor_rpc_store_updates_uuid_and_keeps_other_owners(tmp_path):
    import uuid

    from chisurf.plugins.core.code_editor.backend import services

    first = EditorModel(tmp_path)
    other = EditorModel(tmp_path)
    doc = first.active_doc
    uuid.UUID(doc.document_id)
    first.process_events()
    payload = services.dispatch("editor.document.get", {"document_id": doc.document_id})
    assert payload["ok"]
    revision = payload["document"]["revision"]
    result = services.dispatch(
        "editor.document.set",
        {
            "document_id": doc.document_id,
            "content": "RPC changed source",
            "expected_revision": revision,
        },
    )
    assert result["ok"]
    first.process_events()
    assert doc.text == "RPC changed source"
    assert doc.is_modified
    identity = doc.document_id
    assert first.save_document(path=tmp_path / "rpc_saved.py")
    assert doc.document_id == identity
    payload = services.dispatch("editor.document.get", {"path": str(tmp_path / "rpc_saved.py")})
    assert payload["document"]["document_id"] == identity
    assert payload["document"]["content"] == "RPC changed source"
    first.close()
    assert services.STORE.get(document_id=identity) is None
    assert services.STORE.get(document_id=other.active_doc.document_id) is not None
    other.close()


def test_native_editor_preferences_restore_only_declared_metadata(tmp_path):
    app = CodeEditorApp(tmp_path)
    source = tmp_path / "recent.py"
    source.write_text("private source")
    app.model.open_file(source)
    app.model.run_endpoint = "console"
    app.model.font_scale = 1.4
    exported = app.export_settings()
    assert str(source) in exported["recent_files"]
    assert "private source" not in repr(exported)
    fresh = CodeEditorApp(tmp_path)
    fresh.restore_settings(exported)
    assert fresh.model.run_endpoint == "console"
    assert fresh.model.font_scale == 1.4
    assert fresh.model.recent_files == [str(source)]
    assert len(fresh.model.documents) == 1  # Preferences do not reopen or serialize buffers.
    app.close()
    fresh.close()


def test_native_editor_close_releases_queued_rpc_without_late_writes(tmp_path):
    import threading
    import time

    model = EditorModel(tmp_path)
    errors = []
    writes = []

    def call():
        try:
            model.invoke(lambda: writes.append("written"))
        except RuntimeError as error:
            errors.append(str(error))

    worker = threading.Thread(target=call)
    worker.start()
    deadline = time.monotonic() + 2
    while model.event_queue.empty() and time.monotonic() < deadline:
        time.sleep(0.01)
    model.close()
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert errors and "closed" in errors[0]
    assert not writes


def test_native_editor_rpc_and_local_conflict_keeps_both_versions(tmp_path):
    from chisurf.plugins.core.code_editor.backend import services

    model = EditorModel(tmp_path)
    doc = model.active_doc
    snapshot = services.STORE.get(document_id=doc.document_id)
    doc.text = "local unsynced source"
    result = services.dispatch(
        "editor.document.set",
        {
            "document_id": doc.document_id,
            "content": "remote source",
            "expected_revision": snapshot.revision,
        },
    )
    assert result["ok"]
    model.process_events()
    assert doc.text == "local unsynced source"
    assert any(other.text == "remote source" for other in model.documents if other is not doc)
    assert any("Concurrent RPC" in message for message in model.output_logs)
    model.close()


def test_native_acp_conversation_handshake_and_buffer_rpc(tmp_path, monkeypatch):
    import importlib
    import sys
    import time

    from chisurf.plugins.core.code_editor.acp_client import AcpClient
    from chisurf.plugins.core.code_editor.backend import services

    path = tmp_path / "buffer.py"
    path.write_text("disk source")
    server = tmp_path / "fake_acp.py"
    server.write_text("""import json, sys
prompt_id = None
for line in sys.stdin.buffer:
    message = json.loads(line)
    method = message.get("method")
    params = message.get("params", {})
    def send(value):
        sys.stdout.write(json.dumps(value) + "\\n"); sys.stdout.flush()
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": message["id"], "result": {"agentInfo": {}, "agentCapabilities": {}}})
    elif method == "session/new":
        send({"jsonrpc": "2.0", "id": message["id"], "result": {"sessionId": "session_test"}})
    elif method == "session/set_mode":
        send({"jsonrpc": "2.0", "id": message["id"], "result": {"currentModeId": params["modeId"]}})
    elif method == "session/prompt":
        prompt_id = message["id"]
        send({"jsonrpc": "2.0", "id": "client-write", "method": "fs/write_text_file", "params": {"path": sys.argv[1], "content": "RPC-written source"}})
    elif message.get("id") == "client-write":
        assert "error" not in message
        send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "session_test", "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Updated your buffer"}}}})
        send({"jsonrpc": "2.0", "id": prompt_id, "result": {"stopReason": "end_turn"}})
""")
    module = importlib.import_module("chisurf.plugins.core.code_editor.gui.chat_app")
    original = AcpClient
    monkeypatch.setattr(
        module,
        "AcpClient",
        lambda **kwargs: original(command=[sys.executable, str(server), str(path)], **kwargs),
    )
    editor = EditorModel(tmp_path)
    doc = editor.open_file(path)
    chat = ChatModel(editor_ref=editor)
    chat.send_prompt("Update the open buffer")
    deadline = time.monotonic() + 5
    while chat.is_generating and time.monotonic() < deadline:
        editor.process_events()
        chat.process_events()
        time.sleep(0.01)
    assert not chat.is_generating
    assert chat.history.messages[-1].content == "Updated your buffer"
    assert doc.text == "RPC-written source"
    assert services.STORE.get(document_id=doc.document_id).content == doc.text
    assert path.read_text() == "disk source"
    chat.close()
    editor.close()


def test_native_chat_cancel_blocks_overlap_and_discards_late_response(monkeypatch):
    import threading

    model = ChatModel()
    model.provider = "openai"
    started = threading.Event()
    release = threading.Event()

    def prompt(text):
        started.set()
        release.wait(timeout=3)
        model._on_runtime_event("message.completed", {"content": "late response"})
        model._on_acp_prompt_finished("", "cancelled")

    monkeypatch.setattr(model, "_run_in_process_prompt", prompt)
    model.send_prompt("first")
    assert started.wait(timeout=1)
    model.cancel()
    model.send_prompt("overlapping second prompt")
    assert [message.content for message in model.history.messages] == ["first"]
    release.set()
    model._in_process_thread.join(timeout=2)
    model.process_events()
    assert not model.is_generating
    assert all(message.content != "late response" for message in model.history.messages)
    model.close()


def test_native_long_permission_details_keep_action_buttons_visible():
    model = ChatModel()
    model.pending_permission = {
        "title": "A long tool argument " * 200,
        "options": [
            {"optionId": "allow_once", "name": "Allow once"},
            {"optionId": "deny_once", "name": "Deny"},
        ],
    }
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 600)):
        ChatGui(model)._draw_permission_banner()
    button = next(text for text in painter.texts if text[5] == "Allow once")
    assert button[1] < 250
    model.close()


def test_native_editor_external_rpc_wakes_idle_host(tmp_path):
    import threading
    import time

    from chisurf.plugins.core.code_editor.backend import services

    app = CodeEditorApp(tmp_path)
    wakes = []
    app.set_frame_request_callback(lambda: wakes.append("wake"))
    worker = threading.Thread(target=lambda: app.model.invoke(lambda: None))
    worker.start()
    deadline = time.monotonic() + 2
    while not wakes and time.monotonic() < deadline:
        time.sleep(0.01)
    assert wakes
    app.model.process_events()
    worker.join(timeout=1)
    wakes.clear()
    services.dispatch(
        "editor.document.set",
        {"document_id": app.model.active_doc.document_id, "content": "external source"},
    )
    assert wakes
    app.model.process_events()
    assert app.model.active_doc.text == "external source"
    app.close()


def test_native_editor_undo_to_saved_source_clears_modified_marker(tmp_path):
    model = EditorModel(tmp_path)
    doc = model.active_doc
    baseline = doc.text
    model.insert_code_at_cursor("# changed\n")
    assert doc.is_modified
    doc.editor.undo()
    assert doc.text == baseline
    assert not doc.is_modified
    model.close()


def test_native_editor_real_rpc_transport_updates_buffer_and_stops(tmp_path):
    import socket

    from chisurf.server.transport.zmq import ZmqClient

    def free_port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    cmd, pub = free_port(), free_port()
    while pub == cmd:
        pub = free_port()
    app = CodeEditorApp(tmp_path)
    client = None
    try:
        assert app.model.start_rpc(cmd_port=cmd, pub_port=pub)
        client = ZmqClient(cmd_port=cmd, pub_port=pub, timeout_ms=2000)
        response = client.call(
            "editor.document.set",
            {"document_id": app.model.active_doc.document_id, "content": "real transport source"},
        )
        assert response["result"]["ok"], response
        app.model.process_events()
        assert app.model.active_doc.text == "real transport source"
        app.model.stop_rpc()
        assert app.model._rpc_server is None
    finally:
        if client is not None:
            client.close()
        app.close()


def test_native_editor_rpc_bind_failure_returns_actionable_error(tmp_path, monkeypatch):
    from chisurf.plugins.core.code_editor.rpc_server import EditorRpcServer

    def fail(self):
        raise OSError("port already occupied")

    monkeypatch.setattr(EditorRpcServer, "start", fail)
    model = EditorModel(tmp_path)
    assert not model.start_rpc()
    assert "port already occupied" in model.rpc_status
    assert model._rpc_server is None
    model.close()


def test_native_editor_full_color_and_lint_preferences_apply_and_roundtrip(tmp_path, monkeypatch):
    from chisurf.plugins.core.code_editor.ruff_runner import RuffRunner

    model = EditorModel(tmp_path)
    from chisurf.plugins.core.code_editor.gui.editor_preferences import font_choices

    family = font_choices()[-1]
    model.restore_settings(
        {
            "color_scheme": "Light",
            "paper_color": "#eeeeee",
            "default_color": "#112233",
            "margins_background_color": "#dddddd",
            "marker_background_color": "#778899",
            "caret_line_background_color": "#abcdee",
            "caret_line_visible": False,
            "font_family": family,
            "font_size": 14,
            "language": "JSON",
            "enable_ruff": True,
            "run_ruff_on_save": True,
            "ruff_timeout_ms": 3210,
            "ruff_extra_args": ["--select", "F"],
        }
    )
    doc = model.active_doc
    model.apply_editor_preferences(doc.editor)
    assert doc.editor.config.background_color[:3] == (238, 238, 238)
    assert doc.editor.config.margin_color[:3] == (221, 221, 221)
    assert not doc.editor.config.highlight_current_line
    assert doc.editor.language_name == "JSON"
    calls = []
    monkeypatch.setattr(
        RuffRunner,
        "check",
        lambda self, path, content, **kwargs: (
            calls.append(kwargs) or {"ok": True, "diagnostics": []}
        ),
    )
    model.run_ruff()
    assert calls[-1]["timeout_ms"] == 3210
    assert calls[-1]["extra_args"] == ["--select", "F"]
    triggered = []
    monkeypatch.setattr(model, "start_ruff", lambda fix=False: triggered.append("check"))
    assert model.save_document(path=tmp_path / "settings.py")
    assert triggered == ["check"]
    saved = model.export_settings()
    assert saved["font_family"] == family
    assert saved["font_size"] == 14
    assert saved["paper_color"] == "#eeeeee"
    assert saved["ruff_timeout_ms"] == 3210
    model.close()


def test_native_editor_settings_controls_apply_real_colors(tmp_path, monkeypatch):
    model = EditorModel(tmp_path)
    gui = CodeEditorGui(model)
    tooltips = []
    monkeypatch.setattr(im, "set_item_tooltip", lambda text: tooltips.append(text))
    original = im.color_edit3
    monkeypatch.setattr(
        im,
        "color_edit3",
        lambda label, color: (True, (40, 50, 60)) if label == "Paper" else original(label, color),
    )
    with im.frame(RecordingPainter(), (0, 0, 800, 1200)):
        gui._draw_settings_panel()
    model.apply_editor_preferences(model.active_doc.editor)
    assert model.active_doc.editor.config.background_color == (40, 50, 60, 255)
    assert any("Ruff" in tooltip for tooltip in tooltips)
    assert any("monospaced" in tooltip for tooltip in tooltips)
    model.close()


def test_native_chat_provider_setup_rejects_invalid_acp_command():
    import types

    model = ChatModel()
    errors = []
    settings = types.SimpleNamespace(
        provider="acp",
        command='agent "unclosed',
        temperature=0.4,
        _set_status=lambda text, color: errors.append(text),
    )
    original = list(model.acp_client.command)
    assert not model.use_provider_settings(settings)
    assert model.acp_client.command == original
    assert "Invalid ACP command" in errors[-1]
    settings.command = 'agent --stdio "quoted path"'
    assert model.use_provider_settings(settings)
    assert model.acp_client.command == ["agent", "--stdio", "quoted path"]
    assert "api_key" not in model.export_settings()
    model.close()
