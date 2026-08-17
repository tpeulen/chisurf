"""What a viewport click selects -- PyMOL's ``mouse_selection_mode``.

The block's "Selecting" row showed the word ``Residues`` and nothing read it:
``Viewer.selection_mode`` and ``InternalGui.selecting`` were both constants,
so residues was the only level there was. These pin the four levels chimol can
honour, and the cross-chain trap that adding the finest one exposed.

**The trap:** a residue id is not unique across chains. 1RTD has eight, each
numbering from 1, so matching atoms to a residue on ``res_id`` alone pulled in
every chain's copy -- one residue marked 104 atoms instead of 13, and one picked
*atom* mapped back to eight residues. Every count here is cross-checked against
the atom table rather than against another part of the same code.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

pytest.importorskip("qtpy")

#: Deliberately the multi-chain fixture: a single-chain structure cannot tell a
#: chain-aware lookup from an id-only one, which is how the bug survived.
PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "1rtd.pdb"
)
FALLBACK = PDB.with_name("148l.pdb")


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def session(qapp):
    from chimol.hosts.qt.window import MolViewPluginWindow

    path = PDB if PDB.is_file() else FALLBACK
    if not path.is_file():
        pytest.skip(f"missing fixture {PDB}")
    win = MolViewPluginWindow()
    shared = win.cmd
    win.resize(700, 520)
    win.show()
    for _ in range(4):
        qapp.processEvents()
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(lambda _m: None)

    def run(line: str) -> None:
        win._run_object_menu_command(line)
        for _ in range(3):
            qapp.processEvents()

    run(f"load {path}")
    yield run, win.viewer
    run("set mouse_selection_mode, Residues")
    win.close()


def _atom_table(viewer):
    state = viewer.objects[viewer.get_active_object_id()].state
    atoms = state.atoms
    return (
        atoms,
        np.asarray(atoms["chain"]).astype(str),
        np.asarray(atoms["res_id"], dtype=int),
    )


def _a_multi_chain_pick(viewer) -> int:
    """An atom whose residue id also occurs in another chain, if there is one."""
    _atoms, chains, res_ids = _atom_table(viewer)
    for index in range(min(len(chains), 4000)):
        same_id = res_ids == res_ids[index]
        if len(set(chains[same_id].tolist())) > 1:
            return index
    return 0


def test_the_level_is_a_setting_and_reaches_the_viewer(session):
    run, viewer = session
    for level in ("Atoms", "Chains", "Objects", "Residues"):
        run(f"set mouse_selection_mode, {level}")
        assert viewer.selection_mode == level


def test_an_unknown_level_falls_back_to_residues(session):
    run, viewer = session
    run("set mouse_selection_mode, nonsense")
    assert viewer.selection_mode == "Residues"


def test_pymol_numbering_is_accepted(session):
    """A PyMOL script carries `mouse_selection_mode, 2`, not the word."""
    run, viewer = session
    run("set mouse_selection_mode, 0")
    assert viewer.selection_mode == "Atoms"
    run("set mouse_selection_mode, 2")
    assert viewer.selection_mode == "Chains"
    # Segments and Molecules fold onto the levels chimol can honour.
    run("set mouse_selection_mode, 3")
    assert viewer.selection_mode == "Chains"
    run("set mouse_selection_mode, 5")
    assert viewer.selection_mode == "Objects"


def test_each_level_selects_what_it_says(session):
    run, viewer = session
    _atoms, chains, res_ids = _atom_table(viewer)
    pick = _a_multi_chain_pick(viewer)
    chain, resi = chains[pick], res_ids[pick]
    residues_in_chain = len(
        set(zip(chains[chains == chain].tolist(), res_ids[chains == chain].tolist()))
    )

    run("set mouse_selection_mode, Residues")
    assert len(viewer._residues_for_pick(pick)) == 1

    run("set mouse_selection_mode, Chains")
    assert len(viewer._residues_for_pick(pick)) == residues_in_chain

    run("set mouse_selection_mode, Objects")
    assert len(viewer._residues_for_pick(pick)) == len(viewer._residue_ids)


def test_a_residue_marks_only_its_own_chains_atoms(session):
    """The cross-chain regression, counted against the atom table."""
    run, viewer = session
    _atoms, chains, res_ids = _atom_table(viewer)
    pick = _a_multi_chain_pick(viewer)
    truth = int(np.count_nonzero((chains == chains[pick]) & (res_ids == res_ids[pick])))

    run("set mouse_selection_mode, Residues")
    viewer._selected_atoms = []
    viewer._selected_residues = viewer._residues_for_pick(pick)
    marks = viewer._selection_atom_positions(np.asarray(viewer._coords, dtype=float))
    assert marks is not None
    assert len(marks) == truth


def test_the_atoms_level_marks_one_atom(session):
    run, viewer = session
    pick = _a_multi_chain_pick(viewer)
    run("set mouse_selection_mode, Atoms")
    try:
        viewer._apply_atom_selection([pick], mode="set")
        residues = viewer._residues_holding_selected_atoms([])
        assert len(residues) == 1, "one atom reached more than one residue"
        viewer._selected_residues = residues
        marks = viewer._selection_atom_positions(
            np.asarray(viewer._coords, dtype=float)
        )
        assert marks is not None and len(marks) == 1
    finally:
        viewer._selected_atoms = []
        run("set mouse_selection_mode, Residues")


def test_leaving_the_atoms_level_drops_the_atom_marks(session):
    """Atom-level marks at a coarser level would disagree with the residues."""
    run, viewer = session
    pick = _a_multi_chain_pick(viewer)
    run("set mouse_selection_mode, Atoms")
    viewer._apply_atom_selection([pick], mode="set")
    assert viewer._selected_atoms
    run("set mouse_selection_mode, Residues")
    assert viewer._selected_atoms == []


def test_atom_selection_merges_like_the_residue_one(session):
    run, viewer = session
    _atoms, chains, res_ids = _atom_table(viewer)
    run("set mouse_selection_mode, Atoms")
    try:
        viewer._selected_atoms = []
        viewer._apply_atom_selection([3], mode="add")
        viewer._apply_atom_selection([7], mode="add")
        assert viewer._selected_atoms == [3, 7]
        viewer._apply_atom_selection([3], mode="toggle")
        assert viewer._selected_atoms == [7]
        viewer._apply_atom_selection([9], mode="set")
        assert viewer._selected_atoms == [9]
        viewer._apply_atom_selection([9], mode="subtract")
        assert viewer._selected_atoms == []
    finally:
        run("set mouse_selection_mode, Residues")


def test_the_block_row_cycles_and_is_hit_testable(session):
    """The row was drawn and unreachable, which is what made the word a label."""
    from chimol.chrome.mouse_modes import SELECTION_LEVELS
    from chimol.chrome.gui import InternalGui

    sent: list[str] = []
    gui = InternalGui(run_command=sent.append)
    gui.layout(1280, 860)
    rect = gui._selecting_rect
    assert rect.w > 0 and rect.h > 0, "the Selecting row has no rectangle"
    hit = gui.hit_test(rect.x + rect.w / 2, rect.y + rect.h / 2)
    assert hit.kind == "selecting", f"the row is not reachable; got {hit.kind}"

    gui.selecting = "Residues"
    gui.cycle_selecting()
    assert sent, "clicking the row sent no command"
    assert sent[-1] == "set mouse_selection_mode, Chains"
    gui.selecting = "Residues"
    gui.cycle_selecting(back=True)
    assert sent[-1] == "set mouse_selection_mode, Atoms"

    # And the ring is closed, so the row cannot get stuck off the end.
    level = "Atoms"
    for _ in range(len(SELECTION_LEVELS)):
        gui.selecting = level
        gui.cycle_selecting()
        level = sent[-1].rsplit(",", 1)[1].strip()
    assert level == "Atoms"
