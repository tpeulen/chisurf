"""Crystallographic symmetry: the cell, the operators, and ``symexp``.

The operators are **PyMOL's own table**, transcribed out of
``modules/pymol/xray.py`` by the generator checked in beside the data -- 547
space-group names over 528 distinct operator sets, up to 192 operators each. No
crystallography library is a dependency, and none is wanted: sharing PyMOL's table
is what makes the mates agree with PyMOL's rather than approximately agree.

A transcription can go wrong silently, and a wrong symmetry operator produces a
mate that looks entirely plausible in the wrong place. So the whole table is
checked **mathematically** rather than spot-checked:

* every group must be **closed** under composition modulo lattice translations;
* every rotation must be an isometry -- determinant exactly +/-1. Both signs occur,
  because PyMOL's table covers all 230 groups and the centrosymmetric ones contain
  inversions; the chiral groups proteins crystallise in are checked separately for
  +1 only;
* exactly one identity per group, and no duplicates.

That is 7658 operators verified, which is what makes a carried data table
trustworthy without a reference implementation to compare against.
"""

from __future__ import annotations

import itertools
import pathlib

import numpy as np
import pytest
from chimol.analysis.symmetry import (
    CELL_EDGES,
    SPACE_GROUP_OPERATORS,
    UnitCell,
    cell_corners,
    cell_line_segments,
    normalise_space_group,
    operators_for,
    parse_symmetry_operator,
    read_cryst1,
    read_file_operators,
    symmetry_mates,
)

_DATA = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
)
#: The only fixture with a CRYST1 record.
_CRYSTAL = _DATA / "1rtd.pdb"
_FRAGMENT = _DATA / "solvated_fragment.pdb"


def _key(rotation, translation):
    """An operator's identity modulo whole-cell translations."""
    return (
        tuple(np.round(rotation.ravel(), 6)),
        tuple(np.round(np.mod(translation, 1.0), 6)),
    )


# --------------------------------------------------------------------------- #
# The table, verified rather than inspected
# --------------------------------------------------------------------------- #
def test_every_group_is_closed_under_composition():
    """The check that catches a bad transcription.

    A wrong sign or a wrong fraction almost always breaks closure while looking
    perfectly reasonable on the page. Run over all 547 names at once rather than
    parametrised, so a broken extraction reports as one failure naming the groups
    instead of hundreds.
    """
    broken = []
    for name, operators in SPACE_GROUP_OPERATORS.items():
        parsed = [parse_symmetry_operator(op) for op in operators]
        known = {_key(r, t) for r, t in parsed}
        for (r1, t1), (r2, t2) in itertools.product(parsed, parsed):
            if _key(r1 @ r2, r1 @ t2 + t1) not in known:
                broken.append(name)
                break
    assert not broken, f"{len(broken)} groups are not closed: {broken[:8]}"


def test_every_rotation_is_an_isometry():
    """Determinant exactly +/-1.

    Both signs occur: PyMOL's table covers all 230 space groups, and the
    centrosymmetric ones contain inversions and mirrors.
    """
    wrong = []
    for name, operators in SPACE_GROUP_OPERATORS.items():
        for op in operators:
            rotation, _ = parse_symmetry_operator(op)
            if abs(abs(float(np.linalg.det(rotation))) - 1.0) > 1e-9:
                wrong.append(f"{name}: {op}")
    assert not wrong, wrong[:8]


def test_both_determinant_signs_are_present():
    """A sanity check on the check: if everything were +1 the table would be
    only the chiral groups, and the isometry test above would be weaker than it
    looks.
    """
    signs = set()
    for operators in SPACE_GROUP_OPERATORS.values():
        for op in operators:
            rotation, _ = parse_symmetry_operator(op)
            signs.add(int(round(float(np.linalg.det(rotation)))))
    assert signs == {1, -1}


