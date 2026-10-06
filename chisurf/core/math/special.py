"""Special functions, distributions and matrix functions, without scipy.

The functions ChiSurf used to take from ``scipy.special``, ``scipy.stats`` and
``scipy.linalg``, under the same names and argument orders so a call site
changes its import and nothing else. The arithmetic is IMP.bff's
(``IMP/bff/Numerics.h``), and bff computes it with **the code scipy runs**:
the special functions are scipy's own ``xsf`` library, the distributions
scipy hands to Boost.Math use Boost.Math under scipy's policies. So the
numbers are scipy's to the bit for the special functions and to round-off
for the Boost-backed distributions -- see ``imp.bff/test/numerics/
test_special_functions.py``, which holds bff to that against scipy.

What lives here rather than in bff: broadcasting and reshaping (bff takes
flat float64 arrays of equal length), and the few entries that are numpy
arithmetic over those -- ``logsumexp``, ``xlogy``, ``polygamma``,
``poisson.logpmf``, ``pinvh`` -- written as scipy writes them.

Differences from scipy, all deliberate: no ``out=``/``where=`` ufunc keywords,
no warnings on domain errors (a NaN is returned, as scipy returns), and the
distribution objects carry only the methods ChiSurf calls.
"""

from __future__ import annotations

import math

import numpy as np

__all__ = [
    "LinAlgError",
    "beta",
    "betainc",
    "betaincinv",
    "binom",
    "chdtrc",
    "chdtri",
    "chi2",
    "digamma",
    "erf",
    "erfc",
    "expm",
    "f",
    "fdtr",
    "fdtrc",
    "fdtri",
    "fresnel",
    "gamma",
    "gammainc",
    "gammaincc",
    "gammaln",
    "i0e",
    "j0",
    "j1",
    "logsumexp",
    "ncx2",
    "ndtr",
    "norm",
    "pinvh",
    "poisson",
    "polygamma",
    "psi",
    "rankdata",
    "stdtr",
    "t",
    "xlogy",
    "zeta",
]

LinAlgError = np.linalg.LinAlgError

#: The elementwise functions here, by name: what a user-written model
#: expression may call as ``scipy.special.<name>`` (``ParseModel``).
ELEMENTWISE = (
    "betainc",
    "betaincinv",
    "chdtrc",
    "chdtri",
    "digamma",
    "erf",
    "erfc",
    "fdtr",
    "fdtrc",
    "fdtri",
    "gamma",
    "gammainc",
    "gammaincc",
    "gammaln",
    "i0e",
    "j0",
    "j1",
    "ndtr",
    "polygamma",
    "psi",
    "stdtr",
    "xlogy",
    "zeta",
)


def _bff():
    # Imported on first use: IMP.bff costs ~0.3 s at import, and the modules
    # that call into here are reached from start-up paths that never evaluate.
    from IMP import bff

    return bff


def _flat(value) -> np.ndarray:
    return np.ascontiguousarray(value, dtype=np.float64).ravel()


def _result(out: np.ndarray, shape: tuple, scalar: bool):
    out = np.asarray(out).reshape(shape)
    return float(out) if scalar else out


def _elementwise(name: str, *args):
    """Broadcast ``args``, hand bff flat arrays, give back the broadcast shape."""
    arrays = [np.asarray(a, dtype=np.float64) for a in args]
    scalar = all(a.ndim == 0 for a in arrays)
    arrays = np.broadcast_arrays(*arrays)
    shape = arrays[0].shape
    out = getattr(_bff(), f"{name}_array")(*[_flat(a) for a in arrays])
    return _result(out, shape, scalar)


# --- scipy.special ---------------------------------------------------------


def gammaln(x):
    """``scipy.special.gammaln``: :math:`\\ln|\\Gamma(x)|`."""
    return _elementwise("gammaln", x)


def erf(x):
    """``scipy.special.erf``."""
    return _elementwise("erf", x)


def erfc(x):
    """``scipy.special.erfc``."""
    return _elementwise("erfc", x)


def digamma(x):
    """``scipy.special.digamma`` (alias ``psi``)."""
    return _elementwise("digamma", x)


psi = digamma


def i0e(x):
    """``scipy.special.i0e``: :math:`e^{-|x|} I_0(x)`."""
    return _elementwise("i0e", x)


def j0(x):
    """``scipy.special.j0``."""
    return _elementwise("j0", x)


def j1(x):
    """``scipy.special.j1``."""
    return _elementwise("j1", x)


def ndtr(x):
    """``scipy.special.ndtr``: the standard normal CDF."""
    return _elementwise("ndtr", x)


def gammainc(a, x):
    """``scipy.special.gammainc``: regularised lower incomplete gamma."""
    return _elementwise("gammainc", a, x)


def gammaincc(a, x):
    """``scipy.special.gammaincc``: regularised upper incomplete gamma."""
    return _elementwise("gammaincc", a, x)


def zeta(s, q):
    """``scipy.special.zeta(s, q)``: the Hurwitz zeta function."""
    return _elementwise("zeta", s, q)


