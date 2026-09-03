#leastsqbound = skf.math.optimize.leastsqbound.leastsqbound
from chisurf.core.math.optimization.leastsqbound import (
    OptimizationCancelled,
    leastsqbound,
)

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
