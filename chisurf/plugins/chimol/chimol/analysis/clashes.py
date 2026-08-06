"""Steric clashes, the way PyMOL's sculpting reports and draws them.

PyMOL has no `clashes` command. What it has is the **bump check** the
mutagenesis wizard runs: it builds an object out of the mutated side chain and
everything within 6 A of it, turns on `sculpt_vdw_vis_mode`, and asks the
sculptor for one iteration. The sculptor's van der Waals term returns a
*strain* -- the sum of the overlaps -- and, with the visualisation on, draws a
coloured cylinder across every overlapping pair. That is the picture everyone
recognises: green where the contact is comfortable, red where two atoms are
inside each other.

Transcribed from `layer2/Sculpt.cpp` -- `SculptIterateObject`'s vdW arm and
`SculptCGOBump` -- and its defaults from `layer1/SettingInfo.h`:

* the pair cutoff is **vdw1 + vdw2**, reduced by `sculpt_hb_overlap` (1.0 A)
  when the pair is a hydrogen and its donor/acceptor partner, or by
  `sculpt_hb_overlap_base` (0.35 A) when it is the heavy-atom pair of a
  hydrogen bond. Without that, every hydrogen bond reads as a clash -- which
  is the first thing a naive vdW check gets wrong on a real structure;
* pairs closer than **four bonds** are excluded outright (`ex > 3`), and 1-4
  pairs use `sculpt_vdw_scale14` (0.90) rather than `sculpt_vdw_scale` (0.97);
* the strain a pair contributes is `|cutoff * scale - distance|`
  (`SculptDoBump`), summed over the pairs -- the number the wizard ranks
  rotamers by;
* the colour runs from `(0.2, 1.0, 0.2)` to `(1.0, 0.2, 0.2)` by
  `(overlap - sculpt_vdw_vis_mid) / sculpt_vdw_vis_max`, clamped, where
  `overlap = cutoff - distance`. Nothing is drawn until the pair is within
  `cutoff - sculpt_vdw_vis_min`, and `min` is *negative* (-0.1), so a contact
  slightly *outside* the sum of the radii is still drawn -- in green, saying
  "this one is fine" rather than saying nothing at all.

The one thing not transcribed is the sculptor itself: chimol does not move
atoms to relieve strain, it reports it. `sculpt_vdw_scale` therefore appears
only in the strain, exactly as in PyMOL, where the drawn geometry uses the
unscaled cutoff.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .hbonds import neighbour_lists

__all__ = [
    "ClashCriteria",
    "Clash",
    "ClashReport",
    "find_clashes",
    "clash_color",
]

#: PyMOL's `good_color` and `bad_color`, hard-coded in `SculptIterateObject`.
GOOD_COLOR = (0.2, 1.0, 0.2)
BAD_COLOR = (1.0, 0.2, 0.2)

#: `ElementTable` in `layer2/AtomInfo.cpp`, which is where PyMOL's `vdw` comes
#: from. It matters that the check uses *these* and not whatever the reader
#: stored: chimol's structure reader assigns force-field radii (carbon 1.85,
#: not 1.70), and 0.3 A per atom turns every second contact in a refined
#: structure into a reported overlap. The bump check is a comparison against
#: PyMOL, so it uses PyMOL's radii.
VDW_RADII: dict[str, float] = {
    "H": 1.20, "D": 1.20, "HE": 1.40, "LI": 1.82, "BE": 1.80, "B": 1.85,
    "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47, "NE": 1.54, "NA": 2.27,
    "MG": 1.73, "AL": 2.00, "SI": 2.10, "P": 1.80, "S": 1.80, "CL": 1.75,
    "AR": 1.88, "K": 2.75, "CA": 1.80, "MN": 1.73, "FE": 1.80, "NI": 1.63,
    "CU": 1.40, "ZN": 1.39, "SE": 1.90, "BR": 1.85, "I": 1.98,
}

#: What PyMOL falls back to for an element it has no radius for
#: (`AtomInfoAssignParameters`).
DEFAULT_VDW = 1.80


def radii_for(elements) -> np.ndarray:
    """PyMOL's van der Waals radius per element symbol."""
    return np.array(
        [VDW_RADII.get(str(symbol).strip().upper(), DEFAULT_VDW) for symbol in elements],
        dtype=float,
    )


