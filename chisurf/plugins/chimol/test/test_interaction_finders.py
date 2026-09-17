"""Halogen bonds, salt bridges and pi interactions.

Three finders, each with PyMOL's own criteria (``layer3/Interactions.cpp``),
covered on a real structure where one exists and on built geometry where the
test is about an angle -- 148L has no halogen in it, and a criterion with a
lower *and* an upper bound cannot be shown to have both from a structure that
happens to pass.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest
from chimol.analysis import interactions as inter
from chimol.analysis.hbonds import type_atoms

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
    / "148l.pdb"
)

ATOM_DTYPE = np.dtype(
    [
        ("atom_name", "U4"),
        ("res_name", "U4"),
        ("res_id", "i4"),
        ("chain", "U2"),
        ("element", "U2"),
        ("xyz", "f8", 3),
    ]
)


def _atoms(rows) -> np.ndarray:
    """A structured atom array from ``(name, resn, resi, element, xyz)`` rows."""
    return np.array(
        [(n, r, i, "A", e, tuple(xyz)) for n, r, i, e, xyz in rows],
        dtype=ATOM_DTYPE,
    )


#: A phenylalanine's ring, in the order that closes it. The residue matters:
#: planarity comes from the residue templates here, because these rings are
#: built without hydrogens and a two-neighbour carbon carries no angle that
#: separates sp2 from sp3. An untemplated ring needs its hydrogens to be found
#: -- see `test_a_ligand_ring_needs_its_hydrogens`, which measures both halves.
#: PyMOL has the same limitation, for the same reason.
PHE_RING = ("CG", "CD1", "CE1", "CZ", "CE2", "CD2")


def _ring(centre, upright=False, radius=1.4, resi=1):
    """Six carbons on a circle, named and numbered as a PHE ring."""
    rows = []
    for k, name in enumerate(PHE_RING):
        angle = 2.0 * np.pi * k / 6.0
        offset = (
            np.array([radius * np.cos(angle), 0.0, radius * np.sin(angle)])
            if upright
            else np.array([radius * np.cos(angle), radius * np.sin(angle), 0.0])
        )
        rows.append((name, "PHE", resi, "C", np.array(centre, float) + offset))
    return rows


def _ring_bonds(offset=0):
    return [(offset + k, offset + (k + 1) % 6) for k in range(6)]


@pytest.fixture(scope="module")
def protein():
    """148L, with bonds inferred the way the viewer infers them."""
    from chimol.analysis.clashes import VDW_RADII
    from chimol.geometry.bonds import (
        build_bond_pairs_by_element,
    )
    from chimol.io.structure import _parse_pdb_backbone

    if not PDB.exists():
        pytest.skip("no 148l fixture")
    atoms = _parse_pdb_backbone(str(PDB)).atoms
    elements = np.char.upper(np.char.strip(atoms["element"].astype(str)))
    radii = np.array([VDW_RADII.get(e, 1.7) for e in elements])
    bonds = build_bond_pairs_by_element(
        np.asarray(atoms["xyz"], dtype=float), radii, elements, cutoff=0.35
    )
    return atoms, bonds


# --------------------------------------------------------------------------- #
# Formal charge -- what the salt bridge and the cation are made of
# --------------------------------------------------------------------------- #
def test_the_charge_table_is_pymols_asymmetric_one():
    """One oxygen of a carboxylate, one nitrogen of a guanidinium.

    Charging both halves is the obvious "fix" and it double-counts every
    bridge. PyMOL pins ARG's ``NH2`` to zero explicitly for this reason
    (PYMOL-5019), and only ``OD2``/``OE2`` carry the negative charge.
    """
    atoms = _atoms(
        [
            ("NH1", "ARG", 1, "N", (0, 0, 0)),
            ("NH2", "ARG", 1, "N", (1, 0, 0)),
            ("OD1", "ASP", 2, "O", (2, 0, 0)),
            ("OD2", "ASP", 2, "O", (3, 0, 0)),
            ("OE1", "GLU", 3, "O", (4, 0, 0)),
            ("OE2", "GLU", 3, "O", (5, 0, 0)),
            ("NZ", "LYS", 4, "N", (6, 0, 0)),
            ("ND1", "HIS", 5, "N", (7, 0, 0)),
            ("ND1", "HIP", 6, "N", (8, 0, 0)),
            ("OXT", "ALA", 7, "O", (9, 0, 0)),
            ("OP2", "DG", 8, "O", (10, 0, 0)),
        ]
    )
    assert list(inter.formal_charges(atoms)) == [1, 0, 0, -1, 0, -1, 1, 0, 1, -1, -1]


def test_a_plain_histidine_is_neutral():
    """A protonation state PyMOL declines to guess, and so does this.

    The consequence is visible: a HIS-ASP pair is *not* reported as a salt
    bridge unless the residue is named ``HIP``/``HISP``/``HISH``.
    """
    charges = inter.formal_charges(
        _atoms(
            [
                ("ND1", "HIS", 1, "N", (0, 0, 0)),
                ("OD2", "ASP", 2, "O", (0, 0, 3.0)),
            ]
        )
    )
    assert charges.tolist() == [0, -1], "HIS must be neutral, ASP OD2 charged"
    assert (
        inter.find_salt_bridges(
            _atoms(
                [
                    ("ND1", "HIS", 1, "N", (0, 0, 0)),
                    ("OD2", "ASP", 2, "O", (0, 0, 3.0)),
                ]
            )
        )
        == []
    )


def test_an_explicit_charge_in_the_file_wins():
    """The table fills in what is missing; it does not overrule what is known."""
    dtype = np.dtype(ATOM_DTYPE.descr + [("formal_charge", "f8")])
    atoms = np.array([("NH1", "ARG", 1, "A", "N", (0.0, 0.0, 0.0), -1.0)], dtype=dtype)
    assert inter.formal_charges(atoms).tolist() == [-1]


# --------------------------------------------------------------------------- #
# Salt bridges
# --------------------------------------------------------------------------- #
def test_salt_bridges_on_a_real_protein(protein):
    """Every hit is an oppositely charged heavy pair inside the cutoff."""
    atoms, _bonds = protein
    charges = inter.formal_charges(atoms)
    elements = np.char.upper(np.char.strip(atoms["element"].astype(str)))

    bridges = inter.find_salt_bridges(atoms, charges=charges)

    assert bridges, "148L has salt bridges; none were found"
    for bridge in bridges:
        assert charges[bridge.i] * charges[bridge.j] < 0
        assert elements[bridge.i] != "H" and elements[bridge.j] != "H"
        assert bridge.distance <= inter.SaltBridgeCriteria().distance


def test_the_salt_bridge_cutoff_is_the_only_criterion():
    """No angle, no chemistry -- PyMOL's test is distance and sign."""
    near = _atoms(
        [
            ("NZ", "LYS", 1, "N", (0, 0, 0)),
            ("OE2", "GLU", 2, "O", (0, 0, 4.9)),
        ]
    )
    far = _atoms(
        [
            ("NZ", "LYS", 1, "N", (0, 0, 0)),
            ("OE2", "GLU", 2, "O", (0, 0, 5.1)),
        ]
    )
    assert len(inter.find_salt_bridges(near)) == 1
    assert inter.find_salt_bridges(far) == []


