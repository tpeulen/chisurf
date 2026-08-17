"""``distance`` beyond two picked atoms: PyMOL's modes, through the command.

The finder itself is tested in ``test_hbonds.py``; this file is about the
*command* -- that PyMOL's positional ``cutoff`` and ``mode`` are read where
PyMOL puts them, that each mode draws a different thing, and that a run finding
nothing clears the object it would have replaced instead of leaving the last
answer on screen. That last one is the failure the object menu made visible:
firing **A ▸ find ▸ polar contacts ▸ to any atoms** on a whole object selects
nothing on the far side, and the previous entry's dashes stayed put looking
exactly like the answer.
"""

from __future__ import annotations

import pathlib

import pytest

_PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    pytest.importorskip("chisurf.core.structure")
    from chimol.hosts.qt.window import MolViewPluginWindow

    win = MolViewPluginWindow()
    shared = win.cmd
    win._load_structure_from_path(_PDB)
    for _ in range(20):
        qapp.processEvents()

    messages: list[str] = []
    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        messages.clear()
        errors.clear()
        shared.do(line)
        for _ in range(8):
            qapp.processEvents()

    yield win, do, messages, errors
    win.close()


def _segments(win, name: str) -> int:
    """How many dashed segments a measurement holds."""
    entry = win.viewer._measurements.get(name)
    if entry is None:
        return 0
    return int(entry["positions"].shape[0]) // 2


# --------------------------------------------------------------------------- #
# The modes
# --------------------------------------------------------------------------- #
def test_polar_contacts_are_drawn(session):
    win, do, _messages, errors = session
    do("distance hb, all, all, mode=2")
    assert errors == []
    assert _segments(win, "hb") > 100


def test_each_mode_draws_a_different_thing(session):
    """Bonded pairs, polar contacts and 4 A contacts are three answers."""
    win, do, _messages, errors = session
    counts = {}
    for mode in (1, 2, 3):
        do(f"distance m{mode}, all, all, 4.0, mode={mode}")
        assert errors == [], f"mode {mode} -> {errors[-1]}"
        counts[mode] = _segments(win, f"m{mode}")
    assert counts[1] > counts[2], "bonds should outnumber polar contacts"
    assert counts[3] > counts[1], "4 A contacts should outnumber bonds"


def test_the_centroid_mode_draws_exactly_one_line(session):
    win, do, _messages, errors = session
    do("distance com, resi 1-50, resi 100-150, mode=4")
    assert errors == []
    assert _segments(win, "com") == 1


def test_a_trailing_number_is_the_cutoff_pymol_puts_there(session):
    """``distance name, s1, s2, 4.0`` -- fourth positional, as PyMOL spells it."""
    win, do, _messages, errors = session
    do("distance near, all, all, 2.0, mode=3")
    assert errors == []
    tight = _segments(win, "near")
    do("distance wide, all, all, 4.0, mode=3")
    assert errors == []
    assert _segments(win, "wide") > tight


def test_label_zero_draws_dashes_without_numbers(session):
    win, do, _messages, _errors = session
    do("distance hb, all, all, mode=2, label=0")
    assert win.viewer._measurements["hb"]["labels"] == []
    do("distance hb, all, all, mode=2")
    assert win.viewer._measurements["hb"]["labels"]


# --------------------------------------------------------------------------- #
# The one that made the menu lie
# --------------------------------------------------------------------------- #
def test_finding_nothing_clears_the_previous_answer(session):
    """PyMOL's ``reset=1``. Stale dashes are indistinguishable from an answer."""
    win, do, _messages, errors = session
    do("distance conts, all, all, mode=2")
    assert _segments(win, "conts") > 0
    # `not all` selects nothing, so there is no far side and no contact.
    do("distance conts, all, not all, mode=2")
    assert errors == []
    assert _segments(win, "conts") == 0
    assert "conts" not in win.viewer._measurements


def test_two_atoms_still_measure_as_one_distance(session):
    """The old behaviour, unchanged: a readable label, not a distance set."""
    win, do, messages, errors = session
    do("distance d1, resi 10 and name CA, resi 20 and name CA")
    assert errors == []
    assert win.viewer._measurements["d1"]["kind"] == "distance"
    assert "d1" in messages[-1] or "res" in messages[-1]
