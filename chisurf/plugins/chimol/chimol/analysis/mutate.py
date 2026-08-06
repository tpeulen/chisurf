"""Residue mutation with rotamers, the way PyMOL's mutagenesis wizard does it.

The wizard's loop, from `modules/pymol/wizard/mutagenesis.py`:

1. pick a residue -- it must have `N`, `C` and `O`, or there is no backbone to
   graft onto and the wizard refuses;
2. load an idealised fragment of the target residue and put its backbone on the
   target's, so the new side chain grows out of the *existing* backbone rather
   than moving it;
3. generate one **state per rotamer** from the library, each a set of chi
   dihedrals;
4. build a bump-check object out of the new side chain and everything within
   6 A of it, and ask the sculptor for one iteration per state. The resulting
   strain is what the panel shows beside each rotamer's frequency, and the
   lowest-strain state is the one it starts on;
5. apply: the old side chain is replaced by the chosen state.

This is that, with the data transcribed
(:mod:`~chimol.analysis.residue_library`) and the bump check transcribed
(:mod:`~chimol.analysis.clashes`). Three details decide whether the result is
usable:

* **the backbone is not moved.** The fragment is superposed onto N/CA/C by a
  Kabsch fit on those three atoms and then the *target's own* N, CA, C and O
  are kept, not the fragment's. Fitting and then keeping the fragment's
  backbone would shift the chain by the fit residual -- small, and wrong in a
  way that only shows up as strain against the neighbours;
* **which atoms a chi angle moves** is read from the fragment's own bond graph:
  everything on the far side of the rotated bond. A hard-coded table per
  residue is the version of this that goes wrong on the one residue nobody
  checked;
* **CB is placed by the fragment, not kept.** For a mutation to or from glycine
  there is no CB to keep, and for every other pair the fragment's CB is where
  the idealised geometry puts it, which is what the rotamer angles are measured
  against.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .clashes import ClashCriteria, find_clashes, radii_for
from .residue_library import FRAGMENTS, ROTAMER_ALIASES, ROTAMERS

__all__ = [
    "Rotamer",
    "MutationSite",
    "MutationResult",
    "build_rotamers",
    "mutate_residue",
    "score_rotamers",
]

#: The backbone atoms a mutation keeps from the *target*, not the fragment.
BACKBONE = ("N", "CA", "C", "O")

#: What the wizard calls the neighbourhood: everything within this many
#: Angstrom of the new side chain is what the bump check runs against
#: (`within 6 of ...` in `do_library`).
NEIGHBOURHOOD = 6.0


@dataclass(frozen=True)
class Rotamer:
    """One entry of the rotamer library.

    Attributes
    ----------
    frequency : float
        How often the side chain is observed in this conformation.
    chis : dict
        ``{(a, b, c, d): angle}`` -- the dihedral over those four atom names,
        in degrees.
    coords : numpy.ndarray
        ``(n, 3)`` positions of the built residue, in the same order as
        :attr:`MutationSite.names`.
    strain : float
        The bump check's answer for this conformation, or ``nan`` before it has
        been scored.
    """

    frequency: float
    chis: dict
    coords: np.ndarray
    strain: float = float("nan")


@dataclass
class MutationSite:
    """A residue that can be mutated, and what it would become.

    Attributes
    ----------
    indices : list of int
        Rows of the residue's atoms in the structure's atom table.
    names, elements : list of str
        The atoms of the *new* residue, in build order.
    rotamers : list of Rotamer
        Every conformation the library offers, most frequent first.
    """

    indices: list[int]
    names: list[str] = field(default_factory=list)
    elements: list[str] = field(default_factory=list)
    #: The fragment's own bonds over :attr:`names`. Carried because the bump
    #: check needs them: without the bonds a side chain is scored against
    #: *itself*, every one of its bonds counting as two atoms deep inside their
    #: van der Waals sum, and a tryptophan reports a strain of 60 before it has
    #: touched anything around it.
    bonds: list[tuple[int, int]] = field(default_factory=list)
    rotamers: list[Rotamer] = field(default_factory=list)


@dataclass
class MutationResult:
    """What a mutation produced, before it is written into the structure."""

    site: MutationSite
    chosen: int
    residue_name: str

    @property
    def rotamer(self) -> Rotamer:
        """The conformation that was chosen."""
        return self.site.rotamers[self.chosen]


def _kabsch(mobile: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rotation and translation putting *mobile* onto *target*."""
    mc = mobile.mean(axis=0)
    tc = target.mean(axis=0)
    covariance = (mobile - mc).T @ (target - tc)
    u, _s, vt = np.linalg.svd(covariance)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    correction = np.diag([1.0, 1.0, d])
    rotation = vt.T @ correction @ u.T
    return rotation, tc - rotation @ mc