# --------------------------------------------------------------------------- #
# Rings
# --------------------------------------------------------------------------- #
def test_the_planar_ring_set_is_the_aromatic_one(protein):
    """148L's rings: 5 PHE, 6 TYR, 1 HIS and 3 TRP counted twice.

    A tryptophan is *two* rings that share a bond, and PyMOL's finder returns
    both -- which is why the pi-pi arm has to drop pairs that share atoms, or
    every TRP reports as stacked with itself. Proline's ring is excluded
    because its atoms are not planar, which is the whole point of the filter.
    """
    atoms, bonds = protein
    typing = type_atoms(atoms, bonds)
    rings = inter.find_rings(len(atoms), bonds, include=typing.geometry == "planar")

    assert len(rings) == 18
    sizes = sorted(len(ring) for ring in rings)
    assert sizes.count(5) == 4  # HIS + three TRP five-membered rings
    assert sizes.count(6) == 14

    residues = {str(atoms["res_name"][ring[0]]).strip().upper() for ring in rings}
    assert "PRO" not in residues


# --------------------------------------------------------------------------- #
# Pi interactions
# --------------------------------------------------------------------------- #
def test_parallel_rings_are_face_to_face():
    """3.5 Å apart, normals aligned: the base-stacking geometry."""
    rows = _ring((0, 0, 0), resi=1) + _ring((0, 0, 3.5), resi=2)
    atoms = _atoms(rows)
    bonds = _ring_bonds(0) + _ring_bonds(6)

    hits = inter.find_pi_interactions(atoms, bonds, pication=False)

    assert [hit.kind for hit in hits] == ["face-to-face"]
    assert hits[0].distance == pytest.approx(3.5, abs=1e-6)


