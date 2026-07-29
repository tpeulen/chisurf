"""Maximum-likelihood fluorescence-lifetime estimation harness.

This package is the single ChiSurf seam around tttrlib's ``fit2x`` Poisson
maximum-likelihood estimators (``Fit23``/``Fit24``/``Fit25``).  See
:mod:`chisurf.core.fluorescence.mle.fit2x` for details.
"""

from __future__ import annotations

from .fit2x import (
    HAVE_TTTRLIB,
    parameter_names_of,
    Fit2x,
    Fit2xModel,
    Fit2xResult,
    Fit2xSettings,
    assemble_vv_vh,
)
from .irf import interpolate_shift
from .setup import DetectorSetup, parse_detector_setup

__all__ = [
    "HAVE_TTTRLIB",
    "Fit2x",
    "Fit2xModel",
    "Fit2xResult",
    "Fit2xSettings",
    "parameter_names_of",
    "assemble_vv_vh",
    "DetectorSetup",
    "parse_detector_setup",
    "interpolate_shift",
]
