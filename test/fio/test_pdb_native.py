"""The native PDB reader, against the IMP one it is meant to replace.

Reading a PDB cost ~100 us per atom because ChiSurf built an IMP hierarchy and
then walked back out of it in Python -- IMP's own parser is 0.079 s of a 1.24 s
read. The native reader slices the fixed columns instead: **1239 ms to 25 ms**
on a 9315-atom structure.

The bar for a replacement reader is not "it produces something plausible", it is
**field-for-field agreement with the reader it replaces**, on real files, with
every difference deliberate and named. There is exactly one here: the radius.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fio.structure.coordinates import parse_pdb_native, read_coordinates

PDB_DIR = pathlib.Path(__file__).resolve().parents[2] / "test" / "data" / "atomic_coordinates" / "pdb_files"
FILES = ["148l.pdb", "hGBP1_closed.pdb", "1rtd.pdb"]
#: Everything the two readers must agree on. `radius` is excluded on purpose --
#: see `test_the_radius_is_the_one_documented_difference`.
SHARED_FIELDS = (
    "chain", "res_id", "res_name", "atom_id", "atom_name", "element", "bfactor", "mass",
)


def _files():
    return [p for p in (PDB_DIR / name for name in FILES) if p.is_file()]


@pytest.fixture(scope="module", params=FILES)
def pair(request):
    path = PDB_DIR / request.param
    if not path.is_file():
        pytest.skip(f"missing fixture {path}")
    imp = pytest.importorskip("IMP")  # noqa: F841
    native = parse_pdb_native(str(path), keep_water=True, only_standard_residues=False)
    reference = read_coordinates(
        str(path), keep_water=True, only_standard_residues=False, radii="charmm"
    )
    return request.param, native, reference


def test_the_same_atoms_survive(pair):
    """Including the alternate-location rule, which is where a naive parser
    differs: keeping every altloc doubles those atoms and every distance, area
    and bond inferred from them."""
    name, native, reference = pair
    assert len(native) == len(reference), name


@pytest.mark.parametrize("field", SHARED_FIELDS)
def test_every_field_matches_the_reader_it_replaces(pair, field):
    name, native, reference = pair
    if field in ("bfactor", "mass"):
        assert np.allclose(native[field], reference[field], atol=1e-3), (name, field)
    else:
        assert (native[field] == reference[field]).all(), (name, field)


def test_the_coordinates_match(pair):
    name, native, reference = pair
    assert np.allclose(native["xyz"], reference["xyz"], atol=1e-3), name


def test_the_radius_is_the_one_documented_difference(pair):
    """IMP gives a CHARMM ``Rmin`` per *atom type*; this gives the element's van
    der Waals radius.

    A viewer wants the second -- it is what PyMOL draws a sphere with and
    measures a surface with -- and the modelling code wants the first, which is
    why the choice is a parameter and why ``charmm`` stays the default. The test
    asserts the difference *exists* so that nobody later "fixes" it into
    silence.
    """
    name, native, reference = pair
    assert not np.allclose(native["radius"], reference["radius"]), name
    # And that the native radii really are per element, not per atom type.
    for element in ("C", "N", "O"):
        chosen = native["element"] == element
        if chosen.any():
            assert len(np.unique(native["radius"][chosen])) == 1, (name, element)


def test_a_blank_chain_stays_blank_rather_than_empty():
    """IMP reports a PDB's blank chain as `" "`, and a selection written against
    that must keep working. Stripping it turned every such chain into `""`."""
    path = PDB_DIR / "hGBP1_closed.pdb"
    if not path.is_file():
        pytest.skip("missing fixture")
    native = parse_pdb_native(str(path), keep_water=True, only_standard_residues=False)
    assert set(np.unique(native["chain"])) == {" "}, np.unique(native["chain"])


def test_the_policy_selects_the_reader():
    """`radii="vdw"` is what routes a PDB to the native path."""
    path = PDB_DIR / "148l.pdb"
    if not path.is_file():
        pytest.skip("missing fixture")
    fast = read_coordinates(str(path), keep_water=True, only_standard_residues=False, radii="vdw")
    direct = parse_pdb_native(str(path), keep_water=True, only_standard_residues=False)
    assert len(fast) == len(direct)
    assert np.allclose(fast["radius"], direct["radius"])


def test_an_empty_or_headers_only_file_is_an_empty_array(tmp_path):
    """A file with no ATOM records is not an error; it is a structure with no
    atoms, and every consumer already handles that."""
    path = tmp_path / "headers.pdb"
    path.write_text("HEADER    NOTHING HERE\nEND\n")
    assert len(parse_pdb_native(str(path))) == 0