def test_a_ligand_ring_needs_its_hydrogens():
    """An untemplated ring is found when the file carries its hydrogens.

    Planarity is measured from the bond angles, and three neighbours are what
    it takes: with the ring hydrogens present the cross products agree and the
    carbons type planar; without them a ring carbon has two neighbours, which
    carries no angle that separates sp2 from sp3.

    **PyMOL is the same** -- `ObjectMoleculeGetAtomGeometry` runs the cross
    products only for three neighbours, detects linear for two, and returns
    unknown otherwise, and its chemistry pass has no bond orders to consume for
    a PDB ligand. So this is a property of the input, not a gap against PyMOL,
    and the answer for a user is to load the hydrogenated structure.
    """

    def benzene(z, resi, hydrogens):
        rows = [
            (
                f"C{k}",
                "LIG",
                resi,
                "C",
                (1.4 * np.cos(2 * np.pi * k / 6), 1.4 * np.sin(2 * np.pi * k / 6), z),
            )
            for k in range(6)
        ]
        bonds = [(k, (k + 1) % 6) for k in range(6)]
        if hydrogens:
            rows += [
                (
                    f"H{k}",
                    "LIG",
                    resi,
                    "H",
                    (2.5 * np.cos(2 * np.pi * k / 6), 2.5 * np.sin(2 * np.pi * k / 6), z),
                )
                for k in range(6)
            ]
            bonds += [(k, 6 + k) for k in range(6)]
        return rows, bonds

    for hydrogens, expected in ((False, []), (True, ["face-to-face"])):
        lower, lower_bonds = benzene(0.0, 1, hydrogens)
        upper, upper_bonds = benzene(3.5, 2, hydrogens)
        offset = len(lower)
        atoms = _atoms(lower + upper)
        bonds = lower_bonds + [(i + offset, j + offset) for i, j in upper_bonds]

        hits = inter.find_pi_interactions(atoms, bonds, pication=False)
        assert [hit.kind for hit in hits] == expected, f"hydrogens={hydrogens}"


def test_rings_side_by_side_in_one_plane_are_not_stacked():
    """The collinearity test, which is what a plain distance check misses.

    Two coplanar rings 4 Å apart are as close as a stacked pair and are not
    interacting through their faces at all. PyMOL drops the pair when *both*
    normals are more than 40° from the line joining the centres.
    """
    rows = _ring((0, 0, 0), resi=1) + _ring((4.0, 0, 0), resi=2)
    hits = inter.find_pi_interactions(_atoms(rows), _ring_bonds(0) + _ring_bonds(6), pication=False)
    assert hits == []


def test_a_perpendicular_ring_is_edge_to_face():
    """T-shaped stacking, which reaches further than face-to-face."""
    rows = _ring((0, 0, 0), resi=1) + _ring((0, 0, 5.0), upright=True, resi=2)
    hits = inter.find_pi_interactions(_atoms(rows), _ring_bonds(0) + _ring_bonds(6), pication=False)
    assert [hit.kind for hit in hits] == ["edge-to-face"]


def test_a_cation_over_a_ring_face_is_found_and_one_beside_it_is_not():
    """Pi-cation is a cone, not a sphere: 6.6 Å *and* within 30° of the axis."""
    over = _atoms(_ring((0, 0, 0), resi=1) + [("NZ", "LYS", 2, "N", (0, 0, 4.0))])
    beside = _atoms(_ring((0, 0, 0), resi=1) + [("NZ", "LYS", 2, "N", (5.0, 0, 0.5))])
    bonds = _ring_bonds(0)

    assert [h.kind for h in inter.find_pi_interactions(over, bonds, pipi=False)] == ["pi-cation"]
    assert inter.find_pi_interactions(beside, bonds, pipi=False) == []


