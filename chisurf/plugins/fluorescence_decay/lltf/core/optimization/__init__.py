"""Optimisation for lifetime fitting -- ChiSurf's, which is bff's.

This package used to carry a **third** copy of the bounded
Levenberg-Marquardt in this stack: 365 lines of `leastsqbound.py`, reached
from `lltf/core/fitter.py`. It was deleted on 2026-09-01. There is one
implementation of MINPACK's `lmdif` here and it is `IMP::bff::Minimizer`;
`chisurf.core.fitting.minimizer.minimize` is how anything reaches it,
including a plain Python objective like this plugin's.
"""

from chisurf.core.fitting.minimizer import minimize

__all__ = ["minimize"]
