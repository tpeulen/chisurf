"""``orient``, ``zoom`` and ``center`` on a *selection*.

Three commands were reported as not working, and all three had the same cause:
they resolved a selection to **residue indices** and measured
``get_residue_positions``, which is one CA-trace point per residue. Any residue
without a CA -- a ligand, an ion, a water -- contributed nothing, so
``zoom resn NAG`` and ``center resn NAG`` moved the camera not at all and
``orient resn NAG`` only framed. All three reported success.

``orient`` was worse than that: it was a stub that called ``zoom`` and returned,
behind a TODO saying the renderer could not accept an arbitrary rotation. It
could -- ``set_view_state`` takes the full 3x3 -- so the note had outlived the
limitation by some margin.

None of this was caught by the 120-entry object-menu sweep, because that sweep
asserts *no error was reported*. These tests assert the camera actually moved and
that the result has the property the command promises.

The metric matters. An inertia tensor orders axes by **second moment**, not by
peak-to-peak range: a few outlying atoms can stretch one axis's range past
another's while the bulk is tighter, so ptp is not monotonic with rms. Asserting
ptp order fails on a correct implementation -- which it did, and cost a wrong
diagnosis before the numbers were looked at properly.
"""

from __future__ import annotations

import pathlib

import numpy as np
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
    win.resize(1000, 700)
    win.show()
    for _ in range(12):
        qapp.processEvents()
    win._load_structure_from_path(_PDB)
    for _ in range(25):
        qapp.processEvents()

    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        shared.do(line)
        for _ in range(10):
            qapp.processEvents()

    yield win.viewer, shared, do, errors
    win.close()


def _view(viewer):
    return np.asarray(viewer.get_view_state(), dtype=float)


def _spread(viewer, mask=None):
    """RMS spread along each camera axis -- what the inertia tensor orders by."""
    rotation = _view(viewer)[:9].reshape(3, 3)
    xyz = np.asarray(viewer._atoms["xyz"], dtype=float)
    if mask is not None:
        xyz = xyz[np.asarray(mask, dtype=bool)]
    xyz = xyz - xyz.mean(axis=0)
    return np.sqrt(np.mean((xyz @ rotation) ** 2, axis=0))


def _mask(shared, viewer, selection):
    _obj, _name, mask = shared._resolve_selection_to_atom_mask(viewer, selection)
    return np.asarray(mask, dtype=bool)


# --------------------------------------------------------------------------- #
# orient
# --------------------------------------------------------------------------- #
def test_orient_actually_rotates_the_camera(session):
    """It used to be a `zoom` behind a TODO, so the rotation never changed."""
    viewer, _shared, do, errors = session
    before = _view(viewer)[:9].copy()
    do("orient")
    assert errors == []
    assert not np.allclose(before, _view(viewer)[:9], atol=1e-6)


def test_orient_puts_the_principal_axes_on_the_screen_axes(session):
    viewer, _shared, do, errors = session
    do("orient")
    assert errors == []
    spread = _spread(viewer)
    assert spread[0] >= spread[1] >= spread[2], spread


def test_orient_is_idempotent(session):
    viewer, _shared, do, _errors = session
    do("orient")
    first = _view(viewer).copy()
    do("orient")
    assert np.allclose(first, _view(viewer), atol=1e-6)


def test_orient_undoes_a_turn(session):
    """The property that makes it useful: it always returns to the same frame."""
    viewer, _shared, do, _errors = session
    do("orient")
    oriented = _view(viewer).copy()
    do("turn y, 30")
    assert not np.allclose(oriented, _view(viewer), atol=1e-6)
    do("orient")
    assert np.allclose(oriented, _view(viewer), atol=1e-6)


def test_orient_on_a_ligand_orients_the_ligand(session):
    """The case that exposed all three bugs.

    A 14-atom sugar is one residue, so the residue-position path gave a single
    point and there was nothing to orient.
    """
    viewer, shared, do, errors = session
    do("orient resn NAG")
    assert errors == []
    spread = _spread(viewer, _mask(shared, viewer, "resn NAG"))
    assert spread[0] >= spread[1] >= spread[2], spread