def test_the_chiral_protein_groups_have_no_improper_rotations():
    """A protein cannot crystallise in a centrosymmetric group.

    So for the groups proteins actually use, an improper rotation would be a
    transcription error rather than a legitimate mirror.
    """
    for name in (
        "P212121",
        "P21",
        "C2",
        "P43212",
        "P41212",
        "P3121",
        "P3221",
        "P6122",
        "P6522",
        "P1",
        "C2221",
        "I222",
        "P21212",
    ):
        operators = SPACE_GROUP_OPERATORS.get(name)
        assert operators, f"{name} should be in the table"
        for op in operators:
            rotation, _ = parse_symmetry_operator(op)
            assert float(np.linalg.det(rotation)) == pytest.approx(1.0, abs=1e-9), (
                f"{name}: {op} is improper"
            )


def test_each_group_has_exactly_one_identity():
    wrong = []
    for name, operators in SPACE_GROUP_OPERATORS.items():
        identities = 0
        for op in operators:
            rotation, translation = parse_symmetry_operator(op)
            if np.allclose(rotation, np.eye(3)) and np.allclose(np.mod(translation, 1.0), 0.0):
                identities += 1
        if identities != 1:
            wrong.append(f"{name}: {identities}")
    assert not wrong, wrong[:8]


def test_no_group_lists_an_operator_twice():
    wrong = []
    for name, operators in SPACE_GROUP_OPERATORS.items():
        distinct = {_key(*parse_symmetry_operator(op)) for op in operators}
        if len(distinct) != len(operators):
            wrong.append(name)
    assert not wrong, wrong[:8]


def test_the_table_is_the_size_pymol_ships():
    """A guard on the extraction itself: a truncated run would still pass every
    mathematical check above, because what survived would be self-consistent.
    """
    assert len(SPACE_GROUP_OPERATORS) > 500
    assert len({v for v in SPACE_GROUP_OPERATORS.values()}) > 500
    assert max(len(v) for v in SPACE_GROUP_OPERATORS.values()) == 192


def test_every_space_group_used_by_proteins_resolves():
    """The 25 commonest, in the spellings a CRYST1 record actually carries."""
    for name in (
        "P 21 21 21",
        "P 1 21 1",
        "C 1 2 1",
        "P 21 21 2",
        "P 43 21 2",
        "P 41 21 2",
        "P 32 2 1",
        "P 61 2 2",
        "P 1",
        "C 2 2 21",
        "I 2 2 2",
        "P 31 2 1",
        "P 65 2 2",
        "P 6 2 2",
        "I 4 1 2 2",
        "F 2 2 2",
        "P 6 1",
        "P 3 2 1",
        "P 6 3",
        "I 4",
        "H 3",
        "R 3",
        "P 2 21 21",
        "I 21 3",
        "F 4 3 2",
    ):
        assert operators_for(name), f"{name} does not resolve"


def test_a_spelling_without_spaces_resolves_the_same():
    assert operators_for("P 21 21 21") == operators_for("P212121")
    assert operators_for("p 21 21 21") == operators_for("P212121")


def test_the_multiplicity_matches_the_symbol():
    """Order of the group, from the space-group symbol's own arithmetic."""
    expected = {
        "P1": 1,
        "P21": 2,
        "P212121": 4,
        "C2": 4,
        "C2221": 8,
        "P43212": 8,
        "P3121": 6,
        "P6122": 12,
        "I222": 8,
        "F222": 16,
    }
    for name, order in expected.items():
        assert len(SPACE_GROUP_OPERATORS[name]) == order, name


# --------------------------------------------------------------------------- #
# The operator parser
# --------------------------------------------------------------------------- #
def test_the_identity_parses_to_the_identity():
    rotation, translation = parse_symmetry_operator("x,y,z")
    assert np.allclose(rotation, np.eye(3))
    assert np.allclose(translation, 0.0)


def test_signs_and_fractions_parse():
    rotation, translation = parse_symmetry_operator("-x+1/2,-y,z+1/2")
    assert np.allclose(rotation, np.diag([-1.0, -1.0, 1.0]))
    assert np.allclose(translation, [0.5, 0.0, 0.5])


def test_a_combined_axis_term_parses():
    """``-x+y`` appears in every trigonal and hexagonal group."""
    rotation, _ = parse_symmetry_operator("-y,x-y,z")
    assert np.allclose(rotation, [[0, -1, 0], [1, -1, 0], [0, 0, 1]])