def _neighbours(n: int, bonds) -> list[list[int]]:
    out: list[list[int]] = [[] for _ in range(n)]
    for i, j, *_rest in bonds:
        out[i].append(j)
        out[j].append(i)
    return out


def _moving_side(neighbours, b: int, c: int) -> list[int]:
    """Atoms on *c*'s side of the bond ``b-c`` -- what a chi rotation moves."""
    seen = {b, c}
    stack = [c]
    moving: list[int] = []
    while stack:
        node = stack.pop()
        for other in neighbours[node]:
            if other in seen:
                continue
            seen.add(other)
            moving.append(other)
            stack.append(other)
    return moving


def _dihedral(p0, p1, p2, p3) -> float:
    """Return the dihedral over four points, in degrees, IUPAC sense."""
    b0 = p0 - p1
    b1 = p2 - p1
    b2 = p3 - p2
    b1n = b1 / max(np.linalg.norm(b1), 1e-9)
    v = b0 - (b0 @ b1n) * b1n
    w = b2 - (b2 @ b1n) * b1n
    x = v @ w
    y = np.cross(b1n, v) @ w
    return math.degrees(math.atan2(y, x))


def _rotate_about(coords: np.ndarray, indices, axis_a, axis_b, degrees: float) -> None:
    """Rotate *indices* about the axis through two points, in place."""
    if not indices or abs(degrees) < 1e-9:
        return
    origin = coords[axis_a]
    axis = coords[axis_b] - origin
    norm = np.linalg.norm(axis)
    if norm < 1e-9:
        return
    axis = axis / norm
    theta = math.radians(degrees)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    moving = coords[indices] - origin
    coords[indices] = (
        moving * cos_t
        + np.cross(axis, moving) * sin_t
        + np.outer(moving @ axis, axis) * (1.0 - cos_t)
        + origin
    )


def _is_hydrogen(name: str, element: str) -> bool:
    """Whether a fragment atom is a hydrogen.

    By element, with the name as the fallback: PyMOL's fragments name them
    `1HB`, `2HB`, `HA`, so a leading-character test on the *name* alone calls
    every `1HB` a hydrogen and every `HIS` nitrogen `HE2`... also a hydrogen,
    correctly, but `HG` (mercury) wrongly. The element is the answer and the
    name is only consulted when there is none.
    """
    symbol = str(element).strip().upper()
    if symbol:
        return symbol in ("H", "D")
    stripped = str(name).strip().lstrip("0123456789").upper()
    return stripped.startswith("H")


