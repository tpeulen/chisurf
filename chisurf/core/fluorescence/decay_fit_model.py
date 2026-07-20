"""Drive a real ChiSurf TCSPC fit from a bare decay array.

:mod:`chisurf.core.fluorescence.decay_fit` fits a multi-exponential decay with a
standalone :mod:`scipy` optimiser. That is self-contained and fast, but its
results are plain floats: they cannot be linked to another fit's parameters,
carry no error estimates from ChiSurf's covariance machinery, and duplicate a
forward model that :class:`~chisurf.core.models.tcspc.lifetime.LifetimeModel`
already implements.

This module fits the *same* problem through the real model stack instead, so the
result is a live :class:`~chisurf.core.fitting.fit.Fit` whose
:class:`~chisurf.core.fitting.parameter.FittingParameter` objects support the
ordinary linking, bounds and error-estimate surface.

Getting a ``LifetimeModel`` to compute from an in-memory array needs several
non-obvious settings, and **every one of them fails silently** — the model
returns a flat background rather than raising. :func:`build_lifetime_fit`
centralises them; see the notes there before changing any of it.

The module is Qt-free and importable headlessly.
"""
from __future__ import annotations

import numpy as np

__all__ = ["build_lifetime_fit", "fit_lifetime_model"]

#: Peak counts the IRF is rescaled to. ``Convolve._process_irf`` subtracts
#: ``lamp_background`` and clips at zero *twice*, so a sum-normalised IRF (peak
#: ~0.04) is annihilated. Only the IRF *shape* matters — the model's ``n0``
#: autoscaling absorbs its amplitude — so rescaling is safe.
_IRF_PEAK_COUNTS = 1.0e4


def _as_counts_irf(irf, n_bins: int) -> np.ndarray:
    """Return ``irf`` resized to ``n_bins`` and rescaled to counts."""
    y = np.asarray(irf, dtype=float).ravel()
    if y.size < n_bins:
        padded = np.zeros(n_bins, dtype=float)
        padded[: y.size] = y
        y = padded
    else:
        y = y[:n_bins].copy()
    peak = float(y.max()) if y.size else 0.0
    if peak > 0:
        y = y / peak * _IRF_PEAK_COUNTS
    return y


def _use_synthetic_irf(convolve, width: float, skew: float) -> None:
    """Switch ``convolve`` to its own generated IRF and seed its shape.

    ``Convolve._process_irf`` builds a generalized-normal prompt from the ``iw``
    (width) and ``ik`` (skew) parameters whenever no IRF *curve* is stored,
    locating it at the data's rising edge. Clearing the stored curve therefore
    turns the IRF shape into fitted parameters rather than fixed input. The
    backing attribute is name-mangled and its property setter dereferences the
    value, so it has to be cleared directly.
    """
    object.__setattr__(convolve, "_Convolve__irf", None)
    # Width is magnitude-only — `_process_irf` takes abs(iw), and the sign of the
    # asymmetry lives in ik — so a fit may legitimately return a negative width.
    convolve._iw.value = abs(float(width))
    convolve._ik.value = float(skew)


