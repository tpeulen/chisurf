"""Higher-order intensity correlation.

The multi-tau photon correlator that used to live here -- a numba
implementation of Schaetzel's cascade, plus its normalization, count-rate
filter and stream-coarsening helpers -- has been removed. ``tttrlib`` does
photon correlation, and keeping a second implementation meant two answers to
the same question, only one of which was exercised.
"""

from __future__ import annotations

import numpy as np


def second_order_correlation(
    trace: np.ndarray,
    tau1: np.ndarray,
    tau2: np.ndarray,
    trace2: np.ndarray | None = None,
    trace3: np.ndarray | None = None,
) -> np.ndarray:
    r"""Three-point (second-order) intensity correlation :math:`g^{(3)}`.

    The second-order correlation used in ns-FCS to resolve higher-order
    dynamics/antibunching beyond the ordinary pair correlation (port of the
    Fretica ``FnsFCSSecondOrder`` observable), evaluated on binned intensity
    traces:

    .. math::

        g^{(3)}(\tau_1, \tau_2) =
        \frac{\langle I(t)\,I(t+\tau_1)\,I(t+\tau_1+\tau_2)\rangle}
             {\langle I\rangle\,\langle I'\rangle\,\langle I''\rangle},

    which is ``1`` for an uncorrelated (Poisson) stream and departs from ``1``
    where three-photon correlations are present.

    Parameters
    ----------
    trace : numpy.ndarray
        Binned intensity trace :math:`I(t)` (the first correlation channel).
    tau1, tau2 : numpy.ndarray
        Integer lag grids (in bins) for the two time separations.
    trace2, trace3 : numpy.ndarray, optional
        Second/third channel traces for a cross-``g^{(3)}`` (default: reuse
        ``trace`` for an auto-correlation).  Must match ``trace`` in length.

    Returns
    -------
    numpy.ndarray
        The ``(len(tau1), len(tau2))`` matrix :math:`g^{(3)}(\tau_1, \tau_2)`.
    """
    i1 = np.asarray(trace, dtype=float)
    i2 = i1 if trace2 is None else np.asarray(trace2, dtype=float)
    i3 = i1 if trace3 is None else np.asarray(trace3, dtype=float)
    n = i1.size
    if i2.size != n or i3.size != n:
        raise ValueError("all traces must have the same length")

    m1, m2, m3 = i1.mean(), i2.mean(), i3.mean()
    denom = m1 * m2 * m3
    tau1 = np.asarray(tau1, dtype=int)
    tau2 = np.asarray(tau2, dtype=int)
    g3 = np.full((tau1.size, tau2.size), np.nan)
    if denom <= 0:
        return g3

    for a, t1 in enumerate(tau1):
        for b, t2 in enumerate(tau2):
            shift = int(t1) + int(t2)
            m = n - shift
            if m <= 0:
                continue
            prod = i1[:m] * i2[t1 : t1 + m] * i3[shift : shift + m]
            g3[a, b] = prod.mean() / denom
    return g3