def build_rotamers(
    residue_name: str,
    backbone_xyz: dict[str, np.ndarray],
    *,
    hydrogens: bool = True,
) -> MutationSite:
    """Build every rotamer of *residue_name* onto a backbone.

    Parameters
    ----------
    residue_name : str
        Three-letter code of the residue to build.
    backbone_xyz : dict
        ``{"N": xyz, "CA": xyz, "C": xyz, "O": xyz}`` from the target residue.
        ``O`` is optional; ``N``, ``CA`` and ``C`` are not -- PyMOL's wizard
        refuses a residue missing any of them, and so does this.
    hydrogens : bool
        Keep the fragment's hydrogens. PyMOL's wizard calls this `hyd` and
        defaults it to `auto`: match the structure. Grafting a hydrogenated
        residue into a crystal structure that has none leaves one residue
        drawn with hydrogens and 164 without, which reads as a rendering
        fault.

    Returns
    -------
    MutationSite
        With :attr:`MutationSite.rotamers` filled in but unscored.

    Raises
    ------
    KeyError
        If the residue is not in the library.
    ValueError
        If the backbone is incomplete.
    """
    resn = str(residue_name).strip().upper()
    fragment = FRAGMENTS.get(resn)
    if fragment is None:
        raise KeyError(f"no fragment for {resn}")
    for atom in ("N", "CA", "C"):
        if atom not in backbone_xyz:
            raise ValueError(f"the residue has no {atom} to graft onto")

    names = list(fragment["names"])
    elements = list(fragment["elements"])
    coords = np.asarray(fragment["coords"], dtype=float)
    bonds = [(int(b[0]), int(b[1])) for b in fragment["bonds"]]
    if not hydrogens:
        keep = [
            i for i, (name, element) in enumerate(zip(names, elements))
            if not _is_hydrogen(name, element)
        ]
        remap = {old: new for new, old in enumerate(keep)}
        names = [names[i] for i in keep]
        elements = [elements[i] for i in keep]
        coords = coords[keep]
        bonds = [
            (remap[i], remap[j]) for i, j in bonds
            if i in remap and j in remap
        ]
    index_of = {name: i for i, name in enumerate(names)}

    # Superpose the fragment's backbone onto the target's, then *keep the
    # target's* backbone atoms: the fit is what orients the side chain, and
    # taking the fragment's own N/CA/C back would move the chain by the fit
    # residual.
    anchor = np.array([coords[index_of[a]] for a in ("N", "CA", "C")])
    target = np.array([backbone_xyz[a] for a in ("N", "CA", "C")])
    rotation, shift = _kabsch(anchor, target)
    coords = coords @ rotation.T + shift
    # Land CA *exactly* on the target's before the backbone is overwritten. The
    # fit spreads its residual over the three anchor atoms, so CA ends up a few
    # hundredths off; keeping the target's CA and the fragment's CB then
    # stretches the CA-CB bond by that much (1.58 A where the fragment says
    # 1.53). Absorbing the residual as a translation puts it into the
    # N-CA-CB *angle* instead, which is the harmless place for it.
    coords = coords + (np.asarray(backbone_xyz["CA"], dtype=float) - coords[index_of["CA"]])
    for atom in BACKBONE:
        if atom in index_of and atom in backbone_xyz:
            coords[index_of[atom]] = backbone_xyz[atom]

    neighbours = _neighbours(len(names), bonds)
    library = ROTAMERS.get(ROTAMER_ALIASES.get(resn, resn), [])
    site = MutationSite(indices=[], names=names, elements=elements, bonds=bonds)

    if not library:
        # ALA and GLY have no chi angles at all; the built fragment is the
        # answer, and PyMOL lists them for exactly that reason.
        site.rotamers = [Rotamer(1.0, {}, coords.copy())]
        return site

    for frequency, chis in library:
        built = coords.copy()
        for quad, angle in chis.items():
            if any(name not in index_of for name in quad):
                continue
            a, b, c, d = (index_of[name] for name in quad)
            current = _dihedral(built[a], built[b], built[c], built[d])
            moving = _moving_side(neighbours, b, c)
            _rotate_about(built, moving, b, c, float(angle) - current)
        site.rotamers.append(Rotamer(float(frequency), dict(chis), built))
    return site


