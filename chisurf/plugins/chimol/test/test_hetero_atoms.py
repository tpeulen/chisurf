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

from chimol.io.structure import _read_full_model

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)

# 148L carries no waters but six hetero residues (API, BME, DAL, FGA, MUB, NAG)
# across 63 HETATM records, which the modelling defaults drop wholesale.
_HETERO_RESNAMES = {"API", "BME", "DAL", "FGA", "MUB", "NAG"}
_N_HETATM = 63

# Not every hetero residue stays off the trace. 148L's ligand is a peptidoglycan
# fragment whose stem peptide -- DAL (D-alanine) and FGA (gamma-glutamate) -- is a
# genuine peptide: each carries N, CA, C and O and is bonded to its neighbours. So
# the trace visits it, the cartoon draws it, and it is *not* part of the display
# mask, which is defined as "not drawn by the cartoon".
#
# That only became true once the reader stopped losing ligand atom names: IMP
# prefixes the type of any atom it cannot classify with `HET:`, which truncated to
# `HET:` in the five-character field, so every ligand atom shared one name and no
# ligand residue could ever show a backbone. See `_imp_atom_name`.
_TRACED_HETERO_RESNAMES = {"DAL", "FGA"}
_N_TRACED_HETERO_ATOMS = 15

# Chain E ends on a dangling backbone nitrogen: `ATOM 1317  N  ASN E 163` is the
# only record for that residue. With no CA it cannot enter the trace, so the
# cartoon never draws it -- and the display mask picks it up alongside the ligands.
_N_UNTRACED_POLYMER_ATOMS = 1
_N_DISPLAYED = (
    _N_HETATM + _N_UNTRACED_POLYMER_ATOMS - _N_TRACED_HETERO_ATOMS
)


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
    from chimol.core.viewer import Viewer

    view = Viewer()
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
    assert (_HETERO_RESNAMES - _TRACED_HETERO_RESNAMES) <= marked


def test_a_hetero_residue_with_a_backbone_joins_the_trace(loaded_view):
    """The ligand's stem peptide is a peptide, and is drawn as one.

    DAL and FGA carry N/CA/C/O and are bonded into a chain, so excluding them
    would draw a covalently continuous peptide as disconnected spheres. This is
    only reachable because the reader now keeps ligand atom names.
    """
    names = np.asarray(loaded_view._atoms["res_name"]).astype(str)
    marked = {n.strip() for n in names[loaded_view._ball_mask]}
    assert not (_TRACED_HETERO_RESNAMES & marked)


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


def test_a_degraded_load_is_reported(tmp_path):
    """A silent fallback leaves nobody able to act on it.

    The built-in parser recovers the cartoon, so this costs metadata rather than
    the picture — but the message still has to name the cause, because "the
    reader is unavailable" on its own is not something a user can do anything
    with.
    """
    from chimol.hosts.qt.window import MolViewPluginWindow

    class _Panel:
        def __init__(self):
            self.errors: list[str] = []

        def append_error(self, text):
            self.errors.append(text)

    window = MolViewPluginWindow.__new__(MolViewPluginWindow)
    window.command_panel = _Panel()
    window._report_degraded_load(tmp_path / "weird.pdb", ValueError("no reader"))

    assert window.command_panel.errors
    message = window.command_panel.errors[-1]
    assert "weird.pdb" in message
    # The cause has to be quoted, not merely alluded to.
    assert "no reader" in message
    assert "ValueError" in message
    assert "built-in parser" in message


def test_a_degraded_load_without_a_panel_does_not_raise(tmp_path):
    """Chimol also runs headless, where there is nothing to append to."""
    from chimol.hosts.qt.window import MolViewPluginWindow

    window = MolViewPluginWindow.__new__(MolViewPluginWindow)
    window._report_degraded_load(tmp_path / "x.pdb", None)


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
    # One position per displayed atom. This used to read `> _N_DISPLAYED`,
    # because a merged sphere mesh has ~160 vertices per atom and the coarse CA
    # fallback this guards against produced roughly a tenth of the residue
    # count -- so "more than the atoms" separated them. Spheres are impostors
    # now, one position each, which makes the exact count available and the
    # proxy unnecessary.
    assert atom_objects[0].geometry.positions.shape[0] == _N_DISPLAYED


# --------------------------------------------------------------------------- #
# Selecting the solvent
# --------------------------------------------------------------------------- #
# PyMOL's object-panel H menu has a first-class "waters" entry that runs
# `hide("(solvent and (sele))")`, so hiding the solvent is an everyday action and
# has to be reachable. `water` is not a PyMOL selection keyword -- PyMOL rejects
# it -- but it is what everyone types, and accepting it cannot break a PyMOL
# script that uses a name PyMOL itself refuses.


def test_solvent_and_its_spellings_agree(loaded_view):
    from chimol.core.selection.parser import Evaluator

    oid = loaded_view.get_active_object_id()
    evaluator = Evaluator(loaded_view, oid)
    masks = [
        np.asarray(evaluator.evaluate(expr, oid), dtype=bool)
        for expr in ("solvent", "water", "waters")
    ]
    assert all(np.array_equal(masks[0], m) for m in masks[1:])


def test_polymer_is_the_complement_of_hetero(loaded_view):
    """The two must partition the atoms, or `hide polymer` leaves orphans."""
    from chimol.core.selection.parser import Evaluator

    oid = loaded_view.get_active_object_id()
    evaluator = Evaluator(loaded_view, oid)
    polymer = np.asarray(evaluator.evaluate("polymer", oid), dtype=bool)
    hetero = np.asarray(evaluator.evaluate("hetatm", oid), dtype=bool)
    assert not (polymer & hetero).any()
    assert (polymer | hetero).all()
    assert int(hetero.sum()) == _N_DISPLAYED


def test_hiding_by_a_selection_name_works(loaded_view):
    """`hide water` is the obvious thing to type; PyMOL rejects it, we act on it.

    148L has ligands but no waters, so this uses `hetatm`; a name that selects
    nothing is deliberately left to fail as an unknown representation, which is
    the more useful message in that case.
    """
    from chimol.commands.command import Cmd

    class _Window:
        def __init__(self, viewer):
            self.viewer = viewer

    cmd = Cmd(_Window(loaded_view))
    messages, errors = [], []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)

    before = int(np.count_nonzero(loaded_view._ball_mask))
    assert before > 0
    cmd.do("hide hetatm")
    assert errors == []
    assert int(np.count_nonzero(loaded_view._ball_mask)) == 0
    # And it teaches the PyMOL spelling rather than silently guessing.
    assert any("hide everything, hetatm" in m for m in messages)

    cmd.do("show hetatm")
    assert int(np.count_nonzero(loaded_view._ball_mask)) == before


def test_a_name_that_selects_nothing_is_still_an_error(loaded_view):
    """148L has no waters, so `hide water` there is a typo, not an instruction."""
    from chimol.commands.command import Cmd

    class _Window:
        def __init__(self, viewer):
            self.viewer = viewer

    cmd = Cmd(_Window(loaded_view))
    errors: list[str] = []
    cmd.set_error_callback(errors.append)
    cmd.do("hide water")
    assert errors and "Unsupported representation" in errors[-1]
