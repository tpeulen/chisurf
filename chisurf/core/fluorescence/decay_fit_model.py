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

__all__ = ["build_lifetime_fit", "fit_lifetime_model",
           "build_fret_fit", "fit_fret_model"]

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


def _make_fit(
    model_class,
    decay,
    *,
    bin_width: float,
    irf=None,
    start_bin: int = 0,
    stop_bin: int | None = None,
    background: float = 0.0,
    fit_background: bool = False,
    fit_scatter: bool = False,
    fit_irf: bool = False,
    irf_width: float = 0.2,
    irf_skew: float = 0.0,
    period: float | None = None,
    model_kw: dict | None = None,
):
    """Build a ``Fit`` of ``model_class`` over ``decay``, wired to compute.

    Everything here is shared by every TCSPC model: the data curve, the fit
    window, the convolution settings and the nuisance terms. The caller
    configures whatever is model-specific (lifetimes, distances) and then calls
    ``find_parameters()``.

    Each of these settings **fails silently** when wrong, leaving a flat
    background instead of a decay — see the module docstring.
    """
    import chisurf.core.data
    from chisurf.core.fitting.fit import Fit

    y = np.asarray(decay, dtype=float).ravel()
    n_bins = y.size
    if n_bins < 4:
        raise ValueError(f"decay is too short to fit: {n_bins} bins")
    dt = float(bin_width)
    if not dt > 0:
        raise ValueError(f"bin_width must be positive, got {dt}")

    t = np.arange(n_bins, dtype=float) * dt
    data = chisurf.core.data.DataCurve(x=t, y=y, ey=np.sqrt(np.maximum(y, 1.0)))

    stop = n_bins - 1 if stop_bin is None else int(stop_bin)
    stop = int(np.clip(stop, 0, n_bins - 1))
    start = int(np.clip(int(start_bin), 0, max(0, stop - 1)))

    fit = Fit(model_class=model_class, data=data, xmin=start, xmax=stop,
              model_kw=dict(model_kw or {}))
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

    fit.fit_range = (start, stop)
    return fit


def _configure_lifetimes(group, taus, bounds) -> None:
    """Seed a classic :class:`Lifetime` group (a FRET model's donor) with ``taus``.

    Configuring the existing components rather than appending avoids leaving the
    model's default 4 ns component in place beside the requested ones, which
    would add a duplicate lifetime and a spurious rank deficiency.
    """
    lo, hi = float(bounds[0]), float(bounds[1])
    n = len(taus)
    while len(group) < n:
        group.append()
    for k, tau in enumerate(taus):
        group._amplitudes[k].value = 1.0 / n
        p = group._lifetimes[k]
        p.value = float(tau)
        p.bounds = (lo, hi)
        p.bounds_on = True                     # bounds are off by default


