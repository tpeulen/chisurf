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

    from chimol.ui.dialogs.file_dialog import FileDialog, parse_filter

    pairs = parse_filter("Structures (*.pdb *.cif);;All files (*.*)")
    assert pairs[0] == ("Structures", ["*.pdb", "*.cif"])
    assert pairs[1] == ("All files", ["*.*"])

    tmp = Path(tempfile.mkdtemp())
    (tmp / "sub").mkdir()
    (tmp / "a.pdb").write_text("x")
    (tmp / "b.png").write_text("x")
    (tmp / "c.txt").write_text("x")

    d = FileDialog(mode="open", file_type="PDB (*.pdb);;All files (*.*)", start_dir=tmp)
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


_DRIVE = """
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
    from emtk.events import LEFT_BUTTON
    body = gui.window_body(win)
    d.layout(body)
    from chimol.ui.dialogs.file_dialog import ROW_H

    def row_xy(d, name):
        # The middle of a file row, as a click lands on it (panes are ListViews).
        index = d._file_model.index_of(name)
        box = d._boxes["files"]
        return box.x + 20.0, box.y + (index - d._file_list.scrollbar.top + 0.5) * ROW_H
    # The panes learn their boxes when drawn: draw a frame before clicking.
    win.body_revision += 1
    app.renderer._chrome_quads()
    cx, cy = row_xy(d, "148l.pdb")
    # The desktop hosts' double-click order: press, release, press(double), release.
    app.renderer.on_pointer_press(cx, cy, LEFT_BUTTON, 0)
    app.renderer.on_pointer_release(cx, cy, LEFT_BUTTON, 0)
    app.renderer.on_pointer_press(cx, cy, LEFT_BUTTON, 0, double=True)
    app.renderer.on_pointer_release(cx, cy, LEFT_BUTTON, 0)
    sources = [str(getattr(e, "source_path", "") or "")
               for e in app.viewer.objects.values()]
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
"""


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


_KEYS_DRIVE = """
    import pathlib, tempfile
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="fdlg-keys-"))
    for i in range(30):
        (tmp / f"file{i:02d}.pdb").write_text("x")
    for i in range(25):
        (tmp / f"dir{i:02d}").mkdir()
    app = open_app(size=(1000, 780))
    errors = []
    app.cmd.set_message_callback(lambda _m: None)
    app.cmd.set_error_callback(errors.append)
    from emtk.keys import KEY_DOWN, KEY_PAGE_DOWN, KEY_RETURN
    from emtk.events import LEFT_BUTTON

    app._open_structure_dialog()
    gui = app.renderer._internal_gui
    win = gui.window("file_dialog")
    d = win.on_key
    d.path = tmp
    d.refresh()
    body = gui.window_body(win)
    d.layout(body)
    from chimol.ui.dialogs.file_dialog import ROW_H

    def row_xy(d, name):
        # The middle of a file row, as a click lands on it (panes are ListViews).
        index = d._file_model.index_of(name)
        box = d._boxes["files"]
        return box.x + 20.0, box.y + (index - d._file_list.scrollbar.top + 0.5) * ROW_H

    # A press focuses the dialog: keys must route somewhere after a click.
    win.body_revision += 1
    app.renderer._chrome_quads()
    cx, cy = row_xy(d, "file00.pdb")
    app.renderer.on_pointer_press(cx, cy, LEFT_BUTTON, 0)
    app.renderer.on_pointer_release(cx, cy, LEFT_BUTTON, 0)
    emit("focused", str(gui.focused_field is d))

    for _ in range(4):
        app.renderer.on_key_press(KEY_DOWN, "", 0)
    emit("nav", d.selected_file)
    app.renderer.on_key_press(KEY_PAGE_DOWN, "", 0)
    emit("paged", d.selected_file)
    emit("nav_scrolled", d._file_list.scrollbar.top)

    # The scrollbar is real: dragged through the pointer path, it moves the
    # list, and no further than the list goes.
    d._file_list.scrollbar.top = 0
    gui.window("file_dialog").body_revision += 1
    app.renderer._chrome_quads()
    box = d._boxes["files"]
    bar_x = box.x + box.w - 3.0
    app.renderer.on_pointer_press(bar_x, box.y + 6.0, LEFT_BUTTON, 0)
    app.renderer.on_pointer_move(bar_x, box.y + box.h - 6.0, LEFT_BUTTON, 0)
    app.renderer.on_pointer_release(bar_x, box.y + box.h - 6.0, LEFT_BUTTON, 0)
    top = d._file_list.scrollbar.top
    emit("thumb_drag", top)
    emit("thumb_bounds_ok", str(top <= max(len(d.files) - d._file_list.visible_rows(box.h), 0)))

    # The wheel scrolls the pane under the pointer: folders over folders.
    d._file_list.scrollbar.top = 0
    d._folder_list.scrollbar.top = 0
    fbox = d._boxes["folders"]
    # Negative notches scroll down, on every host (BUG-003).
    app.renderer.on_wheel(fbox.x + 10, fbox.y + 10, -2, 0)
    emit("folders_wheeled", d._folder_list.scrollbar.top)
    app.renderer.on_wheel(d._boxes["files"].x + 10, fbox.y + 10, -2, 0)
    emit("files_wheeled", d._file_list.scrollbar.top)

    # Save mode: click the name line, type, Enter -- Enter must be Choose,
    # which it was not when the bare field held the focus.
    app._on_file_prompt("png {text}", "save", "Save image", "Images (*.png)")
    d2 = gui.window("file_dialog").on_key
    d2.path = tmp
    d2.refresh()
    d2.layout(gui.window_body(gui.window("file_dialog")))
    sel = d2._boxes["selected"]
    app.renderer.on_pointer_press(sel.x + 5, sel.y + 5, LEFT_BUTTON, 0)
    app.renderer.on_pointer_release(sel.x + 5, sel.y + 5, LEFT_BUTTON, 0)
    emit("save_focused", str(gui.focused_field is d2))
    for ch in "typed":
        app.renderer.on_key_press(0, ch, 0)
    emit("typed", d2.name_field.text)
    app.renderer.on_key_press(KEY_RETURN, "", 0)
    emit("typed_png", str((tmp / "typed.png").is_file()))
    emit("errors", "; ".join(errors[:2]) or "none")
"""