def test_orient_on_the_polymer_orients_the_polymer(session):
    viewer, shared, do, errors = session
    do("orient polymer")
    assert errors == []
    spread = _spread(viewer, _mask(shared, viewer, "polymer"))
    assert spread[0] >= spread[1] >= spread[2], spread


def test_orient_on_too_few_atoms_says_so(session):
    """One atom has no orientation, so claiming success would be a lie."""
    viewer, _shared, do, errors = session
    do("orient index 1")
    assert errors and "fewer than two atoms" in errors[-1]


def test_orient_keeps_the_matrix_right_handed(session):
    """A left-handed basis mirrors the molecule, which reads as a wrong structure."""
    viewer, _shared, do, _errors = session
    for selection in ("", "polymer", "resn NAG"):
        do(f"orient {selection}".strip())
        rotation = _view(viewer)[:9].reshape(3, 3)
        assert float(np.linalg.det(rotation)) == pytest.approx(1.0, abs=1e-6)


def test_orient_produces_an_orthonormal_basis(session):
    viewer, _shared, do, _errors = session
    do("orient")
    rotation = _view(viewer)[:9].reshape(3, 3)
    assert np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6)


# --------------------------------------------------------------------------- #
# zoom and center on a selection
# --------------------------------------------------------------------------- #
def test_zoom_on_a_ligand_moves_the_camera(session):
    """It did nothing at all: a ligand has no CA, so the trace gave no points."""
    viewer, _shared, do, errors = session
    do("zoom")
    wide = _view(viewer).copy()
    do("zoom resn NAG")
    assert errors == []
    close = _view(viewer)
    assert not np.allclose(wide, close, atol=1e-6)
    # Zooming onto 14 atoms must bring the camera much nearer than the whole
    # molecule does; slot 11 is the camera distance.
    assert abs(close[11]) < abs(wide[11]) / 2


def test_zoom_on_a_ligand_centres_on_it(session):
    viewer, shared, do, errors = session
    do("zoom resn NAG")
    assert errors == []
    scale = float(getattr(viewer, "_scale_factor", 1.0) or 1.0)
    raw_centre = np.asarray(
        viewer._objects[viewer.get_active_object_id()].state.raw_center, dtype=float
    )
    pivot = _view(viewer)[12:15] / scale + raw_centre
    ligand = np.asarray(viewer._atoms["xyz"], dtype=float)[
        _mask(shared, viewer, "resn NAG")
    ].mean(axis=0)
    assert float(np.linalg.norm(pivot - ligand)) < 1.0


def test_center_on_a_ligand_moves_the_pivot(session):
    viewer, shared, do, errors = session
    do("zoom")
    do("center resn NAG")
    assert errors == []
    scale = float(getattr(viewer, "_scale_factor", 1.0) or 1.0)
    raw_centre = np.asarray(
        viewer._objects[viewer.get_active_object_id()].state.raw_center, dtype=float
    )
    pivot = _view(viewer)[12:15] / scale + raw_centre
    ligand = np.asarray(viewer._atoms["xyz"], dtype=float)[
        _mask(shared, viewer, "resn NAG")
    ].mean(axis=0)
    assert float(np.linalg.norm(pivot - ligand)) < 1.0


def test_zoom_on_a_selection_matching_nothing_says_so(session):
    viewer, _shared, do, errors = session
    do("zoom resn NOSUCH")
    assert errors and "matched no atoms" in errors[-1]


def test_zoom_on_everything_still_frames_everything(session):
    """The unselected path must not regress while the selected one is fixed."""
    viewer, _shared, do, errors = session
    do("zoom resn NAG")
    close = _view(viewer).copy()
    do("zoom")
    assert errors == []
    assert abs(_view(viewer)[11]) > abs(close[11]) * 2


def test_the_camera_commands_agree_about_what_a_selection_is(session):
    """All three go through one seam, so they cannot disagree about the atoms."""
    from chimol.core.viewer import MolView

    assert hasattr(MolView, "_selection_coords")
    import inspect

    for name in ("zoom", "center", "orient"):
        source = inspect.getsource(getattr(MolView, name))
        assert "_selection_coords" in source, name