def test_whitespace_is_tolerated():
    a, _ = parse_symmetry_operator(" -x + 1/2 , y , -z ")
    b, _ = parse_symmetry_operator("-x+1/2,y,-z")
    assert np.allclose(a, b)


def test_thirds_parse_exactly_enough():
    _, translation = parse_symmetry_operator("x,y,z+1/3")
    assert translation[2] == pytest.approx(1.0 / 3.0)


def test_a_malformed_operator_is_refused():
    """Not silently parsed to something else: that would place mates wrongly."""
    for bad in ("x,y", "x,y,z,w", "x,,z"):
        with pytest.raises(ValueError):
            parse_symmetry_operator(bad)


def test_space_group_names_normalise():
    assert normalise_space_group("P 21 21 21") == "P212121"
    assert normalise_space_group("p212121") == "P212121"
    assert operators_for("P 21 21 21") == operators_for("P212121")


def test_an_unknown_space_group_returns_none():
    """So the caller can say so rather than guess."""
    assert operators_for("Fd3m") is None
    assert operators_for("") is None


# --------------------------------------------------------------------------- #
# The cell
# --------------------------------------------------------------------------- #
def test_the_cell_transforms_round_trip():
    cell = UnitCell(a=10.0, b=20.0, c=30.0, alpha=70.0, beta=80.0, gamma=100.0)
    assert np.allclose(cell.frac_to_real() @ cell.real_to_frac(), np.eye(3))


def test_an_orthorhombic_cell_is_diagonal():
    cell = UnitCell(a=10.0, b=20.0, c=30.0)
    assert np.allclose(cell.frac_to_real(), np.diag([10.0, 20.0, 30.0]))


def test_the_volume_of_a_box_is_the_product():
    assert UnitCell(a=10.0, b=20.0, c=30.0).volume == pytest.approx(6000.0)


def test_a_fractional_corner_maps_to_the_cell_corner():
    cell = UnitCell(a=10.0, b=20.0, c=30.0)
    corner = np.array([1.0, 1.0, 1.0]) @ cell.frac_to_real().T
    assert np.allclose(corner, [10.0, 20.0, 30.0])


# --------------------------------------------------------------------------- #
# Reading CRYST1
# --------------------------------------------------------------------------- #
def test_the_crystal_fixtures_cell_is_read():
    """Fixed columns, not whitespace splitting: ``P 21 21 21`` contains spaces."""
    if not _CRYSTAL.exists():
        pytest.skip("no crystal fixture")
    found = read_cryst1(_CRYSTAL)
    assert found is not None
    cell, space_group = found
    assert cell.a == pytest.approx(78.840)
    assert cell.b == pytest.approx(150.700)
    assert cell.c == pytest.approx(280.880)
    assert (cell.alpha, cell.beta, cell.gamma) == (90.0, 90.0, 90.0)
    assert space_group == "P 21 21 21"
    assert operators_for(space_group) is not None


def test_a_file_without_cryst1_reads_as_none():
    assert read_cryst1(_FRAGMENT) is None


def test_a_missing_file_reads_as_none():
    assert read_cryst1(_DATA / "definitely_not_here.pdb") is None


# --------------------------------------------------------------------------- #
# Reading the operators an mmCIF carries
# --------------------------------------------------------------------------- #
#: The same four C222-style operators written the four ways a CIF is allowed to
#: write them. All four must read identically: an operator taken out of the wrong
#: field parses without complaint into a plausible mate in the wrong place -- an
#: id column read as part of ``x+1/2,y+1/2,z`` makes a *threefold scaling*.
_C222_OPERATORS = ["x,y,z", "-x,y,-z", "x+1/2,y+1/2,z", "-x+1/2,y+1/2,-z"]