def build_lifetime_fit(
    decay,
    *,
    bin_width: float,
    irf=None,
    n_components: int = 2,
    initial_lifetimes=None,
    tau_bounds: tuple[float, float] = (0.1, 10.0),
    start_bin: int = 0,
    stop_bin: int | None = None,
    background: float = 0.0,
    fit_background: bool = False,
    fit_scatter: bool = False,
    fit_irf: bool = False,
    irf_width: float = 0.2,
    irf_skew: float = 0.0,
    period: float | None = None,
):
    """Build a runnable :class:`Fit` over ``decay`` with a ``LifetimeModel``.

    Parameters
    ----------
    decay : array_like
        Measured decay in counts, one element per micro-time bin.
    bin_width : float
        Micro-time bin width in nanoseconds.
    irf : array_like, optional
        Measured instrument response, rescaled to counts internally (see
        :data:`_IRF_PEAK_COUNTS`). When omitted the model generates its own
        prompt from the ``iw``/``ik`` parameters, which ``fit_irf`` can free.
    n_components : int
        Number of exponential components.
    initial_lifetimes : array_like, optional
        Starting lifetimes in ns. Defaults to a log-spaced spread across
        ``tau_bounds``, which keeps the components distinct — seeding them all at
        the same value leaves the Jacobian rank-deficient.
    tau_bounds : tuple of float
        ``(lower, upper)`` lifetime bounds in ns, applied to every component.
    start_bin, stop_bin : int
        Fit window as bin indices; ``stop_bin`` defaults to the last bin. The
        model is still evaluated over the whole axis — the window only masks
        which residuals the optimiser sees.
    background : float
        Constant background per bin.
    fit_background, fit_scatter : bool
        Free the corresponding nuisance parameter (``generic.bg`` / ``generic.sc``)
        instead of holding it fixed.
    fit_irf : bool
        Fit the *shape* of the generated prompt (``iw``/``ik``) alongside the
        lifetimes. Has no effect when a measured ``irf`` is supplied, whose shape
        is data rather than a model. The IRF timeshift (``ts``) is free either
        way, following ChiSurf's default.
    irf_width, irf_skew : float
        Seed values for the generated prompt's width (ns) and skew. Ignored when
        a measured ``irf`` is supplied.
    period : float, optional
        Laser period in ns. When given the convolution is periodic, so the
        previous pulse's tail wraps into the window; otherwise it is aperiodic.

    Returns
    -------
    Fit
        A configured fit; call ``fit.run()`` to optimise it.
    """
    import chisurf.core.data
    import chisurf.core.models.tcspc.lifetime as lifetime_model
    from chisurf.core.fitting.fit import Fit

    y = np.asarray(decay, dtype=float).ravel()
    n_bins = y.size
    if n_bins < 4:
        raise ValueError(f"decay is too short to fit: {n_bins} bins")
    dt = float(bin_width)
    if not dt > 0:
        raise ValueError(f"bin_width must be positive, got {dt}")
    n = max(1, int(n_components))

    lo, hi = (float(tau_bounds[0]), float(tau_bounds[1]))
    if not 0 < lo < hi:
        raise ValueError(f"tau_bounds must satisfy 0 < lower < upper, got {tau_bounds}")
    if initial_lifetimes is None:
        taus = np.exp(np.linspace(np.log(lo), np.log(hi), n + 2))[1:-1] if n > 1 \
            else np.array([np.sqrt(lo * hi)])
    else:
        taus = np.clip(np.asarray(initial_lifetimes, dtype=float).ravel()[:n], lo, hi)

    t = np.arange(n_bins, dtype=float) * dt
    data = chisurf.core.data.DataCurve(x=t, y=y, ey=np.sqrt(np.maximum(y, 1.0)))

    stop = n_bins - 1 if stop_bin is None else int(stop_bin)
    stop = int(np.clip(stop, 0, n_bins - 1))
    start = int(np.clip(int(start_bin), 0, max(0, stop - 1)))

    fit = Fit(model_class=lifetime_model.LifetimeModel, data=data,
              xmin=start, xmax=stop)
    m = fit.model

    c = m.convolve
    if irf is not None:
        irf_y = _as_counts_irf(irf, n_bins)
        c._irf = chisurf.core.data.DataCurve(x=t, y=irf_y, ey=np.ones_like(irf_y))
    else:
        _use_synthetic_irf(c, irf_width, irf_skew)
    # The IRF is already background-free here; subtracting anything would clip it.
    c.lamp_background = 0.0
    c.dt = dt                                  # defaults to 1.0
    c.start, c.stop = 0.0, n_bins * dt         # TIME units; the default stop=0
    c._irf_start.value = 0.0                   # disables the convolution outright
    c._irf_stop.value = n_bins * dt            # (setters wrap in np.array: broken)
    # `mode="per"` derives its period as 1000/rep_rate ns.
    if period is not None and float(period) > 0:
        c.mode = 'per'
        c.rep_rate = 1000.0 / float(period)
    else:
        c.mode = 'exp'
    c.do_convolution = True
    c._n0.fixed = True                         # autoscale == self._n0.fixed

    # The model ships with one component already; configuring in place avoids a
    # duplicate lifetime, which would add a spurious rank deficiency.
    while len(m.lifetimes) < n:
        m.lifetimes.append()
    for k, tau in enumerate(taus):
        m.lifetimes._amplitudes[k].value = 1.0 / n
        p = m.lifetimes._lifetimes[k]
        p.value = float(tau)
        p.bounds = (lo, hi)
        p.bounds_on = True                     # bounds are off by default

    m.generic.background = float(background)
    m.generic._bg.fixed = not bool(fit_background)
    m.generic._sc.fixed = not bool(fit_scatter)

    # A measured IRF is data: its shape is input, not a model, so only a
    # generated prompt has its width/skew fitted. The IRF *timeshift* is left at
    # ChiSurf's own default (free) in both cases — a measured IRF is recorded
    # separately from the data and its timing genuinely drifts, so pinning it
    # here measurably biased the lifetimes.
    shape_free = bool(fit_irf) and irf is None
    c._iw.fixed = not shape_free
    c._ik.fixed = not shape_free

    m.find_parameters()
    fit.fit_range = (start, stop)
    return fit