@dataclass(frozen=True)
class ClashCriteria:
    """The sculpting settings the bump check reads, with PyMOL's defaults.

    Attributes
    ----------
    vdw_scale : float
        `sculpt_vdw_scale`, applied to the cutoff for the *strain*.
    vdw_scale14 : float
        `sculpt_vdw_scale14`, the same for pairs exactly four bonds apart.
    hb_overlap : float
        `sculpt_hb_overlap`: how much a hydrogen is allowed to overlap the
        acceptor it is bonded to.
    hb_overlap_base : float
        `sculpt_hb_overlap_base`: the same allowance between the two heavy
        atoms of a hydrogen bond.
    vis_min, vis_mid, vis_max : float
        `sculpt_vdw_vis_min/mid/max`: where drawing starts, where the colour
        starts leaving green, and how far it takes to reach red.
    """

    vdw_scale: float = 0.97
    vdw_scale14: float = 0.90
    hb_overlap: float = 1.0
    hb_overlap_base: float = 0.35
    vis_min: float = -0.1
    vis_mid: float = 0.1
    vis_max: float = 0.3

    @classmethod
    def from_config(cls) -> ClashCriteria:
        """Read the criteria from the display configuration."""
        from ..config import _DISPLAY_CONFIG

        cfg = (_DISPLAY_CONFIG.get("clashes") or {})
        fields = {}
        for name in (
            "vdw_scale", "vdw_scale14", "hb_overlap", "hb_overlap_base",
            "vis_min", "vis_mid", "vis_max",
        ):
            if name in cfg:
                try:
                    fields[name] = float(cfg[name])
                except (TypeError, ValueError):
                    continue
        return cls(**fields)


@dataclass(frozen=True)
class Clash:
    """One overlapping pair.

    Attributes
    ----------
    i, j : int
        Atom indices, ``i < j``.
    distance : float
        How far apart they are.
    cutoff : float
        The sum of the radii, after the hydrogen-bond allowance.
    overlap : float
        ``cutoff - distance``. PyMOL's ``good_bad``: positive is a clash and
        negative is a contact that is merely close.
    strain : float
        What this pair contributes to the total, ``|cutoff * scale - distance|``
        -- zero for a pair that is not inside the scaled cutoff.
    """

    i: int
    j: int
    distance: float
    cutoff: float
    overlap: float
    strain: float


@dataclass
class ClashReport:
    """Every overlapping pair, and the total strain over them."""

    clashes: list[Clash]
    strain: float

    def worst(self, count: int = 10) -> list[Clash]:
        """Return the *count* deepest overlaps, worst first."""
        return sorted(self.clashes, key=lambda c: -c.overlap)[:count]

    def atoms(self) -> set[int]:
        """Every atom involved in a clash."""
        found: set[int] = set()
        for clash in self.clashes:
            found.add(clash.i)
            found.add(clash.j)
        return found


def clash_color(overlap: float, criteria: ClashCriteria) -> tuple[float, float, float]:
    """Interpolate PyMOL's green-to-red bump colour for an overlap.

    `SculptCGOBump`: the factor is zero below ``vis_mid`` and
    ``(overlap - mid) / max`` above it, clamped at one.
    """
    if overlap < criteria.vis_mid:
        factor = 0.0
    else:
        factor = min((overlap - criteria.vis_mid) / max(criteria.vis_max, 1e-6), 1.0)
    return tuple(
        good * (1.0 - factor) + bad * factor
        for good, bad in zip(GOOD_COLOR, BAD_COLOR)
    )


def _pair_key(i: int, j: int) -> tuple[int, int]:
    return (i, j) if i < j else (j, i)


