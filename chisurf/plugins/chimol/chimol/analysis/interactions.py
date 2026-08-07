"""Halogen bonds, salt bridges and pi interactions, with PyMOL's criteria.

These are the three finders behind the **A ▸ find** entries that were visible
and disabled: PyMOL reaches them as ``distance ... mode=9`` (halogen bond),
``mode=10`` (salt bridge) and ``mode=5/6/7`` (pi interactions), and each is a
separate detector rather than a variation on the polar-contact test in
:mod:`~chimol.analysis.hbonds`.

Everything here is transcribed from ``layer3/Interactions.h`` and
``layer3/Interactions.cpp`` -- ``HalogenBondCriteria``, ``SaltBridgeCriteria``,
``FindPiInteractions``, ``TestHalogenBondDonor`` and ``TestHalogenBondAcceptor``
-- plus the formal-charge half of ``assign_pdb_known_residue``
(``layer2/ObjectMolecule2.cpp``), which is what makes a salt bridge findable in
a PDB file at all.

Formal charge is the load-bearing part
--------------------------------------
A salt bridge is *"two non-hydrogen atoms within 5 Å whose formal charges have
opposite sign"*, and a cation for the pi-cation test is *"formal charge above
zero"* -- so both reduce to a charge that a PDB file does not carry. PyMOL fills
it in from nomenclature while it connects the molecule, in a hard-coded table:
``OXT`` on any protein residue, ARG ``NH1``, ASP ``OD2``, GLU ``OE2``, LYS
``NZ``, protonated-HIS ``ND1``, and ``OP2``/``O2P`` on every nucleotide. That
table is :data:`PDB_FORMAL_CHARGES`, transcribed rather than re-derived, and it
carries PyMOL's asymmetries with it:

* only **one** oxygen of a carboxylate is charged (``OD2``, ``OE2``), and only
  one nitrogen of a guanidinium (``NH1``, with ``NH2`` explicitly pinned to
  zero). The charge is a formal bookkeeping device, not a physical one, and a
  finder that charges both halves double-counts every bridge;
* histidine is charged **only** under the protonated residue names (``HIP``,
  ``HISP``, ``HISH``). A plain ``HIS`` is neutral, so a HIS-ASP pair is not
  reported as a salt bridge, which is a decision about protonation state that
  PyMOL declines to make for you.

An explicit charge in the file always wins over the table.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .hbonds import _column, neighbour_lists, type_atoms

__all__ = [
    "HalogenBondCriteria",
    "SaltBridgeCriteria",
    "PiCriteria",
    "Interaction",
    "PDB_FORMAL_CHARGES",
    "HALOGENS",
    "formal_charges",
    "find_rings",
    "find_salt_bridges",
    "find_halogen_bonds",
    "find_pi_interactions",
]

#: The halogens, which are what a halogen bond is about. PyMOL tests
#: ``AtomInfoIsHalogen``: fluorine is included in the element list but its
#: sigma hole is too shallow to reach the angle criteria in practice.
HALOGENS = frozenset({"F", "CL", "BR", "I", "AT"})

#: ``(residue, atom) -> formal charge``, from ``assign_pdb_known_residue``. The
#: residue key ``""`` means "any residue", which is how PyMOL applies ``OXT``.
PDB_FORMAL_CHARGES: dict[tuple[str, str], int] = {
    # Any protein residue: the C-terminal carboxylate.
    ("", "OXT"): -1,
    # Arginine's guanidinium: one nitrogen charged, the other pinned to zero.
    ("ARG", "NH1"): +1,
    ("ARG", "NH2"): 0,
    ("ARGP", "NH1"): +1,
    ("ARGP", "NH2"): 0,
    # Carboxylates: one oxygen each.
    ("ASP", "OD2"): -1,
    ("ASPM", "OD2"): -1,
    ("GLU", "OE2"): -1,
    ("GLUM", "OE2"): -1,
    # Lysine.
    ("LYS", "NZ"): +1,
    ("LYSP", "NZ"): +1,
    # Histidine, only when the name says it is protonated.
    ("HIP", "ND1"): +1,
    ("HISP", "ND1"): +1,
    ("HISH", "ND1"): +1,
}

#: The nucleotide residues whose phosphate PyMOL charges. Both spellings of the
#: atom are accepted, as PyMOL accepts both.
_NUCLEOTIDES = frozenset(
    {"A", "C", "G", "T", "U", "I", "DA", "DC", "DG", "DT", "DU", "DI"}
)
_PHOSPHATE_OXYGENS = ("OP2", "O2P")


@dataclass(frozen=True)
class SaltBridgeCriteria:
    """``salt_bridge_distance``, PyMOL's one setting for this finder."""

    distance: float = 5.0