def _set_port(problem, canonical: str, value: float) -> None:
    """Write a parameter whatever its lock; a caller's number means that number."""
    port = problem.get_parameter(canonical)
    held = port.fixed
    port.fixed = False
    port.value = float(value)
    port.fixed = held


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
    """Build a runnable :class:`Fit` over ``decay`` on BFF's TCSPC lifetime model.

    The model is the ``tcspc_lifetime`` description BFF owns
    (:func:`chisurf.core.models.description.for_family`), standing at the
    topology with ``n_components`` lifetimes.

    Parameters
    ----------
    decay : array_like
        Measured decay in counts, one element per micro-time bin.
    bin_width : float
        Micro-time bin width in nanoseconds.
    irf : array_like, optional
        Measured instrument response. When omitted the model generates a
        generalized-normal prompt at the decay's rising edge from
        ``irf_width``/``irf_skew``, which ``fit_irf`` can free.
    n_components : int
        Number of exponential components.
    initial_lifetimes : array_like, optional
        Starting lifetimes in ns. Defaults to a log-spaced spread across
        ``tau_bounds``, which keeps the components distinct -- seeding them all at
        the same value leaves the Jacobian rank-deficient.
    tau_bounds : tuple of float
        ``(lower, upper)`` lifetime bounds in ns, applied to every component.
    start_bin, stop_bin : int
        Fit window as bin indices; ``stop_bin`` defaults to the last bin. The
        model is still evaluated over the whole axis -- the window only masks
        which residuals the optimiser sees.
    background : float
        Constant background per bin.
    fit_background, fit_scatter : bool
        Free the corresponding instrument parameter instead of holding it.
    fit_irf : bool
        Fit the width and shape of the generated prompt alongside the lifetimes.
        Has no effect when a measured ``irf`` is supplied, whose shape is data
        rather than a model. The IRF timeshift is free either way: a measured
        IRF's timing genuinely drifts, and pinning it biased the lifetimes.
    irf_width, irf_skew : float
        Seed values for the generated prompt's width (ns) and shape. Ignored when
        a measured ``irf`` is supplied.
    period : float, optional
        Laser period in ns. When given the convolution is periodic, so the
        previous pulse's tail wraps into the window; otherwise it is single.

    Returns
    -------
    Fit
        A configured fit; call ``fit.run()`` to optimise it.
    """
    import chisurf.core.curve
    import chisurf.core.data
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.description import for_family

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
    if taus.size < n:
        raise ValueError(f"{n} components need {n} initial lifetimes, got {taus.size}")

    t = np.arange(n_bins, dtype=float) * dt
    data = chisurf.core.data.DataCurve(x=t, y=y, ey=np.sqrt(np.maximum(y, 1.0)))
    stop = n_bins - 1 if stop_bin is None else int(stop_bin)
    stop = int(np.clip(stop, 0, n_bins - 1))
    start = int(np.clip(int(start_bin), 0, max(0, stop - 1)))

    fit = Fit(model_class=for_family("tcspc_lifetime"), data=data, xmin=start, xmax=stop)
    model = fit.model
    model.set_scalar("dt", dt)
    periodic = period is not None and float(period) > 0
    # Without excitation repeating inside the window, the period only bounds
    # what the description derives from it; the window is the natural scale.
    model.set_scalar("period", float(period) if periodic else n_bins * dt)
    model.set_scalar("periodic_excitation", 1.0 if periodic else 0.0)
    model.set_scalar("autoscale", 1.0)
    model.set_scalar("max_components", float(max(3, n)))
    if irf is not None:
        irf_y = np.zeros(n_bins, dtype=float)
        measured = np.asarray(irf, dtype=float).ravel()[:n_bins]
        irf_y[:measured.size] = measured
        model.set_dataset("response", chisurf.core.curve.Curve(x=t, y=irf_y))
    else:
        model.set_scalar("generated_response", 1.0)
    for k, tau in enumerate(taus):
        # Lifetime bounds are the caller's; the description's (up to the period)
        # would otherwise stand.
        model._spec.set_parameter(f"lifetime.tau.{k}", float(tau), True, lo, hi)

    problem = model.problem
    if problem is None:
        raise ValueError("the lifetime model is missing " + ", ".join(model.missing))
    model.structure = f"lifetime.components.{n}"
    for k in range(n):
        _set_port(problem, f"lifetime.amplitude.{k}", 1.0 / n)
        _set_port(problem, f"lifetime.tau.{k}", float(taus[k]))
    _set_port(problem, "instrument.background", float(background))
    if irf is None:
        _set_port(problem, "instrument.irf_width", abs(float(irf_width)))
        _set_port(problem, "instrument.irf_shape", float(irf_skew))

    free = {
        "instrument.n0": False,               # autoscaled
        "instrument.background": bool(fit_background),
        "instrument.scatter": bool(fit_scatter),
        "instrument.timeshift": True,
        "instrument.irf_width": bool(fit_irf) and irf is None,
        "instrument.irf_shape": bool(fit_irf) and irf is None,
    }
    parameters = {p.canonical_id: p for p in model.parameters_all
                  if not getattr(p, "is_output", False)}
    for canonical, is_free in free.items():
        parameters[canonical].fixed = not is_free
    model.find_parameters()
    fit.fit_range = (start, stop)
    model.update()
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
    """Fit ``decay`` on BFF's TCSPC lifetime model and report the result.

    A model-backed counterpart to
    :func:`chisurf.core.fluorescence.decay_fit.fit_lifetime_components`. The
    returned dictionary carries the same keys that function's callers use --
    ``lifetimes``, ``amplitudes``, ``lifetime_spectrum``, ``reconstruction``,
    ``weighted_residuals``, ``chi2_reduced`` -- so it can stand in for it, plus
    ``fit`` and ``model`` (the live objects, whose parameters can be linked to
    other fits) and ``lifetime_errors`` / ``amplitude_errors``.

    Arguments are as for :func:`build_lifetime_fit`.

    Returns
    -------
    dict
        ``{lifetimes, amplitudes, lifetime_spectrum, reconstruction,
        weighted_residuals, chi2_reduced, lifetime_errors, amplitude_errors,
        background, scatter, irf_width, irf_skew, irf_shift, irf_peak, fit,
        model}``. ``lifetimes`` and ``amplitudes`` are sorted by lifetime,
        matching ``fit_lifetime_components``. ``irf_shift`` is in channels and
        ``irf_peak`` is where the (shifted) generated prompt peaks, in ns.

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
    m.update()
    n = max(1, int(n_components))
    parameters = {p.canonical_id: p for p in m.parameters_all
                  if not getattr(p, "is_output", False)}

    def value(canonical):
        return float(parameters[canonical].value)

    def error(canonical):
        return float(getattr(parameters[canonical], "error_estimate", 0.0) or 0.0)

    taus = np.array([value(f"lifetime.tau.{k}") for k in range(n)])
    raw = np.abs([value(f"lifetime.amplitude.{k}") for k in range(n)])
    total = float(raw.sum()) or 1.0
    amps = raw / total
    tau_err = np.array([error(f"lifetime.tau.{k}") for k in range(n)])
    amp_err = np.array([error(f"lifetime.amplitude.{k}") for k in range(n)]) / total

    order = np.argsort(taus)
    taus, amps = taus[order], amps[order]
    tau_err, amp_err = tau_err[order], amp_err[order]
    spectrum = np.empty(2 * n, dtype=float)
    spectrum[0::2], spectrum[1::2] = amps, taus

    dt = float(bin_width)
    shift = value("instrument.timeshift")
    irf_peak = None
    if irf is None:
        problem = m.problem
        active = problem.get_active_structure()
        prompt = np.asarray(problem.get_structure_output(active, f"{active}.generated_response"), dtype=float)
        irf_peak = (float(np.argmax(prompt)) + shift) * dt

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
        "background": value("instrument.background"),
        "scatter": value("instrument.scatter"),
        "irf_width": abs(value("instrument.irf_width")),
        "irf_skew": value("instrument.irf_shape"),
        "irf_shift": shift,
        "irf_peak": irf_peak,
        "fit": fit,
        "model": m,
    }


def build_fret_fit(
    decay,
    *,
    bin_width: float,
    n_states: int = 2,
    donor_lifetime: float = 4.0,
    forster_radius: float = 52.0,
    initial_distances=None,
    sigma: float = 6.0,
    distance_bounds: tuple[float, float] = (10.0, 120.0),
    x_donor_only: float = 0.0,
    fit_donor_only: bool = True,
    fit_donor_lifetime: bool = False,
    irf=None,
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
    """Build a runnable FRET fit: ``n_states`` Gaussian donor-acceptor distances.

    Uses :class:`~chisurf.core.models.tcspc.fret.GaussianModel`, so each state is
    a Gaussian distance distribution whose **mean, width and species fraction are
    fitted parameters**, alongside the donor-only fraction ``xDOnly``. That is a
    genuine FRET fit — the efficiencies come from fitted distances and R₀ — rather
    than lifetimes converted to efficiencies afterwards.

    Parameters
    ----------
    decay : array_like
        Measured donor decay in the presence of acceptor (counts).
    n_states : int
        Number of FRET states.
    donor_lifetime : float
        Donor-only lifetime τ_D0 (ns). Held fixed unless ``fit_donor_lifetime``:
        it is a property of the donor, normally measured separately, and fitting
        it against a distance distribution is badly conditioned.
    forster_radius : float
        Förster radius R₀ (Å); held fixed, as it is calibration, not data.
    initial_distances : array_like, optional
        Starting mean distances (Å). Defaults to a spread across
        ``distance_bounds`` centred on R₀, which keeps the states distinct.
    sigma : float
        Starting width of each Gaussian (Å).
    x_donor_only : float
        Starting donor-only fraction.
    fit_donor_only : bool
        Fit ``xDOnly``. A sample with no donor-only population should pin it,
        since it trades off against the long-distance states.
    fit_donor_lifetime : bool
        Free the donor-only lifetime instead of holding it at ``donor_lifetime``.
    distance_bounds : tuple of float
        ``(lower, upper)`` bounds in Å applied to every fitted mean distance.
    bin_width, irf, start_bin, stop_bin, background, fit_background, fit_scatter, fit_irf, irf_width, irf_skew, period
        As for :func:`build_lifetime_fit`.

    Returns
    -------
    Fit
        A configured fit; call ``fit.run()`` to optimise it.
    """
    import chisurf.core.models.tcspc.fret as fret_model

    n = max(1, int(n_states))
    r_lo, r_hi = float(distance_bounds[0]), float(distance_bounds[1])
    if not 0 < r_lo < r_hi:
        raise ValueError(
            f"distance_bounds must satisfy 0 < lower < upper, got {distance_bounds}")
    r0 = float(forster_radius)
    if not r0 > 0:
        raise ValueError(f"forster_radius must be positive, got {r0}")

    if initial_distances is None:
        # Spread around R0, where the efficiency is most sensitive to distance.
        spread = np.linspace(0.7, 1.3, n) if n > 1 else np.array([1.0])
        distances = np.clip(r0 * spread, r_lo, r_hi)
    else:
        distances = np.clip(
            np.asarray(initial_distances, dtype=float).ravel()[:n], r_lo, r_hi)

    fit = _make_fit(
        fret_model.GaussianModel, decay, bin_width=bin_width, irf=irf,
        start_bin=start_bin, stop_bin=stop_bin, background=background,
        fit_background=fit_background, fit_scatter=fit_scatter, fit_irf=fit_irf,
        irf_width=irf_width, irf_skew=irf_skew, period=period,
    )
    m = fit.model

    # The donor-only decay. `FRETModel` shares one Lifetime group between
    # `m.donor` and `m.lifetimes`, so this is the tau_D0 the FRET rates are
    # measured against.
    _configure_lifetimes(m.donor, [float(donor_lifetime)], (0.01, 100.0))
    m.donor._lifetimes[0].fixed = not bool(fit_donor_lifetime)

    fp = m.fret_parameters
    fp._forster_radius.value = r0
    fp._tauD0.value = float(donor_lifetime)
    fp._xDonly.value = float(x_donor_only)
    fp._xDonly.fixed = not bool(fit_donor_only)

    for k, r in enumerate(distances):
        m.append(float(r), float(sigma), 1.0 / n)
        mean = m.gaussians._gaussianMeans[k]
        mean.bounds = (r_lo, r_hi)
        mean.bounds_on = True

    m.find_parameters()
    return fit


def fit_fret_model(decay, **kwargs) -> dict:
    """Fit ``decay`` as ``n_states`` Gaussian FRET distances and report the result.

    Arguments are as for :func:`build_fret_fit`.

    Returns
    -------
    dict
        ``{distances, sigmas, fractions, efficiencies, donor_only_fraction,
        forster_radius, donor_lifetime, reconstruction, weighted_residuals,
        chi2_reduced, fit, model}``, sorted by distance. ``efficiencies`` are
        derived from the fitted distances as ``1/(1+(R/R0)**6)`` — the mean-
        distance efficiency of each state, not the distribution-averaged one.
    """
    fit = build_fret_fit(decay, **kwargs)
    fit.run()
    m = fit.model

    distances = np.asarray(m.gaussians.mean, dtype=float)
    sigmas = np.asarray(m.gaussians.sigma, dtype=float)
    fractions = np.asarray(m.gaussians.amplitude, dtype=float)
    order = np.argsort(distances)
    distances, sigmas, fractions = distances[order], sigmas[order], fractions[order]

    r0 = float(m.fret_parameters.forster_radius)
    efficiencies = 1.0 / (1.0 + (distances / r0) ** 6)

    wres = np.asarray(m.weighted_residuals, dtype=float)
    irf_peak = None
    if kwargs.get("irf") is None:
        try:
            # The processed prompt carries its absolute position (shift included).
            irf_peak = float(np.argmax(np.asarray(m.convolve.irf.y, dtype=float))) * float(m.convolve.dt)
        except Exception:
            irf_peak = None
    return {
        "distances": distances,
        "sigmas": sigmas,
        "fractions": fractions,
        "efficiencies": efficiencies,
        "donor_only_fraction": float(m.fret_parameters.xDOnly),
        "forster_radius": r0,
        "donor_lifetime": float(m.fret_parameters.tauD0),
        # Same IRF reporting as the lifetime fit, so callers can write the fitted
        # prompt back to a detector regardless of which fit produced it.
        "irf_width": abs(float(m.convolve._iw.value)),
        "irf_skew": float(m.convolve._ik.value),
        "irf_shift": float(m.convolve._ts.value),
        "irf_peak": irf_peak,
        "reconstruction": np.asarray(m.y, dtype=float),
        "weighted_residuals": wres,
        "chi2_reduced": float(np.sum(wres ** 2) / max(1, wres.size)),
        "fit": fit,
        "model": m,
    }
