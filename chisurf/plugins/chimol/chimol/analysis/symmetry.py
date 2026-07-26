"""Crystallographic symmetry: the cell, the operators, and symmetry mates.

For PyMOL's ``symexp``, which builds the neighbouring copies of a molecule in its
crystal so a lattice contact can be looked at.

Where the operators come from
-----------------------------
PyMOL gets them from a space-group table compiled into it. Nothing here can:
neither ``gemmi`` nor ``spglib`` nor ``cctbx`` is installed. So there are three
sources, in order of trust:

1. **operators supplied explicitly** (``set_symmetry``), or read from the file --
   mmCIF carries ``_symmetry_equiv.pos_as_xyz`` and a PDB may carry
   ``REMARK 290   SMTRY``. Exact, whatever the space group;
2. **a built-in table** of the space groups common in protein crystallography;
3. **nothing** -- in which case the space group is *named* and the command
   declines, rather than inventing operators. A wrong symmetry mate looks
   entirely plausible and would be believed.

The table is hand-entered, which means it can be mistyped, so it is not trusted
on inspection: a test checks each entry **mathematically** -- that the operators
form a closed group under composition modulo lattice translations, that the count
matches the expected multiplicity, and that every rotation has determinant +1
(protein space groups are chiral; a mirror or an inversion would be a typo).
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

import numpy as np

__all__ = [
    "SPACE_GROUP_OPERATORS",
    "UnitCell",
    "normalise_space_group",
    "parse_symmetry_operator",
    "symmetry_mates",
]


# --------------------------------------------------------------------------- #
# The unit cell
# --------------------------------------------------------------------------- #
@dataclass
class UnitCell:
    """Cell edges in Angstrom and angles in degrees, with the two transforms."""

    a: float
    b: float
    c: float
    alpha: float = 90.0
    beta: float = 90.0
    gamma: float = 90.0

    def frac_to_real(self) -> np.ndarray:
        """The 3x3 taking fractional coordinates to Cartesian.

        The standard crystallographic setting: **a** along x, **b** in the xy
        plane. Any consistent convention works for generating mates, because the
        operators are applied in fractional space and only the round trip has to
        agree with itself -- but this is the one the PDB uses, so a matrix printed
        here matches one printed elsewhere.
        """
        alpha, beta, gamma = np.radians([self.alpha, self.beta, self.gamma])
        cos_a, cos_b, cos_g = np.cos([alpha, beta, gamma])
        sin_g = np.sin(gamma)
        # Cell volume factor; for a right-angled cell this reduces to 1.
        factor = np.sqrt(
            max(
                0.0,
                1.0 - cos_a**2 - cos_b**2 - cos_g**2 + 2 * cos_a * cos_b * cos_g,
            )
        )
        return np.array([
            [self.a, self.b * cos_g, self.c * cos_b],
            [0.0, self.b * sin_g, self.c * (cos_a - cos_b * cos_g) / sin_g],
            [0.0, 0.0, self.c * factor / sin_g],
        ])

    def real_to_frac(self) -> np.ndarray:
        """The inverse of :meth:`frac_to_real`."""
        return np.linalg.inv(self.frac_to_real())

    @property
    def volume(self) -> float:
        """Cell volume in cubic Angstrom."""
        return float(abs(np.linalg.det(self.frac_to_real())))


# --------------------------------------------------------------------------- #
# Operators
# --------------------------------------------------------------------------- #
_TERM = re.compile(r"([+-]?)\s*(?:(\d+)\s*/\s*(\d+)|(\d*\.?\d+))?\s*\*?\s*([xyz]?)")


def parse_symmetry_operator(text: str) -> tuple[np.ndarray, np.ndarray]:
    """Parse one operator such as ``-x, y+1/2, -z+1/2``.

    Parameters
    ----------
    text : str
        Three comma-separated components in fractional coordinates.

    Returns
    -------
    tuple
        ``(rotation 3x3, translation 3)``.

    Raises
    ------
    ValueError
        When the operator does not have three parseable components. An operator
        that silently parsed to something else would generate a plausible mate in
        the wrong place.
    """
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) != 3:
        raise ValueError(f"a symmetry operator needs three components: {text!r}")

    rotation = np.zeros((3, 3))
    translation = np.zeros(3)
    axes = {"x": 0, "y": 1, "z": 2}

    for row, component in enumerate(parts):
        cleaned = component.replace(" ", "").lower()
        if not cleaned:
            raise ValueError(f"empty component in operator {text!r}")
        # Split into signed terms without losing the sign.
        for match in re.finditer(r"[+-]?[^+-]+", cleaned):
            term = match.group(0)
            sign = -1.0 if term.startswith("-") else 1.0
            term = term.lstrip("+-")
            axis = next((c for c in term if c in axes), None)
            if axis is not None:
                coefficient = term.replace(axis, "").rstrip("*")
                value = _as_number(coefficient) if coefficient else 1.0
                rotation[row, axes[axis]] += sign * value
            else:
                translation[row] += sign * _as_number(term)
    return rotation, translation


def _as_number(text: str) -> float:
    """A coefficient, which may be a fraction like ``1/2``."""
    text = text.strip().rstrip("*")
    if not text:
        return 1.0
    if "/" in text:
        numerator, _, denominator = text.partition("/")
        return float(numerator) / float(denominator)
    return float(text)


def normalise_space_group(name: str) -> str:
    """Collapse the spellings of a space-group name to one key.

    ``P 21 21 21``, ``P212121`` and ``p 21 21 21`` are the same group, and a
    CRYST1 record may carry any of them.
    """
    return "".join(str(name).upper().split())


#: Operators for the space groups common in protein crystallography, keyed by
#: :func:`normalise_space_group`. Verified by test rather than by inspection --
#: see the module docstring.
SPACE_GROUP_OPERATORS: dict[str, tuple[str, ...]] = {
    "P1": ("x,y,z",),
    "P2": ("x,y,z", "-x,y,-z"),
    "P21": ("x,y,z", "-x,y+1/2,-z"),
    "P1211": ("x,y,z", "-x,y+1/2,-z"),
    "C2": ("x,y,z", "-x,y,-z", "x+1/2,y+1/2,z", "-x+1/2,y+1/2,-z"),
    "C121": ("x,y,z", "-x,y,-z", "x+1/2,y+1/2,z", "-x+1/2,y+1/2,-z"),
    "P222": ("x,y,z", "-x,-y,z", "-x,y,-z", "x,-y,-z"),
    "P2221": ("x,y,z", "-x,-y,z+1/2", "-x,y,-z+1/2", "x,-y,-z"),
    "P21212": (
        "x,y,z", "-x,-y,z", "-x+1/2,y+1/2,-z", "x+1/2,-y+1/2,-z",
    ),
    "P212121": (
        "x,y,z", "-x+1/2,-y,z+1/2", "-x,y+1/2,-z+1/2", "x+1/2,-y+1/2,-z",
    ),
    "C2221": (
        "x,y,z", "-x,-y,z+1/2", "-x,y,-z+1/2", "x,-y,-z",
        "x+1/2,y+1/2,z", "-x+1/2,-y+1/2,z+1/2",
        "-x+1/2,y+1/2,-z+1/2", "x+1/2,-y+1/2,-z",
    ),
    "P4": ("x,y,z", "-x,-y,z", "-y,x,z", "y,-x,z"),
    "P41": (
        "x,y,z", "-x,-y,z+1/2", "-y,x,z+1/4", "y,-x,z+3/4",
    ),
    "P43": (
        "x,y,z", "-x,-y,z+1/2", "-y,x,z+3/4", "y,-x,z+1/4",
    ),
    "P41212": (
        "x,y,z", "-x,-y,z+1/2", "-y+1/2,x+1/2,z+1/4", "y+1/2,-x+1/2,z+3/4",
        "-x+1/2,y+1/2,-z+1/4", "x+1/2,-y+1/2,-z+3/4", "y,x,-z", "-y,-x,-z+1/2",
    ),
    "P43212": (
        "x,y,z", "-x,-y,z+1/2", "-y+1/2,x+1/2,z+3/4", "y+1/2,-x+1/2,z+1/4",
        "-x+1/2,y+1/2,-z+3/4", "x+1/2,-y+1/2,-z+1/4", "y,x,-z", "-y,-x,-z+1/2",
    ),
    "P3": ("x,y,z", "-y,x-y,z", "-x+y,-x,z"),
    "P31": ("x,y,z", "-y,x-y,z+1/3", "-x+y,-x,z+2/3"),
    "P32": ("x,y,z", "-y,x-y,z+2/3", "-x+y,-x,z+1/3"),
    "P321": (
        "x,y,z", "-y,x-y,z", "-x+y,-x,z", "y,x,-z", "x-y,-y,-z", "-x,-x+y,-z",
    ),
    "P3121": (
        "x,y,z", "-y,x-y,z+1/3", "-x+y,-x,z+2/3",
        "y,x,-z", "x-y,-y,-z+2/3", "-x,-x+y,-z+1/3",
    ),
    "P3221": (
        "x,y,z", "-y,x-y,z+2/3", "-x+y,-x,z+1/3",
        "y,x,-z", "x-y,-y,-z+1/3", "-x,-x+y,-z+2/3",
    ),
    "P6": ("x,y,z", "-y,x-y,z", "-x+y,-x,z", "-x,-y,z", "y,-x+y,z", "x-y,x,z"),
    "P61": (
        "x,y,z", "-y,x-y,z+1/3", "-x+y,-x,z+2/3",
        "-x,-y,z+1/2", "y,-x+y,z+5/6", "x-y,x,z+1/6",
    ),
    "P65": (
        "x,y,z", "-y,x-y,z+2/3", "-x+y,-x,z+1/3",
        "-x,-y,z+1/2", "y,-x+y,z+1/6", "x-y,x,z+5/6",
    ),
    "I222": (
        "x,y,z", "-x,-y,z", "-x,y,-z", "x,-y,-z",
        "x+1/2,y+1/2,z+1/2", "-x+1/2,-y+1/2,z+1/2",
        "-x+1/2,y+1/2,-z+1/2", "x+1/2,-y+1/2,-z+1/2",
    ),
    "F222": (
        "x,y,z", "-x,-y,z", "-x,y,-z", "x,-y,-z",
        "x,y+1/2,z+1/2", "-x,-y+1/2,z+1/2",
        "-x,y+1/2,-z+1/2", "x,-y+1/2,-z+1/2",
        "x+1/2,y,z+1/2", "-x+1/2,-y,z+1/2",
        "-x+1/2,y,-z+1/2", "x+1/2,-y,-z+1/2",
        "x+1/2,y+1/2,z", "-x+1/2,-y+1/2,z",
        "-x+1/2,y+1/2,-z", "x+1/2,-y+1/2,-z",
    ),
}


def operators_for(name: str) -> tuple[str, ...] | None:
    """Built-in operators for a space group, or None when it is not tabulated."""
    return SPACE_GROUP_OPERATORS.get(normalise_space_group(name))


# --------------------------------------------------------------------------- #
# Generating mates
# --------------------------------------------------------------------------- #
def symmetry_mates(
    coords: np.ndarray,
    cell: UnitCell,
    operators: list[str] | tuple[str, ...],
    *,
    cutoff: float = 5.0,
    shells: int = 1,
    selection: np.ndarray | None = None,
) -> list[dict]:
    """Build the symmetry copies that come within ``cutoff`` of the molecule.

    Follows ``ExecutiveSymExp``: for every lattice translation and every operator,
    transform the coordinates in **fractional** space, shift the copy so it lands
    next to the original rather than an arbitrary distance away, convert back, and
    keep it only if some atom is close enough to matter.

    Parameters
    ----------
    coords : numpy.ndarray
        ``(N, 3)`` Cartesian coordinates in Angstrom.
    cell : UnitCell
        The crystal cell.
    operators : list of str
        Symmetry operators in ``x,y,z`` form.
    cutoff : float, optional
        A mate is kept when any of its atoms is within this distance of the
        selection. ``0`` or less keeps every mate.
    shells : int, optional
        How many lattice translations to try in each direction; 1 means the 27
        cells from -1 to +1, which is what PyMOL uses.
    selection : numpy.ndarray, optional
        Boolean over atoms; distances are measured to these only.

    Returns
    -------
    list of dict
        ``{"operator": int, "translation": (i, j, k), "coords": ndarray}``, the
        identity at the origin excluded -- it is the molecule itself.
    """
    coords = np.asarray(coords, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 3:
        raise ValueError("coords must have shape (N, 3)")
    if not operators:
        raise ValueError("no symmetry operators were given")

    parsed = [parse_symmetry_operator(op) for op in operators]
    to_frac = cell.real_to_frac()
    to_real = cell.frac_to_real()

    reference = coords if selection is None else coords[np.asarray(selection, bool)]
    if reference.size == 0:
        reference = coords

    fractional = coords @ to_frac.T
    centre = fractional.mean(axis=0)

    # One tree for the reference, built once. Rebuilding it per candidate meant
    # 107 tree builds over every atom of the molecule, which on a 17 784-atom
    # structure is most of the run time.
    tree = None
    if cutoff > 0:
        try:
            from scipy.spatial import cKDTree

            tree = cKDTree(reference)
        except Exception:
            tree = None
    lower = reference.min(axis=0) - cutoff
    upper = reference.max(axis=0) + cutoff

    mates: list[dict] = []
    span = range(-int(shells), int(shells) + 1)
    for (i, j, k), (index, (rotation, translation)) in itertools.product(
        itertools.product(span, span, span), enumerate(parsed)
    ):
        if index == 0 and (i, j, k) == (0, 0, 0):
            continue  # the molecule itself

        moved = fractional @ rotation.T + translation
        # Bring the copy next to the original: without this a mate can land many
        # cells away and never come within the cutoff, so the lattice contact you
        # were looking for is silently absent.
        new_centre = centre @ rotation.T + translation
        moved = moved - np.floor(new_centre - centre + 0.5)
        moved = moved + np.array([i, j, k], dtype=float)

        cartesian = moved @ to_real.T
        if cutoff > 0:
            # Bounding boxes first: most candidates are a whole cell away, and
            # rejecting those without touching the tree is what makes this usable
            # on a large structure.
            if np.any(cartesian.max(axis=0) < lower) or np.any(
                cartesian.min(axis=0) > upper
            ):
                continue
            if not _within(cartesian, reference, cutoff, tree=tree):
                continue
        mates.append({
            "operator": index,
            "translation": (i, j, k),
            "coords": cartesian,
        })
    return mates


def _within(a: np.ndarray, b: np.ndarray, cutoff: float, *, tree=None) -> bool:
    """Whether any point of ``a`` is within ``cutoff`` of any point of ``b``.

    ``tree`` is a prebuilt KD-tree over ``b``; passing one avoids rebuilding it
    per candidate mate.
    """
    try:
        if tree is None:
            from scipy.spatial import cKDTree

            tree = cKDTree(b)
        # The nearest neighbour in b for each point of a; one is enough.
        distances, _ = tree.query(a, k=1, distance_upper_bound=cutoff)
        return bool(np.any(np.isfinite(distances)))
    except Exception:
        # Chunked brute force: a full (N, M) matrix on two proteins is large.
        for start in range(0, a.shape[0], 512):
            block = a[start:start + 512]
            distances = np.linalg.norm(block[:, None, :] - b[None, :, :], axis=-1)
            if bool(np.any(distances <= cutoff)):
                return True
        return False


# --------------------------------------------------------------------------- #
# Reading the cell and operators from a file
# --------------------------------------------------------------------------- #
def read_cryst1(path) -> tuple[UnitCell, str] | None:
    """Read the cell and space group from a PDB ``CRYST1`` record.

    Column positions are fixed by the PDB format, and are used rather than
    splitting on whitespace: a space group like ``P 21 21 21`` contains spaces,
    so a split would tear it into pieces and take the Z value for part of the
    name.

    Returns
    -------
    tuple or None
        ``(cell, space group)``, or None when the file carries no CRYST1.
    """
    try:
        with open(path, "r", errors="replace") as handle:
            for line in handle:
                if not line.startswith("CRYST1"):
                    continue
                cell = UnitCell(
                    a=float(line[6:15]), b=float(line[15:24]), c=float(line[24:33]),
                    alpha=float(line[33:40]), beta=float(line[40:47]),
                    gamma=float(line[47:54]),
                )
                return cell, line[55:66].strip()
    except (OSError, ValueError):
        return None
    return None


def read_file_operators(path) -> list[str]:
    """Symmetry operators carried by the file itself, if any.

    A PDB may hold them as ``REMARK 290   SMTRY`` rows -- three per operator,
    each a row of the rotation plus a translation in **Cartesian** terms -- and an
    mmCIF as ``_symmetry_equiv.pos_as_xyz`` in the ``x,y,z`` form used here.

    Only the mmCIF form is read, because it is the one already in the right
    coordinates. The SMTRY rows would need the cell to convert, and getting that
    wrong yields operators that look valid and place mates incorrectly -- exactly
    the failure this module refuses to risk elsewhere.

    Returns
    -------
    list of str
        Operators in ``x,y,z`` form; empty when the file carries none.
    """
    found: list[str] = []
    try:
        with open(path, "r", errors="replace") as handle:
            in_loop = False
            for line in handle:
                stripped = line.strip()
                if stripped.startswith("_symmetry_equiv") and "pos_as_xyz" in stripped:
                    in_loop = True
                    continue
                if in_loop:
                    if not stripped or stripped.startswith(("_", "#", "loop_")):
                        break
                    found.append(stripped.strip("'\""))
    except OSError:
        return []
    return [f for f in found if f.count(",") == 2]
