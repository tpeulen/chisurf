from __future__ import annotations

import numpy as np
from numba import njit
from scipy.signal import fftconvolve
from scipy.stats import poisson


@njit(fastmath=True)
def compute_p1(k_vals, brightness, x_vals, dx):
    r"""Single-molecule photon-count distribution of a 3-D Gaussian volume.

    Evaluates :math:`p^{(1)}(k) \propto \int (\varepsilon\,\mathrm{PSF})^k / k!\,
    e^{-\varepsilon\,\mathrm{PSF}}\, \mathrm{d}V` for the 3-D Gaussian
    :math:`\mathrm{PSF}(x) = e^{-2x^2}`, with ``x = r / w`` the radial distance in
    units of the beam waist.  The volume element of the spherically symmetric
    profile is :math:`\mathrm{d}V = 4\pi w^3 x^2\,\mathrm{d}x`, so the integrand
    carries the shell weight ``x**2``; without it the sum would describe a *1-D*
    Gaussian volume and the recovered brightness would be far too small (the
    second-order shape factor would come out as :math:`2^{-1/2}` instead of the
    3-D Gaussian's :math:`\gamma_2 = 2^{-3/2}`).

    ``p1[0]`` is set to the complement of the ``k >= 1`` terms, which absorbs the
    constant :math:`4\pi w^3 / V_0` prefactor into the definition of the reference
    volume; the fitted mean occupancy ``avgN`` is therefore expressed in that
    reference volume, while the brightness is convention-free.

    Parameters
    ----------
    k_vals : numpy.ndarray
        Photon-count axis ``0, 1, ... k_max`` (float, monotonically increasing).
    brightness : float
        Molecular brightness :math:`\varepsilon` (counts per molecule per bin) at
        the centre of the detection volume.
    x_vals : numpy.ndarray
        Radial quadrature grid in units of the beam waist.
    dx : float
        Spacing of ``x_vals`` (Riemann weight of the radial quadrature).

    Returns
    -------
    numpy.ndarray
        ``p1[k]`` for every ``k`` in ``k_vals``, summing to 1.
    """
    n = k_vals.shape[0]
    p1 = np.zeros(n, np.float64)
    for i in range(1, n):
        k = int(k_vals[i])
        fact = 1.0
        for j in range(1, k + 1):
            fact *= j
        total = 0.0
        for xi in x_vals:
            exp_term = np.exp(-2.0 * xi * xi)
            shell = xi * xi  # dV = 4 pi w^3 x^2 dx
            total += shell * (brightness * exp_term) ** k / fact * np.exp(-brightness * exp_term)
        p1[i] = total * dx
    p1[0] = 1.0 - p1[1:].sum()
    return p1


def pch_single_species(k_vals, brightness):
    r"""``p1(k)`` of one molecule in a 3-D Gaussian volume on the default grid.

    Parameters
    ----------
    k_vals : numpy.ndarray
        Photon-count axis.
    brightness : float
        Molecular brightness :math:`\varepsilon` (counts per molecule per bin).

    Returns
    -------
    numpy.ndarray
        :func:`compute_p1` on ``x in [0, 5]`` (1000 points) — the profile has
        decayed to ``e^{-50}`` there, so the truncation is irrelevant.
    """
    x_vals = np.linspace(0, 5, 1000)
    dx = x_vals[1] - x_vals[0]
    return compute_p1(k_vals, brightness, x_vals, dx)


@njit(fastmath=True)
def convolve_pch_numba(p1, N, length):
    """``N``-fold self-convolution of a single-molecule distribution.

    Parameters
    ----------
    p1 : numpy.ndarray
        Single-molecule distribution ``p1(k)``.
    N : int
        Number of independent molecules in the volume (``0`` gives a delta at
        ``k = 0``).
    length : int
        Length of the photon-count axis; the convolution is truncated to it.

    Returns
    -------
    numpy.ndarray
        Photon-count distribution of exactly ``N`` molecules.
    """
    pk = np.zeros(length, np.float64)
    if N == 0:
        pk[0] = 1.0
        return pk
    temp = p1.copy()
    for _ in range(1, N):
        out = np.zeros(length, np.float64)
        for i in range(length):
            for j in range(length - i):
                out[i + j] += temp[i] * p1[j]
        temp = out
    return temp


def pch_open_system(k_vals, brightness, avgN, maxN=30):
    r"""PCH of one species in an open volume (Poisson-distributed occupancy).

    Parameters
    ----------
    k_vals : numpy.ndarray
        Photon-count axis.
    brightness : float
        Molecular brightness :math:`\varepsilon` (counts per molecule per bin).
    avgN : float
        Mean number of molecules in the reference volume.
    maxN : int
        Largest occupancy kept in the Poisson sum.

    Returns
    -------
    numpy.ndarray
        ``P(k)``, the photon-counting histogram of the species.
    """
    p1 = pch_single_species(k_vals, brightness)
    length = k_vals.shape[0]
    pk_tot = np.zeros(length)
    for N in range(maxN + 1):
        pk_tot += poisson.pmf(N, avgN) * convolve_pch_numba(p1, N, length)
    return pk_tot


def pch_mixture(k_vals, epsilons, avgNs):
    """PCH of a mixture of independent species (convolution of their PCHs).

    Parameters
    ----------
    k_vals : numpy.ndarray
        Photon-count axis.
    epsilons : sequence of float
        Molecular brightness per species.
    avgNs : sequence of float
        Mean occupancy per species, in the same order as ``epsilons``.

    Returns
    -------
    numpy.ndarray
        ``P(k)`` of the mixture.
    """
    pk = np.zeros_like(k_vals, dtype=float)
    pk[0] = 1.0
    for eps, n in zip(epsilons, avgNs, strict=True):
        pj = pch_open_system(k_vals, eps, n)
        pk = fftconvolve(pk, pj)[:len(k_vals)]
    return pk