def gamma(x):
    """:math:`\\Gamma(x)` (``math.gamma``, exact for small integers)."""
    x = np.asarray(x, dtype=np.float64)
    out = np.vectorize(math.gamma, otypes=[np.float64])(x) if x.size else x.copy()
    return float(out) if x.ndim == 0 else out


def polygamma(n, x):
    """``scipy.special.polygamma``, built as scipy builds it.

    :math:`\\psi^{(n)}(x) = (-1)^{n+1}\\, n!\\, \\zeta(n+1, x)`, and the
    digamma function for ``n == 0``.
    """
    n, x = np.broadcast_arrays(np.asarray(n, dtype=np.float64), np.asarray(x, dtype=np.float64))
    scalar = n.ndim == 0
    fac2 = (-1.0) ** (n + 1) * gamma(n + 1.0) * zeta(n + 1, x)
    out = np.where(n == 0, digamma(x), fac2)
    return float(out) if scalar else out


def fresnel(x):
    """``scipy.special.fresnel``: returns ``(S, C)``."""
    arr = np.asarray(x, dtype=np.float64)
    s, c = _bff().fresnel_array(_flat(arr))
    return _result(s, arr.shape, arr.ndim == 0), _result(c, arr.shape, arr.ndim == 0)


def betainc(a, b, x):
    """``scipy.special.betainc``: regularised incomplete beta :math:`I_x(a, b)`."""
    return _elementwise("betainc", a, b, x)


def betaincinv(a, b, y):
    """``scipy.special.betaincinv``."""
    return _elementwise("betaincinv", a, b, y)


def fdtr(dfn, dfd, x):
    """``scipy.special.fdtr``."""
    return _elementwise("fdtr", dfn, dfd, x)


def fdtrc(dfn, dfd, x):
    """``scipy.special.fdtrc``."""
    return _elementwise("fdtrc", dfn, dfd, x)


def fdtri(dfn, dfd, p):
    """``scipy.special.fdtri``."""
    return _elementwise("fdtri", dfn, dfd, p)


def chdtrc(df, x):
    """``scipy.special.chdtrc``."""
    return _elementwise("chdtrc", df, x)


def chdtri(df, y):
    """``scipy.special.chdtri``."""
    return _elementwise("chdtri", df, y)


def stdtr(df, t):
    """``scipy.special.stdtr``: Student's t CDF."""
    return _elementwise("stdtr", df, t)


def xlogy(x, y):
    """``scipy.special.xlogy``: :math:`x \\log y`, and 0 where ``x == 0``."""
    x, y = np.broadcast_arrays(np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64))
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where((x == 0) & ~np.isnan(y), 0.0, x * np.log(y))
    return float(out) if out.ndim == 0 else out


def logsumexp(a, axis=None, b=None, keepdims: bool = False, return_sign: bool = False):
    """``scipy.special.logsumexp``, by scipy's algorithm.

    Shift by the largest finite element, sum, take the log, shift back --
    and keep the ``-inf`` of an all-zero-weight slice instead of a NaN.
    """
    a = np.asarray(a, dtype=np.float64)
    if b is not None:
        a, b = np.broadcast_arrays(a, np.asarray(b, dtype=np.float64))
        if np.any(b == 0):
            a = a + 0.0  # writable copy
            a[b == 0] = -np.inf
    with np.errstate(invalid="ignore"):
        a_max = np.amax(a, axis=axis, keepdims=True)
    if a_max.ndim > 0:
        a_max[~np.isfinite(a_max)] = 0.0
    elif not np.isfinite(a_max):
        a_max = 0.0
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        tmp = np.exp(a - a_max)
        if b is not None:
            tmp = b * tmp
        s = np.sum(tmp, axis=axis, keepdims=keepdims)
        if return_sign:
            sgn = np.sign(s)
            s = np.abs(s)
        out = np.log(s)
    if not keepdims:
        a_max = np.squeeze(a_max, axis=axis)
    out = out + a_max
    if return_sign:
        return out, sgn
    return out


# --- scipy.stats ------------------------------------------------------------


def rankdata(a) -> np.ndarray:
    """``scipy.stats.rankdata(a)`` (method ``"average"``), by scipy's algorithm.

    Ranks start at 1; tied values share the mean of the ranks they span.
    The input is flattened, as scipy flattens it without ``axis``.
    """
    arr = np.ravel(np.asarray(a))
    sorter = np.argsort(arr, kind="mergesort")
    inv = np.empty(sorter.size, dtype=np.intp)
    inv[sorter] = np.arange(sorter.size, dtype=np.intp)
    arr = arr[sorter]
    obs = np.r_[True, arr[1:] != arr[:-1]]
    dense = obs.cumsum()[inv]
    count = np.r_[np.nonzero(obs)[0], len(obs)]
    return 0.5 * (count[dense] + count[dense - 1] + 1)