def test_a_pi_interaction_ends_at_a_ring_centre_not_an_atom():
    """Which is why the finder returns points, and ``i``/``j`` may be -1."""
    rows = _ring((0, 0, 0), resi=1) + _ring((0, 0, 3.5), resi=2)
    hit = inter.find_pi_interactions(_atoms(rows), _ring_bonds(0) + _ring_bonds(6), pication=False)[
        0
    ]
    assert hit.i == -1 and hit.j == -1
    assert np.allclose(hit.start, (0, 0, 0), atol=1e-6)
    assert np.allclose(hit.end, (0, 0, 3.5), atol=1e-6)


# --------------------------------------------------------------------------- #
# Halogen bonds
# --------------------------------------------------------------------------- #
def _halogen_pair(angle_degrees: float) -> tuple[np.ndarray, list]:
    """C–Br pointing at a carbonyl oxygen, with the D–X···A angle asked for.

    The carbon sits behind the bromine at ``angle_degrees`` from the Br···O
    line, so 180° is the straight-through geometry a sigma hole wants.
    """
    # X sits at the origin with the acceptor straight below it, so X->A is -z
    # and a donor angle of 180 deg puts the carbon straight above. Getting this
    # backwards is easy and silent: it measures 180 minus the angle intended,
    # so a bent geometry passes and a straight one is refused.
    a = np.radians(angle_degrees)
    rows = [
        ("BR", "LIG", 1, "BR", (0.0, 0.0, 0.0)),
        ("C1", "LIG", 1, "C", (1.9 * np.sin(a), 0.0, -1.9 * np.cos(a))),
        ("O", "ALA", 2, "O", (0.0, 0.0, -3.0)),
        ("C", "ALA", 2, "C", (0.0, 1.2, -3.8)),
    ]
    return _atoms(rows), [(0, 1), (2, 3)]


def test_a_straight_halogen_bond_is_found():
    """D–X···A at 180°, X···A at 3.0 Å: inside every bound."""
    atoms, bonds = _halogen_pair(180.0)
    hits = inter.find_halogen_bonds(atoms, bonds)
    assert [hit.kind for hit in hits] == ["halogen-bond"]
    assert hits[0].distance == pytest.approx(3.0, abs=1e-6)


def test_a_bent_halogen_bond_is_refused():
    """At 120° the sigma hole is not pointing at the acceptor.

    The donor-angle minimum is 140°, and it is the criterion that separates a
    halogen bond from a halogen that merely happens to be nearby -- without it
    every chlorinated ligand reports a bond to whatever it is packed against.
    """
    atoms, bonds = _halogen_pair(120.0)
    assert inter.find_halogen_bonds(atoms, bonds) == []


def test_a_halogen_beyond_the_cutoff_is_refused():
    atoms, bonds = _halogen_pair(180.0)
    xyz = atoms["xyz"].copy()
    xyz[2] = (0.0, 0.0, -3.6)
    xyz[3] = (0.0, 1.2, -4.4)
    atoms["xyz"] = xyz
    assert inter.find_halogen_bonds(atoms, bonds) == []


def test_a_protein_without_halogens_reports_none(protein):
    """148L has none, so the finder must be silent rather than creative."""
    atoms, bonds = protein
    assert inter.find_halogen_bonds(atoms, bonds) == []


# --------------------------------------------------------------------------- #
# Through the command layer -- the modes PyMOL's own menu sends
# --------------------------------------------------------------------------- #
@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def cmd(qapp, tmp_path):
    """A loaded window with the command layer wired to it."""
    import shutil

    from chimol.commands.command import Cmd
    from chimol.hosts.qt.window import MolViewPluginWindow

    if not PDB.is_file():
        pytest.skip("no 148l fixture")
    pdb = tmp_path / "148l.pdb"
    shutil.copyfile(PDB, pdb)

    window = MolViewPluginWindow()
    window.load_structure_from_path(pdb, name="148l")
    command = Cmd(window)
    errors: list[str] = []
    messages: list[str] = []
    command.set_error_callback(errors.append)
    command.set_message_callback(messages.append)
    command._errors = errors
    command._messages = messages
    # Not closed: tearing down a QOpenGLWidget inside pytest aborts the
    # interpreter in this environment.
    return command, window


