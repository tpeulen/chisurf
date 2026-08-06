"""Viewport mouse selection must behave like PyMOL's.

PyMOL's mouse model distinguishes the *drag* action of a button from the
*click* action: left-drag is ``rota`` while a left click is ``+/-``, and the
selection merge is decided by the action code, never by a modifier. Guarded
here:

* the ``single_*`` cells of the mode matrix resolve to PyMOL's click actions,
* ``+/-`` toggles the clicked residue, ``+Box``/``-Box`` add/subtract a
  rectangle and ``Sele`` replaces -- in the merge, not in a modifier,
* ``sele`` always exists: without a stored entry it is the live viewport
  selection, so ``show sticks, sele`` reaches exactly the residues that were
  clicked or box-selected,
* a stored ``sele`` entry wins over the viewer's current highlight.

The tests above the divider stub the picker and drive the merge directly, which
is the right way to test a merge and **the wrong way to find out whether
clicking works**. They passed for months while the viewport could not select
anything at all, because each of them supplied by hand the conditions the
product did not: they set ``viewer._gl_enabled = True`` -- an attribute no code
anywhere sets, and the gate the whole picking block hung on -- and replaced
``viewer.view`` with a bare ``object()``, so the real widget, the real
projection and the real Qt events were never involved. A fixture is an assertion
too, and these asserted the broken environment into existence.

So the second half drives real ``QMouseEvent``s through the real widget and
reads the selection that comes out.
"""

from __future__ import annotations

import pathlib
import shutil
import types

import numpy as np
import pytest


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )

    src = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    pdb = tmp_path / "148l.pdb"
    shutil.copyfile(src, pdb)

    win = MolViewPluginWindow()
    win._load_structure_from_path(pdb, name="148l")
    return win


@pytest.fixture
def cmd(window):
    from chisurf.plugins.chimol.chimol.cmd.command import Cmd

    c = Cmd(window)
    messages, errors = [], []
    c.set_message_callback(messages.append)
    c.set_error_callback(errors.append)
    c._test_messages = messages  # type: ignore[attr-defined]
    c._test_errors = errors  # type: ignore[attr-defined]
    return c


def _run(cmd, line):
    cmd._test_errors.clear()  # type: ignore[attr-defined]
    cmd.do(line)
    assert cmd._test_errors == [], cmd._test_errors  # type: ignore[attr-defined]


def _count(cmd, expression):
    cmd._test_messages.clear()  # type: ignore[attr-defined]
    _run(cmd, f"count_atoms {expression}")
    assert cmd._test_messages, "count_atoms produced no message"  # type: ignore[attr-defined]
    text = cmd._test_messages[-1]  # type: ignore[attr-defined]
    if ":" in text:
        return int(text.split(":")[1].split("atoms")[0].strip())
    return int(text.strip())


def _stick_count(window) -> int:
    entry = window.viewer._objects.get(str(window.viewer.get_active_object_id()))
    mask = np.asarray(entry.state.sticks_mask, dtype=bool)
    return int(np.count_nonzero(mask))


def _atom_count_for_residue_indices(viewer, indices) -> int:
    entry = viewer._objects.get(str(viewer.get_active_object_id()))
    state = entry.state
    res_ids = np.asarray(state.residue_ids)
    all_res = np.asarray(state.all_atom_res_ids)
    sel_ids = {int(res_ids[i]) for i in indices if 0 <= int(i) < len(res_ids)}
    return int(np.count_nonzero(np.isin(all_res, list(sel_ids))))


def test_click_action_resolves_the_single_cell():
    from chisurf.plugins.chimol.chimol.mouse_modes import click_action_of
    from qtpy import QtCore

    no = QtCore.Qt.NoModifier
    ctrl = QtCore.Qt.ControlModifier
    shft = QtCore.Qt.ShiftModifier
    left = QtCore.Qt.LeftButton
    assert click_action_of("three_button_viewing", left, no) == "+/-"
    assert click_action_of("three_button_viewing", left, ctrl) == "cent"
    assert click_action_of("three_button_viewing", left, shft) == "none"
    assert click_action_of("three_button_maestro", left, no) == "sele"
    assert click_action_of("three_button_maestro", left, shft) == "+/-"
    assert click_action_of("three_button_editing", left, no) == "pkat"


