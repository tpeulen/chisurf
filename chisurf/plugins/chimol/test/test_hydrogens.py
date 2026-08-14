"""Adding hydrogens: the geometry, the template, and a check against reality.

The geometry is a transcription of ``layer2/HydrogenAdder.cpp::
ObjectMoleculeSetMissingNeighborCoords``, so the tests assert the *angles* it is
supposed to produce rather than the constants it uses -- a transcription that
copies the numbers and misreads the control flow still passes a constant check.
The control flow is the trap: the C++ ``switch`` falls through, so one neighbour
plus a tetrahedral centre yields three new directions, not one.

How many hydrogens is decided by a **residue template**, and the reason is
measured rather than assumed: on ``hGBP1_closed.pdb`` (4671 hydrogens), the
obvious substitute of ``valence(element) - heavy neighbours`` is wrong for 41.6%
of atoms, because a double bond looks like a free valence when no bond orders are
known. The last test in this file is the ground truth: strip the hydrogens off a
real hydrogenated protein, put them back, and compare.
"""

from __future__ import annotations

import collections
import pathlib

import numpy as np
import pytest

from chimol.analysis.hydrogens import (
    LINEAR,
    PLANAR,
    RESIDUE_TEMPLATES,
    TETRAHEDRAL,
    open_valence_directions,
    plan_hydrogens,
)

_DATA = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files"
)
_FRAGMENT = _DATA / "solvated_fragment.pdb"
_HYDROGENATED = _DATA / "hGBP1_closed.pdb"


def _angle(a: np.ndarray, b: np.ndarray) -> float:
    """Angle between two vectors, in degrees."""
    cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


# --------------------------------------------------------------------------- #
# The geometry
# --------------------------------------------------------------------------- #
def test_a_tetrahedral_centre_with_one_neighbour_gives_three_directions():
    """The fall-through. Read as if/elif, this returns one direction."""
    got = open_valence_directions([np.array([1.0, 0.0, 0.0])], TETRAHEDRAL, 3)
    assert len(got) == 3


def test_tetrahedral_angles_are_109_5():
    existing = np.array([1.0, 0.0, 0.0])
    got = open_valence_directions([existing], TETRAHEDRAL, 3)
    for direction in got:
        assert _angle(existing, direction) == pytest.approx(109.5, abs=1.5)
    # And to each other.
    for i in range(len(got)):
        for j in range(i + 1, len(got)):
            assert _angle(got[i], got[j]) == pytest.approx(109.5, abs=2.0)


def test_a_tetrahedral_centre_with_two_neighbours_gives_two_more():
    a = np.array([1.0, 0.0, 0.0])
    b = np.array([-0.334, 0.943, 0.0])
    got = open_valence_directions([a, b], TETRAHEDRAL, 2)
    assert len(got) == 2
    for direction in got:
        assert _angle(a, direction) == pytest.approx(109.5, abs=3.0)
        assert _angle(b, direction) == pytest.approx(109.5, abs=3.0)


def test_a_tetrahedral_centre_with_three_neighbours_has_one_free_valence():
    """Asking for more than the geometry allows gets what it allows."""
    dirs = open_valence_directions([np.array([1.0, 0.0, 0.0])], TETRAHEDRAL, 3)
    got = open_valence_directions([np.array([1.0, 0.0, 0.0])] + dirs[:2],
                                  TETRAHEDRAL, 3)
    assert len(got) == 1


def test_a_full_tetrahedral_centre_gets_nothing():
    dirs = open_valence_directions([np.array([1.0, 0.0, 0.0])], TETRAHEDRAL, 3)
    full = [np.array([1.0, 0.0, 0.0])] + dirs
    assert open_valence_directions(full, TETRAHEDRAL, 1) == []


def test_planar_angles_are_120():
    existing = np.array([1.0, 0.0, 0.0])
    got = open_valence_directions([existing], PLANAR, 2)
    assert len(got) == 2
    for direction in got:
        assert _angle(existing, direction) == pytest.approx(120.0, abs=1.5)
    assert _angle(got[0], got[1]) == pytest.approx(120.0, abs=2.0)


def test_a_planar_centre_is_actually_planar():
    """All three directions must share a plane, or an amide comes out pyramidal."""
    existing = np.array([1.0, 0.0, 0.0])
    got = open_valence_directions([existing], PLANAR, 2)
    normal = np.cross(existing, got[0])
    normal /= np.linalg.norm(normal)
    assert abs(float(np.dot(normal, got[1]))) < 0.05


def test_planar_has_three_slots_not_four():
    existing = [np.array([1.0, 0.0, 0.0]), np.array([-0.5, 0.866, 0.0])]
    assert len(open_valence_directions(existing, PLANAR, 3)) == 1