@dataclass(frozen=True)
class HalogenBondCriteria:
    """The six ``halogen_bond_*`` settings, with PyMOL's defaults.

    Attributes
    ----------
    distance : float
        Longest X···A (or H···X) separation accepted.
    as_donor_min_donor_angle, as_donor_min_acceptor_angle : float
        For D–X···A–B, with the halogen donating: the smallest D–X···A and
        X···A–B angles.
    as_acceptor_min_donor_angle : float
        For D–H···X–B, with the halogen accepting: the smallest D–H···X angle.
    as_acceptor_min_acceptor_angle, as_acceptor_max_acceptor_angle : float
        The H···X–B angle is bounded on **both** sides when the halogen
        accepts -- a halogen accepts side-on, perpendicular to its own bond,
        and a straight-through geometry is the sigma hole, not a lone pair.
    """

    distance: float = 3.5
    as_donor_min_donor_angle: float = 140.0
    as_donor_min_acceptor_angle: float = 90.0
    as_acceptor_min_donor_angle: float = 120.0
    as_acceptor_min_acceptor_angle: float = 90.0
    as_acceptor_max_acceptor_angle: float = 170.0


@dataclass(frozen=True)
class PiCriteria:
    """The pi-interaction cut-offs.

    PyMOL's comment says these are "borrowed from
    ``mmshare/include/structureinteraction.h``", and they are literals in
    ``FindPiInteractions`` rather than settings, so they are literals here too.

    Attributes
    ----------
    ring_alignment_max_angle : float
        A pair of rings is dropped as *collinear* when **both** normals are
        further than this from the line joining the centres -- two rings in the
        same plane, side by side, are not stacked.
    face_to_face_max_distance, face_to_face_max_angle : float
        Parallel stacking.
    edge_to_face_max_distance, edge_to_face_min_angle : float
        T-shaped stacking, which reaches further because the contact is an edge.
    cation_max_distance, cation_max_angle : float
        Pi-cation: the cation must be over the ring's face.
    max_ring_size : int
        ``RingSetFinder``'s ``maxringsize``.
    """

    ring_alignment_max_angle: float = 40.0
    face_to_face_max_distance: float = 4.4
    face_to_face_max_angle: float = 30.0
    edge_to_face_max_distance: float = 5.5
    edge_to_face_min_angle: float = 60.0
    cation_max_distance: float = 6.6
    cation_max_angle: float = 30.0
    max_ring_size: int = 7


@dataclass(frozen=True)
class Interaction:
    """One interaction, as a pair of points to draw between.

    Attributes
    ----------
    kind : str
        ``"salt-bridge"``, ``"halogen-bond"``, ``"face-to-face"``,
        ``"edge-to-face"`` or ``"pi-cation"``. PyMOL prints the same three
        names for the pi kinds at ``FB_Blather``.
    start, end : numpy.ndarray
        The two ends, in world coordinates. For a pi interaction an end is a
        **ring centre**, which is not an atom -- which is why this carries
        points rather than only indices.
    i, j : int
        Atom indices where the end is an atom, ``-1`` where it is a ring centre.
    distance : float
        Between ``start`` and ``end``.
    """

    kind: str
    start: np.ndarray
    end: np.ndarray
    i: int
    j: int
    distance: float