def score_rotamers(
    site: MutationSite,
    environment_xyz: np.ndarray,
    environment_elements,
    *,
    criteria: ClashCriteria | None = None,
) -> MutationSite:
    """Run the bump check on every rotamer, cheapest first afterwards.

    The wizard's step 4: each conformation is scored against the *surroundings*
    -- never against its own backbone, which every rotamer shares and which
    would add the same constant to all of them.

    Parameters
    ----------
    site : MutationSite
        From :func:`build_rotamers`.
    environment_xyz : numpy.ndarray
        ``(m, 3)`` positions of everything the new side chain must live beside,
        with the mutated residue's own atoms already removed.
    environment_elements : sequence of str
        Their elements, for the van der Waals radii.
    criteria : ClashCriteria, optional
        Defaults to PyMOL's sculpting settings.

    Returns
    -------
    MutationSite
        The same site, with :attr:`Rotamer.strain` filled in. The order is left
        alone -- most frequent first, as the library gives it -- because that is
        the order a chooser should show, with strain as a second column rather
        than as the sort key.
    """
    env = np.asarray(environment_xyz, dtype=float).reshape(-1, 3)
    env_radii = radii_for(environment_elements)
    side_chain = [
        index for index, name in enumerate(site.names)
        if name not in BACKBONE
        and not _is_hydrogen(name, site.elements[index])
    ]
    # The side chain's own bonds, renumbered onto the block it occupies in the
    # combined array, so its bonded pairs are excluded rather than scored.
    position = {atom: row for row, atom in enumerate(side_chain)}
    bonds = [
        (position[i], position[j])
        for i, j in site.bonds
        if i in position and j in position
    ]
    scored: list[Rotamer] = []
    for rotamer in site.rotamers:
        if not side_chain or not len(env):
            scored.append(Rotamer(rotamer.frequency, rotamer.chis, rotamer.coords, 0.0))
            continue
        xyz = np.vstack([rotamer.coords[side_chain], env])
        radii = np.concatenate([
            radii_for([site.elements[i] for i in side_chain]), env_radii
        ])
        subject = np.zeros(len(xyz), dtype=bool)
        subject[: len(side_chain)] = True
        report = find_clashes(xyz, radii, bonds, subject=subject, criteria=criteria)
        scored.append(
            Rotamer(rotamer.frequency, rotamer.chis, rotamer.coords, report.strain)
        )
    site.rotamers = scored
    return site


def mutate_residue(
    atoms: np.ndarray,
    residue_indices,
    residue_name: str,
    *,
    rotamer: int | None = None,
    hydrogens: bool | None = None,
    criteria: ClashCriteria | None = None,
) -> MutationResult:
    """Mutate one residue, choosing the rotamer with the least strain.

    Parameters
    ----------
    atoms : numpy.ndarray
        The structure's atom table.
    residue_indices : sequence of int
        Rows belonging to the residue being replaced.
    residue_name : str
        What it becomes.
    rotamer : int, optional
        Which conformation to take. Defaults to the least strained, which is
        what the wizard starts on (`state_best`).
    hydrogens : bool, optional
        Keep the fragment's hydrogens. ``None`` is PyMOL's `hyd auto`: match
        the structure, so a crystal structure without hydrogens gets a residue
        without them.
    criteria : ClashCriteria, optional
        Defaults to PyMOL's sculpting settings.

    Returns
    -------
    MutationResult
    """
    indices = [int(i) for i in residue_indices]
    if not indices:
        raise ValueError("no residue to mutate")

    names = atoms.dtype.names or ()
    xyz = np.asarray(atoms["xyz"], dtype=float)
    atom_names = (
        np.array([str(n).strip() for n in atoms["atom_name"]])
        if "atom_name" in names else np.array([""] * len(atoms))
    )
    elements = (
        np.array([str(e).strip() for e in atoms["element"]])
        if "element" in names else np.array([""] * len(atoms))
    )

    backbone = {
        atom_names[i]: xyz[i] for i in indices if atom_names[i] in BACKBONE
    }
    if hydrogens is None:
        hydrogens = bool(np.any(np.isin(
            np.char.upper(elements.astype(str)), ("H", "D")
        )))
    site = build_rotamers(residue_name, backbone, hydrogens=hydrogens)
    site.indices = indices

    # The surroundings: everything within the wizard's 6 A of the residue,
    # minus the residue itself. Anything further away cannot bump into a side
    # chain that is at most ~6 A long.
    centre = xyz[indices].mean(axis=0)
    near = np.linalg.norm(xyz - centre, axis=1) <= (NEIGHBOURHOOD + 6.0)
    near[indices] = False
    site = score_rotamers(
        site, xyz[near], elements[near], criteria=criteria
    )

    if rotamer is None:
        chosen = int(min(
            range(len(site.rotamers)),
            key=lambda k: (site.rotamers[k].strain, -site.rotamers[k].frequency),
        ))
    else:
        chosen = max(0, min(int(rotamer), len(site.rotamers) - 1))
    return MutationResult(site=site, chosen=chosen, residue_name=residue_name.upper())
