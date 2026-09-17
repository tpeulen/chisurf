"""The shot-noise (static) line Burst Variance Analysis is read against.

BVA itself -- slicing each burst and reducing its slices to a proximity-ratio
mean and standard deviation -- is :class:`tttrlib.BVA`, driven from
:mod:`chisurf.plugins.burst.burst_bva.core.computation`, which batches one
engine call per measurement over the whole burst table. What is left here is
the reference curve those per-burst points are plotted against.
"""

import numpy as np
import tttrlib

__all__ = ["compute_static_bva_line"]


def compute_static_bva_line(
    prox_mean_bins: np.ndarray,  # Proximity ratio bins
    number_of_photons_per_slice: int = 4,
    n_samples: int = 10_000,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the shot-noise-limited (static) BVA line.

    A static species observed with ``n`` photons per slice has slice proximity
    ratio ``Binomial(n, p) / n``, so its mean is ``p`` and its standard
    deviation is exactly ``sqrt(p (1 - p) / n)``. The line is a closed form and
    is evaluated as one by :meth:`tttrlib.BVA.compute_static_bva_line` -- the
    same engine that produces the per-burst values the line is drawn against, so
    the curve and the points cannot disagree about what "static" means.

    Parameters
    ----------
    prox_mean_bins : np.ndarray
        Proximity-ratio values ``p`` at which to evaluate the line.
    number_of_photons_per_slice : int, optional
        The number of photons per slice, ``n``. Default is 4.
    n_samples : int, optional
        Ignored, and accepted only so existing callers keep working. It was the
        Monte-Carlo sample count of the sampled implementation this replaced;
        a closed form has no sampling error to trade against it.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        A tuple containing two arrays:

        - ``prox_mean``: mean proximity ratio for each bin.
        - ``prox_sd``: standard deviation of the proximity ratio for each bin.

    Notes
    -----
    A non-positive ``number_of_photons_per_slice`` carries no information about
    the proximity ratio; zeros are returned for both arrays rather than dividing
    by zero. The engine evaluates the line at ``n = 1`` in that case instead, so
    the guard stays on this side.

    The sampled implementation this replaced drew ``n_samples`` binomial
    variates per bin from the *global* NumPy random state, so the plotted floor
    moved from run to run and depended on whatever had last seeded that state.
    At its default 10,000 samples it sat ~3e-3 from the exact line -- the same
    order as the excess standard deviation BVA exists to detect.
    """
    prox_mean_bins = np.asarray(prox_mean_bins, dtype=float)
    if number_of_photons_per_slice <= 0:
        zeros = np.zeros(len(prox_mean_bins))
        return zeros, zeros.copy()

    mean, sd = tttrlib.BVA.compute_static_bva_line(prox_mean_bins, int(number_of_photons_per_slice))
    return np.asarray(mean, dtype=float), np.asarray(sd, dtype=float)