def _acute_angle(v1: np.ndarray, v2: np.ndarray) -> float:
    """The angle between two vectors folded into ``[0, 90]``, in degrees.

    PyMOL's ``angle_acute_degrees``. A ring's normal has no preferred side, so
    an angle of 170° between two normals means the same thing as 10°, and a
    test written against the unfolded angle silently misses half the pairs.
    """
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 < 1e-9 or n2 < 1e-9:
        return 90.0
    dot = abs(float(np.dot(v1, v2)) / (n1 * n2))
    return math.degrees(math.acos(min(1.0, dot)))


def _angle_degrees(v1: np.ndarray, v2: np.ndarray) -> float:
    """The unfolded angle between two vectors, in degrees."""
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    dot = float(np.dot(v1, v2)) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def formal_charges(atoms: np.ndarray) -> np.ndarray:
    """Per-atom formal charge, from the file if it carries one, else the table.

    Parameters
    ----------
    atoms : numpy.ndarray
        Structured atom array with ``res_name`` and ``atom_name`` columns, and
        optionally a ``charge`` (or ``formal_charge``) column.

    Returns
    -------
    numpy.ndarray
        ``int`` per atom.

    Notes
    -----
    An explicit charge wins. That is not PyMOL's precedence for a *PDB* file --
    there the table is applied while connecting and overwrites -- but chimol
    reads formats that carry real charges (mmCIF, mol2) and the table exists to
    replace a value that is missing, not one that is known.
    """
    n = len(atoms)
    charges = np.zeros(n, dtype=int)
    names = (atoms.dtype.names or ())

    explicit = None
    for column in ("formal_charge", "charge"):
        if column in names:
            try:
                explicit = np.asarray(atoms[column]).astype(float)
            except (TypeError, ValueError):
                explicit = None
            break

    res_names = _column(atoms, "res_name")
    atom_names = _column(atoms, "atom_name")

    for index in range(n):
        resn = str(res_names[index])
        name = str(atom_names[index])
        value = PDB_FORMAL_CHARGES.get((resn, name))
        if value is None:
            value = PDB_FORMAL_CHARGES.get(("", name))
        if value is None and resn in _NUCLEOTIDES and name in _PHOSPHATE_OXYGENS:
            value = -1
        if value is not None:
            charges[index] = value

    if explicit is not None:
        known = np.isfinite(explicit) & (np.abs(explicit) > 1e-9)
        charges[known] = np.rint(explicit[known]).astype(int)
    return charges


def find_rings(
    n_atoms: int,
    bond_pairs,
    *,
    include: np.ndarray | None = None,
    max_size: int = 7,
) -> list[list[int]]:
    """Every ring up to ``max_size`` atoms, as sorted index lists.

    PyMOL's ``AbstractRingFinder`` with ``RingSetFinder``'s defaults: a bounded
    depth-first walk from each atom, and a ring is recorded once, sorted, in a
    set. ``include`` is ``atomIsExcluded`` inverted -- the planar-atom filter
    the pi finder passes, which is what makes "ring" mean "aromatic-ish ring"
    without a bond-order model.

    Parameters
    ----------
    n_atoms : int
        Size of the molecule.
    bond_pairs : array-like
        ``(M, 2)`` bond list.
    include : numpy.ndarray, optional
        Boolean per atom; atoms outside it are not walked through.
    max_size : int, optional
        Largest ring returned.

    Returns
    -------
    list of list of int
        Each ring's atom indices, sorted, without duplicates.
    """
    neighbours = neighbour_lists(n_atoms, bond_pairs)
    allowed = (
        np.ones(n_atoms, dtype=bool) if include is None
        else np.asarray(include, dtype=bool)
    )
    found: set[tuple[int, ...]] = set()

    for start in range(n_atoms):
        if not allowed[start] or len(neighbours[start]) < 2:
            continue
        # Walk only *upwards* from the starting atom. Every ring then has
        # exactly one starting point -- its lowest index -- so the same ring is
        # not re-walked from each of its members.
        stack: list[tuple[int, list[int]]] = [(start, [start])]
        while stack:
            atom, path = stack.pop()
            for nxt in neighbours[atom]:
                if nxt == start and len(path) >= 3:
                    found.add(tuple(sorted(path)))
                    continue
                if nxt <= start or nxt in path or not allowed[nxt]:
                    continue
                if len(path) < max_size:
                    stack.append((nxt, path + [nxt]))

    return [list(ring) for ring in sorted(found)]


