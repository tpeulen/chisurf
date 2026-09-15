"""Picking a labelling site instead of naming it -- the labelling wizard.

The wizard is the GUI surface of `add_dye`: a click names the attachment atom
(an fps position resolved by identity, ``(chain, residue, atom name)``, from
the structure's own file), a menu chooses the dye, Attach computes the
accessible volume. Two contracts are pinned here because both have broken
silently before:

* **Attach ends the pick, not the wizard** -- several sites usually share one
  dye, so the dye stays chosen and the next click is the next position;
* **the AV must not steal the active object** -- camera commands with no
  selection measure the active object, and a dye cloud carries no atoms, so
  `add_av` making itself active broke every `orient` that followed.
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
    shared.set_window(win)
    errors: list[str] = []
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)
    shared.do(f"load {PDB}")
    yield win, shared, errors, qapp
    shared.do("wizard done")
    shared.do("delete all")
    win.close()


def _cb_119(viewer) -> int:
    """Index of 148L's residue-119 CB -- the usual labelling position."""
    oid = viewer.get_active_object_id()
    atoms = viewer.objects[oid].state.atoms
    hits = np.where(
        (atoms["res_id"] == 119) & (atoms["atom_name"] == "CB")
    )[0]
    assert hits.size, "148l has no residue-119 CB; fixture changed?"
    return int(hits[0])


def test_the_panel_walks_pick_mutate_dye_attach(session):
    """As simple as introducing a mutation: pick a residue, (CYS by default), a dye, Attach."""
    win, shared, errors, qapp = session
    shared.do("wizard labelling")
    viewer = win.viewer
    state = viewer.wizard
    from chimol.plugins.labelling.wizard import LabellingWizard

    assert isinstance(state, LabellingWizard)
    labels = [row.label for row in state.panel()]
    assert labels[0] == "Labelling"
    assert "Dye: ..." in labels
    assert state.prompt() == ["Labelling: pick a residue"]
    assert state.target == "CYS", "the default mutation is to a cysteine"

    # The click: routed through the same hook the viewport installs; it names a residue.
    consumed = viewer.pick_hook(_cb_119(viewer))
    assert consumed
    assert state.residue[:3] == (viewer.get_active_object_id(), "E", 119)
    labels = [row.label for row in state.panel()]
    assert any(label.startswith("Residue") and "119" in label for label in labels)
    assert "Mutate to: CYS" in labels and "Attach at: auto" in labels

    shared.do("wizard dye, Cy5")
    assert state.dye == "Cy5"
    assert any(row.label == "Attach" for row in state.panel())

    shared.do("wizard apply")
    assert errors == [], errors[:2]
    assert state.created, "Attach made no AV object"
    # the residue is a cysteine now, and the dye hangs off its SG
    oid = viewer.get_active_object_id()
    atoms = viewer.objects[oid].state.atoms
    rows = atoms["res_id"] == 119
    assert set(np.char.strip(atoms["res_name"][rows].astype(str))) == {"CYS"}
    assert "SG" in set(np.char.strip(atoms["atom_name"][rows].astype(str)))
    av_entry = viewer.objects[state.created[-1]]
    assert "SG" in str(getattr(av_entry, "name", "")), av_entry.name
    # Attach kept the wizard and the dye, dropped the pick.
    assert state.residue == ()
    assert state.dye == "Cy5"
    assert state.prompt() == ["Labelling: pick a residue"]
    shared.do("wizard done")
    assert viewer.wizard is None


def test_keep_attaches_to_the_residue_as_it_is(session):
    """`Mutate to: keep` labels the residue's own CB (auto: SG, else CB, else CA)."""
    win, shared, errors, qapp = session
    shared.do("wizard labelling")
    viewer = win.viewer
    state = viewer.wizard
    shared.do("wizard target, keep")
    assert state.target == ""
    shared.do("wizard atom, CB")
    assert state.attach_atom == "CB"
    shared.do("wizard dye, Cy5")
    viewer.pick_hook(_cb_119(viewer))
    resn_before = str(viewer.objects[viewer.get_active_object_id()].state.atoms["res_name"][_cb_119(viewer)]).strip()
    shared.do("wizard apply")
    assert errors == [], errors[:2]
    atoms = viewer.objects[viewer.get_active_object_id()].state.atoms
    assert str(atoms["res_name"][_cb_119(viewer)]).strip() == resn_before
    assert "CB" in str(viewer.objects[state.created[-1]].name)
    shared.do("wizard done")


def test_the_second_site_is_one_click_and_attach(session):
    win, shared, errors, qapp = session
    shared.do("wizard labelling")
    viewer = win.viewer
    state = viewer.wizard
    shared.do("wizard dye, Cy5")
    viewer.pick_hook(_cb_119(viewer))
    shared.do("wizard apply")
    made = len(state.created)
    # Pick again straight away: the dye survived the previous Attach.
    viewer.pick_hook(_cb_119(viewer))
    shared.do("wizard apply")
    assert len(state.created) == made + 1
    assert errors == [], errors[:2]
    shared.do("wizard done")


def test_delete_last_removes_the_av_object(session):
    win, shared, errors, qapp = session
    shared.do("wizard labelling")
    viewer = win.viewer
    state = viewer.wizard
    shared.do("wizard dye, Cy5")
    viewer.pick_hook(_cb_119(viewer))
    shared.do("wizard apply")
    doomed = state.created[-1]
    assert doomed in viewer.objects
    shared.do("wizard delete, last")
    assert doomed not in viewer.objects
    assert not state.created
    shared.do("wizard done")


def test_attach_keeps_the_structure_the_active_object(session):
    """The regression: `orient` after `add_dye` said "nothing to orient".

    `add_av` used to hand the AV the active role; camera commands with no
    selection measure the active object, and a dye cloud has no atoms.
    """
    win, shared, errors, qapp = session
    viewer = win.viewer
    before = viewer.get_active_object_id()
    shared.do("wizard labelling")
    shared.do("wizard dye, Cy5")
    viewer.pick_hook(_cb_119(viewer))
    shared.do("wizard apply")
    assert viewer.get_active_object_id() == before
    errors.clear()
    shared.do("orient")
    assert errors == [], errors[:2]
    shared.do("wizard done")


def test_a_pick_without_a_dye_attach_says_so(session):
    win, shared, errors, qapp = session
    shared.do("wizard labelling")
    viewer = win.viewer
    viewer.pick_hook(_cb_119(viewer))
    shared.do("wizard apply")   # no dye chosen: refused, not crashed
    assert not viewer.wizard.created
    shared.do("wizard done")


def test_a_residue_picked_in_the_sequence_strip_is_the_wizards_pick(session):
    """The strip's click applies a selection; a running wizard adopts it (bus: selection.changed)."""
    from chimol.hosts.base import apply_sequence_selection

    win, shared, errors, qapp = session
    shared.do("wizard labelling")
    viewer = win.viewer
    state = viewer.wizard
    assert state.residue == ()
    oid = viewer.get_active_object_id()
    residue_ids = np.asarray(viewer.active_state().residue_ids)
    index = int(np.where(residue_ids == 44)[0][0])
    apply_sequence_selection(viewer, oid, [index])          # what the strip's click does
    assert state.residue[:3] == (oid, "E", 44), state.residue
    labels = [row.label for row in state.panel()]
    assert any("44" in label for label in labels)
    shared.do("wizard done")
    # and the subscription went with the wizard
    assert viewer.bus.count("selection.changed") == 0
