r"""Fluorescence-Intensity Distribution Analysis (FIDA).

FIDA (Kask et al., PNAS 1999) fits the photon-counting histogram (PCH) of a
confocal intensity trace to recover, for each molecular species, its specific
molecular **brightness** :math:`q` (counts per molecule per bin) and its mean
**number** :math:`N` in the detection volume — the same observables as PCH but
computed through the probability *generating function* with an explicit spatial
brightness profile, which handles arbitrary (non-Gaussian) detection volumes and
multiple species cleanly.

The generating function of the photon count in one bin is

.. math::

    G(\xi) = \exp\!\Big\{ \sum_i N_i \int_0^1 w(x)\,
             \big[e^{(\xi-1)\,q_i x} - 1\big]\,dx
             + (\xi - 1)\,\lambda_\mathrm{bg} \Big\},

where :math:`w(x)` is the spatial *brightness profile* — the differential
detection volume at relative brightness :math:`x \in (0, 1]`, normalised to
:math:`\int w\,dx = 1` (the FIDA ``dV/dx``) — and :math:`\lambda_\mathrm{bg}` is
the mean background per bin.  The histogram :math:`P(k)` is recovered as the
Taylor coefficients of :math:`G`, obtained by evaluating :math:`G` on the
complex unit circle and inverse-FFT (:math:`P(k)` is the coefficient of
:math:`\xi^k`, since :math:`G(\xi) = \sum_k P(k)\,\xi^k`).

This is a port of the Fretica ``FPCHFida`` / ``FPCHFidaFit`` functions.
"""

from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np


def dvdx_gaussian(
    n_bins: int = 256, x_min: float = 1e-4, structure: float = 1.0,
) -> Tuple[np.ndarray, np.ndarray]:
    r"""Spatial brightness profile ``w(x)`` for a 3-D Gaussian detection volume.

    For a 3-D Gaussian profile the volume with relative brightness :math:`\ge x`
    scales as :math:`(-\ln x)^{3/2}`, so the differential volume is
    :math:`w(x) \propto (-\ln x)^{1/2}/x`.  Returned normalised to unit integral.

    Parameters
    ----------
    n_bins : int
        Number of brightness bins on ``(x_min, 1]``.
    x_min : float
        Lower brightness cutoff (the profile diverges mildly as ``x -> 0``).
    structure : float
        Axial/lateral structure parameter (kept for API parity; the shape of
        ``w(x)`` for an anisotropic 3-D Gaussian is unchanged up to the overall
        normalisation absorbed here).

    Returns
    -------
    x, w : numpy.ndarray
        Brightness grid and the normalised profile weight (``sum(w) * dx == 1``).
    """
    x = np.linspace(x_min, 1.0, n_bins)
    w = np.sqrt(-np.log(x)) / x
    dx = x[1] - x[0]
    w = w / (w.sum() * dx)
    return x, w


def fida_pch(
    k_max: int,
    species: Sequence[Tuple[float, float]],
    profile: Tuple[np.ndarray, np.ndarray] | None = None,
    background: float = 0.0,
    oversample: int = 8,
) -> np.ndarray:
    r"""Photon-counting histogram ``P(0..k_max)`` via the FIDA generating function.

    Parameters
    ----------
    k_max : int
        Largest photon count in the histogram (inclusive).
    species : sequence of (float, float)
        ``(q, N)`` per species: molecular brightness ``q`` (counts/molecule/bin)
        and mean number ``N`` in the reference volume.
    profile : (x, w), optional
        Spatial brightness profile (:func:`dvdx_gaussian` by default), with
        ``w`` normalised to unit integral over ``x``.
    background : float
        Mean background counts per bin.
    oversample : int
        FFT length factor ``M = oversample * (k_max + 1)`` for the PGF inversion
        (larger reduces circular-aliasing of the tail).

    Returns
    -------
    numpy.ndarray
        ``P(k)`` for ``k = 0 .. k_max`` (non-negative, summing to ~1).
    """
    if profile is None:
        profile = dvdx_gaussian()
    x, w = profile
    dx = x[1] - x[0]

    m = int(max(oversample, 1) * (k_max + 1))
    j = np.arange(m)
    # Evaluate the PGF on exp(-2*pi*i*j/m) so that G_j = sum_k P_k xi^k is the
    # forward DFT of P and P = ifft(G) recovers the coefficients directly.
    xi = np.exp(-2j * np.pi * j / m)

    exponent = np.zeros(m, dtype=complex)
    for q, n in species:
        # N * int w(x) (e^{(xi-1) q x} - 1) dx, vectorised over the circle points.
        # shape (m, len(x)): (xi-1)[:, None] * q * x[None, :]
        integ = (np.exp((xi[:, None] - 1.0) * (q * x[None, :])) - 1.0)
        exponent += n * (integ * w[None, :]).sum(axis=1) * dx
    exponent += (xi - 1.0) * background

    g = np.exp(exponent)
    p = np.real(np.fft.ifft(g))[: k_max + 1]
    p = np.clip(p, 0.0, None)                             # kill tiny negative FFT noise
    total = p.sum()
    if total > 0:
        p = p / total
    return p


def fida_residuals(
    p_model: np.ndarray, counts: np.ndarray, n_bins: int,
) -> np.ndarray:
    r"""Multinomial (Fretica ``FPCHFidaFit``) residuals for a PCH fit.

    ``R_k = (n_\mathrm{bins} p_k - counts_k) / \sqrt{n_\mathrm{bins} p_k (1-p_k)}``,
    the standardised residual for the number of bins with ``k`` photons under a
    multinomial model of ``n_bins`` independent time bins.
    """
    p = np.clip(np.asarray(p_model, dtype=float), 1e-12, 1.0 - 1e-12)
    expected = n_bins * p
    sigma = np.sqrt(n_bins * p * (1.0 - p))
    return (expected - np.asarray(counts, dtype=float)) / sigma