def test_selection_merges_like_pymol_actions(window):
    viewer = window.viewer
    viewer.set_selected_residues([0])
    assert list(viewer._selected_residues) == [0]

    viewer._apply_selection_indices([0], mode="toggle")
    assert list(viewer._selected_residues) == []

    viewer._apply_selection_indices([1], mode="toggle")
    assert list(viewer._selected_residues) == [1]

    viewer._apply_selection_indices([2, 3], mode="add")
    assert list(viewer._selected_residues) == [1, 2, 3]

    viewer._apply_selection_indices([2], mode="subtract")
    assert list(viewer._selected_residues) == [1, 3]

    viewer._apply_selection_indices([9], mode="set")
    assert list(viewer._selected_residues) == [9]

    viewer._apply_selection_indices([], mode="set")
    assert list(viewer._selected_residues) == []


def test_rect_selection_honours_the_action(window, monkeypatch):
    from chisurf.plugins.chimol.chimol.renderer import view as view_mod
    from qtpy import QtCore

    stub = types.SimpleNamespace(
        pick_residues_in_rect=lambda coords, view, rect: np.array([4, 5, 6])
    )
    monkeypatch.setattr(view_mod, "_get_picking_module", lambda: stub)
    viewer = window.viewer
    assert viewer.view is not None, "the viewer has no widget to pick in"

    rect = QtCore.QRect(0, 0, 10, 10)
    viewer.set_selected_residues([1])
    viewer.handle_rect_selection(rect, None, "+box")
    assert list(viewer._selected_residues) == [1, 4, 5, 6]

    viewer.handle_rect_selection(rect, None, "-box")
    assert list(viewer._selected_residues) == [1]

    viewer.handle_rect_selection(rect, None, "sele")
    assert list(viewer._selected_residues) == [4, 5, 6]

    viewer.handle_rect_selection(rect, None, "+/-")
    assert list(viewer._selected_residues) == []

    viewer.handle_rect_selection(rect, None, "+box")
    assert list(viewer._selected_residues) == [4, 5, 6]


def test_sele_resolves_to_the_live_viewport_selection(cmd):
    cmd._named_selections.pop("sele", None)
    viewer = cmd.window.viewer
    viewer.set_selected_residues([0, 1, 2])
    assert _count(cmd, "sele") == _atom_count_for_residue_indices(viewer, [0, 1, 2])


def test_sele_drives_subset_reps_like_pymol(cmd):
    cmd._named_selections.pop("sele", None)
    viewer = cmd.window.viewer
    viewer.set_selected_residues([0, 1, 2])
    _run(cmd, "as cartoon")
    _run(cmd, "show sticks, sele")
    assert _stick_count(cmd.window) == _atom_count_for_residue_indices(
        viewer, [0, 1, 2]
    )


def test_an_empty_space_click_deselects_like_pymol(window, monkeypatch):
    """PyMOL: "left-clicking away from any atom should deactivate the
    selection." With nothing picked, `+/-` (toggle) has nothing to toggle, so
    it clears -- it must not leave a stale selection behind."""
    from chisurf.plugins.chimol.chimol.renderer import view as view_mod
    from qtpy import QtCore

    stub = types.SimpleNamespace(pick_atom_from_click=lambda *a, **k: None)
    monkeypatch.setattr(view_mod, "_get_picking_module", lambda: stub)
    viewer = window.viewer
    assert viewer.view is not None, "the viewer has no widget to pick in"

    viewer.set_selected_residues([0, 1, 2])
    ev = types.SimpleNamespace(modifiers=lambda: QtCore.Qt.NoModifier)
    viewer.handle_mouse_click(ev, "+/-")
    assert list(viewer._selected_residues) == []

    viewer.set_selected_residues([0, 1, 2])
    viewer.handle_mouse_click(ev, "sele")
    assert list(viewer._selected_residues) == []