_CIF_LAYOUTS = {
    "loop, id first": """data_test
#
loop_
_symmetry_equiv.id
_symmetry_equiv.pos_as_xyz
1 x,y,z
2 -x,y,-z
3 x+1/2,y+1/2,z
4 -x+1/2,y+1/2,-z
#
""",
    "loop, operator first": """data_test
loop_
_symmetry_equiv.pos_as_xyz
_symmetry_equiv.id
x,y,z 1
-x,y,-z 2
x+1/2,y+1/2,z 3
-x+1/2,y+1/2,-z 4
#
""",
    "loop, quoted as RCSB writes it": """data_test
loop_
_symmetry_equiv.id
_symmetry_equiv.pos_as_xyz
1 'X,Y,Z'
2 '-X,Y,-Z'
3 'X+1/2,Y+1/2,Z'
4 '-X+1/2,Y+1/2,-Z'
#
""",
    "loop, CIF-core tag with rows packed onto one line": """data_test
loop_
_symmetry_equiv_pos_as_xyz
x,y,z -x,y,-z
x+1/2,y+1/2,z -x+1/2,y+1/2,-z
""",
}


def _written(tmp_path, text, name="test.cif"):
    path = tmp_path / name
    path.write_text(text)
    return path


@pytest.mark.parametrize("layout", sorted(_CIF_LAYOUTS))
def test_every_cif_layout_reads_the_same_operators(tmp_path, layout):
    operators = read_file_operators(_written(tmp_path, _CIF_LAYOUTS[layout]))
    assert [o.replace(" ", "").lower() for o in operators] == _C222_OPERATORS


@pytest.mark.parametrize("layout", sorted(_CIF_LAYOUTS))
def test_every_cif_layout_parses_to_an_isometry(tmp_path, layout):
    """The failure the id column caused: ``3 x+1/2,...`` has determinant 3."""
    for operator in read_file_operators(_written(tmp_path, _CIF_LAYOUTS[layout])):
        rotation, translation = parse_symmetry_operator(operator)
        assert abs(abs(np.linalg.det(rotation)) - 1.0) < 1e-9
        assert np.all(np.abs(translation) < 1.0)


def test_a_tag_and_its_value_on_one_line_are_read(tmp_path):
    """The non-loop form: a single operator written beside its tag."""
    text = "data_test\n_symmetry_equiv_pos_as_xyz  'x, y, z'\n#\n"
    assert read_file_operators(_written(tmp_path, text)) == ["x, y, z"]


def test_a_tag_with_its_value_on_the_next_line_is_read(tmp_path):
    text = "data_test\n_symmetry_equiv.pos_as_xyz\n-x,y,-z\n#\n"
    assert read_file_operators(_written(tmp_path, text)) == ["-x,y,-z"]


def test_an_unrelated_loop_contributes_nothing(tmp_path):
    """A file's other loops must not be mistaken for operators."""
    text = """data_test
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
ATOM 1 N
ATOM 2 C
#
loop_
_symmetry_equiv.id
_symmetry_equiv.pos_as_xyz
1 x,y,z
#
"""
    assert read_file_operators(_written(tmp_path, text)) == ["x,y,z"]


def test_a_file_without_operators_reads_as_empty(tmp_path):
    assert read_file_operators(_written(tmp_path, "data_test\n_cell.length_a 20\n")) == []
    assert read_file_operators(tmp_path / "definitely_not_here.cif") == []


def test_the_operators_read_from_a_file_place_the_same_mates(tmp_path):
    """End to end: file operators must move a molecule like the table's do."""
    coords = _cube_of_points()
    cell = UnitCell(a=20.0, b=20.0, c=20.0)
    operators = read_file_operators(_written(tmp_path, _CIF_LAYOUTS["loop, id first"]))
    from_file = symmetry_mates(coords, cell, operators, cutoff=0.0, shells=0)
    from_text = symmetry_mates(coords, cell, _C222_OPERATORS, cutoff=0.0, shells=0)
    assert len(from_file) == len(from_text) == 3
    for one, other in zip(from_file, from_text):
        assert np.allclose(one["coords"], other["coords"])


# --------------------------------------------------------------------------- #
# Generating mates
# --------------------------------------------------------------------------- #
def _cube_of_points(n=40, spread=8.0, seed=0):
    rng = np.random.default_rng(seed)
    return rng.uniform(0.0, spread, (n, 3))


def test_a_mate_is_a_rigid_copy():
    """Symmetry is an isometry: internal distances cannot change."""
    coords = _cube_of_points()
    cell = UnitCell(a=20.0, b=20.0, c=20.0)
    mates = symmetry_mates(coords, cell, operators_for("P212121"), cutoff=0.0)
    assert mates
    reference = np.linalg.norm(coords[1:] - coords[0], axis=1)
    for mate in mates[:5]:
        moved = mate["coords"]
        assert np.allclose(np.linalg.norm(moved[1:] - moved[0], axis=1), reference, atol=1e-9)


