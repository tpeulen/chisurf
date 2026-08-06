"""Photon-counting-histogram distributions for a mixture of species.

The PCH of an open system: the probability of detecting *k* photons in a bin, for
one species of a given molecular brightness and mean occupancy, and for a mixture
of such species by convolution.

These were defined inside the Qt model-widget module, so the histogram a PCH fit
computes could not be evaluated -- or checked against a reference -- without
importing the GUI. They are plain numpy.
"""

from __future__ import annotations

import math

import numpy as np


def compute_p1(k_vals: np.ndarray, brightness: float, x_vals: np.ndarray, dx: float) -> np.ndarray:
    """Compute the PCH distribution P(k) for a single species.

    The detection volume is the 3-D Gaussian ``PSF(x) = exp(-2 x**2)``, whose
    volume element ``dV = 4 pi w**3 x**2 dx`` contributes the radial shell weight
    ``x**2``; dropping it would collapse the integral onto a *1-D* Gaussian and
    bias the recovered brightness low (see
    :func:`chisurf.plugins.pch.api.algorithms.compute_p1`).

    The Poisson term is evaluated in log space, ``exp(k ln(lam) - lgamma(k+1) -
    lam)``, because ``lam**k / k!`` overflows a ``double`` on both ends: ``k!``
    passes ``DBL_MAX`` at ``k = 171`` (so ``p1[k]`` would be exactly zero above
    it at any brightness) and the numerator overflows a little further out,
    where ``inf/inf`` gives ``NaN``.

    Parameters
    ----------
    k_vals : numpy.ndarray
        Photon count values k to evaluate.
    brightness : float
        Molecular brightness.
    x_vals : numpy.ndarray
        Radial integration points, in units of the beam waist.
    dx : float
        Spatial step size.

    Returns
    -------
    numpy.ndarray
        Probability distribution P(k) for the given k values.
    """
    n = k_vals.shape[0]
    p1 = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        k = int(k_vals[i])
        if k <= 0:
            continue
        log_fact = math.lgamma(k + 1.0)
        total = 0.0
        for xi in x_vals:
            lam = brightness * np.exp(-2.0 * xi * xi)
            if lam <= 0.0:
                continue
            total += xi * xi * np.exp(k * np.log(lam) - log_fact - lam)
        p1[i] = total * dx
    s = p1[1:].sum()
    p1[0] = max(0.0, 1.0 - s)
    return p1


def pch_single_species(k_vals: np.ndarray, brightness: float) -> np.ndarray:
    """Compute the PCH distribution for a single species with standard spatial grid.

    Parameters
    ----------
    k_vals : numpy.ndarray
        Photon count values k to evaluate.
    brightness : float
        Molecular brightness.

    Returns
    -------
    numpy.ndarray
        Probability distribution P(k).
    """
    x_vals = np.linspace(0.0, 5.0, 1000)
    dx = x_vals[1] - x_vals[0]
    return compute_p1(k_vals, float(brightness), x_vals, float(dx))


def pch_open_system(k_vals: np.ndarray, brightness: float, avgN: float, maxN: int = 30) -> np.ndarray:
    """Compute the PCH distribution for an open system with Poisson-weighted particle number.

    Parameters
    ----------
    k_vals : numpy.ndarray
        Photon count values k to evaluate.
    brightness : float
        Molecular brightness per particle.
    avgN : float
        Average number of particles in the observation volume.
    maxN : int, optional
        Maximum particle number for the Poisson summation (default 30).

    Returns
    -------
    numpy.ndarray
        Probability distribution P(k).
    """
    from scipy.stats import poisson  # type: ignore[import]

    p1 = pch_single_species(k_vals, brightness)
    length = k_vals.shape[0]
    pk_tot = np.zeros(length, dtype=float)
    avgN = float(max(avgN, 0.0))
    for N in range(maxN + 1):
        w = poisson.pmf(N, avgN)
        if w <= 0.0:
            continue
        if N == 0:
            base = np.zeros(length, dtype=float)
            base[0] = 1.0
        else:
            base = p1.copy()
            for _ in range(1, N):
                out = np.zeros(length, dtype=float)
                for i in range(length):
                    for j in range(length - i):
                        out[i + j] += base[i] * p1[j]
                base = out
        pk_tot += w * base
    return pk_tot


def pch_mixture(k_vals: np.ndarray, epsilons: np.ndarray, avgNs: np.ndarray) -> np.ndarray:
    """Compute the PCH distribution for a mixture of species via convolution.

    Parameters
    ----------
    k_vals : numpy.ndarray
        Photon count values k to evaluate.
    epsilons : numpy.ndarray
        Brightness values for each species.
    avgNs : numpy.ndarray
        Average particle numbers for each species.

    Returns
    -------
    numpy.ndarray
        Probability distribution P(k) for the mixture.
    """
    from scipy.signal import fftconvolve  # type: ignore[import]

    k_vals = np.asarray(k_vals, dtype=float)
    eps = np.asarray(epsilons, dtype=float)
    Ns = np.asarray(avgNs, dtype=float)
    if eps.size == 0 or Ns.size == 0:
        return np.ones_like(k_vals, dtype=float)

    pk = np.zeros_like(k_vals, dtype=float)
    pk[0] = 1.0
    for e, n in zip(eps, Ns):
        if n <= 0.0 or e <= 0.0:
            continue
        pj = pch_open_system(k_vals, float(e), float(n))
        pj = np.asarray(pj, dtype=float)
        if pj.shape != pk.shape:
            m = min(pk.size, pj.size)
            pj = pj[:m]
            pk = pk[:m]
        pk = fftconvolve(pk, pj)[: pk.size]
    if not np.any(np.isfinite(pk)):
        pk = np.ones_like(k_vals, dtype=float)
    return pk
