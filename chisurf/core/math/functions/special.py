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

    Moved to IMP.bff (`SpecialFunctions.h`); this is a thin forwarder. The
    C++ carries the same nine coefficients, **including** the transposed digit
    in the first one (3.5156299, where Abramowitz & Stegun print 3.5156229) --
    reproduced deliberately so the port cannot move a fitted distribution. See
    the note in `src/SpecialFunctions.cpp`.
    """
    from IMP.bff import i0 as _i0, i0_array as _i0_array
    if np.isscalar(x) or np.ndim(x) == 0:
        return float(_i0(float(x)))
    return _i0_array(np.asarray(x, dtype=float))


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

    Moved to IMP.bff; a thin forwarder, and identical to what :func:`i0`
    dispatches to for array input -- the two were separate copies of the same
    polynomial until 2026-09-02.
    """
    from IMP.bff import i0_array as _f
    return _f(np.asarray(x, dtype=float))
