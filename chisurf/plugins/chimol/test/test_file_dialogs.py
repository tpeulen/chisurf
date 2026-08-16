"""Open and Save are the **in-viewport file dialog** -- every host, no Qt.

The hosts that could show a file chooser each had a different answer -- Qt
on the desktop, the operating system's own panels on the toolkit-free host
(``osascript``/``zenity``, removed once this landed), and *nothing* in a
browser, where a page cannot spawn a process at all. The dialog is now one
code path drawn by the same engine that draws the menus (a port of the
L2DFileDialog interaction model; the annotated reference lives in the
chisurf checkout's ``junk/``): folders left, files right, ".." goes up, a
single click selects, a double click enters or takes, a read-only line
carries the path, Cancel / Choose at the bottom, a red error when Choose
runs with nothing chosen.

What is pinned here, in the toolkit-free subprocess probe (Qt
**unimportable** in the child):

* the dialog model: filtering, navigation, the save-name default
  extension, the choose/cancel contract;
* the wiring: ``open`` with no path opens the dialog, a double click on a
  row loads that file, a ``file_prompt`` menu entry runs its command on
  the chosen path quoted, and nothing runs on cancel;
* the render: the grab actually contains the dialog -- buttons in the
  chrome's button blue, panes dark, title bar the active-window blue --
  because a panel that layout forgot to draw passes every behaviour test
  and helps nobody;
* the quote fix this surfaced: ``png "<path>"`` used to write a file
  *named with the quotes*; ``save``/``png``/``edit`` strip them now.
"""

from __future__ import annotations

import pytest

pytest.importorskip("rendercanvas", reason="the offscreen canvas host")

from toolkit_free import DATA, probe  # noqa: E402

_PDB_DIR = DATA / "atomic_coordinates" / "pdb_files"
_PDB = _PDB_DIR / "148l.pdb"


def test_filter_sections_and_dialog_model():
    """Filters parse; navigation, selection and save names behave."""
    import tempfile
    from pathlib import Path

    from chimol.renderer.file_dialog import FileDialog, parse_filter

    pairs = parse_filter("Structures (*.pdb *.cif);;All files (*.*)")
    assert pairs[0] == ("Structures", ["*.pdb", "*.cif"])
    assert pairs[1] == ("All files", ["*.*"])

    tmp = Path(tempfile.mkdtemp())
    (tmp / "sub").mkdir()
    (tmp / "a.pdb").write_text("x")
    (tmp / "b.png").write_text("x")
    (tmp / "c.txt").write_text("x")

    d = FileDialog(mode="open", file_type="PDB (*.pdb);;All files (*.*)",
                   start_dir=tmp)
    assert d.folders == ["sub"] and d.files == ["a.pdb"]
    d.selected_file = "a.pdb"
    assert d.selected_path() == tmp / "a.pdb"
    d.filter_index = 1
    d.refresh()
    assert sorted(d.files) == ["a.pdb", "b.png", "c.txt"]
    d.enter("sub")
    assert d.path.name == "sub"
    d.enter("..")
    assert d.path == tmp.resolve()

    s = FileDialog(mode="save", file_type="Images (*.png)", start_dir=tmp)
    s.name_field.set_text("out")
    assert s.selected_path() == tmp / "out.png", (
        "a typed name without a suffix must gain the filter's default"
    )
    s.name_field.set_text("")
    assert s.selected_path() is None
    picked = []
    s.on_choose = picked.append
    s._closer = lambda: None
    s.name_field.set_text("shot")
    assert s.choose() is True
    assert picked == [str(tmp / "shot.png")]