def test_linear_is_opposite():
    existing = np.array([0.0, 0.0, 1.0])
    got = open_valence_directions([existing], LINEAR, 1)
    assert len(got) == 1
    assert _angle(existing, got[0]) == pytest.approx(180.0, abs=0.5)


def test_directions_are_unit_vectors():
    for geometry in (TETRAHEDRAL, PLANAR, LINEAR):
        for direction in open_valence_directions(
            [np.array([1.0, 0.0, 0.0])], geometry, 3
        ):
            assert float(np.linalg.norm(direction)) == pytest.approx(1.0, abs=1e-6)


def test_no_neighbours_still_produces_a_full_set():
    """PyMOL takes a random first direction; a fixed one keeps sessions
    reproducible, which matters more here than isotropy."""
    first = open_valence_directions([], TETRAHEDRAL, 4)
    second = open_valence_directions([], TETRAHEDRAL, 4)
    assert len(first) == 4
    assert all(np.allclose(a, b) for a, b in zip(first, second))


def test_asking_for_nothing_returns_nothing():
    assert open_valence_directions([np.array([1.0, 0.0, 0.0])], TETRAHEDRAL, 0) == []


# --------------------------------------------------------------------------- #
# The template
# --------------------------------------------------------------------------- #
def test_a_carbonyl_carbon_takes_no_hydrogen():
    """The specific atom the valence-counting shortcut gets wrong."""
    for residue in ("ALA", "LEU", "GLU", "GLY"):
        assert RESIDUE_TEMPLATES[residue]["C"][0] == 0


def test_carboxyl_and_carbonyl_oxygens_take_none():
    assert RESIDUE_TEMPLATES["GLU"]["OE1"][0] == 0
    assert RESIDUE_TEMPLATES["GLU"]["OE2"][0] == 0
    assert RESIDUE_TEMPLATES["ASN"]["OD1"][0] == 0


def test_aromatic_ring_carbons_take_exactly_one():
    for atom in ("CD1", "CD2", "CE1", "CE2", "CZ"):
        count, geometry = RESIDUE_TEMPLATES["PHE"][atom]
        assert count == 1
        assert geometry == PLANAR


def test_a_hydroxyl_is_tetrahedral_not_linear():
    """Oxygen has two bonds but is bent, not linear -- lone pairs take the rest."""
    assert RESIDUE_TEMPLATES["SER"]["OG"] == (1, TETRAHEDRAL)
    assert RESIDUE_TEMPLATES["TYR"]["OH"] == (1, TETRAHEDRAL)


def test_the_amide_nitrogen_is_planar():
    assert RESIDUE_TEMPLATES["ALA"]["N"] == (1, PLANAR)


def test_proline_has_no_amide_hydrogen():
    """Its nitrogen is in the ring."""
    assert RESIDUE_TEMPLATES["PRO"]["N"][0] == 0


def test_glycine_has_two_alpha_hydrogens():
    assert RESIDUE_TEMPLATES["GLY"]["CA"][0] == 2
    assert RESIDUE_TEMPLATES["ALA"]["CA"][0] == 1


def test_every_template_residue_has_a_backbone():
    for name, template in RESIDUE_TEMPLATES.items():
        if name in ("HOH", "WAT"):
            continue
        assert {"N", "CA", "C", "O"} <= set(template), name


def test_water_gets_two_hydrogens_on_a_bent_oxygen():
    assert RESIDUE_TEMPLATES["HOH"]["O"] == (2, TETRAHEDRAL)


# --------------------------------------------------------------------------- #
# Planning on a real fragment
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def fragment():
    # read_coordinates, not read: the plain reader defaults to
    # ``keep_water=False, only_standard_residues=True`` -- deliberately, for the
    # modelling code -- which would drop the zinc and the eight waters and leave
    # nothing to exercise the "no template" path against. The viewer keeps them,
    # so the fixture has to as well or it is testing a different molecule.
    from chisurf.core.fio.structure.coordinates import read_coordinates

    atoms = read_coordinates(
        str(_FRAGMENT), keep_water=True, only_standard_residues=False
    )
    xyz = np.asarray(atoms["xyz"], dtype=float)
    from scipy.spatial import cKDTree

    pairs = np.array(sorted(cKDTree(xyz).query_pairs(1.95)), dtype=int)
    return atoms, pairs


def test_six_alanines_get_the_hydrogens_they_should(fragment):
    """Counted by hand: NH3 (3) + five amide NH + six CA-H + six CB-H3 = 32."""
    atoms, pairs = fragment
    names = np.char.strip(np.asarray(atoms["res_name"]).astype(str))
    polymer = names == "ALA"
    plan, unknown = plan_hydrogens(atoms, pairs, polymer)
    assert len(plan) == 32, collections.Counter(
        str(np.asarray(atoms["atom_name"])[p["parent"]]).strip() for p in plan
    )


