"""Optimisation support shared by the fitting stack.

The bounded Levenberg-Marquardt itself is IMP.bff's ``FitMinimizer``, reached
through :mod:`chisurf.core.fitting.minimizer`; scipy-shaped solvers are in
:mod:`chisurf.core.math.numerics`. What is left here is the exception a
progress callback raises to stop a fit.

``leastsqbound`` (scipy's MINPACK ``_lmdif`` behind the MINUIT bounds
transform) used to live in this package. It had no caller after the fitter
moved onto bff on 2026-09-01 and was removed on 2026-10-06 with the rest of
chisurf's private scipy imports.
"""


class OptimizationCancelled(Exception):
    """Signal that an optimisation was cancelled by the caller.

    Raised from a user-provided ``progress_callback`` (for example when a GUI
    progress dialog's Cancel button is pressed). The minimiser propagates it
    to the caller instead of swallowing it together with other callback
    errors.
    """

# ``nnls.solve_nnls`` (an amplitude-Tikhonov wrapper around
# ``scipy.optimize.nnls``, on the *normal* equations rather than the augmented
# system) used to live here. Removed 2026-09-02: zero callers anywhere in the
# tree, and it was a third spelling of a regularisation weight on top of the
# two real ones -- non-negative regularised inversion now has exactly one
# surface, :mod:`chisurf.core.fitting.inversion`.

# ``solve_richardson_lucy`` (a generic matrix-operator Richardson-Lucy) used to
# live here, wrapping an identically-named function in
# :mod:`chisurf.core.math.linalg`. Removed 2026-09-02: zero callers
# anywhere in the tree (only the two duplicates called each other), and it was
# not a drop-in for the engine anyway -- ``tttrlib.richardson_lucy_2d/3d``
# assume a translation-invariant image/PSF pair, not an arbitrary dense
# operator matrix, so there was no faithful forward to make. Image
# deconvolution's one implementation is
# :func:`chisurf.core.fluorescence.imaging.restoration.richardson_lucy`,
# already tttrlib-backed and covered by ``test/core/test_restoration.py``.