def test_keys_scrollbars_and_save_typing():
    """Keyboard navigation, real scrollbars, wheel-per-pane, Enter=Choose.

    The round-21 report: "keys not working, missing scrollbar". Keys did
    nothing because the dialog declined them in open mode and let the bare
    TextField take them in save mode (Enter then went nowhere); the
    scrollbar was a 3-pixel strip that could not be dragged. All of it is
    pinned here through the renderer's real input paths, Qt unimportable.
    """
    m = probe(_KEYS_DRIVE, block_qt=True)
    assert m["focused"] == "True", "a press did not give the dialog the keys"
    assert m["nav"] == "file04.pdb", "arrow navigation did not move the selection"
    assert m["paged"].startswith("file"), "page-down did not page"
    assert int(m["paged"][4:-4]) > 4, f"page-down did not page: {m['paged']}"
    assert int(m["nav_scrolled"]) > 0, "navigation did not keep the row on screen"
    assert int(m["thumb_drag"]) > 0, "dragging the thumb did not scroll"
    assert m["thumb_bounds_ok"] == "True"
    assert int(m["folders_wheeled"]) > 0, "the wheel over folders scrolled nothing"
    assert int(m["files_wheeled"]) > 0, "the wheel over files scrolled nothing"
    assert m["save_focused"] == "True"
    assert m["typed"] == "typed"
    assert m["typed_png"] == "True", "Enter after typing did not Choose"
    assert m["errors"] == "none", m["errors"]


