"""Fit a measured fluorescence decay as a mixture of parametric components.

A small, dependency-light decay fitter shared by the fFCS Filter Calculator's
"auto-fit" (derive filter components straight from the measured mixed decay) and,
more generally, anywhere a decay must be decomposed into lifetime components
without spinning up the full TCSPC fit machinery. It is deliberately built on the
single canonical generator
:func:`chisurf.core.fluorescence.decay.synthetic_decay`, so the forward model
(sum-of-exponentials + IRF convolution) is not duplicated.

Two entry points:

- :func:`fit_lifetime_components` — discrete multi-exponential: optimize ``n``
  lifetimes (bounded, in log-space) with non-negative amplitudes solved by NNLS at
  each step, minimizing the Poisson-weighted residuals.
- :func:`fit_component_amplitudes` — non-negative amplitudes only, for a fixed set
  of component decays (the linear unmixing step, weighted).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from chisurf.core.fluorescence.decay import synthetic_decay


def _poisson_sigma(decay: np.ndarray, weights: Any | None) -> np.ndarray:
    if weights is not None:
        w = np.asarray(weights, dtype=float).ravel()
        return np.where(w > 0, w, 1.0)
    # Poisson: sigma = sqrt(counts), floored at 1 so empty bins don't dominate.
    return np.sqrt(np.maximum(np.asarray(decay, dtype=float), 1.0))


def _basis(lifetimes: np.ndarray, n_bins: int, bin_width: float,
           irf: Any | None, start_bin: int) -> np.ndarray:
    """Design matrix ``B[bin, i]`` — a unit-sum decay per lifetime."""
    cols = [
        synthetic_decay(n_bins, [float(t)], bin_width=bin_width, irf=irf,
                        start_bin=start_bin, normalize=True)
        for t in lifetimes
    ]
    return np.stack(cols, axis=1)


def _nnls_amplitudes(basis: np.ndarray, decay: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    from scipy.optimize import nnls

    a_mat = basis / sigma[:, None]
    b_vec = decay / sigma
    amplitudes, _ = nnls(a_mat, b_vec)
    return amplitudes


def fit_component_amplitudes(
    decay: Any,
    components: Any,
    *,
    weights: Any | None = None,
) -> dict:
    """Non-negative weighted amplitudes for fixed component decays.

    ``components`` is a ``(n_components, n_bins)`` array (or list of decays).
    Returns ``{amplitudes, reconstruction, weighted_residuals, chi2_reduced}``.
    """
    decay = np.asarray(decay, dtype=float).ravel()
    basis = np.asarray(components, dtype=float)
    if basis.ndim != 2:
        raise ValueError("components must be 2-D (n_components, n_bins)")
    # NNLS wants the design matrix as (n_bins, n_components); accept either input
    # orientation and transpose the (n_components, n_bins) form.
    if basis.shape[0] != decay.size and basis.shape[1] == decay.size:
        basis = basis.T
    sigma = _poisson_sigma(decay, weights)
    amplitudes = _nnls_amplitudes(basis, decay, sigma)
    recon = basis @ amplitudes
    wres = (recon - decay) / sigma
    dof = max(1, decay.size - basis.shape[1])
    return {
        "amplitudes": amplitudes,
        "reconstruction": recon,
        "weighted_residuals": wres,
        "chi2_reduced": float(np.sum(wres ** 2) / dof),
    }


def fit_lifetime_components(
    decay: Any,
    *,
    bin_width: float,
    n_components: int = 2,
    irf: Any | None = None,
    tau_bounds: tuple[float, float] = (0.1, 10.0),
    initial_lifetimes: Any | None = None,
    weights: Any | None = None,
    start_bin: int = 0,
    max_nfev: int = 200,
    fit_irf: bool = False,
    irf_fwhm0: float = 0.3,
    irf_fwhm_bounds: tuple[float, float] = (0.02, 3.0),
    irf_skew: float = 0.0,
) -> dict:
    """Fit a decay as ``Σ aᵢ·decay(τᵢ)`` with ``aᵢ ≥ 0`` (auto multi-exponential).

    The ``n_components`` lifetimes are optimized (bounded, in log-space) to
    minimize the Poisson-weighted residuals; the amplitudes are solved by NNLS at
    every step, so the fit needs no amplitude starting guess and never returns a
    negative amplitude. Reuses :func:`synthetic_decay` for the forward model, so an
    ``irf`` is convolved consistently with the rest of ChiSurf.

    When ``fit_irf`` is true a synthetic Gaussian IRF (via
    :func:`chisurf.core.fluorescence.tcspc.irf.synthetic_irf`) is fitted jointly —
    its FWHM becomes a free parameter (bounded by ``irf_fwhm_bounds``) — instead of
    using a fixed ``irf``.

    Returns ``{lifetimes, amplitudes, lifetime_spectrum, reconstruction,
    weighted_residuals, chi2_reduced, irf_fwhm}`` (``lifetime_spectrum`` is the
    interleaved ``[a₀, τ₀, …]`` form, amplitude-sorted by lifetime; ``irf_fwhm`` is
    the fitted width or ``None``).
    """
    from scipy.optimize import least_squares

    decay = np.asarray(decay, dtype=float).ravel()
    n_bins = decay.size
    n = max(1, int(n_components))
    lo, hi = float(tau_bounds[0]), float(tau_bounds[1])
    if lo <= 0 or hi <= lo:
        raise ValueError("tau_bounds must be positive with hi > lo")
    if initial_lifetimes is not None:
        tau0 = np.clip(np.asarray(initial_lifetimes, dtype=float).ravel(), lo, hi)
    else:
        tau0 = np.geomspace(lo * 1.5, hi * 0.7, n) if n > 1 else np.array([np.sqrt(lo * hi)])
    sigma = _poisson_sigma(decay, weights)
    time_ns = np.arange(n_bins, dtype=float) * float(bin_width)

    def _irf_for(x: np.ndarray):
        if not fit_irf:
            return irf
        from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

        fwhm = float(np.exp(x[n]))
        return synthetic_irf(time_ns, 2.0 * fwhm, fwhm, shape=float(irf_skew))

    def _reconstruct(x: np.ndarray):
        lifetimes = np.exp(x[:n])
        basis = _basis(lifetimes, n_bins, bin_width, _irf_for(x), start_bin)
        amplitudes = _nnls_amplitudes(basis, decay, sigma)
        return lifetimes, amplitudes, basis @ amplitudes

    def residual(x: np.ndarray) -> np.ndarray:
        _, _, recon = _reconstruct(x)
        return (recon - decay) / sigma

    x0 = list(np.log(tau0))
    lb = [np.log(lo)] * n
    ub = [np.log(hi)] * n
    if fit_irf:
        f_lo, f_hi = float(irf_fwhm_bounds[0]), float(irf_fwhm_bounds[1])
        x0.append(np.log(float(np.clip(irf_fwhm0, f_lo, f_hi))))
        lb.append(np.log(f_lo))
        ub.append(np.log(f_hi))

    result = least_squares(
        residual, np.asarray(x0), bounds=(lb, ub), max_nfev=int(max_nfev), method="trf",
    )
    lifetimes, amplitudes, recon = _reconstruct(result.x)
    wres = (recon - decay) / sigma
    n_params = 2 * n + (1 if fit_irf else 0)
    dof = max(1, n_bins - n_params)

    order = np.argsort(lifetimes)
    lifetimes, amplitudes = lifetimes[order], amplitudes[order]
    spectrum = np.empty(2 * n, dtype=float)
    spectrum[0::2] = amplitudes
    spectrum[1::2] = lifetimes
    return {
        "lifetimes": lifetimes,
        "amplitudes": amplitudes,
        "lifetime_spectrum": spectrum,
        "reconstruction": recon,
        "weighted_residuals": wres,
        "chi2_reduced": float(np.sum(wres ** 2) / dof),
        "irf_fwhm": float(np.exp(result.x[n])) if fit_irf else None,
    }