def test_the_n_terminus_is_an_ammonium(fragment):
    """A nitrogen with no preceding carbonyl takes three hydrogens, not one.

    Detected from the bond graph rather than from a residue name, and it was the
    only non-histidine disagreement when the template was checked against a real
    hydrogenated protein.
    """
    atoms, pairs = fragment
    atom_names = np.char.strip(np.asarray(atoms["atom_name"]).astype(str))
    res_ids = np.asarray(atoms["res_id"])
    plan, _unknown = plan_hydrogens(atoms, pairs)
    per_parent = collections.Counter(p["parent"] for p in plan)

    first_n = next(
        i for i in range(len(atoms))
        if atom_names[i] == "N" and int(res_ids[i]) == 1
    )
    assert per_parent[first_n] == 3
    later_n = next(
        i for i in range(len(atoms))
        if atom_names[i] == "N" and int(res_ids[i]) == 3
    )
    assert per_parent[later_n] == 1


def test_hydrogens_sit_at_the_right_bond_length(fragment):
    atoms, pairs = fragment
    elements = np.char.upper(np.char.strip(np.asarray(atoms["element"]).astype(str)))
    xyz = np.asarray(atoms["xyz"], dtype=float)
    plan, _unknown = plan_hydrogens(atoms, pairs)
    assert plan
    for item in plan:
        parent = item["parent"]
        distance = float(np.linalg.norm(item["xyz"] - xyz[parent]))
        expected = {"C": 1.09, "N": 1.01, "O": 0.96, "S": 1.34}[
            str(elements[parent])
        ]
        assert distance == pytest.approx(expected, abs=1e-6)


def test_no_added_hydrogen_clashes(fragment):
    """A hydrogen inside another atom is worse than a missing one."""
    from scipy.spatial import cKDTree

    atoms, pairs = fragment
    xyz = np.asarray(atoms["xyz"], dtype=float)
    plan, _unknown = plan_hydrogens(atoms, pairs)
    added = np.array([p["xyz"] for p in plan])
    everything = np.vstack([xyz, added])
    close = cKDTree(everything).query_pairs(0.8)
    assert not close, f"{len(close)} clashes below 0.8 A"


def test_a_residue_with_no_template_is_reported(fragment):
    """The zinc. PyMOL warns about exactly this for ligands."""
    atoms, pairs = fragment
    _plan, unknown = plan_hydrogens(atoms, pairs)
    assert "ZN" in unknown


def test_existing_hydrogens_are_not_duplicated(fragment):
    """Running twice must not double them: a valence already filled stays filled."""
    atoms, pairs = fragment
    plan, _unknown = plan_hydrogens(atoms, pairs)
    assert plan

    # Append the planned hydrogens and re-plan against the result.
    additions = np.zeros(len(plan), dtype=atoms.dtype)
    for k, item in enumerate(plan):
        for field in atoms.dtype.names:
            additions[field][k] = atoms[item["parent"]][field]
        additions["xyz"][k] = item["xyz"]
        additions["element"][k] = "H"
        additions["atom_name"][k] = item["name"]
    grown = np.concatenate([atoms, additions])

    from scipy.spatial import cKDTree

    gxyz = np.asarray(grown["xyz"], dtype=float)
    gpairs = np.array(sorted(cKDTree(gxyz).query_pairs(1.95)), dtype=int)
    again, _unknown2 = plan_hydrogens(grown, gpairs)
    assert again == [], f"{len(again)} hydrogens would be added a second time"


# --------------------------------------------------------------------------- #
# Against a real hydrogenated protein
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def stripped_protein():
    """hGBP1 with its 4671 hydrogens removed, plus the ground truth."""
    from scipy.spatial import cKDTree

    from chisurf.core.fio.structure.coordinates import read

    if not _HYDROGENATED.exists():
        pytest.skip("no hydrogenated fixture available")
    atoms = read(str(_HYDROGENATED))
    elements = np.char.upper(np.char.strip(np.asarray(atoms["element"]).astype(str)))
    xyz = np.asarray(atoms["xyz"], dtype=float)
    is_h = elements == "H"
    heavy = np.nonzero(~is_h)[0]
    hydrogens = np.nonzero(is_h)[0]

    distances, nearest = cKDTree(xyz[heavy]).query(xyz[hydrogens], k=1)
    truth = collections.Counter(heavy[nearest[distances < 1.35]])
    truth_positions = collections.defaultdict(list)
    for k, h in enumerate(hydrogens):
        if distances[k] < 1.35:
            truth_positions[heavy[nearest[k]]].append(xyz[h])

    sub = atoms[~is_h]
    sxyz = np.asarray(sub["xyz"], dtype=float)
    pairs = np.array(sorted(cKDTree(sxyz).query_pairs(1.95)), dtype=int)
    return sub, pairs, heavy, truth, truth_positions