def test_the_identity_at_the_origin_is_excluded():
    """It is the molecule itself, not a mate."""
    coords = _cube_of_points()
    cell = UnitCell(a=20.0, b=20.0, c=20.0)
    mates = symmetry_mates(coords, cell, operators_for("P1"), cutoff=0.0)
    assert all(not (m["operator"] == 0 and m["translation"] == (0, 0, 0)) for m in mates)


def test_p1_gives_only_lattice_translations():
    """One operator, so every mate is a pure translation: 27 cells minus itself."""
    coords = _cube_of_points()
    cell = UnitCell(a=20.0, b=20.0, c=20.0)
    mates = symmetry_mates(coords, cell, operators_for("P1"), cutoff=0.0)
    assert len(mates) == 26


def test_a_pure_translation_offsets_by_the_cell_edge():
    """The strongest check on the fractional-to-Cartesian transform."""
    coords = _cube_of_points()
    cell = UnitCell(a=20.0, b=30.0, c=40.0)
    mates = symmetry_mates(coords, cell, operators_for("P1"), cutoff=0.0)
    offsets = {tuple(np.round(m["coords"].mean(axis=0) - coords.mean(axis=0), 6)) for m in mates}
    assert (20.0, 0.0, 0.0) in offsets
    assert (0.0, 30.0, 0.0) in offsets
    assert (0.0, 0.0, 40.0) in offsets


def test_the_cutoff_rejects_distant_mates():
    coords = _cube_of_points(spread=6.0)
    cell = UnitCell(a=60.0, b=60.0, c=60.0)  # far apart
    near = symmetry_mates(coords, cell, operators_for("P1"), cutoff=2.0)
    everything = symmetry_mates(coords, cell, operators_for("P1"), cutoff=0.0)
    assert len(near) < len(everything)


def test_shells_controls_how_far_it_looks():
    coords = _cube_of_points()
    cell = UnitCell(a=20.0, b=20.0, c=20.0)
    one = symmetry_mates(coords, cell, operators_for("P1"), cutoff=0.0, shells=1)
    two = symmetry_mates(coords, cell, operators_for("P1"), cutoff=0.0, shells=2)
    assert len(one) == 26  # 3**3 - 1
    assert len(two) == 124  # 5**3 - 1


def test_no_operators_is_refused():
    with pytest.raises(ValueError, match="no symmetry operators"):
        symmetry_mates(_cube_of_points(), UnitCell(10, 10, 10), [])


def test_the_wrong_coordinate_shape_is_refused():
    with pytest.raises(ValueError, match="shape"):
        symmetry_mates(np.zeros((4, 2)), UnitCell(10, 10, 10), ["x,y,z"])


def test_mates_are_found_in_a_real_crystal():
    """HIV-RT: lattice contacts within 5 A, out of 107 candidates."""
    if not _CRYSTAL.exists():
        pytest.skip("no crystal fixture")
    from chisurf.core.fio.structure.coordinates import read_coordinates

    cell, space_group = read_cryst1(_CRYSTAL)
    atoms = read_coordinates(str(_CRYSTAL), keep_water=True, only_standard_residues=False)
    coords = np.asarray(atoms["xyz"], dtype=float)
    mates = symmetry_mates(coords, cell, operators_for(space_group), cutoff=5.0)
    assert mates, "a real crystal must have lattice contacts"
    assert len(mates) < 4 * 27 - 1, "the cutoff must reject something"
    for mate in mates:
        assert mate["coords"].shape == coords.shape


# --------------------------------------------------------------------------- #
# The cell box, for drawing it
# --------------------------------------------------------------------------- #
def test_the_box_has_twelve_edges():
    assert len(CELL_EDGES) == 12


def test_every_corner_meets_three_edges():
    """A parallelepiped's corners have degree three. Derived from the bit pattern
    rather than typed out, so this checks the derivation, not a transcription.
    """
    from collections import Counter

    degree = Counter(i for edge in CELL_EDGES for i in edge)
    assert set(degree) == set(range(8))
    assert set(degree.values()) == {3}