def find_clashes(
    coords: np.ndarray,
    radii: np.ndarray,
    bond_pairs,
    *,
    subject=None,
    donors=None,
    acceptors=None,
    is_hydrogen=None,
    criteria: ClashCriteria | None = None,
) -> ClashReport:
    """Every van der Waals overlap, and the strain they add up to.

    Parameters
    ----------
    coords : numpy.ndarray
        ``(n, 3)`` atom positions.
    radii : numpy.ndarray
        ``(n,)`` van der Waals radii.
    bond_pairs : iterable of (int, int)
        The bonds, used for the exclusion: a pair separated by three bonds or
        fewer never clashes, and a 1-4 pair gets the softer scale.
    subject : array_like of bool or int, optional
        Restrict to pairs with at least one atom here -- the wizard's "check
        this side chain against its surroundings" rather than "check
        everything against everything".
    donors, acceptors : array_like of bool, optional
        Which atoms donate and accept a hydrogen bond, from
        :func:`~chimol.analysis.hbonds.type_atoms`. Without them the
        hydrogen-bond allowance cannot be applied and every hydrogen bond is
        reported as a clash.
    is_hydrogen : array_like of bool, optional
        Which atoms are hydrogens, for the larger of the two allowances.
    criteria : ClashCriteria, optional
        Defaults to PyMOL's.

    Returns
    -------
    ClashReport
    """
    criteria = criteria or ClashCriteria()
    xyz = np.asarray(coords, dtype=float)
    rad = np.asarray(radii, dtype=float)
    n = xyz.shape[0]
    if n == 0 or rad.shape[0] != n:
        return ClashReport([], 0.0)

    don = _as_mask(donors, n)
    acc = _as_mask(acceptors, n)
    hyd = _as_mask(is_hydrogen, n)
    keep = _as_mask(subject, n, default=True)

    # Bond separation, PyMOL's `ex`: 1-2, 1-3 and 1-4 pairs are special and
    # anything closer than 1-5 is not a clash at all.
    neighbours = neighbour_lists(n, bond_pairs)
    excluded = _bond_separation(neighbours, n)

    # A cell list over the largest possible cutoff. Two vdW radii plus the
    # visualisation's negative `min` is the widest a drawn pair can be.
    reach = float(rad.max() * 2.0 - criteria.vis_min) if n else 0.0
    pairs = _pairs_within(xyz, reach, keep)

    clashes: list[Clash] = []
    total = 0.0
    for i, j in pairs:
        level = excluded.get((i, j))
        if level is not None and level < 4:
            continue                              # 1-2 and 1-3: never a clash
        cutoff = float(rad[i] + rad[j])
        distance = float(np.linalg.norm(xyz[i] - xyz[j]))

        if level == 4:
            # PyMOL's `ex == 4` arm: the cutoff itself is scaled by
            # `sculpt_vdw_scale14` and the pair contributes strain -- but
            # `SculptCGOBump` is **not** called for it, so a 1-4 pair is never
            # drawn. It is a torsion the geometry already fixes, and drawing
            # them buries the real clashes in a haze of intra-residue lines.
            cutoff *= criteria.vdw_scale14
            if distance < cutoff:
                total += abs(cutoff - distance)
            continue

        if (don[i] and acc[j]) or (acc[i] and don[j]):
            cutoff -= criteria.hb_overlap if (hyd[i] or hyd[j]) else criteria.hb_overlap_base
        overlap = cutoff - distance
        if overlap < criteria.vis_min:
            continue
        target = cutoff * criteria.vdw_scale
        strain = abs(target - distance) if distance < target else 0.0
        total += strain
        clashes.append(Clash(i, j, distance, cutoff, overlap, strain))
    return ClashReport(clashes, total)


def _bond_separation(neighbours, n: int) -> dict[tuple[int, int], int]:
    """PyMOL's ``ex`` per pair: 2 for 1-2, 3 for 1-3, 4 for 1-4, absent beyond.

    A breadth-first walk three bonds deep from every atom. The pair test in
    :mod:`~chimol.analysis.hbonds` answers "are these two within n bonds"; the
    bump check needs the *distance*, because a 1-4 pair is not excluded, it is
    softened.
    """
    levels: dict[tuple[int, int], int] = {}
    for start in range(n):
        frontier = {start}
        seen = {start}
        for depth in range(1, 4):
            nxt: set[int] = set()
            for node in frontier:
                for other in neighbours[node]:
                    if other in seen:
                        continue
                    seen.add(other)
                    nxt.add(other)
                    key = _pair_key(start, other)
                    level = depth + 1             # bonds -> PyMOL's 1-2/1-3/1-4
                    if levels.get(key, 99) > level:
                        levels[key] = level
            frontier = nxt
            if not frontier:
                break
    return levels