def _ring_centre_and_normal(
    ring: list[int], xyz: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """PyMOL's ``CNRing``: the centroid, and the normal of its first corner.

    The normal comes from the **first three atoms in index order**, exactly as
    ``CNRing`` takes it, not from a plane fitted to all of them. For a planar
    ring the two agree; for a puckered one they do not, and reproducing the
    reported geometry matters more here than improving it.
    """
    coords = xyz[ring]
    centre = coords.mean(axis=0)
    normal = np.zeros(3, dtype=float)
    if len(ring) >= 3:
        v01 = coords[1] - coords[0]
        v12 = coords[2] - coords[1]
        cross = np.cross(v01, v12)
        length = float(np.linalg.norm(cross))
        if length > 1e-9:
            normal = cross / length
    return centre, normal


def find_salt_bridges(
    atoms: np.ndarray,
    mask1: np.ndarray | None = None,
    mask2: np.ndarray | None = None,
    *,
    charges: np.ndarray | None = None,
    criteria: SaltBridgeCriteria | None = None,
) -> list[Interaction]:
    """Oppositely charged heavy atoms within ``salt_bridge_distance``.

    ``FindSaltBridgeInteractions``: the whole test is *"the product of the two
    formal charges is negative, neither atom is a hydrogen, and they are within
    the cutoff"*. There is no angle and no chemistry beyond the charge, which is
    why :func:`formal_charges` is where the accuracy lives.

    Parameters
    ----------
    atoms : numpy.ndarray
        Structured atom array with ``xyz``, ``res_name``, ``atom_name`` and
        ``element``.
    mask1, mask2 : numpy.ndarray, optional
        Which atoms form each side. ``None`` means every atom.
    charges : numpy.ndarray, optional
        Pre-computed formal charges; :func:`formal_charges` by default.
    criteria : SaltBridgeCriteria, optional

    Returns
    -------
    list of Interaction
    """
    criteria = criteria or SaltBridgeCriteria()
    xyz = np.asarray(atoms["xyz"], dtype=float)
    n = len(atoms)
    if charges is None:
        charges = formal_charges(atoms)
    elements = _column(atoms, "element")

    side1 = np.ones(n, dtype=bool) if mask1 is None else np.asarray(mask1, bool)
    side2 = np.ones(n, dtype=bool) if mask2 is None else np.asarray(mask2, bool)

    heavy = elements != "H"
    positive = np.nonzero((charges > 0) & heavy)[0]
    negative = np.nonzero((charges < 0) & heavy)[0]
    if not len(positive) or not len(negative):
        return []

    out: list[Interaction] = []
    cutoff = float(criteria.distance)
    for i in positive:
        deltas = xyz[negative] - xyz[i]
        distances = np.linalg.norm(deltas, axis=1)
        for j, dist in zip(negative[distances <= cutoff],
                           distances[distances <= cutoff]):
            # Either atom may be on either side, which is how PyMOL's coverage
            # test behaves when both selections are the same object.
            if not ((side1[i] and side2[j]) or (side2[i] and side1[j])):
                continue
            out.append(Interaction("salt-bridge", xyz[i], xyz[j],
                                   int(i), int(j), float(dist)))
    return out


def find_halogen_bonds(
    atoms: np.ndarray,
    bond_pairs,
    mask1: np.ndarray | None = None,
    mask2: np.ndarray | None = None,
    *,
    criteria: HalogenBondCriteria | None = None,
) -> list[Interaction]:
    """Halogen bonds, with the halogen donating or accepting.

    ``FindHalogenBondInteractions`` checks both arrangements for every pair:

    * **halogen as donor**, D–X···A–B. The sigma hole is on the far side of the
      D–X bond, so the D–X···A angle has to be nearly straight (140°);
    * **halogen as acceptor**, D–H···X–B. Here the halogen offers a lone pair,
      side-on, so the H···X–B angle is bounded *both* ways (90-170°).

    Donors and acceptors come from :func:`~chimol.analysis.hbonds.type_atoms`,
    so the same chemistry that decides a polar contact decides this.

    Returns
    -------
    list of Interaction
    """
    criteria = criteria or HalogenBondCriteria()
    xyz = np.asarray(atoms["xyz"], dtype=float)
    n = len(atoms)
    elements = _column(atoms, "element")
    neighbours = neighbour_lists(n, bond_pairs)
    typing = type_atoms(atoms, bond_pairs)

    side1 = np.ones(n, dtype=bool) if mask1 is None else np.asarray(mask1, bool)
    side2 = np.ones(n, dtype=bool) if mask2 is None else np.asarray(mask2, bool)

    halogens = np.nonzero(np.isin(elements, list(HALOGENS)))[0]
    if not len(halogens):
        return []

    cutoff = float(criteria.distance)
    out: list[Interaction] = []
    seen: set[tuple[int, int]] = set()

    for x in halogens:
        # A halogen with no bond has no D and no B, so neither test applies.
        bonded = neighbours[int(x)]
        if not bonded:
            continue
        d_atom = bonded[0]
        deltas = xyz - xyz[x]
        distances = np.linalg.norm(deltas, axis=1)
        candidates = np.nonzero(
            (distances <= cutoff) & (distances > 1e-3)
        )[0]

        for other in candidates:
            other = int(other)
            if other in bonded or other == int(x):
                continue
            if not ((side1[x] and side2[other]) or (side2[x] and side1[other])):
                continue
            key = (min(int(x), other), max(int(x), other))
            if key in seen:
                continue

            hit = False
            # X donates: D-X...A-B, with B a neighbour of the acceptor. The
            # vectors are PyMOL's, spelled as `CheckHalogenBondAsDonor` builds
            # them -- both point *away* from the atom whose angle is being
            # measured, and reversing either one measures 180 minus the angle
            # meant, which passes a bent geometry and rejects a straight one.
            if typing.acceptor[other]:
                v_a_x = xyz[other] - xyz[x]        # X -> A
                v_d_x = xyz[d_atom] - xyz[x]       # X -> D
                donor_angle = _angle_degrees(v_a_x, v_d_x)
                if donor_angle >= criteria.as_donor_min_donor_angle:
                    for b in neighbours[other] or [None]:
                        if b is None:
                            # No B to measure against; PyMOL skips the pair
                            # rather than assuming a geometry for it.
                            continue
                        v_a_b = xyz[other] - xyz[b]  # B -> A
                        if (
                            _angle_degrees(v_a_x, v_a_b)
                            >= criteria.as_donor_min_acceptor_angle
                        ):
                            hit = True
                            break

            # X accepts: D-H...X-B. The "H" is the partner's hydrogen where it
            # has one and the partner itself where it does not, which is the
            # same substitution the polar-contact test makes for a structure
            # without hydrogens.
            if not hit and typing.donor[other]:
                v_x_h = xyz[x] - xyz[other]        # H -> X
                donors_d = [i for i in neighbours[other] if elements[i] != "H"]
                v_d_h = (
                    xyz[donors_d[0]] - xyz[other] if donors_d else -v_x_h
                )                                  # H -> D
                donor_angle = _angle_degrees(v_x_h, v_d_h)
                if donor_angle >= criteria.as_acceptor_min_donor_angle:
                    v_x_b = xyz[x] - xyz[d_atom]   # B -> X
                    acc_angle = _angle_degrees(v_x_h, v_x_b)
                    if (
                        criteria.as_acceptor_min_acceptor_angle
                        <= acc_angle
                        <= criteria.as_acceptor_max_acceptor_angle
                    ):
                        hit = True

            if hit:
                seen.add(key)
                out.append(Interaction(
                    "halogen-bond", xyz[x], xyz[other],
                    int(x), other, float(distances[other]),
                ))
    return out


def find_pi_interactions(
    atoms: np.ndarray,
    bond_pairs,
    mask1: np.ndarray | None = None,
    mask2: np.ndarray | None = None,
    *,
    pipi: bool = True,
    pication: bool = True,
    charges: np.ndarray | None = None,
    criteria: PiCriteria | None = None,
) -> list[Interaction]:
    """Ring-ring stacking and cation-ring contacts.

    ``FindPiInteractions``. Rings are reduced to a centre and a normal, and

    * **pi-pi** needs the centres within 5.5 Å and the pair not *collinear* --
      at least one normal within 40° of the line joining the centres, which is
      what tells stacked rings from two rings lying side by side in one plane.
      It is then face-to-face (normals within 30°, centres within 4.4 Å) or
      edge-to-face (normals more than 60° apart);
    * **pi-cation** needs a positive formal charge within 6.6 Å of a ring
      centre and within 30° of the ring's axis -- over the face, not beside it.

    Both directions are searched when the two selections differ, as PyMOL does
    by recursing with the selections swapped.

    Returns
    -------
    list of Interaction
    """
    criteria = criteria or PiCriteria()
    xyz = np.asarray(atoms["xyz"], dtype=float)
    n = len(atoms)
    side1 = np.ones(n, dtype=bool) if mask1 is None else np.asarray(mask1, bool)
    side2 = np.ones(n, dtype=bool) if mask2 is None else np.asarray(mask2, bool)

    typing = type_atoms(atoms, bond_pairs)
    planar = typing.geometry == "planar"
    rings = find_rings(n, bond_pairs, include=planar,
                       max_size=criteria.max_ring_size)
    if not rings:
        return []

    geometry = [_ring_centre_and_normal(ring, xyz) for ring in rings]
    out: list[Interaction] = []

    def ring_side(ring: list[int], mask: np.ndarray) -> bool:
        return bool(mask[ring].any())

    if pipi:
        for a in range(len(rings)):
            for b in range(a + 1, len(rings)):
                if set(rings[a]) & set(rings[b]):
                    # Fused rings share atoms; PyMOL's ring set can contain
                    # both the five- and six-membered ring of a tryptophan and
                    # they are not stacked with each other.
                    continue
                if not (
                    (ring_side(rings[a], side1) and ring_side(rings[b], side2))
                    or (ring_side(rings[b], side1)
                        and ring_side(rings[a], side2))
                ):
                    continue
                (c1, n1), (c2, n2) = geometry[a], geometry[b]
                v = c2 - c1
                distance = float(np.linalg.norm(v))
                if distance < 1e-2 or distance > criteria.edge_to_face_max_distance:
                    continue
                if (
                    _acute_angle(n2, v) > criteria.ring_alignment_max_angle
                    and _acute_angle(n1, v) > criteria.ring_alignment_max_angle
                ):
                    continue
                angle = _acute_angle(n1, n2)
                if (
                    angle < criteria.face_to_face_max_angle
                    and distance < criteria.face_to_face_max_distance
                ):
                    kind = "face-to-face"
                elif angle > criteria.edge_to_face_min_angle:
                    kind = "edge-to-face"
                else:
                    continue
                out.append(Interaction(kind, c1, c2, -1, -1, distance))

    if pication:
        if charges is None:
            charges = formal_charges(atoms)
        cations = np.nonzero(charges > 0)[0]
        for index, (centre, normal) in enumerate(geometry):
            ring = rings[index]
            for cation in cations:
                cation = int(cation)
                if cation in ring:
                    continue
                if not (
                    (ring_side(ring, side1) and side2[cation])
                    or (ring_side(ring, side2) and side1[cation])
                ):
                    continue
                v = xyz[cation] - centre
                distance = float(np.linalg.norm(v))
                if distance > criteria.cation_max_distance:
                    continue
                if _acute_angle(normal, v) > criteria.cation_max_angle:
                    continue
                out.append(Interaction(
                    "pi-cation", centre, xyz[cation], -1, cation, distance
                ))

    return out