class _Norm:
    """``scipy.stats.norm``: ``pdf``, ``cdf``, ``sf`` with ``loc``/``scale``."""

    @staticmethod
    def pdf(x, loc=0.0, scale=1.0):
        z = (np.asarray(x, dtype=np.float64) - loc) / scale
        return np.exp(-(z**2) / 2.0) / np.sqrt(2.0 * np.pi) / scale

    @staticmethod
    def cdf(x, loc=0.0, scale=1.0):
        return ndtr((np.asarray(x, dtype=np.float64) - loc) / scale)

    @staticmethod
    def sf(x, loc=0.0, scale=1.0):
        return ndtr(-(np.asarray(x, dtype=np.float64) - loc) / scale)


class _Beta:
    """``scipy.stats.beta``: ``cdf``, ``sf``, ``ppf``."""

    @staticmethod
    def cdf(x, a, b):
        return betainc(a, b, x)

    @staticmethod
    def sf(x, a, b):
        return 1.0 - betainc(a, b, x)

    @staticmethod
    def ppf(q, a, b):
        return betaincinv(a, b, q)


class _F:
    """``scipy.stats.f``: ``cdf``, ``sf``, ``ppf``, ``isf``."""

    @staticmethod
    def cdf(x, dfn, dfd):
        return fdtr(dfn, dfd, x)

    @staticmethod
    def sf(x, dfn, dfd):
        return fdtrc(dfn, dfd, x)

    @staticmethod
    def ppf(q, dfn, dfd):
        return fdtri(dfn, dfd, q)

    @staticmethod
    def isf(q, dfn, dfd):
        # scipy's generic rv_continuous._isf: the ppf of the complement.
        return fdtri(dfn, dfd, 1.0 - np.asarray(q, dtype=np.float64))


class _Chi2:
    """``scipy.stats.chi2``: ``sf``, ``isf``."""

    @staticmethod
    def sf(x, df):
        return chdtrc(df, x)

    @staticmethod
    def isf(q, df):
        return chdtri(df, q)


class _T:
    """``scipy.stats.t``: ``cdf``, ``sf``."""

    @staticmethod
    def cdf(x, df):
        return stdtr(df, x)

    @staticmethod
    def sf(x, df):
        return stdtr(df, -np.asarray(x, dtype=np.float64))


class _Binom:
    """``scipy.stats.binom``: ``pmf``."""

    @staticmethod
    def pmf(k, n, p):
        return _elementwise("binom_pmf", k, n, p)


class _Poisson:
    """``scipy.stats.poisson``: ``logpmf``, ``pmf``.

    scipy's ``_logpmf``, :math:`k \\log\\mu - \\ln\\Gamma(k+1) - \\mu`, with the
    generic wrapper's ``-inf`` outside the support (negative or non-integer k).
    """

    @staticmethod
    def logpmf(k, mu):
        k, mu = np.broadcast_arrays(np.asarray(k, dtype=np.float64), np.asarray(mu, dtype=np.float64))
        out = np.asarray(xlogy(k, mu) - gammaln(k + 1.0) - mu, dtype=np.float64)
        outside = (k < 0) | (k != np.floor(k))
        if np.any(outside):
            out = np.where(outside, -np.inf, out)
        return float(out) if out.ndim == 0 else out

    @classmethod
    def pmf(cls, k, mu):
        return np.exp(cls.logpmf(k, mu))


class _Ncx2:
    """``scipy.stats.ncx2``: ``pdf``."""

    @staticmethod
    def pdf(x, df, nc):
        return _elementwise("ncx2_pdf", x, df, nc)


norm = _Norm()
beta = _Beta()
f = _F()
chi2 = _Chi2()
t = _T()
binom = _Binom()
poisson = _Poisson()
ncx2 = _Ncx2()


# --- scipy.linalg ------------------------------------------------------------


def expm(a) -> np.ndarray:
    """``scipy.linalg.expm`` for a square real matrix (Padé scaling and squaring)."""
    a = np.asarray(a, dtype=np.float64)
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise ValueError("expm expects a square matrix")
    return np.asarray(_bff().expm(np.ascontiguousarray(a)))


def pinvh(a, atol=None, rtol=None, lower: bool = True, return_rank: bool = False):
    """``scipy.linalg.pinvh``: pseudo-inverse of a Hermitian matrix, scipy's way.

    Eigen-decompose, drop eigenvalues with ``|s| <= atol + rtol * max|s|``
    (``rtol`` defaults to ``max(M, N) * eps`` when neither tolerance is given),
    invert the rest.
    """
    a = np.asarray(a, dtype=np.float64)
    s, u = np.linalg.eigh(a, UPLO="L" if lower else "U")
    t = np.finfo(s.dtype).eps
    maxs = np.max(np.abs(s)) if s.size else 0.0
    atol = 0.0 if atol is None else float(atol)
    rtol = max(a.shape) * t if (rtol is None) else float(rtol)
    if atol < 0.0 or rtol < 0.0:
        raise ValueError("atol and rtol values must be positive.")
    val = atol + maxs * rtol
    above = np.abs(s) > val
    psigma_diag = 1.0 / s[above]
    u = u[:, above]
    b = (u * psigma_diag) @ u.conj().T
    if return_rank:
        return b, int(np.count_nonzero(above))
    return b
