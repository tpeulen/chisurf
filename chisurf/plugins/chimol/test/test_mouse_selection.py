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
    viewer._gl_enabled = True  # type: ignore[attr-defined]
    if viewer.view is None:
        viewer.view = object()

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
