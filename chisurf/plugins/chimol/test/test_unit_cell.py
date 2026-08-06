"""The unit cell box, and the symmetry mates it made visible.

``symexp`` builds the mates around a molecule and ``cell`` draws the box they
tile. The box is not transcribed from anywhere -- a cell is fully determined by
its six parameters, and ``UnitCell.frac_to_real`` already turns fractional
coordinates into Cartesian ones, so the twelve edges are that matrix applied to
the corners of the unit cube.

Drawing it is what exposed the defect these tests also cover: **every mate was
drawn at the render origin**, stacked on top of the original, because each
object is otherwise centred on its own centroid. `symexp`'s entire purpose is
seeing how molecules pack, so superimposing them removed the feature while
leaving every command reporting success.
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
#: A real hexagonal cell, so the box is not a cuboid and a wrong `frac_to_real`
#: would show. 148L carries no CRYST1, which is why it is set explicitly.
CELL = "61.2, 61.2, 96.8, 90, 90, 120, P 32 2 1"


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(qapp):
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.cmd import cmd as shared
    from chisurf.plugins.chimol.chimol.settings import set_setting

    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    win = MolViewPluginWindow()
    win.resize(800, 600)
    win.show()
    for _ in range(5):
        qapp.processEvents()

    messages: list[str] = []
    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)

    def run(line: str) -> None:
        win._run_object_menu_command(line)
        for _ in range(4):
            qapp.processEvents()

    run(f"load {PDB}")
    yield win, run, messages, errors
    set_setting("cell_color", "default")
    win.close()


def _cell_object(win):
    for obj in win.viewer.get_current_scene().objects:
        if obj.id.endswith(":cell") or obj.id == "cell":
            return obj
    return None


def test_the_box_is_twelve_edges_over_eight_corners(window):
    """A parallelepiped, whatever the cell angles are."""
    win, run, _messages, errors = window
    run(f"set_symmetry all, {CELL}")
    run("cell")
    assert errors == [], errors

    obj = _cell_object(win)
    assert obj is not None, "`cell` drew nothing"
    positions = np.asarray(obj.geometry.positions, dtype=float)
    assert positions.shape[0] == 24, positions.shape
    corners = np.unique(np.round(positions, 3), axis=0)
    assert corners.shape[0] == 8, corners.shape


def test_the_box_has_the_shape_the_cell_parameters_give_it(window):
    """A hexagonal cell is not a cuboid, and the box must not be one.

    Checked through the edge *lengths*: three distinct ones, matching a, b and
    c. A box built from a bounding volume rather than from ``frac_to_real``
    would pass a corner count and fail this.
    """
    win, run, _messages, _errors = window
    run(f"set_symmetry all, {CELL}")
    run("cell")
    obj = _cell_object(win)
    assert obj is not None

    scale = float(win.viewer._scale_factor)
    positions = np.asarray(obj.geometry.positions, dtype=float).reshape(-1, 2, 3)
    lengths = np.linalg.norm(positions[:, 1] - positions[:, 0], axis=1) / scale
    unique = np.unique(np.round(lengths, 1))
    assert sorted(unique) == pytest.approx([61.2, 96.8], abs=0.15) or set(
        np.round(unique, 1)
    ) == {61.2, 96.8}, unique


def test_an_object_with_no_cell_says_so(window):
    """148L carries no CRYST1, and an empty picture explains nothing."""
    win, run, _messages, errors = window
    errors.clear()
    run("cell")
    assert _cell_object(win) is None
    assert errors, "no cell and no complaint"
    assert "no unit cell" in errors[-1] and "set_symmetry" in errors[-1], errors[-1]


def test_the_box_can_be_switched_off_again(window):
    win, run, _messages, _errors = window
    run(f"set_symmetry all, {CELL}")
    run("cell all, on")
    assert _cell_object(win) is not None
    run("cell all, off")
    assert _cell_object(win) is None


def test_cell_color_drives_the_box(window):
    win, run, _messages, _errors = window
    run(f"set_symmetry all, {CELL}")
    run("cell all, on")
    default = np.unique(np.asarray(_cell_object(win).geometry.colors, dtype=float), axis=0)
    run("set cell_color, red")
    reddened = np.unique(np.asarray(_cell_object(win).geometry.colors, dtype=float), axis=0)
    assert reddened.shape[0] == 1
    assert int(np.argmax(reddened[0, :3])) == 0, reddened
    assert not np.allclose(default, reddened)


def test_symmetry_mates_are_drawn_where_they_actually_are(window):
    """The defect drawing the box exposed.

    Every object is drawn centred on its own centroid, so each mate landed at
    the render origin: measured before the fix, six mates with six distinct
    centroids in Angstrom were all drawn at (0, 0, 0). Every command reported
    success and the picture was one molecule.

    The check compares the distances *as drawn* with the distances in Angstrom,
    which is the property that matters and the one superposition destroys.
    """
    win, run, _messages, errors = window
    run(f"set_symmetry all, {CELL}")
    errors.clear()
    run("symexp mate, all, 5.0, 1")
    assert errors == [], errors

    viewer = win.viewer
    scale = float(viewer._scale_factor)
    angstrom, drawn = [], []
    for entry in viewer._objects.values():
        state = entry.state
        if state.atoms is None or state.all_atom_coords is None:
            continue
        angstrom.append(np.asarray(state.atoms["xyz"], dtype=float).mean(axis=0))
        drawn.append(np.asarray(state.all_atom_coords, dtype=float).mean(axis=0) / scale)
    assert len(angstrom) > 2, "symexp made no mates to check"

    reference_a, reference_d = angstrom[0], drawn[0]
    for centre_a, centre_d in zip(angstrom[1:], drawn[1:]):
        separation_a = float(np.linalg.norm(centre_a - reference_a))
        separation_d = float(np.linalg.norm(centre_d - reference_d))
        assert separation_a > 1.0, "a mate sitting on the original is not a mate"
        assert separation_d == pytest.approx(separation_a, abs=0.05), (
            f"drawn {separation_d:.1f} A apart, actually {separation_a:.1f} A"
        )
