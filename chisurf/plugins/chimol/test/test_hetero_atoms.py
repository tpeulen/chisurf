"""Waters, ions and ligands must survive the load and be visible.

The core structure reader is tuned for modelling: it drops solvent and
non-standard residues. That is wrong for a viewer, where the deposited entry
then appears without content the file plainly carries and the atom count
disagrees with the file — the gap that made a fetched entry look emptier here
than in PyMOL, which shows the same atoms as nonbonded glyphs by default.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.io.structure import _read_full_model

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)

# 148L carries no waters but six hetero residues (API, BME, DAL, FGA, MUB, NAG)
# across 63 HETATM records, which the modelling defaults drop wholesale.
_HETERO_RESNAMES = {"API", "BME", "DAL", "FGA", "MUB", "NAG"}
_N_HETATM = 63

# Chain E ends on a dangling backbone nitrogen: `ATOM 1317  N  ASN E 163` is the
# only record for that residue. With no CA it cannot enter the trace, so the
# cartoon never draws it -- and the display mask, which is defined by exactly
# that ("not drawn by the cartoon"), picks it up alongside the ligands.
_N_UNTRACED_POLYMER_ATOMS = 1
_N_DISPLAYED = _N_HETATM + _N_UNTRACED_POLYMER_ATOMS


@pytest.fixture(scope="module")
def structure_factory():
    cs_struct = pytest.importorskip("chisurf.core.structure")
    return cs_struct.Structure


# --------------------------------------------------------------------------- #
# The reader
# --------------------------------------------------------------------------- #
def test_full_model_keeps_the_hetero_residues(structure_factory):
    full = _read_full_model(structure_factory, _PDB_148L)
    names = {str(n).strip() for n in np.asarray(full.atoms["res_name"])}
    assert _HETERO_RESNAMES <= names


def test_the_modelling_default_still_drops_them(structure_factory):
    """The core default must not change: modelling code depends on it."""
    lean = structure_factory(str(_PDB_148L))
    names = {str(n).strip() for n in np.asarray(lean.atoms["res_name"])}
    assert not (_HETERO_RESNAMES & names)


def test_the_viewer_gains_exactly_the_hetatm_records(structure_factory):
    lean = structure_factory(str(_PDB_148L))
    full = _read_full_model(structure_factory, _PDB_148L)
    assert len(full.atoms) - len(lean.atoms) == _N_HETATM


def test_a_factory_without_the_arguments_still_works():
    """Standalone Chimol may be handed a plain one-argument factory."""
    calls = []

    def plain_factory(path):
        calls.append(path)
        return object()

    result = _read_full_model(plain_factory, pathlib.Path("x.pdb"))
    assert result is not None
    assert calls == ["x.pdb"]


def test_a_factory_that_raises_is_not_swallowed():
    """Only a signature mismatch triggers the fallback, not a read failure."""

    def broken_factory(path, **kwargs):
        raise ValueError("unreadable")

    with pytest.raises(ValueError):
        _read_full_model(broken_factory, pathlib.Path("x.pdb"))


# --------------------------------------------------------------------------- #
# The viewer
# --------------------------------------------------------------------------- #
@pytest.fixture
def loaded_view(qapp, structure_factory):
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    view.add_structure(
        _read_full_model(structure_factory, _PDB_148L),
        name="148l",
        source_path=str(_PDB_148L),
    )
    return view


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_hetero_atoms_are_marked_for_display(loaded_view):
    mask = loaded_view._ball_mask
    assert mask is not None
    assert int(np.count_nonzero(mask)) == _N_DISPLAYED


def test_the_marked_atoms_are_the_hetero_residues(loaded_view):
    names = np.asarray(loaded_view._atoms["res_name"]).astype(str)
    marked = {n.strip() for n in names[loaded_view._ball_mask]}
    assert _HETERO_RESNAMES <= marked


def test_an_untraced_polymer_residue_is_displayed_too(loaded_view):
    """A residue with no CA is invisible in the cartoon; show its atoms.

    Defining the mask by absence from the trace rather than by a residue-name
    table is what makes this fall out: the dangling ASN 163 nitrogen would
    otherwise be loaded and then drawn by nothing at all.
    """
    atoms = loaded_view._atoms
    res_ids = np.asarray(atoms["res_id"])
    names = np.asarray(atoms["res_name"]).astype(str)
    dangling = np.nonzero((res_ids == 163) & (np.char.strip(names) == "ASN"))[0]
    assert dangling.size == _N_UNTRACED_POLYMER_ATOMS
    assert loaded_view._ball_mask[dangling].all()


def test_showing_atoms_is_turned_on_for_them(loaded_view):
    """Loaded-but-hidden is the same as missing, from the user's side."""
    assert loaded_view._show_atoms is True


def test_the_polymer_is_not_marked(loaded_view):
    """Only the hetero atoms; the rest stays with the cartoon."""
    n_marked = int(np.count_nonzero(loaded_view._ball_mask))
    assert n_marked < len(loaded_view._atoms)
    assert loaded_view._show_cartoon is True


def test_hetero_atoms_reach_the_scene(loaded_view):
    """The per-atom mask must survive into the built geometry.

    The mesh builder accepted only a per-*residue* mask, so a per-atom
    selection silently fell back to a coarse every-tenth-CA sampling and the
    hetero atoms were never drawn.
    """
    scene = loaded_view.get_current_scene()
    assert scene is not None
    atom_objects = [o for o in scene.objects if "atoms" in o.id]
    assert atom_objects, "no atom geometry in the scene"
    # A merged sphere mesh has many vertices per atom; the coarse CA fallback
    # produced a points object with about a tenth of the residue count.
    assert atom_objects[0].geometry.positions.shape[0] > _N_DISPLAYED
