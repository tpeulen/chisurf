"""Element data, re-exported from the one central table.

The table lives in :mod:`chisurf.core.fio.structure.elements` because the
*reader* needs it -- a PDB's masses and van der Waals radii are assigned while
the file is parsed, which is core rather than plugin work. This module keeps the
import path chimol's own code and tests already use, and keeps there being one
table: two copies of a periodic table is exactly the kind of duplication that
drifts silently and is discovered by a molecular weight nobody can reproduce.

Regenerate with ``analysis/make_elements.py``; the generated file is the one in
core.
"""

from __future__ import annotations

from chisurf.core.fio.structure.elements import (  # noqa: F401
    ATOMIC_MASS,
    DEFAULT_VDW_RADIUS,
    VDW_RADIUS,
    mass_of,
    masses_for,
    radii_for,
    radius_of,
)

__all__ = [
    "ATOMIC_MASS",
    "VDW_RADIUS",
    "DEFAULT_VDW_RADIUS",
    "mass_of",
    "masses_for",
    "radii_for",
    "radius_of",
]
