"""Headless tests for attachment-atom lookup (``core/av._find_attachment_point``).

A labelling site is three editable strings — chain, residue number, atom name —
and nothing validates a loaded ``fps.json`` against the structure. The lookup
therefore has to say "no" when a site does not exist: resolving a miss to *the
resseq-th atom of the file* attaches the dye to an unrelated atom and hands back
a plausible, entirely wrong accessible volume (RF-379).

Pure numpy plus the shipped T4 lysozyme structure — no IMP or AV backend.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from ..core.av import _find_attachment_point, load_structure_with_vdw

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[5]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
    / "148l.pdb"
)


@pytest.fixture(scope="module")
def atoms_148l():
    """Load T4 lysozyme (sole chain ``E``, residues 1-162) as an (N, 4) array."""
    if not _PDB_148L.is_file():
        pytest.skip(f"missing test structure {_PDB_148L}")
    return load_structure_with_vdw(str(_PDB_148L))


def test_existing_atom_resolves_by_identity(atoms_148l):
    """A site that exists comes back as its own coordinates, not an index guess."""
    xyz = _find_attachment_point(atoms_148l, "E", 18, "CA", pdb_path=str(_PDB_148L))
    assert xyz is not None
    # The atom is in the structure, and it is not atoms[resseq - 1].
    assert np.any(np.all(np.isclose(atoms_148l[:, :3], xyz), axis=1))
    assert not np.allclose(xyz, atoms_148l[17, :3])


@pytest.mark.parametrize(
    "chain, resseq, atom_name",
    [
        ("E", 134, "CG"),  # ALA 134 has no CG
        ("E", 18, "SD"),  # residue exists, atom does not
        ("A", 18, "CB"),  # chain does not exist
        ("E", 300, "CA"),  # past the end of a 162-residue protein
        ("E", 500, "CA"),  # past the end of the atom array as well
    ],
)
def test_missing_site_returns_none(atoms_148l, chain, resseq, atom_name):
    """An unresolvable site is a miss — never ``atoms[resseq - 1]``."""
    assert (
        _find_attachment_point(atoms_148l, chain, resseq, atom_name, pdb_path=str(_PDB_148L))
        is None
    )


def test_without_pdb_path_the_index_proxy_still_applies(atoms_148l):
    """With no file to resolve against, resseq stays a positional proxy."""
    xyz = _find_attachment_point(atoms_148l, "E", 134, "CG")
    assert xyz is not None
    assert np.allclose(xyz, atoms_148l[133, :3])
    assert _find_attachment_point(atoms_148l, "E", 5000, "CA") is None
