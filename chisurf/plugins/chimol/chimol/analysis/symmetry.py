"""Crystallographic symmetry: the cell, the operators, and symmetry mates.

For PyMOL's ``symexp``, which builds the neighbouring copies of a molecule in its
crystal so a lattice contact can be looked at.

Where the operators come from
-----------------------------
From **PyMOL's own table**, transcribed out of ``modules/pymol/xray.py`` into
:mod:`space_groups` by the generator checked in beside it -- 547 space-group names
over 528 distinct operator sets, up to 192 operators each. No crystallography
library is a dependency (no ``gemmi``, ``spglib`` or ``cctbx``), and none is
wanted: sharing PyMOL's table is what makes the mates agree with PyMOL's rather
than approximately agree.

Three sources, in order of trust:

1. **operators supplied explicitly** (``set_symmetry``), or read from the file --
   mmCIF carries ``_symmetry_equiv.pos_as_xyz``. Exact, whatever the space group;
2. **PyMOL's table**, by space-group name;
3. **nothing** -- in which case the space group is *named* and the command
   declines, rather than inventing operators. A wrong symmetry mate looks
   entirely plausible and would be believed.

The transcription is not trusted on inspection: a test checks **every** group
mathematically -- that its operators are closed under composition modulo lattice
translations, that each rotation is a proper rotation or a proper improper one for
the centrosymmetric groups, and that there is exactly one identity. A bad
extraction fails those rather than placing mates plausibly wrongly.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

import numpy as np

__all__ = [
    "SPACE_GROUP_ALIASES",
    "SPACE_GROUP_OPERATORS",
    "operators_for",
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


#: PyMOL's table, keyed by :func:`normalise_space_group`. Re-exported here so
#: callers have one import; the data and its generator live in `space_groups.py`.
from .space_groups import (  # noqa: E402
    SPACE_GROUP_ALIASES,
    SPACE_GROUP_OPERATORS,
    lookup_operators,
)


def operators_for(name: str) -> tuple[str, ...] | None:
    """Operators for a space group, or None when the name is not in the table.

    Aliases are followed, so a conventional symbol and PyMOL's alternative
    spelling both resolve; ``P 21 21 21`` and ``P212121`` are the same key.
    """
    return lookup_operators(name)


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


#: One field of a CIF data row: single-quoted, double-quoted, or bare. Quotes are
#: not decoration here -- ``1 'X,Y,Z'`` is two fields, and stripping the quotes off
#: the whole row instead would leave the id glued to the operator.
_CIF_FIELD = re.compile(r"'([^']*)'|\"([^\"]*)\"|(\S+)")

#: The tags an operator can be written under, in the PDBx (dotted) and the older
#: CIF-core (underscored) spelling. Compared lower-cased: CIF tags are
#: case-insensitive.
_SYMOP_TAGS = frozenset({
    "_symmetry_equiv.pos_as_xyz",
    "_symmetry_equiv_pos_as_xyz",
})


def _cif_fields(text: str) -> list[str]:
    """Split one CIF data row into its fields, honouring and removing quotes."""
    return [
        # Exactly one of the three alternatives matched; an empty quoted field is
        # a field, so "first group that is not None" and not "first truthy one".
        next(group for group in match.groups() if group is not None)
        for match in _CIF_FIELD.finditer(text)
    ]


def read_file_operators(path) -> list[str]:
    """Symmetry operators carried by the file itself, if any.

    A PDB may hold them as ``REMARK 290   SMTRY`` rows -- three per operator,
    each a row of the rotation plus a translation in **Cartesian** terms -- and an
    mmCIF as ``_symmetry_equiv.pos_as_xyz`` in the ``x,y,z`` form used here.

    Only the mmCIF form is read, because it is the one already in the right
    coordinates. The SMTRY rows would need the cell to convert, and getting that
    wrong yields operators that look valid and place mates incorrectly -- exactly
    the failure this module refuses to risk elsewhere.

    The value is located by parsing the loop header rather than by taking the
    whole data row: a PDBx loop nearly always carries ``_symmetry_equiv.id``
    beside the operator, and a row read whole turns ``3 x+1/2,y+1/2,z`` into a
    threefold *scaling* (the id digit becomes the coefficient of ``x``) that
    :func:`parse_symmetry_operator` has no way to recognise as wrong. The tags may
    come in either order, and the non-loop form -- one tag with its value on the
    same line or the next -- is read too.

    Returns
    -------
    list of str
        Operators in ``x,y,z`` form; empty when the file carries none.
    """
    try:
        with open(path, "r", errors="replace") as handle:
            lines = [line.strip() for line in handle]
    except OSError:
        return []

    found: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if line.lower() == "loop_":
            index, operators = _read_symop_loop(lines, index)
            found.extend(operators)
        elif line.startswith("_") and line.split()[0].lower() in _SYMOP_TAGS:
            index, operator = _read_symop_item(lines, index, line)
            found.extend(operator)
    return [f for f in found if f.count(",") == 2]


def _read_symop_loop(lines: list[str], index: int) -> tuple[int, list[str]]:
    """Read the operator column out of the loop whose header starts at ``index``.

    Returns the index just past the loop and the operators found, which is empty
    when the loop is some other loop.
    """
    tags: list[str] = []
    while index < len(lines) and lines[index].startswith("_"):
        tags.append(lines[index].split()[0].lower())
        index += 1

    column = next((i for i, tag in enumerate(tags) if tag in _SYMOP_TAGS), None)
    fields: list[str] = []
    while index < len(lines):
        row = lines[index]
        if row.startswith("#"):
            index += 1
            continue
        if not row or row.startswith(("_", ";")) or row.lower() in ("loop_", "stop_"):
            break
        if row.lower().startswith("data_"):
            break
        # Fields are collected across rows rather than per row: CIF allows a row
        # to be packed onto one line or wrapped over several, and chunking by the
        # tag count reads both the same way. Only for the loop that is wanted --
        # splitting the rows of an ``atom_site`` loop would cost a regex pass over
        # every atom of the structure for nothing.
        if column is not None:
            fields.extend(_cif_fields(row))
        index += 1

    if column is None:
        return index, []
    return index, fields[column::len(tags)][:len(fields) // len(tags)]


def _read_symop_item(lines: list[str], index: int, line: str) -> tuple[int, list[str]]:
    """Read a non-loop ``tag value`` item whose tag line is ``line``.

    The value may sit on the tag line or on the next one; ``index`` points just
    past the tag line. Returns the new index and a one- or zero-item list.
    """
    fields = _cif_fields(line)[1:]
    while not fields and index < len(lines):
        candidate = lines[index]
        index += 1
        if candidate and not candidate.startswith("#"):
            fields = _cif_fields(candidate)
    return index, fields[:1]


# --------------------------------------------------------------------------- #
# Drawing the cell
# --------------------------------------------------------------------------- #
#: The twelve edges of a parallelepiped, as pairs of corner indices. Corners are
#: numbered by their fractional coordinates read as bits: corner ``i`` has
#: ``x = i & 1``, ``y = (i >> 1) & 1``, ``z = (i >> 2) & 1``. Two corners share an
#: edge exactly when their indices differ in one bit, which is where this list
#: comes from -- it is not an arbitrary ordering to be checked by eye.
CELL_EDGES = tuple(
    (i, i ^ bit)
    for bit in (1, 2, 4)
    for i in range(8)
    if not (i & bit)
)


def cell_corners(cell: UnitCell, origin=None) -> np.ndarray:
    """The eight corners of the unit cell, in Cartesian coordinates.

    Parameters
    ----------
    cell : UnitCell
        The crystal cell.
    origin : array-like, optional
        Cartesian position of the cell's origin; the coordinate origin by
        default.

    Returns
    -------
    numpy.ndarray
        ``(8, 3)`` corners, ordered so corner ``i`` has fractional coordinates
        ``(i & 1, (i >> 1) & 1, (i >> 2) & 1)``.
    """
    fractional = np.array([
        [i & 1, (i >> 1) & 1, (i >> 2) & 1] for i in range(8)
    ], dtype=float)
    corners = fractional @ cell.frac_to_real().T
    if origin is not None:
        corners = corners + np.asarray(origin, dtype=float)
    return corners


def cell_line_segments(cell: UnitCell, origin=None) -> np.ndarray:
    """The cell box as line segments, ready for a ``line`` geometry.

    Returns
    -------
    numpy.ndarray
        ``(24, 3)`` -- twelve edges as consecutive vertex pairs.
    """
    corners = cell_corners(cell, origin)
    return np.array(
        [corners[a] for edge in CELL_EDGES for a in edge], dtype=float
    )
