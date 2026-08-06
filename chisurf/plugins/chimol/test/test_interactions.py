"""Hydrogen-bond networks and the bump check.

The clash arithmetic is transcribed from sculpting's van der Waals term, so the
tests assert the three things a reader loses when they re-derive it: that a
hydrogen bond is *not* a clash (the pair cutoff drops by the hb allowance), that
bonded neighbours are excluded and a 1-4 pair merely softened, and that the
colour crosses from green to red exactly where `sculpt_vdw_vis_mid` and `_max`
put it.

The networks are ours rather than PyMOL's -- it has no notion of one -- so those
tests are about the grouping: what counts as connected, and what the three water
policies do to a donor-water-acceptor bridge, which is the case the whole
feature exists for.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.analysis.clashes import (
    BAD_COLOR,
    GOOD_COLOR,
    ClashCriteria,
    clash_color,
    find_clashes,
    radii_for,
)
from chisurf.plugins.chimol.chimol.analysis.hbond_networks import (
    NetworkOptions,
    find_hbond_networks,
    network_colors,
)
from chisurf.plugins.chimol.chimol.analysis.hbonds import HBond

_PDB = pathlib.Path(__file__).resolve().parents[4] / "test" / "data" / (
    "atomic_coordinates"
) / "pdb_files"


def _atoms(*rows) -> np.ndarray:
    """``(name, resn, resi, chain, element, xyz)`` as a structured array."""
    dtype = np.dtype([
        ("atom_name", "U4"), ("res_name", "U4"), ("res_id", "i4"),
        ("chain", "U2"), ("element", "U2"), ("xyz", "f8", 3),
    ])
    return np.array(
        [(n, r, i, c, e, tuple(v)) for n, r, i, c, e, v in rows], dtype=dtype
    )


# --------------------------------------------------------------------------- #
# Clashes
# --------------------------------------------------------------------------- #
def test_two_carbons_inside_each_other_clash():
    """The cutoff is the sum of the radii and the overlap is what is left."""
    coords = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0]])
    radii = np.array([1.7, 1.7])

    report = find_clashes(coords, radii, [])

    assert len(report.clashes) == 1
    clash = report.clashes[0]
    assert clash.cutoff == pytest.approx(3.4)
    assert clash.overlap == pytest.approx(0.4)
    # SculptDoBump's strain: |cutoff * vdw_scale - distance|.
    assert clash.strain == pytest.approx(abs(3.4 * 0.97 - 3.0))
    assert report.strain == pytest.approx(clash.strain)


def test_a_comfortable_contact_is_reported_but_costs_nothing():
    """`sculpt_vdw_vis_min` is *negative*: a pair just outside contact is drawn.

    In green, saying "this one is fine". Reading `min` as a positive threshold
    drops exactly the contacts a bump check is meant to reassure you about.
    """
    coords = np.array([[0.0, 0.0, 0.0], [3.45, 0.0, 0.0]])
    radii = np.array([1.7, 1.7])

    report = find_clashes(coords, radii, [])

    assert len(report.clashes) == 1
    assert report.clashes[0].overlap < 0
    assert report.strain == 0.0


def test_a_hydrogen_bond_is_not_a_clash():
    """Without the hb allowance every hydrogen bond reports as an overlap.

    A donor N and an acceptor O at 2.9 A are 0.15 A inside the sum of their
    radii; `sculpt_hb_overlap_base` (0.35) is what says that is a bond rather
    than a bump.
    """
    coords = np.array([[0.0, 0.0, 0.0], [2.9, 0.0, 0.0]])
    radii = np.array([1.55, 1.5])
    donors = np.array([True, False])
    acceptors = np.array([False, True])

    plain = find_clashes(coords, radii, [])
    typed = find_clashes(coords, radii, [], donors=donors, acceptors=acceptors)

    assert plain.clashes[0].overlap > 0, "the fixture is not close enough to test"
    assert plain.strain > 0
    assert typed.strain == 0.0, "the hydrogen-bond allowance did not apply"


def test_bonded_neighbours_never_clash():
    """1-2, 1-3 and 1-4 pairs are never *drawn* -- PyMOL's `ex` arms.

    Two bonded carbons are 1.5 A apart, a metre inside the sum of their radii;
    without the exclusion every bond in the structure is a clash. A 1-4 pair
    is the subtler one: PyMOL scales its cutoff by `sculpt_vdw_scale14` and
    counts its strain, but never calls `SculptCGOBump` for it, because a
    torsion the geometry already fixes is not something to draw a red line
    across -- and drawing them buries the real clashes in intra-residue haze.
    """
    coords = np.array([
        [0.0, 0.0, 0.0], [1.5, 0.0, 0.0], [2.2, 1.2, 0.0], [2.9, 0.1, 0.0],
    ])
    radii = np.full(4, 1.7)
    bonds = [(0, 1), (1, 2), (2, 3)]

    report = find_clashes(coords, radii, bonds)

    assert report.clashes == [], "a bonded chain has nothing to draw"
    assert report.strain > 0, "the 1-4 pair still contributes strain"


def test_a_one_four_pair_uses_the_softer_scale():
    """`sculpt_vdw_scale14` is 0.90 against 0.97, so a 1-4 pair strains less."""
    coords = np.array([
        [0.0, 0.0, 0.0], [1.5, 0.0, 0.0], [2.2, 1.2, 0.0], [2.9, 0.1, 0.0],
    ])
    radii = np.full(4, 1.7)
    bonded = find_clashes(coords, radii, [(0, 1), (1, 2), (2, 3)])
    free = find_clashes(coords, radii, [])

    same_pair = next(c for c in free.clashes if (c.i, c.j) == (0, 3))
    assert bonded.strain < same_pair.strain


def test_the_bump_colour_runs_green_to_red_where_pymol_puts_it():
    criteria = ClashCriteria()
    assert clash_color(criteria.vis_mid - 0.01, criteria) == pytest.approx(GOOD_COLOR)
    assert clash_color(
        criteria.vis_mid + criteria.vis_max, criteria
    ) == pytest.approx(BAD_COLOR)
    half = clash_color(criteria.vis_mid + criteria.vis_max / 2, criteria)
    assert half[0] == pytest.approx(0.5 * GOOD_COLOR[0] + 0.5 * BAD_COLOR[0])


def test_the_subject_restricts_which_pairs_are_looked_at():
    """Only pairs involving the subject are looked at.

    The wizard checks one side chain against everything, not everything against
    everything -- and on a real neighbourhood that is the difference between
    fifty pairs and nine million.
    """
    coords = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [6.0, 0.0, 0.0], [9.0, 0.0, 0.0]])
    radii = np.full(4, 1.7)

    everything = find_clashes(coords, radii, [])
    just_one = find_clashes(coords, radii, [], subject=np.array([1]))

    assert len(everything.clashes) == 3
    assert {(c.i, c.j) for c in just_one.clashes} == {(0, 1), (1, 2)}


# --------------------------------------------------------------------------- #
# Networks
# --------------------------------------------------------------------------- #
def _bond(donor: int, acceptor: int) -> HBond:
    return HBond(
        donor=donor, acceptor=acceptor, hydrogen=None,
        hydrogen_xyz=np.zeros(3), distance=2.9,
    )


def test_bonds_that_share_an_atom_are_one_network():
    atoms = _atoms(
        ("N", "SER", 1, "A", "N", (0, 0, 0)),
        ("OG", "SER", 1, "A", "O", (3, 0, 0)),
        ("OD1", "ASP", 2, "A", "O", (6, 0, 0)),
        ("N", "LYS", 9, "A", "N", (20, 0, 0)),
        ("O", "GLU", 8, "A", "O", (23, 0, 0)),
    )
    bonds = [_bond(0, 1), _bond(1, 2), _bond(3, 4)]

    networks = find_hbond_networks(atoms, None, bonds=bonds)

    assert [net.size for net in networks] == [2, 1]
    assert networks[0].atoms == [0, 1, 2]
    assert len(networks[0].residues) == 2


def test_water_bridges_two_halves_or_does_not(monkeypatch):
    """The three water policies, on the case the feature exists for.

    A donor and an acceptor too far apart to bond, each bonded to the same
    ordered water: one network through the water, two lone bonds without it,
    and nothing at all when only water-to-water is asked for.
    """
    atoms = _atoms(
        ("OG", "SER", 1, "A", "O", (0, 0, 0)),
        ("O", "HOH", 500, "A", "O", (3, 0, 0)),
        ("OD1", "ASP", 2, "A", "O", (6, 0, 0)),
    )
    bonds = [_bond(0, 1), _bond(1, 2)]

    bridged = find_hbond_networks(atoms, None, bonds=bonds)
    assert [net.size for net in bridged] == [2]
    assert bridged[0].waters == 1

    without = find_hbond_networks(
        atoms, None, bonds=bonds, options=NetworkOptions(waters="exclude")
    )
    assert without == []

    wire = find_hbond_networks(
        atoms, None, bonds=bonds, options=NetworkOptions(waters="only")
    )
    assert wire == []


def test_a_water_wire_is_found_on_its_own():
    atoms = _atoms(
        ("O", "HOH", 1, "A", "O", (0, 0, 0)),
        ("O", "HOH", 2, "A", "O", (3, 0, 0)),
        ("O", "HOH", 3, "A", "O", (6, 0, 0)),
        ("OG", "SER", 9, "A", "O", (9, 0, 0)),
    )
    bonds = [_bond(0, 1), _bond(1, 2), _bond(2, 3)]

    wire = find_hbond_networks(
        atoms, None, bonds=bonds, options=NetworkOptions(waters="only")
    )

    assert [net.size for net in wire] == [2]
    assert wire[0].waters == 3


def test_min_size_drops_the_lone_surface_contacts():
    atoms = _atoms(
        ("N", "SER", 1, "A", "N", (0, 0, 0)),
        ("OG", "SER", 1, "A", "O", (3, 0, 0)),
        ("OD1", "ASP", 2, "A", "O", (6, 0, 0)),
        ("N", "LYS", 9, "A", "N", (20, 0, 0)),
        ("O", "GLU", 8, "A", "O", (23, 0, 0)),
    )
    bonds = [_bond(0, 1), _bond(1, 2), _bond(3, 4)]

    kept = find_hbond_networks(
        atoms, None, bonds=bonds, options=NetworkOptions(min_size=2)
    )

    assert [net.size for net in kept] == [2]


def test_a_network_reports_the_chains_it_spans():
    atoms = _atoms(
        ("OG", "SER", 1, "A", "O", (0, 0, 0)),
        ("OD1", "ASP", 2, "B", "O", (3, 0, 0)),
    )
    networks = find_hbond_networks(atoms, None, bonds=[_bond(0, 1)])

    assert networks[0].spans_chains
    assert networks[0].chains == ["A", "B"]
    assert "chains A+B" in networks[0].describe()


def test_the_colours_are_stable_and_cycle():
    """A figure whose networks change colour between runs cannot be referred to."""
    assert network_colors(3) == network_colors(3)
    assert network_colors(12)[10] == network_colors(12)[0]


# --------------------------------------------------------------------------- #
# On a real structure
# --------------------------------------------------------------------------- #
def _read(name: str):
    from chisurf.core.fio.structure.coordinates import read_coordinates
    from chisurf.plugins.chimol.chimol.geometry.bonds import (
        build_bond_pairs_by_element,
    )

    path = _PDB / name
    if not path.exists():
        pytest.skip(f"no {name} fixture")
    atoms = read_coordinates(
        str(path), keep_water=True, only_standard_residues=False
    )
    elements = np.char.strip(np.asarray(atoms["element"]).astype(str))
    bonds = build_bond_pairs_by_element(
        np.asarray(atoms["xyz"], dtype=float),
        np.asarray(atoms["radius"], dtype=float),
        elements,
    )
    return atoms, bonds


def test_a_real_protein_has_networks_and_almost_no_clashes():
    """148L: a deposited structure is refined, so its strain must be small.

    This is the test that would catch the hydrogen-bond allowance going
    missing, or the neighbour exclusion breaking -- either turns a clean
    crystal structure into hundreds of clashes.
    """
    from chisurf.plugins.chimol.chimol.analysis.hbonds import type_atoms

    atoms, bonds = _read("148l.pdb")
    networks = find_hbond_networks(atoms, bonds, options=NetworkOptions(min_size=3))
    assert networks, "no hydrogen-bond networks in a 165-residue protein"
    assert networks[0].size >= 5, "the largest network is suspiciously small"

    typing = type_atoms(atoms, bonds)
    elements = np.char.strip(np.asarray(atoms["element"]).astype(str))
    report = find_clashes(
        np.asarray(atoms["xyz"], dtype=float),
        radii_for(elements),
        bonds,
        donors=typing.donor,
        acceptors=typing.acceptor,
        is_hydrogen=np.isin(elements, ("H", "D")),
    )
    overlapping = [c for c in report.clashes if c.overlap > 0.4]
    assert len(overlapping) < 0.05 * len(atoms), (
        f"{len(overlapping)} deep overlaps in a refined structure of "
        f"{len(atoms)} atoms -- the exclusion or the hb allowance is not applying"
    )
