"""Notebook keyboard execution must follow the familiar cell workflow."""

from __future__ import annotations

from emtk import im
from emtk.events import SHIFT_MODIFIER
from emtk.testing import RecordingPainter

from chisurf.plugins.core.code_editor.gui.notebook_app import NativeNotebook


def test_shift_enter_runs_cell_and_focuses_or_creates_the_next(tmp_path):
    notebook = NativeNotebook.new()
    notebook.path = str(tmp_path / "shortcut.ipynb")
    notebook.active_cell.editor.set_text("print('cell executed')")
    storage = {}

    with im.frame(RecordingPainter(), (0, 0, 1200, 800), storage=storage) as context:
        context.push_id(notebook.active_cell.node["id"])
        editor_id = context.get_id("##cell_source")
        context.pop_id()
        context.state(("focus",))["id"] = editor_id
        context.io.key = 0x01000004
        context.io.text = "\r"
        context.io.key_shift = True
        context.io.key_events = [(0x01000004, "\r", SHIFT_MODIFIER)]
        notebook.draw(1100, 720)

    assert notebook._execution_thread is not None
    notebook._execution_thread.join(timeout=30)
    assert not notebook.is_running
    assert any("cell executed" in output.get("text", "") for output in notebook.cells[0].outputs)

    with im.frame(RecordingPainter(), (0, 0, 1200, 800), storage=storage):
        notebook.draw(1100, 720)
    assert len(notebook.cells) == 2
    assert notebook.active_index == 1
    assert storage[("__state__", ("focus",))]["id"] == (notebook.cells[1].node["id"], "cell_source")
    notebook.close()


def test_visible_run_button_executes_the_cell(monkeypatch, tmp_path):
    notebook = NativeNotebook.new()
    notebook.path = str(tmp_path / "run-button.ipynb")
    notebook.active_cell.editor.set_text("print('button executed')")
    storage = {}
    painter = RecordingPainter()
    button = im.button
    run_rect = {}

    def remember_run(label, size=None):
        result = button(label, size)
        if label == "▶ Run · Shift+Enter":
            run_rect["box"] = im.get_item_rect()
        return result

    monkeypatch.setattr(im, "button", remember_run)
    with im.frame(painter, (0, 0, 1200, 800), storage=storage):
        notebook.draw(1100, 720)
    box = run_rect["box"]
    io = im.IO()
    io.mouse_pos = (box[0] + box[2] / 2, box[1] + box[3] / 2)
    io.mouse_down[0] = True
    io.mouse_clicked[0] = True
    with im.frame(RecordingPainter(), (0, 0, 1200, 800), io=io, storage=storage):
        notebook.draw(1100, 720)
    io.mouse_down[0] = False
    io.mouse_released[0] = True
    with im.frame(RecordingPainter(), (0, 0, 1200, 800), io=io, storage=storage):
        notebook.draw(1100, 720)
    notebook._execution_thread.join(timeout=30)
    assert not notebook.is_running
    assert any("button executed" in output.get("text", "") for output in notebook.cells[0].outputs)
    notebook.close()
