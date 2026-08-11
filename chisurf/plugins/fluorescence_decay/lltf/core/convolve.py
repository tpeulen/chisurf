"""TCSPC convolution for the lifetime-fitting tool.

This module used to carry its own copy of the convolution kernels -- four numba
functions that were, docstrings aside, character-for-character the ones in
:mod:`chisurf.core.fluorescence.tcspc.convolve`. Keeping a private copy of the
forward model is how a plugin quietly drifts from the application it belongs to,
and it had: the copy's ``convolve_lifetime_spectrum`` called the **numba**
kernel where the shared one calls the photon library's compiled SIMD path, so
this tool paid a JIT compile on first evaluation and ran the slower kernel
afterwards. The copies also carried a defect that has since been fixed in the
shared version -- the periodic kernel never gave the final channel its
inter-pulse tail.

So there is nothing here but the shared implementation, re-exported under the
names this plugin already imports.
"""

from __future__ import annotations

from chisurf.core.fluorescence.tcspc.convolve import (  # noqa: F401
    convolve_decay,
    convolve_lifetime_spectrum,
    convolve_lifetime_spectrum_periodic,
    periodic_shift,
)
from chisurf.core.fluorescence.tcspc.corrections import (  # noqa: F401
    add_pile_up_to_model,
)

__all__ = [
    "add_pile_up_to_model",
    "convolve_decay",
    "convolve_lifetime_spectrum",
    "convolve_lifetime_spectrum_periodic",
    "periodic_shift",
]
