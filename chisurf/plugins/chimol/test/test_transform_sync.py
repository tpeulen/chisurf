"""A transform has to move both coordinate arrays, and lengths have to be Angstrom.

chimol keeps atom coordinates twice: ``atoms["xyz"]`` in Angstrom, and the
renderer's arrays in scene units (Angstrom times ``_scale_factor``). Different
commands read different ones, so the two drifting apart is not a cosmetic problem
— it makes commands disagree about where the molecule *is*.

That is exactly what happened. ``_apply_rigid_transform`` skipped structured
arrays on purpose, so ``translate`` and ``rotate`` moved the render arrays and left
the atom array behind. On a displaced copy, ``rms`` reported 281 Å while ``align``
read the atom array, saw nothing to do, and announced an RMSD of 0.000 — and
``align`` then moved nothing at all.

The second half is the unit boundary: ``rms`` measured render coordinates and
printed the result with an Angstrom sign on it, so every RMSD it reported was ten
times too large.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    """Build a viewer with 148L loaded and a command interpreter over it."""
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.cmd.command import Cmd
    from chisurf.plugins.chimol.chimol.io.structure import _read_full_model
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    view.add_structure(
        _read_full_model(cs_struct.Structure, _PDB_148L),
        name="ref",
        source_path=str(_PDB_148L),
    )

    class _Window:
        viewer = view

        def _refresh_objects_from_viewer(self):
            pass

        def windowTitle(self):
            return "chimol"

    cmd = Cmd(_Window())
    messages: list[str] = []
    errors: list[str] = []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    return cmd, view, messages, errors


def _atom_x(view) -> float:
    return float(np.asarray(view._atoms["xyz"], dtype=float)[:, 0].mean())


def _render_x(view) -> float:
    return float(np.asarray(view._all_atom_coords, dtype=float)[:, 0].mean())


def _xyz(view, object_id) -> np.ndarray:
    return np.asarray(view._objects[object_id].state.atoms["xyz"], dtype=float)


def _ids(view) -> dict:
    return {str(o["name"]): str(o["id"]) for o in view.list_objects()}


# --------------------------------------------------------------------------- #
# The two arrays move together
# --------------------------------------------------------------------------- #
def test_translate_moves_the_atom_array(session):
    """The regression: it moved only the renderer's copy."""
    cmd, view, _, _ = session
    before = _atom_x(view)
    cmd.do("translate [10, 0, 0]")
    assert _atom_x(view) == pytest.approx(before + 10.0, abs=1e-6)


def test_translate_moves_both_arrays_by_the_same_distance(session):
    """In their own units: the renderer's are scaled, the atom array's are not."""
    cmd, view, _, _ = session
    scale = float(view._scale_factor)
    assert scale != 1.0, "this test is only meaningful when the viewer scales"

    atom_before, render_before = _atom_x(view), _render_x(view)
    cmd.do("translate [10, 0, 0]")

    atom_moved = _atom_x(view) - atom_before
    render_moved = _render_x(view) - render_before
    assert atom_moved == pytest.approx(10.0, abs=1e-6)
    assert render_moved == pytest.approx(10.0 * scale, abs=1e-4)


def test_a_rotation_reaches_the_atom_array(session):
    cmd, view, _, _ = session
    before = np.asarray(view._atoms["xyz"], dtype=float).copy()
    cmd.do("rotate z, 90")
    after = np.asarray(view._atoms["xyz"], dtype=float)
    assert not np.allclose(before, after)
    # A rotation about the centre preserves every distance from it.
    centre = before.mean(axis=0)
    assert np.allclose(
        np.linalg.norm(before - centre, axis=1),
        np.linalg.norm(after - after.mean(axis=0), axis=1),
        atol=1e-4,
    )


def test_a_transform_leaves_the_atom_array_readable(session):
    """Anything else in the record has to survive being moved."""
    cmd, view, _, _ = session
    names_before = np.char.strip(view._atoms["res_name"].astype(str)).copy()
    cmd.do("translate [5, 5, 5]")
    names_after = np.char.strip(view._atoms["res_name"].astype(str))
    assert (names_before == names_after).all()


