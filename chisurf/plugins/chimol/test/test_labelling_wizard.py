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


def test_the_panel_walks_pick_dye_attach(session):
    win, shared, errors, qapp = session
    shared.do("wizard labelling")
    viewer = win.viewer
    state = viewer._wizard
    assert type(state).__name__ == "LabellingWizard"
    labels = [row.label for row in state.panel()]
    assert labels[0] == "Labelling"
    assert "Dye: ..." in labels
    assert state.prompt() == ["Labelling: pick an attachment atom"]

    # The click: routed through the same hook the viewport installs.
    consumed = viewer._wizard_pick(_cb_119(viewer))
    assert consumed
    assert state.atom[:4] == (viewer.get_active_object_id(), "E", 119, "CB")
    assert any("at E119/CB" in row.label for row in state.panel())

    shared.do("wizard dye, Cy5")
    assert state.dye == "Cy5"
    assert any(row.label == "Attach" for row in state.panel())

    shared.do("wizard apply")
    assert errors == [], errors[:2]
    assert state.created, "Attach made no AV object"
    # Attach kept the wizard and the dye, dropped the pick.
    assert state.atom == ()
    assert state.dye == "Cy5"
    assert state.prompt() == ["Labelling: pick an attachment atom"]
    shared.do("wizard done")
    assert viewer._wizard is None


def test_the_second_site_is_one_click_and_attach(session):
    win, shared, errors, qapp = session
    shared.do("wizard labelling")
    viewer = win.viewer
    state = viewer._wizard
    shared.do("wizard dye, Cy5")
    viewer._wizard_pick(_cb_119(viewer))
    shared.do("wizard apply")
    made = len(state.created)
    # Pick again straight away: the dye survived the previous Attach.
    viewer._wizard_pick(_cb_119(viewer))
    shared.do("wizard apply")
    assert len(state.created) == made + 1
    assert errors == [], errors[:2]
    shared.do("wizard done")


def test_delete_last_removes_the_av_object(session):
    win, shared, errors, qapp = session
    shared.do("wizard labelling")
    viewer = win.viewer
    state = viewer._wizard
    shared.do("wizard dye, Cy5")
    viewer._wizard_pick(_cb_119(viewer))
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
    viewer._wizard_pick(_cb_119(viewer))
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
    viewer._wizard_pick(_cb_119(viewer))
    shared.do("wizard apply")   # no dye chosen: refused, not crashed
    assert not viewer._wizard.created
    shared.do("wizard done")