def test_the_corners_are_the_fractional_vertices():
    cell = UnitCell(a=10.0, b=20.0, c=30.0)
    corners = cell_corners(cell)
    assert corners.shape == (8, 3)
    # Corner i has fractional coordinates read off i's bits.
    assert np.allclose(corners[0], [0.0, 0.0, 0.0])
    assert np.allclose(corners[1], [10.0, 0.0, 0.0])
    assert np.allclose(corners[2], [0.0, 20.0, 0.0])
    assert np.allclose(corners[4], [0.0, 0.0, 30.0])
    assert np.allclose(corners[7], [10.0, 20.0, 30.0])


def test_the_box_edges_are_the_cell_edges():
    """Twelve edges, four of each cell length -- the check that the edge list and
    the corner numbering agree with each other.
    """
    cell = UnitCell(a=10.0, b=20.0, c=30.0)
    segments = cell_line_segments(cell)
    assert segments.shape == (24, 3)
    lengths = [
        round(float(np.linalg.norm(segments[2 * k + 1] - segments[2 * k])), 6) for k in range(12)
    ]
    from collections import Counter

    assert Counter(lengths) == {10.0: 4, 20.0: 4, 30.0: 4}


def test_a_triclinic_box_still_closes():
    """Opposite edges of a parallelepiped are parallel and equal, whatever the
    angles -- so the twelve lengths still come in three groups of four.
    """
    cell = UnitCell(a=10.0, b=20.0, c=30.0, alpha=70.0, beta=80.0, gamma=100.0)
    segments = cell_line_segments(cell)
    lengths = [
        round(float(np.linalg.norm(segments[2 * k + 1] - segments[2 * k])), 6) for k in range(12)
    ]
    from collections import Counter

    assert sorted(Counter(lengths).values()) == [4, 4, 4]


def test_the_origin_shifts_the_whole_box():
    cell = UnitCell(a=10.0, b=10.0, c=10.0)
    at_origin = cell_corners(cell)
    moved = cell_corners(cell, origin=[5.0, -2.0, 1.0])
    assert np.allclose(moved - at_origin, [5.0, -2.0, 1.0])


# --------------------------------------------------------------------------- #
# `cell` resolves the same way `symexp` does
# --------------------------------------------------------------------------- #
@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def crystal_cmd(qapp, tmp_path):
    """A window with 1RTD -- a file that carries its own CRYST1 record."""
    import shutil

    from chimol.commands.command import Cmd
    from chimol.hosts.qt.window import MolViewPluginWindow

    if not _CRYSTAL.is_file():
        pytest.skip("no crystal fixture")
    pdb = tmp_path / "1rtd.pdb"
    shutil.copyfile(_CRYSTAL, pdb)

    window = MolViewPluginWindow()
    window.load_structure_from_path(pdb, name="1rtd")
    command = Cmd(window)
    errors: list[str] = []
    messages: list[str] = []
    command.set_error_callback(errors.append)
    command.set_message_callback(messages.append)
    command._errors = errors
    command._messages = messages
    return command, window


def test_cell_reads_the_file_like_symexp_does(crystal_cmd):
    """`cell` tested ``state.symmetry`` and nothing else.

    So it worked only after an explicit `set_symmetry`, while `symexp` -- which
    goes through ``_symmetry_for`` and falls back to the file's CRYST1 and then
    the space-group table -- worked straight from the file. Two paths to one
    answer, and the message from the wrong one said the record was missing
    while it sat in the file on screen.
    """
    command, window = crystal_cmd
    command.do("cell all, on")
    assert command._errors == [], command._errors
    assert any("drawn for" in m for m in command._messages), command._messages

    entry = next(iter(window.viewer.objects.values()))
    assert entry.state.show_cell is True
    # ...and the resolution is written back, because the renderer reads it too.
    assert (entry.state.symmetry or {}).get("cell") is not None


def test_cell_off_hides_it_again(crystal_cmd):
    command, window = crystal_cmd
    command.do("cell all, on")
    command.do("cell all, off")
    entry = next(iter(window.viewer.objects.values()))
    assert entry.state.show_cell is False
