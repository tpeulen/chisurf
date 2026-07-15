"""Maximum-likelihood fluorescence-lifetime estimation harness.

This package is the single ChiSurf seam around tttrlib's ``fit2x`` Poisson
maximum-likelihood estimators (``Fit23``/``Fit24``/``Fit25``).  See
:mod:`chisurf.core.fluorescence.mle.fit2x` for details.
"""

from __future__ import annotations

from .fit2x import (
    HAVE_TTTRLIB,
    PARAMETER_NAMES,
    Fit2x,
    Fit2xModel,
    Fit2xResult,
    Fit2xSettings,
    assemble_jordi,
)

__all__ = [
    "HAVE_TTTRLIB",
    "Fit2x",
    "Fit2xModel",
    "Fit2xResult",
    "Fit2xSettings",
    "PARAMETER_NAMES",
    "assemble_jordi",
]
