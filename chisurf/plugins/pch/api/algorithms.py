"""PCH distributions, re-exported from the one implementation in ``core``.

This module used to be a second, numba-compiled copy of
:mod:`chisurf.core.models.pch.pch`, which had already delegated to tttrlib's
C++ engine. Two implementations of the same integral is exactly the
arrangement where the conventions drift apart -- and for PCH a drift in the
``p1[0]`` normalisation changes what the fitted occupancy *means* rather than
what it equals, so nothing that compares amplitudes would catch it. There is
now one implementation; this is the plugin's name for it.
"""

from __future__ import annotations

from chisurf.core.models.pch.pch import (
    compute_p1,
    pch_mixture,
    pch_open_system,
    pch_single_species,
)

__all__ = [
    "compute_p1",
    "pch_mixture",
    "pch_open_system",
    "pch_single_species",
]