def _as_mask(value, n: int, default: bool = False) -> np.ndarray:
    """Coerce a boolean mask, an index array or ``None`` into an ``(n,)`` mask."""
    if value is None:
        return np.full(n, default, dtype=bool)
    arr = np.asarray(value)
    if arr.dtype == bool:
        if arr.shape[0] != n:
            return np.full(n, default, dtype=bool)
        return arr
    mask = np.zeros(n, dtype=bool)
    valid = arr[(arr >= 0) & (arr < n)].astype(int)
    mask[valid] = True
    return mask


def _pairs_within(xyz: np.ndarray, reach: float, keep: np.ndarray):
    """Index pairs closer than *reach*, at least one of them in *keep*.

    A uniform grid rather than an all-pairs distance: the bump check runs once
    per rotamer, and a 3000-atom neighbourhood squared is 9 million distances
    for the fifty pairs that matter.
    """
    n = xyz.shape[0]
    if n < 2 or reach <= 0.0:
        return []
    cell = max(reach, 1e-3)
    keys = np.floor(xyz / cell).astype(np.int64)
    buckets: dict[tuple[int, int, int], list[int]] = {}
    for index in range(n):
        buckets.setdefault(tuple(keys[index]), []).append(index)

    reach2 = reach * reach
    seen: set[tuple[int, int]] = set()
    offsets = [
        (dx, dy, dz)
        for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
    ]
    subject = np.nonzero(keep)[0] if keep.any() else np.arange(n)
    for i in subject:
        base = keys[i]
        for dx, dy, dz in offsets:
            for j in buckets.get((base[0] + dx, base[1] + dy, base[2] + dz), ()):
                if j == i:
                    continue
                key = _pair_key(int(i), int(j))
                if key in seen:
                    continue
                delta = xyz[key[0]] - xyz[key[1]]
                if float(delta @ delta) <= reach2:
                    seen.add(key)
    return sorted(seen)


def bump_geometry(
    clash: Clash,
    coords: np.ndarray,
    radii: np.ndarray,
    criteria: ClashCriteria,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Return the two ends and the radius PyMOL draws a bump with.

    `SculptCGOBump` mode 1: the segment does not run between the two atoms but
    between two points either side of the **contact point** -- the position
    that divides the pair in proportion to their radii -- so the marker sits in
    the gap rather than through both atoms. Its length is a small fraction
    ``delta`` of the way back towards each atom, and its radius is half the
    overlap above ``vis_min``.
    """
    v1 = np.asarray(coords[clash.i], dtype=float)
    v2 = np.asarray(coords[clash.j], dtype=float)
    vdw1 = float(radii[clash.i])
    vdw2 = float(radii[clash.j])
    good_bad = clash.overlap

    if good_bad < 0.0:
        delta = abs(good_bad)
    else:
        delta = 0.5 * (0.01 + abs(good_bad)) / max(clash.cutoff, 1e-6)
    delta = min(max(delta, 0.01), 0.1)
    radius = max(0.5 * (good_bad - criteria.vis_min), 0.01)

    total = vdw1 + vdw2
    contact = (v2 * vdw1 + v1 * vdw2) / (total if total > 1e-6 else 1.0)
    end1 = v1 * delta + contact * (1.0 - delta)
    end2 = v2 * delta + contact * (1.0 - delta)
    return end1, end2, radius


def strain_of(report: ClashReport) -> float:
    """Return the wizard's number: the overlap the sculptor would relieve."""
    return float(report.strain)


def format_report(report: ClashReport, names, count: int = 10) -> list[str]:
    """Summarise a report as one line per worst clash, for a console or a panel.

    Parameters
    ----------
    report : ClashReport
        What :func:`find_clashes` produced.
    names : sequence of str
        Per-atom labels, e.g. ``LYS`128/NZ``.
    count : int
        How many to list.
    """
    lines = [
        f"{len(report.clashes)} contacts, "
        f"{sum(1 for c in report.clashes if c.overlap > 0)} overlapping, "
        f"strain {report.strain:.2f}"
    ]
    for clash in report.worst(count):
        if clash.overlap <= 0:
            break
        lines.append(
            f"  {names[clash.i]} -- {names[clash.j]}: "
            f"{clash.distance:.2f} A, {clash.overlap:.2f} A into the pair"
        )
    return lines
