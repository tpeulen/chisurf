"""Clicking atoms to measure them -- PyMOL's measurement wizard.

The value of each measurement is checked against coordinates read straight out
of the PDB file, because that is the one thing an assertion can catch that
looking at the panel cannot: the wizard drew a perfectly convincing dashed line
labelled with the wrong number for as long as `distance` reported scene units.

The other half is *where* the measurement is stored. `MolView._update_measurements`
transforms the positions it is given into scene space, so a measurement built
from the scene array is scaled and centred twice and lands nowhere near the
atoms. Both are pinned here.
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
    """A window with 148L loaded, the runner, and the viewer."""
    from chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chimol.cmd import cmd as shared

    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    win = MolViewPluginWindow()
    win.resize(700, 520)
    win.show()
    for _ in range(4):
        qapp.processEvents()

    messages: list[str] = []
    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)

    def run(line: str) -> tuple[str, str]:
        before_m, before_e = len(messages), len(errors)
        win._run_object_menu_command(line)
        for _ in range(3):
            qapp.processEvents()
        said = messages[-1] if len(messages) > before_m else ""
        complained = errors[-1] if len(errors) > before_e else ""
        return said, complained

    run(f"load {PDB}")
    yield run, win.viewer
    run("wizard done")
    win.close()


def _ca_atoms(viewer):
    """``(indices, xyz)`` of the first few CA atoms of the active object."""
    state = viewer._objects[viewer.get_active_object_id()].state
    atoms = state.atoms
    names = np.array([str(n).strip() for n in atoms["atom_name"]])
    ca = np.where(names == "CA")[0]
    return [int(i) for i in ca[:4]], np.asarray(atoms["xyz"], dtype=float)


def _value(said: str) -> float:
    """The number a wizard report ends with (``... = 3.72 A``)."""
    return float(said.rsplit("=", 1)[1].split()[0])


def test_the_wizard_takes_over_picking(session):
    run, viewer = session
    assert getattr(viewer, "_wizard_pick", None) is None
    _said, complained = run("wizard measurement")
    assert not complained, complained
    assert callable(viewer._wizard_pick), "the wizard is not listening for picks"
    run("wizard done")
    assert viewer._wizard_pick is None, "clicks were never given back"


def test_two_picks_measure_the_distance_in_angstrom(session):
    run, viewer = session
    run("wizard measurement")
    try:
        (i, j, *_rest), xyz = _ca_atoms(viewer)
        truth = float(np.linalg.norm(xyz[i] - xyz[j]))
        viewer._wizard_pick(i)
        viewer._wizard_pick(j)
        said = _last_measurement_message(viewer)
        assert _value(said) == pytest.approx(truth, abs=5e-3)
    finally:
        run("wizard delete, all")
        run("wizard done")


def test_the_measurement_is_stored_in_world_coordinates(session):
    """Scene coordinates would be scaled and centred a second time when drawn."""
    run, viewer = session
    run("wizard measurement")
    try:
        (i, j, *_rest), xyz = _ca_atoms(viewer)
        viewer._wizard_pick(i)
        viewer._wizard_pick(j)
        stored = np.asarray(list(viewer._measurements.values())[-1]["positions"])
        assert stored == pytest.approx(np.array([xyz[i], xyz[j]]), abs=1e-6)
    finally:
        run("wizard delete, all")
        run("wizard done")


def test_angle_and_dihedral_need_three_and_four_picks(session):
    run, viewer = session
    run("wizard measurement")
    try:
        (i, j, k, l), xyz = _ca_atoms(viewer)

        run("wizard mode, angle")
        viewer._wizard_pick(i)
        viewer._wizard_pick(j)
        assert not viewer._measurements, "an angle was made from two atoms"
        viewer._wizard_pick(k)
        assert viewer._measurements, "three atoms did not make an angle"
        u, v = xyz[i] - xyz[j], xyz[k] - xyz[j]
        truth = np.degrees(np.arccos(
            np.dot(u, v) / np.linalg.norm(u) / np.linalg.norm(v)
        ))
        assert _value(_last_measurement_message(viewer)) == pytest.approx(
            truth, abs=0.05
        )

        run("wizard delete, all")
        run("wizard mode, dihedral")
        for index in (i, j, k):
            viewer._wizard_pick(index)
        assert not viewer._measurements, "a dihedral was made from three atoms"
        viewer._wizard_pick(l)
        assert viewer._measurements, "four atoms did not make a dihedral"
    finally:
        run("wizard delete, all")
        run("wizard done")


def test_switching_mode_drops_a_half_finished_group(session):
    """Three atoms on the way to a dihedral are not the start of a distance."""
    run, viewer = session
    run("wizard measurement")
    try:
        (i, j, k, _l), _xyz = _ca_atoms(viewer)
        run("wizard mode, dihedral")
        viewer._wizard_pick(i)
        viewer._wizard_pick(j)
        viewer._wizard_pick(k)
        assert len(viewer._wizard.picks) == 3
        run("wizard mode, distance")
        assert viewer._wizard.picks == []
        assert not viewer._measurements
    finally:
        run("wizard delete, all")
        run("wizard done")


def test_a_repeated_pick_does_not_measure_an_atom_against_itself(session):
    run, viewer = session
    run("wizard measurement")
    try:
        (i, *_rest), _xyz = _ca_atoms(viewer)
        viewer._wizard_pick(i)
        viewer._wizard_pick(i)
        assert not viewer._measurements, "an atom was measured against itself"
        assert len(viewer._wizard.picks) == 1
    finally:
        run("wizard done")


def test_unpick_takes_back_a_mis_click(session):
    run, viewer = session
    run("wizard measurement")
    try:
        (i, j, *_rest), _xyz = _ca_atoms(viewer)
        viewer._wizard_pick(i)
        assert len(viewer._wizard.picks) == 1
        run("wizard unpick")
        assert viewer._wizard.picks == []
        # And the taken-back atom can be picked again straight away.
        viewer._wizard_pick(i)
        viewer._wizard_pick(j)
        assert viewer._measurements
    finally:
        run("wizard delete, all")
        run("wizard done")


def test_delete_last_and_all(session):
    run, viewer = session
    run("wizard measurement")
    try:
        (i, j, k, l), _xyz = _ca_atoms(viewer)
        viewer._wizard_pick(i)
        viewer._wizard_pick(j)
        viewer._wizard_pick(k)
        viewer._wizard_pick(l)
        assert len(viewer._measurements) == 2
        run("wizard delete, last")
        assert len(viewer._measurements) == 1
        run("wizard delete, all")
        assert not viewer._measurements
    finally:
        run("wizard done")


def test_every_panel_row_is_a_real_control(session):
    """A row with a drop-down arrow and no menu is a control that does nothing."""
    run, viewer = session
    run("wizard measurement")
    try:
        (i, *_rest), _xyz = _ca_atoms(viewer)
        viewer._wizard_pick(i)
        state = viewer._wizard
        for row in state.panel():
            if row.kind == "menu":
                assert state.menu(row.action), (
                    f"row {row.label!r} draws a menu arrow but has no menu"
                )
            elif row.kind == "button":
                assert row.action, f"button {row.label!r} runs nothing"
    finally:
        run("wizard done")


def _last_measurement_message(viewer) -> str:
    """The label of the newest measurement, as the report spells it."""
    name = list(viewer._measurements)[-1]
    data = viewer._measurements[name]
    return f"{name} = {data['label']} x"