def test_an_empty_space_pick_leaves_the_selection_alone(window, monkeypatch):
    """`pkat` is an editing pick: it highlights but never owns the selection,
    so an empty pick must not wipe what is selected."""
    from chisurf.plugins.chimol.chimol.renderer import view as view_mod
    from qtpy import QtCore

    stub = types.SimpleNamespace(pick_atom_from_click=lambda *a, **k: None)
    monkeypatch.setattr(view_mod, "_get_picking_module", lambda: stub)
    viewer = window.viewer
    assert viewer.view is not None, "the viewer has no widget to pick in"

    viewer.set_selected_residues([0, 1, 2])
    ev = types.SimpleNamespace(modifiers=lambda: QtCore.Qt.NoModifier)
    viewer.handle_mouse_click(ev, "pkat")
    assert list(viewer._selected_residues) == [0, 1, 2]


def test_an_empty_viewport_selection_matches_nothing(cmd):
    cmd._named_selections.pop("sele", None)
    viewer = cmd.window.viewer
    viewer.set_selected_residues([])
    assert _count(cmd, "sele") == 0


def test_a_stored_sele_wins_over_the_viewer_highlight(cmd):
    _run(cmd, "select sele, chain E and resi 1-10")
    viewer = cmd.window.viewer
    viewer.set_selected_residues([0, 1, 2])
    assert _count(cmd, "sele") == _count(cmd, "chain E and resi 1-10")


# --------------------------------------------------------------------------- #
# Driven as real events, through the real widget
# --------------------------------------------------------------------------- #
@pytest.fixture
def viewport(qapp):
    """A laid-out viewer with a structure in it, and its GL widget."""
    from chisurf.plugins.chimol.chimol.io.structure import load_structure_payload
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    src = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    if not src.is_file():
        pytest.skip(f"missing fixture {src}")
    _reader, payload = load_structure_payload(str(src))
    view = MolView()
    view.resize(900, 700)
    view.show()
    for _ in range(5):
        qapp.processEvents()
    view.add_payload(payload, name="148l", source_path=str(src))
    for _ in range(5):
        qapp.processEvents()

    widget = view.view
    assert widget is not None, "no widget: the picking path cannot be tested"
    # Assert the viewport rather than assume it. `scene_width` clamps to 1 on a
    # widget that was never laid out, which puts every projection in one column
    # and makes every assertion below meaningless-but-passing.
    assert widget.scene_width() > 16, widget.scene_width()
    assert widget.scene_height() > 16, widget.scene_height()
    yield view, widget, qapp
    view.close()


def _pump(qapp, n=5):
    for _ in range(n):
        qapp.processEvents()


def _selection(view):
    return sorted(int(i) for i in (getattr(view, "_selected_residues", []) or []))