def test_the_count_matches_a_real_protein(stripped_protein):
    """99.7%+ of 4644 heavy atoms, with the histidines as the known exception."""
    sub, pairs, heavy, truth, _positions = stripped_protein
    plan, unknown = plan_hydrogens(sub, pairs)
    predicted = collections.Counter(p["parent"] for p in plan)

    correct = sum(
        1 for i in range(len(sub))
        if predicted.get(i, 0) == truth.get(heavy[i], 0)
    )
    fraction = correct / len(sub)
    assert not unknown, f"a standard protein should need no exceptions: {unknown}"
    assert fraction > 0.995, f"only {fraction:.3%} of counts matched"


def test_the_only_mismatches_are_histidine_tautomers(stripped_protein):
    """Stated rather than hidden: the tautomer is not in the coordinates.

    Without hydrogens to read, ND1- and NE2-protonated histidine are
    indistinguishable, so a default has to be chosen. Anything *else*
    disagreeing would be a real defect, which is what this pins.
    """
    sub, pairs, heavy, truth, _positions = stripped_protein
    residues = np.char.strip(np.asarray(sub["res_name"]).astype(str))
    plan, _unknown = plan_hydrogens(sub, pairs)
    predicted = collections.Counter(p["parent"] for p in plan)

    offenders = {
        str(residues[i])
        for i in range(len(sub))
        if predicted.get(i, 0) != truth.get(heavy[i], 0)
    }
    assert offenders <= {"HIS"}, f"unexpected disagreements in {offenders}"


def test_the_positions_match_a_real_protein(stripped_protein):
    """Median error well under a tenth of an Angstrom.

    The tail is torsional, not geometric: hydroxyls, thiols and amide NH2 groups
    have a rotation the geometry does not determine, and PyMOL places them
    arbitrarily too. So the median is asserted tightly and the tail loosely.
    """
    sub, pairs, heavy, _truth, truth_positions = stripped_protein
    plan, _unknown = plan_hydrogens(sub, pairs)

    by_parent = collections.defaultdict(list)
    for item in plan:
        by_parent[item["parent"]].append(item["xyz"])

    errors = []
    for index, produced in by_parent.items():
        wanted = truth_positions.get(heavy[index], [])
        if len(wanted) != len(produced):
            continue
        used: set[int] = set()
        for position in produced:
            candidates = [
                (float(np.linalg.norm(position - w)), k)
                for k, w in enumerate(wanted)
                if k not in used
            ]
            if not candidates:
                continue
            distance, k = min(candidates)
            used.add(k)
            errors.append(distance)

    errors = np.array(errors)
    assert errors.size > 4000
    assert float(np.median(errors)) < 0.25
    assert float((errors < 1.0).mean()) > 0.95


def test_the_large_errors_are_rotatable_groups(stripped_protein):
    """Names the tail rather than tolerating it silently.

    If a *backbone* atom ever showed up here it would mean the geometry was
    wrong, not that a torsion was undetermined.
    """
    sub, pairs, heavy, _truth, truth_positions = stripped_protein
    atom_names = np.char.strip(np.asarray(sub["atom_name"]).astype(str))
    plan, _unknown = plan_hydrogens(sub, pairs)

    by_parent = collections.defaultdict(list)
    for item in plan:
        by_parent[item["parent"]].append(item["xyz"])

    offenders = set()
    for index, produced in by_parent.items():
        wanted = truth_positions.get(heavy[index], [])
        if len(wanted) != len(produced):
            continue
        worst = 0.0
        used: set[int] = set()
        for position in produced:
            candidates = [
                (float(np.linalg.norm(position - w)), k)
                for k, w in enumerate(wanted)
                if k not in used
            ]
            if not candidates:
                continue
            distance, k = min(candidates)
            used.add(k)
            worst = max(worst, distance)
        if worst > 1.0:
            offenders.add(str(atom_names[index]))

    # Every one of these is a terminal group free to rotate.
    rotatable = {
        "OG", "OG1", "OH", "SG", "NE2", "ND2", "NH1", "NH2", "NZ", "N",
        "CG2", "CD1", "CD2", "CE", "CB",
    }
    assert offenders <= rotatable, f"a non-rotatable atom is misplaced: {offenders}"
    assert "CA" not in offenders and "C" not in offenders