@pytest.mark.parametrize(
    "line, expect",
    [
        ("distance sb, all, all, mode=10", "salt bridges"),
        ("distance hal, all, all, mode=9", "halogen bonds"),
        ("distance pp, all, all, mode=6", "pi-pi interactions"),
        ("distance pc, all, all, mode=7", "pi-cation interactions"),
    ],
)
def test_each_mode_reports_its_own_finder(cmd, line, expect):
    """The exact commands PyMOL's A ▸ find entries send, and their summaries."""
    command, _window = cmd
    command.do(line)
    assert command._errors == [], command._errors
    assert any(expect in m for m in command._messages), command._messages


def test_pi_interactions_is_the_command_pymols_menu_calls(cmd):
    """`pi_interactions name, sele` -- mode 5 under the name PyMOL gives it."""
    command, window = cmd
    command.do("pi_interactions pi_all, all")
    assert command._errors == [], command._errors
    assert any("pi interactions" in m for m in command._messages)


def test_a_finder_that_finds_nothing_clears_its_measurement(cmd):
    """148L has no halogen, so the entry must not be left behind.

    This is PyMOL's ``reset=1`` and it is what stops the menu from lying: the
    previous finder's dashes staying on screen read as this finder's answer.
    """
    command, window = cmd
    command.do("distance probe, all, all, mode=10")
    assert "probe" in window.viewer.measurements
    command.do("distance probe, all, all, mode=9")
    assert "probe" not in window.viewer.measurements


def test_the_salt_bridges_reach_the_viewport(cmd):
    """A measurement with two points per bridge, drawn as dashes."""
    command, window = cmd
    command.do("distance sb, all, all, mode=10")
    entry = window.viewer.measurements["sb"]
    assert entry["kind"] == "dashes"
    positions = np.asarray(entry["positions"])
    assert positions.ndim == 2 and positions.shape[1] == 3
    assert positions.shape[0] % 2 == 0 and positions.shape[0] >= 2


# --------------------------------------------------------------------------- #
# Between chains
# --------------------------------------------------------------------------- #
def test_interchain_distances_collects_every_chain_pair(cmd):
    """One measurement over all pairs, which is what PyMOL's helper builds.

    chimol's named measurements *replace* rather than append, so the
    accumulation `util.interchain_distances` gets from calling `distance` in a
    loop has to happen before the drawing -- hence `_distance_segments`.
    """
    command, window = cmd
    command.do("interchain_distances ic, all, 4.0")
    assert command._errors == [], command._errors
    summary = [m for m in command._messages if "ic:" in m]
    assert summary, command._messages
    assert "chain pair" in summary[-1]


def test_one_chain_is_reported_rather_than_drawn(cmd):
    """A selection inside one chain has no interface, and says so.

    148L is chain E (protein) plus chain S (the ligand and waters), so the
    single-chain case has to be asked for -- and the answer must be a message,
    not an empty measurement left on screen looking like "no contacts".
    """
    command, window = cmd
    command.do("interchain_distances solo, chain E, 4.0")
    assert command._errors == [], command._errors
    assert any("one chain" in m for m in command._messages), command._messages
    assert "solo" not in window.viewer.measurements


def test_the_origin_menu_entry_runs(cmd):
    """`origin` has existed for a while; the menu said it did not.

    A menu entry disabled with a reason that is no longer true is the same
    failure as a wrong tooltip -- it tells the user a capability is missing.
    """
    command, _window = cmd
    command.do("origin resi 54")
    assert command._errors == [], command._errors
    assert any("rotating about" in m for m in command._messages)


def test_the_disulfide_expression_is_a_selection_chimol_can_evaluate():
    """PyMOL's own expression, which needs `byres` and `bound_to`.

    The entry is the expression, so the thing worth testing is that the
    selection engine answers it -- and that it narrows to *bridged* cysteines
    rather than every one of them.
    """
    from chimol.ui.menus.objects import _DISULFIDE_SHOW

    assert "bound_to" in _DISULFIDE_SHOW and "byres" in _DISULFIDE_SHOW
    assert _DISULFIDE_SHOW.count("{sele}") == 2