# --------------------------------------------------------------------------- #
# Commands that read different arrays now agree
# --------------------------------------------------------------------------- #
def test_rms_reports_angstrom(session):
    """A pure translation of 5 A must read as an RMSD of exactly 5 A.

    It used to be measured on the renderer's scene units and printed with an
    Angstrom sign, so it came out ten times too large.
    """
    cmd, view, messages, _ = session
    cmd.do("copy mob, ref")
    ids = _ids(view)
    view.apply_transform_to_object(
        np.eye(3), np.array([5.0 * view._scale_factor, 0.0, 0.0]),
        object_id=ids["mob"],
    )
    truth = float(
        np.sqrt(((_xyz(view, ids["ref"]) - _xyz(view, ids["mob"])) ** 2).sum(1).mean())
    )
    assert truth == pytest.approx(5.0, abs=1e-6)

    cmd.do("rms mob, ref")
    assert float(messages[-1].split(":")[-1].split()[0]) == pytest.approx(5.0, abs=1e-3)


def test_align_sees_a_displacement_and_removes_it(session):
    """It used to read the untouched atom array and report an RMSD of 0.000."""
    cmd, view, _, _ = session
    cmd.do("copy mob, ref")
    ids = _ids(view)

    angle = np.deg2rad(30.0)
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0.0],
            [np.sin(angle), np.cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    view.apply_transform_to_object(
        rotation, np.array([250.0, -100.0, 50.0]), object_id=ids["mob"]
    )

    before = float(
        np.sqrt(((_xyz(view, ids["ref"]) - _xyz(view, ids["mob"])) ** 2).sum(1).mean())
    )
    assert before > 1.0, "the copy should genuinely be displaced"

    cmd.do("align mob, ref")
    after = float(
        np.sqrt(((_xyz(view, ids["ref"]) - _xyz(view, ids["mob"])) ** 2).sum(1).mean())
    )
    assert after < 1e-3


def test_rms_and_align_agree_after_aligning(session):
    """The two read different arrays; they must not tell different stories."""
    cmd, view, messages, _ = session
    cmd.do("copy mob, ref")
    ids = _ids(view)
    view.apply_transform_to_object(
        np.eye(3), np.array([80.0, 0.0, 0.0]), object_id=ids["mob"]
    )
    cmd.do("align mob, ref")
    cmd.do("rms mob, ref")
    assert float(messages[-1].split(":")[-1].split()[0]) == pytest.approx(0.0, abs=1e-3)


def test_a_transform_reaches_the_distance_selections(session):
    """`within` measures the atom array, so a moved molecule must move for it too."""
    cmd, view, messages, _ = session
    cmd.do("count_atoms all within 5 of resn NAG")
    before = int(messages[-1])
    assert before > 0

    cmd.do("translate [100, 0, 0]")
    cmd.do("count_atoms all within 5 of resn NAG")
    # The ligand moved with everything else, so its neighbourhood is unchanged --
    # which is only true if both the selection and the transform see one geometry.
    assert int(messages[-1]) == before


def test_a_transform_barely_changes_the_surface_area(session):
    """Area is a rigid invariant, but the *sampled* area is not exactly.

    The dots sit at fixed directions in the lab frame, so rotating the molecule
    changes which of them land in a crevice: the answer moves by about the
    sampling error, no more. That is a property of Shrake-Rupley rather than a
    defect, and it is why comparing structures wants a high ``dot_density``.

    Translation alone must be exact, and is checked separately below.
    """
    cmd, view, messages, _ = session
    cmd.do("get_area resn NAG")
    before = float(messages[-1].split()[1])

    cmd.do("rotate y, 37")
    cmd.do("translate [12, -4, 8]")
    cmd.do("get_area resn NAG")
    after = float(messages[-1].split()[1])

    assert after == pytest.approx(before, rel=0.03)   # within the sampling error
    assert after != before                            # ...and not bit-identical


def test_a_pure_translation_leaves_the_area_exactly_alone(session):
    """No rotation, so the dots meet the same geometry and the answer is identical.

    A desynchronised atom array would break this: `get_area` reads the atom
    coordinates, so the move has to reach them.
    """
    cmd, view, messages, _ = session
    cmd.do("get_area resn NAG")
    before = float(messages[-1].split()[1])
    cmd.do("translate [12, -4, 8]")
    cmd.do("get_area resn NAG")
    assert float(messages[-1].split()[1]) == pytest.approx(before, rel=1e-9)


def test_export_matches_the_atom_array_after_a_transform(session, tmp_path):
    """`save` and the atom array must not disagree about where the molecule is."""
    cmd, view, _, errors = session
    cmd.do("translate [15, 0, 0]")
    out = tmp_path / "moved.pdb"
    cmd.do(f"save {out}")
    assert errors == []

    written = np.array(
        [
            [float(line[30:38]), float(line[38:46]), float(line[46:54])]
            for line in out.read_text().splitlines()
            if line.startswith(("ATOM", "HETATM"))
        ]
    )
    assert np.allclose(
        written, np.asarray(view._atoms["xyz"], dtype=float), atol=5e-4
    )
