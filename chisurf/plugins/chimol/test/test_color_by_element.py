"""C > by element -- PyMOL's `util.cnc` / `util.cba`, not a colour *mode*.

Reported twice: selecting a side chain and colouring it by element recoloured
the whole protein. The menu issued ``color byelement``, which is a colour
**mode** -- a property of an object -- so the selection only picked which
objects to set it on, and `_apply_color_mode` cleared every per-atom override
on the way. The per-atom implementation already existed and the menu did not
use it.

PyMOL's submenu is also not one entry but **49**: `util.cnc` (colour H/N/O/S,
leave carbon), eight `util.cba` carbon colours, four more sets of eight, and a
hydrogen set. Transcribed from ``junk/pymol-open-source/modules/pymol/menu.py``.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

pytest.importorskip("qtpy")

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def session(qapp):
    from chimol.hosts.qt.window import MolViewPluginWindow

    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    win = MolViewPluginWindow()
    shared = win.cmd
    win.resize(700, 520)
    win.show()
    for _ in range(4):
        qapp.processEvents()
    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)

    def run(line: str) -> list[str]:
        before = len(errors)
        win._run_object_menu_command(line)
        for _ in range(3):
            qapp.processEvents()
        return errors[before:]

    run(f"load {PDB}")
    yield run, win.viewer
    win.close()


def _atoms(viewer):
    state = viewer.objects[viewer.get_active_object_id()].state
    atoms = state.atoms
    return (
        state,
        np.asarray(atoms["res_id"], dtype=int),
        np.array([str(e).strip().upper() for e in atoms["element"]]),
        len(atoms),
    )


def _recoloured(viewer, run, command) -> np.ndarray:
    """Indices of the atoms whose colour the command actually changed."""
    state, _res, _el, n = _atoms(viewer)
    before = viewer._atom_rgba_array(n).copy()
    complained = run(command)
    assert not complained, complained
    after = np.asarray(state.colors_per_atom_override, dtype=float)
    return np.nonzero(np.any(np.abs(before - after) > 1e-6, axis=1))[0]


def test_cnc_touches_only_the_selection_and_leaves_carbon(session):
    """The report, as a measurement: a side chain, not the whole protein."""
    run, viewer = session
    _state, res, el, _n = _atoms(viewer)

    changed = _recoloured(viewer, run, "cnc resi 20-25")
    expected = np.nonzero((res >= 20) & (res <= 25) & (el != "C"))[0]
    assert sorted(changed.tolist()) == sorted(expected.tolist())
    assert "C" not in set(el[changed].tolist()), "carbon was recoloured"


def test_cba_colours_the_carbons_too(session):
    """`cba` is the same thing with a carbon colour, which is the difference."""
    run, viewer = session
    _state, res, el, _n = _atoms(viewer)

    changed = _recoloured(viewer, run, "cba yellow, resi 40-45")
    touched = set(el[changed].tolist())
    assert "C" in touched, "cba left carbon alone; that is what cnc is for"
    assert set(res[changed].tolist()) <= set(range(40, 46))


def test_the_by_element_menu_is_pymols_forty_nine_entries():
    """One leaf was the bug: PyMOL offers a CNOS entry and 48 carbon/H colours."""
    from chimol.ui.menus.objects import COLOR_MENU

    by_element = COLOR_MENU[0]
    assert by_element.label == "by element"

    def leaves(entries):
        total = 0
        for entry in entries:
            if entry.children:
                total += leaves(entry.children)
            elif entry.command:
                total += 1
        return total

    assert leaves(by_element.children) == 49


def test_no_menu_entry_still_reaches_the_object_wide_mode():
    """`color byelement` is a *mode*; a menu that issues it repaints the object."""
    from chimol.ui.menus.objects import COLOR_MENU

    def commands(entries):
        for entry in entries:
            if entry.children:
                yield from commands(entry.children)
            elif entry.command:
                yield entry.command

    assert not [c for c in commands(COLOR_MENU) if "byelement" in c]
