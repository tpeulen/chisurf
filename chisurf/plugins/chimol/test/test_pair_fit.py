"""Superposing on explicitly matched atom pairs — PyMOL's ``pair_fit``.

``align`` finds its own correspondence between two structures. ``pair_fit`` takes
one you state, matching atoms *in order* within each pair, which is what you need
when the two are not the same sequence or when only a few atoms should drive the
fit — a labelling site, a ligand, a domain.

Several pairs contribute to **one** least-squares fit, so a superposition that a
single stretch would leave ambiguous can be pinned down by adding another.
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
def displaced(qapp):
    """A structure and a rigidly displaced copy of it, with a command runner."""
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chimol.commands.command import Cmd
    from chimol.io.structure import _read_full_model
    from chimol.core.viewer import MolView

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

    cmd.do("copy mob, ref")
    ids = {str(o["name"]): str(o["id"]) for o in view.list_objects()}

    angle = np.deg2rad(40.0)
    rotation = np.array(
        [
            [np.cos(angle), 0.0, np.sin(angle)],
            [0.0, 1.0, 0.0],
            [-np.sin(angle), 0.0, np.cos(angle)],
        ]
    )
    view.apply_transform_to_object(
        rotation, np.array([150.0, 60.0, -90.0]), object_id=ids["mob"]
    )
    return cmd, view, ids, messages, errors


def _xyz(view, ids, name) -> np.ndarray:
    return np.asarray(view._objects[ids[name]].state.atoms["xyz"], dtype=float)


def _rmsd(view, ids) -> float:
    return float(
        np.sqrt(((_xyz(view, ids, "ref") - _xyz(view, ids, "mob")) ** 2).sum(1).mean())
    )


# --------------------------------------------------------------------------- #
# It fits
# --------------------------------------------------------------------------- #
def test_a_rigid_displacement_is_removed(displaced):
    cmd, view, ids, _, errors = displaced
    assert _rmsd(view, ids) > 10.0

    cmd.do("pair_fit mob and name CA, ref and name CA")
    assert errors == []
    assert _rmsd(view, ids) < 1e-4


def test_the_fit_reports_how_many_pairs_it_used(displaced):
    cmd, _, _, messages, _ = displaced
    cmd.do("pair_fit mob and name CA, ref and name CA")
    assert "165 atom pairs" in messages[-1]


def test_several_pairs_make_one_fit(displaced):
    """Two disjoint stretches, one least-squares superposition."""
    cmd, view, ids, messages, errors = displaced
    cmd.do(
        "pair_fit mob and resi 10-25 and name CA, ref and resi 10-25 and name CA, "
        "mob and resi 60-75 and name CA, ref and resi 60-75 and name CA"
    )
    assert errors == []
    assert "32 atom pairs" in messages[-1]
    assert _rmsd(view, ids) < 1e-4


def test_a_partial_selection_still_fits_the_whole_object(displaced):
    """The transform moves the object, not just the atoms named in the fit."""
    cmd, view, ids, _, _ = displaced
    cmd.do("pair_fit mob and resi 10-40 and name CA, ref and resi 10-40 and name CA")
    # Fitted on 31 atoms, but every atom of the object should now coincide.
    assert _rmsd(view, ids) < 1e-4


def test_the_fit_is_in_angstrom(displaced):
    """The coordinates are the atom array's; the transform wants scene units.

    Getting that conversion wrong leaves the object short of its target by the
    scale factor rather than landing on it.
    """
    cmd, view, ids, _, _ = displaced
    scale = float(view._scale_factor)
    assert scale != 1.0, "this test is only meaningful when the viewer scales"
    cmd.do("pair_fit mob and name CA, ref and name CA")
    assert _rmsd(view, ids) < 1e-4


def test_the_reported_rmsd_matches_the_result(displaced):
    cmd, view, ids, messages, _ = displaced
    cmd.do("pair_fit mob and name CA, ref and name CA")
    reported = float(messages[-1].split("RMSD:")[1].split()[0])
    assert reported == pytest.approx(_rmsd(view, ids), abs=1e-3)


# --------------------------------------------------------------------------- #
# What it refuses, and why
# --------------------------------------------------------------------------- #
def test_an_odd_number_of_selections_is_refused(displaced):
    cmd, _, _, _, errors = displaced
    cmd.do("pair_fit mob and name CA")
    assert errors and "Usage" in errors[-1]


def test_three_selections_are_refused(displaced):
    cmd, _, _, _, errors = displaced
    cmd.do("pair_fit mob and name CA, ref and name CA, mob and name CB")
    assert errors and "even number" in errors[-1]


def test_mismatched_counts_are_refused_with_both_numbers(displaced):
    """Pairs are matched in order, so unequal counts have no meaning."""
    cmd, _, _, _, errors = displaced
    cmd.do(
        "pair_fit mob and resi 10-20 and name CA, ref and resi 10-30 and name CA"
    )
    assert errors
    assert "11 atoms" in errors[-1] and "21" in errors[-1]


def test_too_few_pairs_are_refused(displaced):
    """Fewer than three points do not fix an orientation."""
    cmd, _, _, _, errors = displaced
    cmd.do("pair_fit mob and resi 10 and name CA, ref and resi 10 and name CA")
    assert errors and "three atom pairs" in errors[-1]


def test_mobile_selections_must_share_an_object(displaced):
    """They all move together, so they cannot name different objects."""
    cmd, _, _, _, errors = displaced
    cmd.do(
        "pair_fit mob and resi 10-25 and name CA, ref and resi 10-25 and name CA, "
        "ref and resi 60-75 and name CA, mob and resi 60-75 and name CA"
    )
    assert errors and "same object" in errors[-1]


def test_an_empty_selection_is_reported(displaced):
    cmd, _, _, _, errors = displaced
    cmd.do("pair_fit mob and resn ZZZ, ref and resn ZZZ")
    assert errors and "matched no atoms" in errors[-1]
