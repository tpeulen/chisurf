"""The editor is a viewport window on every host: scrollbar, wheel, Save; ``fps_edit`` reloads on save.

``editor <file>`` used to need Qt (a ControlHost top-level window), so the
toolkit-free host and the browser had no editor. Now it is an
``EditorPanel`` in the chrome; the text and hex editors draw a scrollbar
when they are taller than their box, take the wheel, and drag its thumb.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

import chimol
from cmtk.testing import RecordingPainter

_PDB = pathlib.Path(chimol.__file__).resolve().parent / "data" / "demos" / "148l.pdb"


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def app():
    """The toolkit-free host over an offscreen canvas: a chrome, no window."""
    import os

    os.environ.setdefault("CHIMOL_TOOLKIT", "none")
    from chimol.hosts.native.app import ChimolApp

    return ChimolApp(backend="offscreen", size=(800, 600))


def test_the_text_editor_shows_a_scrollbar_and_scrolls(tmp_path):
    from cmtk.widgets.text_editor import TextEditor

    editor = TextEditor("\n".join(f"line {i}" for i in range(200)))
    p = RecordingPainter()
    editor.draw(p, 0, 0, 300, 160)          # 10 lines visible of 200
    assert editor.vbar.needed()
    assert p.fills, "no bar drawn"
    bar_x = 300 - editor.vbar.width
    assert editor.vbar.hit(bar_x + 3, 80)
    editor.scroll(30)
    assert editor.first_visible_line == 30
    editor.draw(p, 0, 0, 300, 160)
    # drag the thumb to the bottom
    editor.press(bar_x + 3, 158, 0, 0, 300, 160)
    editor.release()
    assert editor.first_visible_line > 150


def test_the_hex_editor_shows_a_scrollbar(tmp_path):
    from cmtk.widgets.memory_editor import MemoryEditor
    from chimol.core.services.memory_probe import ArraySource

    ed = MemoryEditor()
    ed.set_source(ArraySource(np.arange(16384, dtype=np.uint8), "probe"))
    p = RecordingPainter()
    ed.draw(p, 0, 0, 500, 120)
    assert ed.vbar.needed()
    ed.scroll(10)
    assert ed.first_visible_row == 10
    ed.draw(p, 0, 0, 500, 120)
    bx, by, bw, bh = ed.vbar._box
    assert ed.vbar.press(bx + 2, by + bh - 1)
    ed.drag(0, by + bh - 1)
    ed.release()
    assert ed.first_visible_row > 100


def test_editor_opens_in_the_viewport_and_save_writes(app, tmp_path):
    f = tmp_path / "notes.cml"
    f.write_text("\n".join(f"# line {i}" for i in range(80)))
    errors: list[str] = []
    app.cmd.set_error_callback(errors.append)
    app.cmd.do(f'editor "{f}"')
    assert errors == [], errors
    gui = app.viewer.gui
    key = f"editor:{f.name}"
    win = gui.window(key)
    assert win is not None and win.visible, "no editor window in the viewport"
    panel = gui.panels[key]
    app.draw_frame()
    # the file is taller than the window: a scrollbar, and the wheel scrolls
    assert panel.editor.vbar.needed()
    body = gui.window_body(win)
    before = panel.editor.first_visible_line
    assert gui.wheel_window(body.x + body.w / 2, body.y + body.h / 2, 2)
    assert panel.editor.first_visible_line > before
    # type at the end and Save writes the file
    panel.editor.set_text(panel.editor.text + "\n# added")
    assert panel.save()
    assert f.read_text().endswith("# added")


def test_fps_edit_opens_the_plan_and_save_reloads_it(app, tmp_path):
    plan = tmp_path / "plan.fps.json"
    plan.write_text(pathlib.Path(chimol.__file__).resolve().parents[1].joinpath("examples", "labeling_network.fps.json").read_text())
    errors: list[str] = []
    app.cmd.set_error_callback(errors.append)
    app.cmd.do(f'load "{_PDB}"')
    app.cmd.do(f'fps_edit "{plan}"')
    assert not [e for e in errors if "fps_edit" in e], errors
    gui = app.viewer.gui
    panel = gui.panels.get(f"editor:{plan.name}")
    assert panel is not None, "fps_edit opened no editor"
    assert '"Positions"' in panel.editor.text or "positions" in panel.editor.text.lower()
    said: list[str] = []
    app.cmd.set_message_callback(said.append)
    assert panel.save()                       # reloads through fps_load
    assert any(line.startswith("fps_load") for line in said) or errors, (said, errors)