_DRIVE = '''
    import pathlib

    app = open_app(size=(1000, 780))
    errors = []
    app.cmd.set_message_callback(lambda _m: None)
    app.cmd.set_error_callback(errors.append)

    # `open` with no path opens the in-viewport dialog, rooted where the
    # host's last-open guess says -- pointed at the pdb_files dir here.
    app._open_structure_dialog()
    gui = app.renderer._internal_gui
    win = gui.window("file_dialog")
    emit("visible", str(bool(win and win.visible)))
    d = win.on_key
    d.path = pathlib.Path({start!r})
    d.refresh()
    emit("folders", ",".join(d.folders[:4]))
    emit("files", ",".join(n for n in d.files if n.endswith(".pdb")))

    # A double click on a row chooses it: press pair through the renderer,
    # exactly as a host delivers it.
    from chimol.host.events import LEFT_BUTTON
    body = gui.window_body(win)
    d.layout(body)
    row = next(r for r, n in d._file_rows if n == "148l.pdb")
    cx, cy = row.x + row.w / 2, row.y + row.h / 2
    app.renderer.on_pointer_press(cx, cy, LEFT_BUTTON, 0, double=True)
    app.renderer.on_pointer_release(cx, cy, LEFT_BUTTON, 0)
    sources = [str(getattr(e, "source_path", "") or "")
               for e in app.viewer._objects.values()]
    emit("loaded", str(any(s.endswith("148l.pdb") for s in sources)))
    emit("closed_after_choose", str(not win.visible))

    # A file_prompt entry in save mode: the typed name gains .png, the
    # command runs on the quoted path, and the PNG is real.
    out = pathlib.Path({out!r})
    app._on_file_prompt("png {{text}}", "save", "Save image", "Images (*.png)")
    win2 = gui.window("file_dialog")
    d2 = win2.on_key
    d2.path = out.parent
    d2.refresh()
    d2.name_field.set_text(out.stem)
    emit("chose", str(d2.choose()))
    emit("png_written", str(out.is_file() and out.stat().st_size > 500))
    emit("quoted_junk", str((out.parent / ('"' + out.name + '"')).exists()))

    # Render: the dialog must actually draw, not only compute.
    app.host.on_open_structure()
    win3 = gui.window("file_dialog")
    win3.on_key.path = pathlib.Path({start!r})
    win3.on_key.refresh()
    gui.raise_window("file_dialog")
    import numpy as np
    arr = np.array(app.renderer.grab_image()).astype(int)
    body3 = gui.window_body(win3)
    win3.on_key.layout(body3)
    boxes = win3.on_key._boxes
    def px(box):
        y = int(min(max(boxes[box].y + boxes[box].h / 2, 0), arr.shape[0] - 1))
        x = int(min(max(boxes[box].x + boxes[box].w / 2, 0), arr.shape[1] - 1))
        return tuple(int(v) for v in arr[y, x])
    emit("up_px", px("up"))
    emit("choose_px", px("choose"))
    emit("pane_px", px("files"))
    ty = int(min(max(win3.y + 6, 0), arr.shape[0] - 1))
    tx = int(min(max(win3.x + win3.w / 2, 0), arr.shape[1] - 1))
    emit("title_px", tuple(int(v) for v in arr[ty, tx]))
    emit("errors", "; ".join(errors[:3]) or "none")
'''


def test_open_save_and_render_through_the_dialog():
    """Open loads, save writes a real PNG, and the panel actually draws."""
    import tempfile
    from pathlib import Path

    out = Path(tempfile.mkdtemp(prefix="fdlg-test-")) / "shot.png"
    m = probe(_DRIVE.format(start=str(_PDB_DIR), out=str(out)), block_qt=True)
    assert m["visible"] == "True"
    assert "148l" in m["files"]
    assert m["loaded"] == "True", "the double click did not load the file"
    assert m["closed_after_choose"] == "True"
    assert m["chose"] == "True"
    assert m["png_written"] == "True", "save did not write the PNG"
    assert m["quoted_junk"] == "False", "the quotes leaked into the filename"
    # BUTTON_BG (157,157,255) buttons, dark panes, active-blue title bar.
    assert m["up_px"] == "(157, 157, 255)", m["up_px"]
    assert m["choose_px"] == "(157, 157, 255)", m["choose_px"]
    assert sum(int(v) for v in m["pane_px"].strip("()").split(", ")) < 200
    assert m["title_px"] == "(41, 74, 122)", m["title_px"]
    assert m["errors"] == "none", m["errors"]


def test_browser_host_gets_the_same_dialog():
    """The page wires the same two hooks -- no system panel exists there."""
    from chimol.renderer.file_dialog import open_file_dialog
    from chimol.web.demo import Viewer  # noqa: F401 - import proves Qt-free

    import inspect

    source = inspect.getsource(Viewer)
    assert "open_file_dialog" in source, (
        "the browser host no longer wires the in-viewport file dialog"
    )
    assert "on_open_structure" in source and "on_file_prompt" in source
    assert callable(open_file_dialog)