_PICTURE_DRIVE = """
    import pathlib, tempfile
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="fdlg-pic-"))
    for i in range(200):
        (tmp / f"file{i:03d}.pdb").write_text("x")
    app = open_app(size=(1000, 780))
    app.cmd.set_message_callback(lambda _m: None)
    app.cmd.set_error_callback(lambda _e: None)
    app.cmd.do("load 148l.pdb")
    from emtk.events import LEFT_BUTTON
    from emtk.keys import KEY_DOWN
    r = app.renderer
    gui = r._internal_gui
    app._open_structure_dialog()
    win = gui.window("file_dialog")
    d = win.on_key
    d.path = tmp
    d.refresh()
    d.layout(gui.window_body(win))
    from chimol.ui.dialogs.file_dialog import ROW_H

    def row_xy(d, name):
        # The middle of a file row, as a click lands on it (panes are ListViews).
        index = d._file_model.index_of(name)
        box = d._boxes["files"]
        return box.x + 20.0, box.y + (index - d._file_list.scrollbar.top + 0.5) * ROW_H

    # Click a row (focus + selection), then a key must move the PICTURE.
    win.body_revision += 1
    r._chrome_quads()
    cx, cy = row_xy(d, "file000.pdb")
    r.on_pointer_press(cx, cy, LEFT_BUTTON, 0)
    r.on_pointer_release(cx, cy, LEFT_BUTTON, 0)
    q0 = r._chrome_quads()
    r.on_key_press(KEY_DOWN, "", 0)
    emit("key_moves_picture", str(q0 is not r._chrome_quads()))

    # The wheel must move the picture.
    q0 = r._chrome_quads()
    r.on_wheel(d._boxes["files"].x + 10, 200.0, -3, 0)
    emit("wheel_moves_picture", str(q0 is not r._chrome_quads()))

    # The thumb drag must move the picture AND the list.
    d._file_list.scrollbar.top = 0
    win.body_revision += 1
    r._chrome_quads()
    box = d._boxes["files"]
    bar_x = box.x + box.w - 3.0
    r.on_pointer_press(bar_x, box.y + 6.0, LEFT_BUTTON, 0)
    q_drag_start = r._chrome_quads()
    for step in range(1, 6):
        r.on_pointer_move(bar_x, box.y + 6.0 + step * (box.h - 12.0) / 5.0,
                          LEFT_BUTTON, 0)
        r._chrome_quads()
    r.on_pointer_release(bar_x, box.y + box.h - 6.0, LEFT_BUTTON, 0)
    emit("drag_scrolled", d._file_list.scrollbar.top)
    emit("drag_moved_picture", str(q_drag_start is not r._chrome_quads()))
"""


def test_dialog_changes_reach_the_picture_not_just_the_model():
    """Scrolling, keys and drags repaint -- the frozen-chrome-cache bug.

    The chrome fingerprint covered a window's frame and never its body, so
    the dialog scrolled, selected and typed on the **model** while the
    screen kept the cached quads: the thumb drag genuinely looked dead.
    GuiWindow.body_revision is bumped by every dialog mutator and included
    in the fingerprint; this test asserts on the chrome cache itself --
    the quad array must CHANGE, which model-level assertions cannot see
    (the round-16 lesson, one port later).
    """
    m = probe(_PICTURE_DRIVE, block_qt=True)
    assert m["key_moves_picture"] == "True", "a key did not repaint the dialog"
    assert m["wheel_moves_picture"] == "True", "the wheel did not repaint"
    assert int(m["drag_scrolled"]) > 0, "the thumb drag did not scroll"
    assert m["drag_moved_picture"] == "True", "the drag did not repaint"


def test_every_host_wires_the_same_two_prompts():
    """Open and Save reach one dialog, wired one way, on all three hosts.

    The browser had to draw its own (nothing in a page may spawn a process),
    the toolkit-free window drew the same one, and the Qt shell called
    ``QFileDialog`` -- so the chooser depended on how the viewer had been
    started. The two hooks come from `ui/dialogs/prompts.py` now, and this is
    what says all three still use them.
    """
    import inspect

    from chimol.hosts.native.app import ChimolApp
    from chimol.hosts.qt import window as qt_window
    from chimol.hosts.web.page import Page  # noqa: F401 - import proves Qt-free
    from chimol.ui.dialogs.prompts import file_prompt, open_structure_dialog

    for source in (
        inspect.getsource(Page),
        inspect.getsource(ChimolApp),
        inspect.getsource(qt_window.MolViewPluginWindow),
    ):
        assert "open_structure_dialog" in source, (
            "a host no longer wires the in-viewport file dialog"
        )
        assert "file_prompt" in source
    assert callable(open_structure_dialog) and callable(file_prompt)