def fit_lifetime_model(
    decay,
    *,
    bin_width: float,
    irf=None,
    n_components: int = 2,
    initial_lifetimes=None,
    tau_bounds: tuple[float, float] = (0.1, 10.0),
    start_bin: int = 0,
    stop_bin: int | None = None,
    background: float = 0.0,
    fit_background: bool = False,
    fit_scatter: bool = False,
    fit_irf: bool = False,
    irf_width: float = 0.2,
    irf_skew: float = 0.0,
    period: float | None = None,
) -> dict:
    """Fit ``decay`` through a real ``LifetimeModel`` and report the result.

    A model-backed counterpart to
    :func:`chisurf.core.fluorescence.decay_fit.fit_lifetime_components`. The
    returned dictionary carries the same keys that function's callers use —
    ``lifetimes``, ``amplitudes``, ``lifetime_spectrum``, ``reconstruction``,
    ``weighted_residuals``, ``chi2_reduced`` — so it can stand in for it, plus
    ``fit`` and ``model`` (the live objects, whose ``FittingParameter``s can be
    linked to other fits) and ``lifetime_errors`` / ``amplitude_errors``.

    Arguments are as for :func:`build_lifetime_fit`.

    Returns
    -------
    dict
        ``{lifetimes, amplitudes, lifetime_spectrum, reconstruction,
        weighted_residuals, chi2_reduced, lifetime_errors, amplitude_errors,
        background, scatter, irf_width, irf_skew, irf_shift, fit, model}``.
        ``lifetimes`` and ``amplitudes`` are sorted by lifetime, matching
        ``fit_lifetime_components``.

        ``amplitudes`` are **pre-exponential**, not the photon fractions
        ``fit_lifetime_components`` reports; convert with
        ``f_i = a_i*tau_i / sum(a_j*tau_j)``.
    """
    fit = build_lifetime_fit(
        decay, bin_width=bin_width, irf=irf, n_components=n_components,
        initial_lifetimes=initial_lifetimes, tau_bounds=tau_bounds,
        start_bin=start_bin, stop_bin=stop_bin, background=background,
        fit_background=fit_background, fit_scatter=fit_scatter,
        fit_irf=fit_irf, irf_width=irf_width, irf_skew=irf_skew, period=period,
    )
    fit.run()
    m = fit.model

    taus = np.asarray([p.value for p in m.lifetimes._lifetimes], dtype=float)
    amps = np.asarray(m.lifetimes.amplitudes, dtype=float)
    tau_err = np.asarray(
        [getattr(p, "error_estimate", 0.0) or 0.0 for p in m.lifetimes._lifetimes],
        dtype=float)
    amp_err = np.asarray(
        [getattr(p, "error_estimate", 0.0) or 0.0 for p in m.lifetimes._amplitudes],
        dtype=float)

    order = np.argsort(taus)
    taus, amps = taus[order], amps[order]
    tau_err, amp_err = tau_err[order], amp_err[order]

    spectrum = np.empty(2 * taus.size, dtype=float)
    spectrum[0::2], spectrum[1::2] = amps, taus

    wres = np.asarray(m.weighted_residuals, dtype=float)
    return {
        "lifetimes": taus,
        "amplitudes": amps,
        "lifetime_spectrum": spectrum,
        "lifetime_errors": tau_err,
        "amplitude_errors": amp_err,
        "reconstruction": np.asarray(m.y, dtype=float),
        "weighted_residuals": wres,
        "chi2_reduced": float(np.sum(wres ** 2) / max(1, wres.size)),
        "background": float(m.generic.background),
        "scatter": float(m.generic.scatter),
        # Width is magnitude-only (`_process_irf` takes its absolute value), so
        # report it as such rather than passing a negative width to callers.
        "irf_width": abs(float(m.convolve._iw.value)),
        "irf_skew": float(m.convolve._ik.value),
        "irf_shift": float(m.convolve._ts.value),
        "fit": fit,
        "model": m,
    }