def _atom_point(view, widget):
    """Widget position of an atom that is actually on screen."""
    from qtpy import QtCore

    sx, sy, visible = widget.project_to_screen(view._all_atom_coords)
    on = np.nonzero(visible)[0]
    assert on.size, "no atom projected in front of the camera"
    index = int(on[on.size // 2])
    return index, QtCore.QPoint(int(round(sx[index])), int(round(sy[index])))


def _send(widget, kind, point, button, held, modifiers):
    from qtpy import QtCore, QtGui, QtWidgets

    QtWidgets.QApplication.sendEvent(
        widget, QtGui.QMouseEvent(kind, QtCore.QPointF(point), button, held, modifiers)
    )


def _click(widget, qapp, point, modifiers=None, button=None):
    from qtpy import QtCore

    modifiers = QtCore.Qt.NoModifier if modifiers is None else modifiers
    button = QtCore.Qt.LeftButton if button is None else button
    _send(widget, QtCore.QEvent.MouseButtonPress, point, button, button, modifiers)
    _send(
        widget, QtCore.QEvent.MouseButtonRelease, point, button,
        QtCore.Qt.NoButton, modifiers,
    )
    _pump(qapp)


def _drag(widget, qapp, start, end, modifiers):
    from qtpy import QtCore

    _send(
        widget, QtCore.QEvent.MouseButtonPress, start,
        QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, modifiers,
    )
    for fraction in (0.34, 0.67, 1.0):
        step = QtCore.QPoint(
            int(start.x() + (end.x() - start.x()) * fraction),
            int(start.y() + (end.y() - start.y()) * fraction),
        )
        _send(
            widget, QtCore.QEvent.MouseMove, step,
            QtCore.Qt.NoButton, QtCore.Qt.LeftButton, modifiers,
        )
    _send(
        widget, QtCore.QEvent.MouseButtonRelease, end,
        QtCore.Qt.LeftButton, QtCore.Qt.NoButton, modifiers,
    )
    _pump(qapp)


def test_atoms_project_inside_the_scene_column(viewport):
    """Through the renderer's own matrices, so a pick lands where atoms are drawn.

    The column, not the widget: the panel takes a strip on the right and the
    sequence viewer a band on top, and a projection ignoring either is out by
    that much everywhere. The version this replaced used pyqtgraph's camera API
    on a renderer that has not been pyqtgraph for a long time, and raised on
    every click.
    """
    view, widget, _qapp = viewport
    sx, sy, visible = widget.project_to_screen(view._all_atom_coords)
    assert visible.all(), "atoms went behind the camera in a framed view"
    assert 0 <= sx.min() and sx.max() <= widget.scene_width()
    strip = widget.height() - widget.scene_height()
    assert strip <= sy.min() and sy.max() <= widget.height()


def test_a_click_on_an_atom_selects_its_residue(viewport):
    """`SnglClk L` is `+/-`: the clicked residue toggles in."""
    view, widget, qapp = viewport
    index, point = _atom_point(view, widget)
    assert _selection(view) == []
    _click(widget, qapp, point)
    picked = _selection(view)
    assert len(picked) == 1, "clicking an atom selected nothing"
    residue_id = int(view._all_atom_res_ids[index])
    assert int(view._residue_ids[picked[0]]) == residue_id, (
        "the click selected a different residue than the atom it hit"
    )


def test_clicking_the_same_atom_again_deselects_it(viewport):
    view, widget, qapp = viewport
    _index, point = _atom_point(view, widget)
    _click(widget, qapp, point)
    assert _selection(view)
    _click(widget, qapp, point)
    assert _selection(view) == []


def test_clicking_empty_space_deactivates_the_selection(viewport):
    from qtpy import QtCore

    view, widget, qapp = viewport
    _index, point = _atom_point(view, widget)
    _click(widget, qapp, point)
    assert _selection(view)
    _click(widget, qapp, QtCore.QPoint(4, widget.height() - 4))
    assert _selection(view) == []


def test_ctrl_shift_click_sets_the_selection(viewport):
    """`CtSh L` is `Sele`, and a click is a box that was never dragged.

    The press claims those modifiers for a rubber band, so a plain ctrl-shift
    *click* -- how anyone coming from PyMOL picks a residue -- fell through a
    zero-size rectangle and did nothing.
    """
    from qtpy import QtCore

    view, widget, qapp = viewport
    _index, point = _atom_point(view, widget)
    _click(
        widget, qapp, point, QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier
    )
    assert len(_selection(view)) == 1


def test_shift_drag_selects_every_residue_in_the_box(viewport):
    """`Shft L` is `+Box`, and it takes exactly the residues the box encloses."""
    from qtpy import QtCore

    view, widget, qapp = viewport
    rx, ry, visible = widget.project_to_screen(view._coords)
    on = np.nonzero(visible)[0]
    cx, cy = float(np.median(rx[on])), float(np.median(ry[on]))
    start = QtCore.QPoint(int(cx - 60), int(cy - 60))
    end = QtCore.QPoint(int(cx + 60), int(cy + 60))
    expected = sorted(
        int(i) for i in on
        if start.x() <= rx[i] <= end.x() and start.y() <= ry[i] <= end.y()
    )
    assert len(expected) > 3, "the box caught too little to be a test"
    _drag(widget, qapp, start, end, QtCore.Qt.ShiftModifier)
    assert _selection(view) == expected


def test_the_middle_button_stops_panning_when_released(viewport):
    """It did not: the class defined `mouseReleaseEvent` twice.

    Python keeps the last, so the one that ended the pan never ran and after a
    single middle-drag the molecule followed the cursor for the session.
    """
    from qtpy import QtCore

    view, widget, qapp = viewport
    _index, point = _atom_point(view, widget)
    _send(
        widget, QtCore.QEvent.MouseButtonPress, point,
        QtCore.Qt.MiddleButton, QtCore.Qt.MiddleButton, QtCore.Qt.NoModifier,
    )
    _pump(qapp, 2)
    assert widget._panning, "plain middle is `Move`, which pans"
    _send(
        widget, QtCore.QEvent.MouseButtonRelease, point,
        QtCore.Qt.MiddleButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier,
    )
    _pump(qapp, 2)
    assert not widget._panning


def test_ctrl_left_pans_rather_than_rotating(viewport):
    """`Ctrl L` is `Move` in the block, and the block is what people read.

    The gesture used to be chosen from the *button* while dragging rather than
    from the action the press resolved, so the only pan was the middle button.
    """
    from qtpy import QtCore

    view, widget, qapp = viewport
    _index, point = _atom_point(view, widget)
    _send(
        widget, QtCore.QEvent.MouseButtonPress, point,
        QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.ControlModifier,
    )
    _pump(qapp, 2)
    assert widget._panning
    _send(
        widget, QtCore.QEvent.MouseButtonRelease, point,
        QtCore.Qt.LeftButton, QtCore.Qt.NoButton, QtCore.Qt.ControlModifier,
    )
    _pump(qapp, 2)
    assert not widget._panning


def test_ctrl_shift_middle_moves_the_pivot(viewport):
    """`CtSh M` is `Orig`, which the block drew and nothing was wired to."""
    from qtpy import QtCore

    view, widget, qapp = viewport
    _index, point = _atom_point(view, widget)
    before = np.asarray(widget._pan_offset, dtype=float).copy()
    _click(
        widget, qapp, point,
        QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier,
        button=QtCore.Qt.MiddleButton,
    )
    after = np.asarray(widget._pan_offset, dtype=float)
    assert not np.allclose(before, after), "the pivot did not move"
    assert _selection(view) == [], "`Orig` is not a selection action"


def test_every_cell_the_block_shows_starts_the_gesture_it_names(viewport):
    """The block on screen is reference material, so it must not over-promise.

    The middle button had three cells that drew a name and did nothing -- it was
    turned into a pan before the table was ever consulted.
    """
    from qtpy import QtCore

    from chisurf.plugins.chimol.chimol.mouse_modes import action_of

    view, widget, qapp = viewport
    mode = widget._internal_gui.mouse_mode
    gestures = {
        "move": "pan", "+box": "band", "-box": "band", "sele": "band",
        "rota": "click", "pkat": "click", "orig": "click",
    }
    for modifiers in (
        QtCore.Qt.NoModifier,
        QtCore.Qt.ShiftModifier,
        QtCore.Qt.ControlModifier,
        QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier,
    ):
        for button in (QtCore.Qt.LeftButton, QtCore.Qt.MiddleButton):
            action = action_of(mode, button, modifiers)
            wanted = gestures.get(action)
            if wanted is None:
                continue
            widget._panning = False
            widget._drag_selecting = False
            widget._press_pos = None
            _index, point = _atom_point(view, widget)
            _send(
                widget, QtCore.QEvent.MouseButtonPress, point,
                button, button, modifiers,
            )
            _pump(qapp, 2)
            started = (
                "pan" if widget._panning
                else "band" if widget._drag_selecting
                else "click" if widget._press_pos is not None
                else "none"
            )
            _send(
                widget, QtCore.QEvent.MouseButtonRelease, point,
                button, QtCore.Qt.NoButton, modifiers,
            )
            _pump(qapp, 2)
            assert started == wanted, (
                f"the block says {action!r} for this cell, and the press started "
                f"{started!r} instead of {wanted!r}"
            )
