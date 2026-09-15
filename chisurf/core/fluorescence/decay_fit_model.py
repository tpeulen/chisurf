"""Drive a real ChiSurf TCSPC fit from a bare decay array.

:mod:`chisurf.core.fluorescence.decay_fit` fits a multi-exponential decay with a
standalone :mod:`scipy` optimiser. That is self-contained and fast, but its
results are plain floats: they cannot be linked to another fit's parameters and
carry no error estimates from ChiSurf's covariance machinery.

This module fits the *same* problem on the models BFF owns instead -- the
``tcspc_lifetime`` and ``tcspc_fret_gaussian`` descriptions -- so the result is a
live :class:`~chisurf.core.fitting.fit.Fit` whose parameters support the ordinary
linking, bounds and error-estimate surface.

The module is Qt-free and importable headlessly.
"""
from __future__ import annotations

import numpy as np

__all__ = ["build_lifetime_fit", "fit_lifetime_model",
           "build_fret_fit", "fit_fret_model"]


def _set_port(problem, canonical: str, value: float) -> None:
    """Write a parameter whatever its lock; a caller's number means that number."""
    port = problem.get_parameter(canonical)
    held = port.fixed
    port.fixed = False
    port.value = float(value)
    port.fixed = held


def _parameters(model) -> dict:
    return {p.canonical_id: p for p in model.parameters_all if not getattr(p, "is_output", False)}


