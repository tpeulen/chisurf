from __future__ import annotations


import numpy as np


def i0(x):
    """Modified Bessel function I0(x) for any real x, elementwise.

    Parameters
    ----------
    x : float or numpy.ndarray
        Argument(s). Scalars and arrays are both accepted; the result has the
        shape of the input.

    Returns
    -------
    float or numpy.ndarray
        I0 evaluated at *x*.

    Notes
    -----
    This is the Abramowitz & Stegun polynomial approximation (Numerical
    Recipes' ``bessi0``), **not** the exact Bessel function.
    :func:`scipy.special.i0` is not a drop-in replacement: it is correct to
    machine precision where this is correct to about 1e-7, so swapping it in
    would move every fitted worm-like-chain distribution by more than the
    optimiser's tolerance. The approximation is kept deliberately.

    Both branches of the piecewise formula are evaluated and selected with
    :func:`numpy.where`, so the unused branch is fed a substituted argument
    (3.75) rather than the real one -- otherwise the small-|x| elements would
    divide by zero on their way into the large-|x| expression.

    References
    ----------

    .. [1] Abramowitz, M and Stegun, I.A. 1964, Handbook of Mathematical
       Functions, Applied Mathematics Series, Volume 55 (Washington:
       National Bureal of Standards; reprinted 1968 by Dover Publications,
       New York), Chapter 10
    """
    ax = np.abs(x)
    small = ax < 3.75

    y = np.where(small, ax / 3.75, 0.0) ** 2
    below = 1.0 + y * (3.5156299 + y * (
        3.0899424 + y * (1.2067492 + y * (
            0.2659732 + y * (0.360768e-1 + y *
                             0.45813e-2)))))

    ax_safe = np.where(small, 3.75, ax)
    y = 3.75 / ax_safe
    above = (np.exp(ax_safe) / np.sqrt(ax_safe)) * \
        (0.39894228 + y * (0.1328592e-1 + y * (
            0.225319e-2 + y * (-0.157565e-2 + y * (
                0.916281e-2 + y * (-0.2057706e-1 + y * (
                    0.2635537e-1 + y * (-0.1647633e-1 + y *
                                        0.392377e-2))))))))

    result = np.where(small, below, above)
    return float(result) if np.isscalar(x) or np.ndim(x) == 0 else result


def i0_array(x: np.ndarray) -> np.ndarray:
    """Modified Bessel function I0 over an array.

    Parameters
    ----------
    x : numpy.ndarray
        Arguments.

    Returns
    -------
    numpy.ndarray
        I0 evaluated elementwise.

    Notes
    -----
    Retained as an alias: :func:`i0` handles arrays directly now, and this
    existed only because the scalar version could not. It had no callers.
    """
    return np.asarray(i0(np.asarray(x, dtype=float)))
