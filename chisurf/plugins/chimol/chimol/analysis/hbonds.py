"""Polar contacts, the way PyMOL's ``distance ... mode=2`` finds them.

This is the missing piece behind three visible gaps: ``preset technical`` and
``preset ligands`` both reported drawing no polar contacts, and the object
menu's **A ▸ find** submenu was disabled entirely.

The algorithm
-------------
Transcribed from ``layer2/ObjectMolecule2.cpp`` --
``ObjectMoleculeTestHBond``, ``ObjectMoleculeFindBestDonorH`` and
``ObjectMoleculeGetCheckHBond`` -- plus ``ObjectMoleculeGetAvgHBondVector``
(``layer2/ObjectMolecule.cpp``) and ``CoordSetFindOpenValenceVector``
(``layer2/ObjectMolecule.cpp``). A donor/acceptor pair inside ``cutoff`` is a
hydrogen bond when

* the hydrogen (real, or placed on an open valence) lies in front of the
  acceptor's lone-pair plane -- ``h_bond_cone``;
* the **A–D–H angle** is at most ``h_bond_max_angle`` (63°); and
* the donor–acceptor distance is under a cutoff that *slides with that angle*,
  from ``h_bond_cutoff_center`` (3.6 Å, straight on) down to
  ``h_bond_cutoff_edge`` (3.2 Å, at the maximum angle), interpolated by
  ``0.5·(θ/θmax)^power_a + 0.5·(θ/θmax)^power_b``.

Three details are easy to lose and each changes the answer:

* the sliding cutoff is **not** a plain distance test. The names are also the
  wrong way round from what they suggest: *center* is the cutoff at angle
  **zero** and *edge* the one at the maximum angle;
* the virtual hydrogen is placed **1.0 Å** along the open valence, not at the
  real X–H bond length -- ``FindBestDonorH`` adds a unit vector. Only the
  direction is used, but a reader who "fixes" the length changes the A–D–H
  angle and with it the cutoff;
* with no neighbour at all to work from -- a water oxygen in a structure with
  no hydrogens -- PyMOL aims the virtual hydrogen straight at the acceptor, so
  the angle is zero and the test degenerates to "within 3.6 Å". That is not a
  bug to fix; it is how PyMOL finds water-mediated contacts in a
  hydrogen-less PDB, and it is reproduced here.

Which atoms donate and accept
-----------------------------
PyMOL derives this from bond orders (``ObjectMoleculeInferHBondFromChem``),
which a PDB file does not carry. PyMOL fills the gap twice over: a hard-coded
table of double bonds for standard residues applied while connecting
(``assign_pdb_known_residue``), and valence arithmetic for everything else.

chimol already holds the equivalent of the first as
:data:`~chimol.analysis.hydrogens.RESIDUE_TEMPLATES` -- how many hydrogens each
named atom of a standard residue carries, and whether its centre is planar or
tetrahedral -- measured to 99.78 % against a fully hydrogenated protein. So:

* a **templated** atom takes its valence and geometry from the template. That
  is what makes a backbone carbonyl oxygen an acceptor and *not* a donor, which
  is precisely where valence counting goes wrong;
* an **untemplated** atom (a ligand, a modified residue) falls back to the
  element's expected valence with the geometry read off its bond angles
  (``ObjectMoleculeGetAtomGeometry``) -- the same arithmetic PyMOL is left with
  when it has no bond orders, including its consequence that a ligand carbonyl
  oxygen reads as a donor as well as an acceptor;
* **explicit hydrogens win over both.** A structure that carries its hydrogens
  is answered from them.

One deviation from PyMOL, deliberate and measured: PyMOL marks a **proline
nitrogen as a donor** (three single bonds make it look like a tertiary amine
with a free valence) and then invents a hydrogen for it. Proline has no amide
hydrogen. The template says zero, so chimol does not donate from it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..config import _DISPLAY_CONFIG
from .hydrogens import LINEAR, PLANAR, RESIDUE_TEMPLATES, TETRAHEDRAL

__all__ = [
    "HBondCriteria",
    "HBond",
    "AtomTyping",
    "DONOR_METALS",
    "EXPECTED_VALENCE",
    "type_atoms",
    "find_hydrogen_bonds",
    "neighbour_lists",
    "within_n_bonds",
]

#: Cations and Lewis acids PyMOL treats as donors outright -- the first arm of
#: the ``switch`` in ``ObjectMoleculeInferHBondFromChem``. They accept a lone
#: pair rather than donate a proton, but for the purpose of drawing a contact
#: PyMOL puts them on the donor side, which is what makes a zinc-to-histidine
#: line appear.
DONOR_METALS = frozenset(
    {"FE", "CA", "CU", "K", "NA", "MG", "ZN", "HG", "SR", "BA"}
)

#: ``AtomInfoGetExpectedValence`` for the elements a structure actually holds.
EXPECTED_VALENCE = {
    "H": 1, "D": 1, "C": 4, "N": 3, "O": 2, "S": 2, "P": 3, "SE": 2,
    "F": 1, "CL": 1, "BR": 1, "I": 1,
    "NA": 1, "K": 1, "CA": 1, "MG": 1, "ZN": 1, "FE": 1, "CU": 1,
    "MN": 1, "HG": 1, "SR": 1, "BA": 1, "CO": 1, "NI": 1, "CD": 1,
}

#: Geometry assumed for an untemplated N or O with fewer than two neighbours,
#: where there is no angle to read one from. Oxygen is the hydroxyl case and
#: nitrogen the amide one, which is what each is most often.
_LONELY_GEOM = {"O": TETRAHEDRAL, "N": PLANAR}

_EPS = 1e-6


# --------------------------------------------------------------------------- #
# Criteria
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HBondCriteria:
    """The six ``h_bond_*`` settings, with PyMOL's defaults.

    Attributes
    ----------
    max_angle : float
        ``h_bond_max_angle`` -- largest A–D–H angle accepted, in degrees.
    cutoff_center : float
        ``h_bond_cutoff_center`` -- donor–acceptor cutoff at zero angle.
    cutoff_edge : float
        ``h_bond_cutoff_edge`` -- the cutoff at ``max_angle``. Zero disables the
        interpolation and leaves a flat ``cutoff_center``.
    power_a, power_b : float
        ``h_bond_power_a`` / ``h_bond_power_b`` -- shape the interpolation.
    cone : float
        ``h_bond_cone`` -- how far behind the acceptor's lone-pair plane a
        hydrogen may sit, in degrees. 180 admits the whole front hemisphere.
    exclusion : int
        ``h_bond_exclusion`` -- pairs within this many bonds of each other are
        not contacts. 3 excludes 1-2, 1-3 and 1-4 neighbours.
    from_proton : bool
        ``h_bond_from_proton`` -- draw the line from the hydrogen rather than
        from the donor heavy atom, when a real hydrogen is present.
    """

    max_angle: float = 63.0
    cutoff_center: float = 3.6
    cutoff_edge: float = 3.2
    power_a: float = 1.6
    power_b: float = 5.0
    cone: float = 180.0
    exclusion: int = 3
    from_proton: bool = True

    @classmethod
    def from_config(cls) -> HBondCriteria:
        """Read the live values out of the display config."""
        cfg = _DISPLAY_CONFIG.get("hbond", {}) or {}
        defaults = cls()
        return cls(
            max_angle=float(cfg.get("max_angle", defaults.max_angle)),
            cutoff_center=float(cfg.get("cutoff_center", defaults.cutoff_center)),
            cutoff_edge=float(cfg.get("cutoff_edge", defaults.cutoff_edge)),
            power_a=float(cfg.get("power_a", defaults.power_a)),
            power_b=float(cfg.get("power_b", defaults.power_b)),
            cone=float(cfg.get("cone", defaults.cone)),
            exclusion=int(cfg.get("exclusion", defaults.exclusion)),
            from_proton=bool(cfg.get("from_proton", defaults.from_proton)),
        )

    @property
    def factor_a(self) -> float:
        """``0.5 / max_angle**power_a`` -- half the interpolation at the edge."""
        return 0.5 / (self.max_angle ** self.power_a)

    @property
    def factor_b(self) -> float:
        """``0.5 / max_angle**power_b`` -- the other half."""
        return 0.5 / (self.max_angle ** self.power_b)

    @property
    def cone_dangle(self) -> float:
        """``cos(cone / 2)``, the dot product the plane test compares against."""
        return math.cos(math.pi * 0.5 * self.cone / 180.0)

    @property
    def search_cutoff(self) -> float:
        """Widest donor–acceptor distance any angle can accept."""
        return max(self.cutoff_center, self.cutoff_edge)


@dataclass(frozen=True)
class HBond:
    """One polar contact.

    Attributes
    ----------
    donor : int
        Row of the donor heavy atom in the atom table.
    acceptor : int
        Row of the acceptor.
    hydrogen : int or None
        Row of the real hydrogen that made the bond, or ``None`` when the
        hydrogen was placed on an open valence.
    hydrogen_xyz : numpy.ndarray
        Where that hydrogen is, real or placed.
    distance : float
        Donor-to-acceptor distance in Angstrom -- what PyMOL labels the dash
        with, regardless of ``from_proton``.
    """

    donor: int
    acceptor: int
    hydrogen: int | None
    hydrogen_xyz: np.ndarray
    distance: float


# --------------------------------------------------------------------------- #
# Typing
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AtomTyping:
    """Per-atom chemistry the H-bond test needs.

    Attributes
    ----------
    valence : numpy.ndarray
        Connections each atom expects, hydrogens included. ``valence`` above the
        neighbour count is what "there is an implicit hydrogen here" means.
    geometry : numpy.ndarray
        ``"tetrahedral"``, ``"planar"``, ``"linear"`` or ``""`` (unknown), which
        decides where an implicit hydrogen goes.
    donor, acceptor : numpy.ndarray
        Boolean per atom.
    templated : numpy.ndarray
        Whether the atom's residue had a template. Untemplated atoms are the
        approximated ones, and a caller that wants to report the approximation
        needs to know which they are.
    """

    valence: np.ndarray
    geometry: np.ndarray
    donor: np.ndarray
    acceptor: np.ndarray
    templated: np.ndarray


def neighbour_lists(n_atoms: int, bond_pairs) -> list[list[int]]:
    """Adjacency as a list of lists, which is what the tree walks want."""
    out: list[list[int]] = [[] for _ in range(n_atoms)]
    if bond_pairs is None:
        return out
    pairs = np.asarray(bond_pairs, dtype=int)
    if pairs.ndim != 2 or pairs.shape[0] == 0 or pairs.shape[1] < 2:
        return out
    for a, b in pairs[:, :2]:
        if 0 <= a < n_atoms and 0 <= b < n_atoms and a != b:
            out[int(a)].append(int(b))
            out[int(b)].append(int(a))
    return out


def _column(atoms: np.ndarray, name: str, fill: str = "") -> np.ndarray:
    """A structured-array column as stripped upper-case strings, or a fill."""
    if name in (atoms.dtype.names or ()):
        return np.char.upper(np.char.strip(np.asarray(atoms[name]).astype(str)))
    return np.full(len(atoms), fill, dtype=object)


def atom_geometry_from_angles(
    index: int, xyz: np.ndarray, neighbours: list[list[int]]
) -> str:
    """Geometry read off the bond angles -- ``ObjectMoleculeGetAtomGeometry``.

    Four neighbours is tetrahedral outright. Three is decided by how coplanar
    they are: the three pairwise cross products of the bond vectors agree
    (average dot product above 0.75) only when the centre is flat. Two is linear
    when the bonds oppose each other (dot below −0.75). Fewer than two carries
    no angle, so there is nothing to read.

    Parameters
    ----------
    index : int
        Atom to type.
    xyz : (N, 3) numpy.ndarray
        Coordinates.
    neighbours : list of list of int
        Adjacency.

    Returns
    -------
    str
        ``"tetrahedral"``, ``"planar"``, ``"linear"``, or ``""`` when unknown.
    """
    nbr = neighbours[index]
    nn = len(nbr)
    if nn == 4:
        return TETRAHEDRAL
    v0 = xyz[index]
    if nn == 3:
        d = xyz[nbr] - v0
        cp = np.array([
            np.cross(d[0], d[1]), np.cross(d[1], d[2]), np.cross(d[2], d[0])
        ])
        norms = np.linalg.norm(cp, axis=1)
        if np.any(norms < _EPS):
            return TETRAHEDRAL
        cp = cp / norms[:, None]
        avg = float(cp[0] @ cp[1] + cp[1] @ cp[2] + cp[2] @ cp[0]) / 3.0
        return PLANAR if avg > 0.75 else TETRAHEDRAL
    if nn == 2:
        d = xyz[nbr] - v0
        norms = np.linalg.norm(d, axis=1)
        if np.any(norms < _EPS):
            return ""
        d = d / norms[:, None]
        if float(d[0] @ d[1]) < -0.75:
            return LINEAR
    return ""


def type_atoms(atoms: np.ndarray, bond_pairs) -> AtomTyping:
    """Valence, geometry, donor and acceptor flags for every atom.

    See the module docstring for where each rule comes from. In short: the
    residue template where there is one, the element's expected valence and the
    bond angles where there is not, and explicit hydrogens over both.

    Parameters
    ----------
    atoms : numpy.ndarray
        Structured atom array with at least ``xyz``, ``element`` or
        ``atom_name``, and ``res_name``.
    bond_pairs : numpy.ndarray or None
        ``(M, 2)`` bonds.

    Returns
    -------
    AtomTyping
        Arrays parallel to ``atoms``.
    """
    n = len(atoms)
    xyz = np.asarray(atoms["xyz"], dtype=float)
    names = _column(atoms, "atom_name")
    res_names = _column(atoms, "res_name")
    elements = _column(atoms, "element")
    if "element" not in (atoms.dtype.names or ()):
        elements = np.array([str(x)[:1] for x in names])
    charges = (
        np.asarray(atoms["charge"], dtype=float)
        if "charge" in (atoms.dtype.names or ())
        else np.zeros(n)
    )

    neighbours = neighbour_lists(n, bond_pairs)
    is_h = np.isin(elements, ("H", "D"))

    valence = np.zeros(n, dtype=int)
    geometry = np.empty(n, dtype=object)
    geometry[:] = ""
    donor = np.zeros(n, dtype=bool)
    acceptor = np.zeros(n, dtype=bool)
    templated = np.zeros(n, dtype=bool)

    for i in range(n):
        element = str(elements[i])
        nbr = neighbours[i]
        nn = len(nbr)
        n_explicit_h = int(sum(1 for j in nbr for _ in (0,) if is_h[j]))

        template = RESIDUE_TEMPLATES.get(str(res_names[i]))
        entry = template.get(str(names[i])) if template else None
        if is_h[i]:
            # A hydrogen is never an endpoint, and it needs no template of its
            # own -- it *is* the thing a template would have predicted. Marking
            # it templated keeps the "how much of this was approximated" count
            # honest on a structure that carries its hydrogens.
            templated[i] = template is not None
            valence[i] = 1
            continue
        if entry is not None:
            templated[i] = True
            n_template_h, geom = entry
            # Valence counts every connection, so the heavy neighbours the file
            # actually shows plus the hydrogens the template says belong there.
            # Hydrogens already present are not counted twice.
            heavy = nn - n_explicit_h
            valence[i] = heavy + max(n_template_h, n_explicit_h)
            geometry[i] = geom
            has_hydro = max(n_template_h, n_explicit_h) > 0
        else:
            expected = EXPECTED_VALENCE.get(element, 0)
            valence[i] = max(expected, nn)
            geom = atom_geometry_from_angles(i, xyz, neighbours)
            if not geom:
                geom = _LONELY_GEOM.get(element, TETRAHEDRAL)
            geometry[i] = geom
            # PyMOL's rule where it has nothing better: a free valence slot is a
            # hydrogen. It is what makes an untemplated hydroxyl a donor, and
            # equally what makes an untemplated carbonyl one.
            has_hydro = (nn < valence[i]) or n_explicit_h > 0

        if element in DONOR_METALS and element not in ("C", "N", "O"):
            donor[i] = True
            continue

        if element == "N":
            if has_hydro:
                donor[i] = True
            elif (
                charges[i] <= 0
                and geometry[i] == PLANAR
                and (nn - n_explicit_h) < 3
            ):
                # A planar nitrogen with a spare coordination site is
                # delocalized -- PyMOL's `delocalized && nn < 3` acceptor. This
                # is the histidine NE2 of the ND1 tautomer, and every ring
                # nitrogen of a nucleic-acid base.
                acceptor[i] = True
        elif element == "O":
            if charges[i] <= 0:
                acceptor[i] = True
            if has_hydro:
                donor[i] = True

    return AtomTyping(
        valence=valence,
        geometry=geometry,
        donor=donor,
        acceptor=acceptor,
        templated=templated,
    )


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
def _unit(v: np.ndarray) -> np.ndarray:
    """``normalize23f``: a unit vector, or zero when there is nothing to scale."""
    length = float(np.linalg.norm(v))
    if length <= _EPS:
        return np.zeros(3)
    return np.asarray(v, dtype=float) / length


def _open_valence_vector(
    index: int,
    seek: np.ndarray,
    xyz: np.ndarray,
    neighbours: list[list[int]],
    geometry: np.ndarray,
) -> np.ndarray | None:
    """Where an implicit hydrogen would sit -- ``CoordSetFindOpenValenceVector``.

    The ``seek``-aware branch only: this is always called with a direction to
    aim at (the donor-to-acceptor vector), which is what lets a rotatable
    hydroxyl hydrogen point at its partner.

    Parameters
    ----------
    index : int
        The donor.
    seek : (3,) numpy.ndarray
        Direction to lean towards. **Not normalised** -- PyMOL passes the raw
        donor-to-acceptor vector and copies it wholesale in the no-neighbour
        case, which places the hydrogen on top of the acceptor and makes the
        A–D–H angle exactly zero.
    xyz : (N, 3) numpy.ndarray
        Coordinates.
    neighbours : list of list of int
        Adjacency.
    geometry : numpy.ndarray
        Per-atom geometry from :func:`type_atoms`.

    Returns
    -------
    numpy.ndarray or None
        A displacement from the donor, or ``None`` when the geometry leaves no
        room.
    """
    v0 = xyz[index]
    occ = []
    for a1 in neighbours[index]:
        d = _unit(xyz[a1] - v0)
        if np.any(d):
            occ.append(d)
        if len(occ) == 4:
            break

    geom = str(geometry[index])
    if not occ or len(occ) > 4 or not geom:
        return np.asarray(seek, dtype=float)

    if len(occ) == 1:
        if geom == TETRAHEDRAL:
            z = _unit(np.cross(np.cross(occ[0], seek), occ[0]))
            return -0.334 * occ[0] + 0.943 * z
        if geom == PLANAR:
            z = _unit(np.cross(np.cross(occ[0], seek), occ[0]))
            return -0.500 * occ[0] + 0.866 * z
        if geom == LINEAR:
            return -occ[0]
        return None
    if len(occ) == 2:
        t = occ[0] + occ[1]
        if geom == TETRAHEDRAL:
            z = _unit(np.cross(np.cross(t, occ[0]), t))
            if float(z @ seek) < 0.0:
                z = -z
            return -t + 1.41 * z
        if geom == PLANAR:
            return -t
        return None
    if len(occ) == 3:
        if geom == TETRAHEDRAL:
            return -(occ[0] + occ[1] + occ[2])
        return None
    return None


def _best_donor_h(
    donor_index: int,
    seek: np.ndarray,
    xyz: np.ndarray,
    neighbours: list[list[int]],
    typing: AtomTyping,
    is_h: np.ndarray,
) -> tuple[np.ndarray, int | None] | None:
    """The hydrogen this donor would use -- ``ObjectMoleculeFindBestDonorH``.

    A real hydrogen always beats a placed one, and among real ones the one
    pointing closest to ``seek`` wins. Returns its **position**, not a
    direction; a placed hydrogen sits 1.0 Å out because ``seek`` is only used
    for aim and the open-valence vector is a unit vector.
    """
    origin = xyz[donor_index]
    best: np.ndarray | None = None
    best_dot = 0.0
    h_real: int | None = None

    nn = len(neighbours[donor_index])
    if nn < int(typing.valence[donor_index]) or bool(typing.donor[donor_index]):
        direction = _open_valence_vector(
            donor_index, seek, xyz, neighbours, typing.geometry
        )
        if direction is not None:
            best_dot = float(np.dot(direction, seek))
            best = origin + direction

    for a1 in neighbours[donor_index]:
        if not is_h[a1]:
            continue
        cand = xyz[a1]
        cand_dot = float(np.dot(_unit(cand - origin), seek))
        if best is None or best_dot < cand_dot or h_real is None:
            best = cand
            best_dot = cand_dot
            h_real = int(a1)

    if best is None:
        return None
    return best, h_real


def _avg_hbond_vector(
    index: int,
    incoming: np.ndarray,
    xyz: np.ndarray,
    neighbours: list[list[int]],
    typing: AtomTyping,
    elements: np.ndarray,
    is_h: np.ndarray,
) -> tuple[float, np.ndarray]:
    """The acceptor's lone-pair direction -- ``ObjectMoleculeGetAvgHBondVector``.

    The average of the unit vectors pointing *away* from each neighbour, so it
    aims where the lone pairs are. Hydrogens are skipped unless the atom is an
    oxygen, which is how a water keeps both of its.

    With exactly one neighbour and a rotatable lone pair -- a hydroxyl oxygen or
    an sp2 nitrogen -- the direction is tilted towards the incoming hydrogen,
    because such an acceptor can turn to meet it. The two constants are
    ``cos``/``sin`` of 109.5°.

    Returns
    -------
    tuple
        ``(strength, direction)``. PyMOL uses the plane only when ``strength``
        exceeds 0.1; a symmetric set of neighbours cancels out and leaves none.
    """
    v_atom = xyz[index]
    element = str(elements[index])
    sp2 = str(typing.geometry[index]) == PLANAR

    v_acc = np.zeros(3)
    count = 0
    for a1 in neighbours[index]:
        if is_h[a1] and element != "O":
            continue
        d = _unit(v_atom - xyz[a1])
        if not np.any(d):
            continue
        v_acc = v_acc + d
        count += 1

    if not count:
        return 0.0, v_acc
    strength = float(np.linalg.norm(v_acc)) / count
    v = _unit(v_acc)

    if count == 1 and abs(float(np.dot(v, incoming))) < 0.99:
        if (element == "O" and not sp2) or (element == "N" and sp2):
            v_perp = _unit(incoming - v * float(np.dot(incoming, v)))
            v = _unit(v - (0.333644 * v + 0.942699 * v_perp))
    return strength, v


def _test_hbond(
    don_to_acc: np.ndarray,
    don_to_h: np.ndarray,
    h_to_acc: np.ndarray,
    acc_plane: np.ndarray | None,
    hbc: HBondCriteria,
) -> bool:
    """``ObjectMoleculeTestHBond``: the cone, the angle, the sliding cutoff."""
    n_h_to_acc = _unit(h_to_acc)
    if acc_plane is not None:
        n_acc_plane = _unit(acc_plane)
        if float(np.dot(n_h_to_acc, n_acc_plane)) > -hbc.cone_dangle:
            return False

    n_don_to_h = _unit(don_to_h)
    n_don_to_acc = _unit(don_to_acc)

    dangle = float(np.dot(n_don_to_h, n_don_to_acc))
    if 0.0 < dangle < 1.0:
        angle = math.degrees(math.acos(dangle))
    elif dangle > 0.0:
        angle = 0.0
    else:
        # Anything at or behind a right angle is clamped to 90, which the
        # max-angle test then rejects. Not a measurement -- a sentinel.
        angle = 90.0

    if angle > hbc.max_angle:
        return False

    if hbc.cutoff_edge != 0.0:
        curve = (
            (angle ** hbc.power_a) * hbc.factor_a
            + (angle ** hbc.power_b) * hbc.factor_b
        )
        cutoff = hbc.cutoff_edge * curve + hbc.cutoff_center * (1.0 - curve)
    else:
        cutoff = hbc.cutoff_center

    return float(np.linalg.norm(don_to_acc)) <= cutoff


def within_n_bonds(
    a: int, b: int, max_dist: int, neighbours: list[list[int]]
) -> bool:
    """Whether ``b`` is at most ``max_dist`` bonds from ``a``.

    ``SelectorCheckNeighbors``, which walks outward from ``a`` and stops as soon
    as it reaches ``b``.
    """
    if max_dist <= 0:
        return False
    depth = {a: 0}
    stack = [a]
    while stack:
        node = stack.pop()
        dist = depth[node] + 1
        for other in neighbours[node]:
            if other == b:
                return True
            if other not in depth and dist < max_dist:
                depth[other] = dist
                stack.append(other)
    return False


# --------------------------------------------------------------------------- #
# The finder
# --------------------------------------------------------------------------- #
def find_hydrogen_bonds(
    atoms: np.ndarray,
    bond_pairs,
    mask_a: np.ndarray | None = None,
    mask_b: np.ndarray | None = None,
    criteria: HBondCriteria | None = None,
    cutoff: float | None = None,
    typing: AtomTyping | None = None,
) -> list[HBond]:
    """Every polar contact between two atom selections.

    A pair is tried both ways round -- ``a`` donating to ``b`` first, then ``b``
    to ``a`` -- and the first that passes wins, exactly as
    ``SelectorGetDistSet`` does it. Pairs that appear in both selections are
    reported once.

    Parameters
    ----------
    atoms : numpy.ndarray
        Structured atom array. When a contact spans two objects, pass their
        concatenated tables and offset ``bond_pairs`` accordingly; the bond
        graph then has no edge between them, which is what stops the
        neighbour-exclusion rule from reaching across.
    bond_pairs : numpy.ndarray or None
        ``(M, 2)`` bonds.
    mask_a, mask_b : numpy.ndarray, optional
        Boolean atom masks for the two sides. Both default to every atom, which
        is ``distance name, all, all, mode=2``.
    criteria : HBondCriteria, optional
        Defaults to the live settings.
    cutoff : float, optional
        Overrides the widest distance searched. PyMOL's ``distance`` takes this
        as its fourth argument; a negative value means "use the criteria", and
        a value *wider* than the criteria allow finds nothing extra, because the
        angle-dependent cutoff still applies.
    typing : AtomTyping, optional
        Precomputed typing, to avoid redoing it across repeated calls.

    Returns
    -------
    list of HBond
        Sorted by donor then acceptor, so the output is stable.
    """
    n = len(atoms)
    if n == 0:
        return []
    hbc = criteria or HBondCriteria.from_config()
    typing = typing or type_atoms(atoms, bond_pairs)

    xyz = np.asarray(atoms["xyz"], dtype=float)
    elements = _column(atoms, "element")
    if "element" not in (atoms.dtype.names or ()):
        elements = np.array([str(x)[:1] for x in _column(atoms, "atom_name")])
    is_h = np.isin(elements, ("H", "D"))
    neighbours = neighbour_lists(n, bond_pairs)

    mask_a = (
        np.ones(n, dtype=bool) if mask_a is None else np.asarray(mask_a, dtype=bool)
    )
    mask_b = (
        np.ones(n, dtype=bool) if mask_b is None else np.asarray(mask_b, dtype=bool)
    )

    search = hbc.search_cutoff if cutoff is None or cutoff < 0 else float(cutoff)
    # Only heavy donors and acceptors are ever endpoints, so the neighbour
    # search runs over those instead of every atom. On a 20 000-atom protein
    # that is a tenth of the pairs.
    polar = (typing.donor | typing.acceptor) & ~is_h
    side_a = np.nonzero(mask_a & polar)[0]
    side_b = np.nonzero(mask_b & polar)[0]
    if not side_a.size or not side_b.size:
        return []

    from scipy.spatial import cKDTree

    tree_b = cKDTree(xyz[side_b])
    found: dict[tuple[int, int], HBond] = {}

    for local_a, atom_a in enumerate(side_a):
        for local_b in tree_b.query_ball_point(xyz[atom_a], search):
            atom_b = int(side_b[local_b])
            if atom_a == atom_b:
                continue
            # `coverage` in SelectorGetDistSet: a pair inside both selections is
            # reported once, in index order.
            if mask_a[atom_b] and mask_b[atom_a] and atom_b < atom_a:
                continue
            key = (min(int(atom_a), atom_b), max(int(atom_a), atom_b))
            if key in found:
                continue
            if hbc.exclusion and within_n_bonds(
                int(atom_a), atom_b, hbc.exclusion, neighbours
            ):
                continue

            bond = _check_pair(
                int(atom_a), atom_b, xyz, neighbours, typing, elements, is_h, hbc
            )
            if bond is None:
                bond = _check_pair(
                    atom_b, int(atom_a), xyz, neighbours, typing, elements, is_h, hbc
                )
            if bond is not None:
                found[key] = bond

    return sorted(found.values(), key=lambda b: (b.donor, b.acceptor))


def _check_pair(
    don: int,
    acc: int,
    xyz: np.ndarray,
    neighbours: list[list[int]],
    typing: AtomTyping,
    elements: np.ndarray,
    is_h: np.ndarray,
    hbc: HBondCriteria,
) -> HBond | None:
    """``ObjectMoleculeGetCheckHBond`` for one ordered pair."""
    if not (typing.donor[don] and typing.acceptor[acc]):
        return None

    v_don = xyz[don]
    v_acc = xyz[acc]
    don_to_acc = v_acc - v_don

    best = _best_donor_h(don, don_to_acc, xyz, neighbours, typing, is_h)
    if best is None:
        return None
    h_xyz, h_real = best

    don_to_h = h_xyz - v_don
    h_to_acc = v_acc - h_xyz

    strength, plane = _avg_hbond_vector(
        acc, h_to_acc, xyz, neighbours, typing, elements, is_h
    )
    acc_plane = plane if strength > 0.1 else None

    if not _test_hbond(don_to_acc, don_to_h, h_to_acc, acc_plane, hbc):
        return None

    return HBond(
        donor=don,
        acceptor=acc,
        hydrogen=h_real,
        hydrogen_xyz=h_xyz,
        distance=float(np.linalg.norm(don_to_acc)),
    )