def _described_fit(family, decay, *, bin_width, irf, start_bin, stop_bin, period, scalars=None,
                   overrides=None):
    """A :class:`Fit` of a BFF-described TCSPC model over ``decay``, standing complete.

    What every TCSPC description shares: the decay on its time axis, the fit
    window, the measured or modelled IRF, periodic or single convolution and an
    autoscaled ``n0``. ``overrides`` are ``{canonical: (initial, lower, upper)}``
    applied as the caller's bounds before the model is built.
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
    t = np.arange(n_bins, dtype=float) * dt
    data = chisurf.core.data.DataCurve(x=t, y=y, ey=np.sqrt(np.maximum(y, 1.0)))
    stop = n_bins - 1 if stop_bin is None else int(stop_bin)
    stop = int(np.clip(stop, 0, n_bins - 1))
    start = int(np.clip(int(start_bin), 0, max(0, stop - 1)))

    fit = Fit(model_class=for_family(family), data=data, xmin=start, xmax=stop)
    model = fit.model
    model.set_scalar("dt", dt)
    periodic = period is not None and float(period) > 0
    # Without excitation repeating inside the window, the period only bounds
    # what the description derives from it; the window is the natural scale.
    model.set_scalar("period", float(period) if periodic else n_bins * dt)
    model.set_scalar("periodic_excitation", 1.0 if periodic else 0.0)
    model.set_scalar("autoscale", 1.0)
    for name, value in (scalars or {}).items():
        model.set_scalar(name, float(value))
    if irf is not None:
        irf_y = np.zeros(n_bins, dtype=float)
        measured = np.asarray(irf, dtype=float).ravel()[:n_bins]
        irf_y[:measured.size] = measured
        model.set_dataset("response", chisurf.core.curve.Curve(x=t, y=irf_y))
    else:
        model.set_scalar("generated_response", 1.0)
    for canonical, (initial, lower, upper) in (overrides or {}).items():
        model._spec.set_parameter(canonical, float(initial), True, float(lower), float(upper))
    problem = model.problem
    if problem is None:
        raise ValueError(f"the {family} model is missing " + ", ".join(model.missing))
    return fit, model, problem, (start, stop)


def _hold_instrument(model, problem, *, irf, background, fit_background, fit_scatter, fit_irf,
                     irf_width, irf_skew, extra=None):
    """The instrument's starting values and which of its parameters are fitted.

    ``background`` is counts per channel, as the caller measures it; the
    instrument takes it as a fraction of the fluorescence total, converted at
    the starting curve with the scale the data imply.
    """
    from chisurf.core.fluorescence.tcspc.instrument import fluorescence_total, set_absolute_instrument

    data = np.asarray(model.fit.data.y, dtype=float)
    total = fluorescence_total(model)
    n0 = max(float(data.sum()) - float(background) * data.size, 1.0) / total if total > 0 else 1.0
    set_absolute_instrument(model, n0, 0.0, float(background))
    if irf is None:
        _set_port(problem, "instrument.irf_width", abs(float(irf_width)))
        _set_port(problem, "instrument.irf_shape", float(irf_skew))
    free = {
        "instrument.n0": False,               # autoscaled
        "instrument.background": bool(fit_background),
        "instrument.scatter": bool(fit_scatter),
        # A measured IRF's timing genuinely drifts; pinning it biased the lifetimes.
        "instrument.timeshift": True,
        # A measured IRF is data, not a model: only a modelled one has a shape to fit.
        "instrument.irf_width": bool(fit_irf) and irf is None,
        "instrument.irf_shape": bool(fit_irf) and irf is None,
        **(extra or {}),
    }
    parameters = _parameters(model)
    for canonical, is_free in free.items():
        parameters[canonical].fixed = not is_free


def _irf_report(model, *, irf, bin_width) -> dict:
    from chisurf.core.fluorescence.tcspc.instrument import absolute_instrument

    value = {k: float(p.value) for k, p in _parameters(model).items()}
    counts = absolute_instrument(model)
    shift = value["instrument.timeshift"]
    irf_peak = None
    if irf is None:
        problem = model.problem
        active = problem.get_active_structure()
        prompt = np.asarray(problem.get_structure_output(active, f"{active}.generated_response"), dtype=float)
        irf_peak = (float(np.argmax(prompt)) + shift) * float(bin_width)
    return {
        # Counts, as the scipy fitter this stands in for reports them: the
        # instrument's fractions at the fitted curve.
        "background": counts["background"],
        "scatter": counts["scatter"],
        # Width is magnitude-only, so report it as such.
        "irf_width": abs(value["instrument.irf_width"]),
        "irf_skew": value["instrument.irf_shape"],
        "irf_shift": shift,
        "irf_peak": irf_peak,
    }


def _misfit(model) -> dict:
    wres = np.asarray(model.weighted_residuals, dtype=float)
    return {
        "reconstruction": np.asarray(model.y, dtype=float),
        "weighted_residuals": wres,
        "chi2_reduced": float(np.sum(wres ** 2) / max(1, wres.size)),
    }


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

    fit, model, problem, window = _described_fit(
        "tcspc_lifetime", decay, bin_width=bin_width, irf=irf, start_bin=start_bin,
        stop_bin=stop_bin, period=period, scalars={"max_components": max(3, n)},
        # Lifetime bounds are the caller's; the description's (up to the period)
        # would otherwise stand.
        overrides={f"lifetime.tau.{k}": (tau, lo, hi) for k, tau in enumerate(taus)})
    model.structure = f"lifetime.components.{n}"
    for k in range(n):
        _set_port(problem, f"lifetime.amplitude.{k}", 1.0 / n)
        _set_port(problem, f"lifetime.tau.{k}", float(taus[k]))
    _hold_instrument(model, problem, irf=irf, background=background, fit_background=fit_background,
                     fit_scatter=fit_scatter, fit_irf=fit_irf, irf_width=irf_width, irf_skew=irf_skew)
    model.find_parameters()
    fit.fit_range = window
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
    parameters = _parameters(m)

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
    return {
        "lifetimes": taus,
        "amplitudes": amps,
        "lifetime_spectrum": spectrum,
        "lifetime_errors": tau_err,
        "amplitude_errors": amp_err,
        **_misfit(m),
        **_irf_report(m, irf=irf, bin_width=bin_width),
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

    Uses BFF's ``tcspc_fret_gaussian`` model, so each state is a Gaussian
    distance distribution whose **mean and species fraction are fitted
    parameters** (the width is held at ``sigma``), alongside the donor-only
    fraction. That is a
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

    fit, model, problem, window = _described_fit(
        "tcspc_fret_gaussian", decay, bin_width=bin_width, irf=irf, start_bin=start_bin,
        stop_bin=stop_bin, period=period, scalars={"max_components": max(3, n)},
        overrides={f"distance.mean.{k}": (r, r_lo, r_hi) for k, r in enumerate(distances)})
    model.structure = f"tcspc_fret_gaussian.components.{n}"
    for k, r in enumerate(distances):
        _set_port(problem, f"distance.mean.{k}", float(r))
        _set_port(problem, f"distance.sigma.{k}", float(sigma))
        _set_port(problem, f"distance.amplitude.{k}", 1.0 / n)
    # The donor-only decay the FRET rates are measured against.
    _set_port(problem, "donor.amplitude.0", 1.0)
    _set_port(problem, "donor.tau.0", float(donor_lifetime))
    _set_port(problem, "fret.tau0", float(donor_lifetime))
    _set_port(problem, "fret.forster_radius", r0)
    _set_port(problem, "fret.x_donly", float(x_donor_only))
    _hold_instrument(model, problem, irf=irf, background=background, fit_background=fit_background,
                     fit_scatter=fit_scatter, fit_irf=fit_irf, irf_width=irf_width, irf_skew=irf_skew,
                     extra={"fret.x_donly": bool(fit_donor_only),
                            "donor.tau.0": bool(fit_donor_lifetime),
                            "fret.forster_radius": False, "fret.tau0": False})
    model.find_parameters()
    fit.fit_range = window
    model.update()
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
    m.update()
    n = max(1, int(kwargs.get("n_states", 2)))
    value = {k: float(p.value) for k, p in _parameters(m).items()}

    distances = np.abs([value[f"distance.mean.{k}"] for k in range(n)])
    sigmas = np.array([value[f"distance.sigma.{k}"] for k in range(n)])
    raw = np.abs([value[f"distance.amplitude.{k}"] for k in range(n)])
    fractions = raw / (float(raw.sum()) or 1.0)
    order = np.argsort(distances)
    distances, sigmas, fractions = distances[order], sigmas[order], fractions[order]

    r0 = value["fret.forster_radius"]
    efficiencies = 1.0 / (1.0 + (distances / r0) ** 6)
    return {
        "distances": distances,
        "sigmas": sigmas,
        "fractions": fractions,
        "efficiencies": efficiencies,
        "donor_only_fraction": abs(value["fret.x_donly"]),
        "forster_radius": r0,
        "donor_lifetime": value["fret.tau0"],
        # Same IRF reporting as the lifetime fit, so callers can write the fitted
        # prompt back to a detector regardless of which fit produced it.
        **_irf_report(m, irf=kwargs.get("irf"), bin_width=kwargs["bin_width"]),
        **_misfit(m),
        "fit": fit,
        "model": m,
    }
