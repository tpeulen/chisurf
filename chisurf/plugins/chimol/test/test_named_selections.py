"""Named selections must behave like PyMOL's selection objects.

PyMOL's ``select mysel, chain E`` creates a name that is usable anywhere a
selection is: ``show sticks, mysel``, ``count_atoms mysel``, and even inside
another expression (``mysel and resi 10``). Before this the name was stored but
never resolved again -- ``show sticks, mysel`` matched nothing while ``show
sticks, chain E`` worked -- which made it impossible to change the
representation of a subset without retyping its expression every time.

Guarded here:

* a named selection stores the atoms, not just a residue highlight,
* a bare name resolves to its own object regardless of what is active,
* a named selection composes inside another expression,
* ``select <expr>`` with a single argument names the result ``sele``,
* recalling a selection still drives the GUI highlight.
"""

from __future__ import annotations

import pathlib
import shutil

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
    # `count_atoms` returns its count, which the runner emits directly; the
    # "count_atoms: N atoms in (...)" spelling is the fallback for callers that
    # invoke it for its side effects.
    if ":" in text:
        return int(text.split(":")[1].split("atoms")[0].strip())
    return int(text.strip())


def _stick_count(window) -> int:
    entry = window.viewer._objects.get(str(window.viewer.get_active_object_id()))
    mask = np.asarray(entry.state.sticks_mask, dtype=bool)
    return int(np.count_nonzero(mask))


def test_select_stores_atoms_not_just_an_expression(cmd):
    _run(cmd, "select mysel, chain E")
    entry = cmd._named_selections["mysel"]
    assert int(np.count_nonzero(np.asarray(entry["mask"], dtype=bool))) > 0
    assert entry["indices"], "recall highlight was not stored"


def test_a_named_selection_changes_the_representation_of_a_subset(cmd):
    _run(cmd, "select mysel, chain E and resi 1-40")
    _run(cmd, "as cartoon")
    _run(cmd, "show sticks, mysel")
    count = _stick_count(cmd.window)
    assert count == _count(cmd, "chain E and resi 1-40")
    assert 0 < count < len(cmd.window.viewer._all_atom_coords)


def test_a_named_selection_compounds_inside_an_expression(cmd):
    _run(cmd, "select mysel, chain E and resi 1-40")
    assert _count(cmd, "mysel and name CA") == _count(cmd, "name CA and chain E and resi 1-40")


def test_a_named_selection_hides_from_a_subset(cmd):
    _run(cmd, "select mysel, chain E")
    _run(cmd, "show sticks, mysel")
    before = _stick_count(cmd.window)
    _run(cmd, "hide sticks, mysel and name CA")
    assert 0 <= _stick_count(cmd.window) < before


def test_anonymous_select_names_the_default_sele(cmd):
    _run(cmd, "select chain S")
    assert "sele" in cmd._named_selections
    assert _count(cmd, "sele") == _count(cmd, "chain S")


def test_a_named_selection_recalls_the_highlight(cmd):
    _run(cmd, "select mysel, chain E and resi 1-40")
    _run(cmd, "select mysel")
    viewer = cmd.window.viewer
    selected = list(getattr(viewer, "_selected_residues", []))
    assert selected, "recall did not restore the GUI highlight"
    assert len(selected) == len(cmd._named_selections["mysel"]["indices"])


def test_an_unknown_selection_name_matches_nothing(cmd):
    assert _count(cmd, "does_not_exist") == 0
