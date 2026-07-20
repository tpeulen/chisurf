"""Shared adapters for detector-resolved fluorescence decay computation.

This module is the integration point between reusable lifetime spectra and the
existing ChiSurf fit/model stack. Consumers should ask a model to generate its
decay so IRF convolution, polarization, scatter/background, pile-up,
linearization, detector response, and model-specific corrections remain in one
authoritative path.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np


def afterpulse_decay_pattern(n_bins: int) -> np.ndarray:
    """Return a normalized constant microtime pattern for afterpulsing.

    Detector dark counts and temporally uniform afterpulsing enter a TCSPC
    histogram as a constant offset.  Keeping this basis pattern here gives
    fitting, filter calculation, and simulation code one shared definition.
    """
    count = int(n_bins)
    if count <= 0:
        raise ValueError("n_bins must be positive")
    return np.full(count, 1.0 / count, dtype=float)


def scattered_light_decay_pattern(irf: Any, n_bins: int) -> np.ndarray:
    """Return a normalized IRF-shaped scattered-light pattern.

    The supplied IRF is cropped or zero-padded to the decay window. Negative,
    empty, or non-finite responses are rejected because they cannot represent
    a photon-count distribution.
    """
    count = int(n_bins)
    if count <= 0:
        raise ValueError("n_bins must be positive")
    response = np.asarray(irf, dtype=float).ravel()
    if response.size == 0 or np.any(~np.isfinite(response)) or np.any(response < 0.0):
        raise ValueError("irf must be a non-empty, finite, non-negative vector")
    pattern = np.zeros(count, dtype=float)
    copied = min(count, response.size)
    pattern[:copied] = response[:copied]
    integral = pattern.sum()
    if integral <= 0.0:
        raise ValueError("irf must contain a positive value inside the decay window")
    return pattern / integral


def optimize_synthetic_scatter_pattern(
    total_decay: Any,
    component_decays: Iterable[Any],
    *,
    bin_width_ns: float,
    initial_fwhm_ns: float = 0.2,
    shape: float = 0.0,
    include_constant: bool = True,
) -> tuple[np.ndarray, dict[str, float]]:
    """Fit a synthetic IRF shape and scatter amplitude to one detector decay.

    This mirrors the TCSPC forward model's additive ``scatter * IRF`` term.
    The prompt position and Gaussian FWHM are optimized while every candidate
    is linearly unmixed with the supplied species patterns (and optionally a
    constant afterpulse basis). The returned IRF is normalized; its fitted
    amplitude remains the responsibility of the caller's unmix/filter step.
    """
    from scipy.optimize import lsq_linear

    from chisurf.core.fluorescence.tcspc.irf import detect_rising_edge, synthetic_irf

    total = np.asarray(total_decay, dtype=float).ravel()
    if total.size < 3 or np.any(~np.isfinite(total)) or np.any(total < 0.0):
        raise ValueError("total_decay must be a finite, non-negative decay")
    dt = float(bin_width_ns)
    if not np.isfinite(dt) or dt <= 0.0:
        raise ValueError("bin_width_ns must be positive and finite")
    signal = []
    for index, decay in enumerate(component_decays):
        pattern = np.asarray(decay, dtype=float).ravel()
        if (
            pattern.size != total.size
            or np.any(~np.isfinite(pattern))
            or np.any(pattern < 0.0)
            or pattern.sum() <= 0.0
        ):
            raise ValueError(
                f"component_decays[{index}] must match total_decay, be non-negative, and be non-zero"
            )
        signal.append(pattern / pattern.sum())

    time = np.arange(total.size, dtype=float) * dt
    prompt_bin = detect_rising_edge(total)
    initial_center = float(np.clip(prompt_bin * dt, time[0], time[-1]))
    initial_fwhm = float(np.clip(initial_fwhm_ns, dt, max(dt, time[-1] / 3.0)))
    fixed = list(signal)
    if include_constant:
        fixed.append(afterpulse_decay_pattern(total.size))
    scale = np.sqrt(np.maximum(total, 1.0))

    def candidate(parameters: np.ndarray) -> np.ndarray:
        return synthetic_irf(
            time,
            center_ns=float(parameters[0]),
            fwhm_ns=float(parameters[1]),
            shape=float(shape),
        )

    def objective(parameters: np.ndarray) -> float:
        design = np.column_stack(fixed + [candidate(parameters)])
        fitted = lsq_linear(
            design / scale[:, None], total / scale, bounds=(0.0, np.inf)
        )
        residual = (total - design @ fitted.x) / scale
        return float(residual @ residual)

    centers = np.clip(
        initial_center + np.arange(-3, 4, dtype=float) * dt,
        time[0],
        time[-1],
    )
    widths = np.maximum(dt, initial_fwhm * np.array([0.6, 0.8, 1.0, 1.25, 1.6]))
    candidates = [np.array([center, width]) for center in centers for width in widths]
    parameters = min(candidates, key=objective)
    pattern = scattered_light_decay_pattern(candidate(parameters), total.size)
    return pattern, {
        "center_ns": float(parameters[0]),
        "fwhm_ns": float(parameters[1]),
        "shape": float(shape),
        "objective": objective(parameters),
    }


def sample_decay_shot_noise(
    decay: Any,
    *,
    photon_count: float | None = None,
    seed: int | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Poisson-sample an expected fluorescence decay histogram.

    When ``photon_count`` is given, *decay* is normalized and scaled to that
    expected integrated count before sampling. Otherwise its values are treated
    directly as expected counts. A seed makes synthetic projects reproducible;
    callers performing repeated simulations may instead pass a generator.
    """
    expected = np.asarray(decay, dtype=float).ravel()
    if expected.size == 0 or np.any(~np.isfinite(expected)) or np.any(expected < 0.0):
        raise ValueError("decay must be a non-empty, finite, non-negative vector")
    if not np.any(expected > 0.0):
        raise ValueError("decay must contain at least one positive value")
    if photon_count is not None:
        count = float(photon_count)
        if not np.isfinite(count) or count <= 0.0:
            raise ValueError("photon_count must be positive and finite")
        expected = expected / expected.sum() * count
    if rng is not None and seed is not None:
        raise ValueError("pass either rng or seed, not both")
    generator = rng if rng is not None else np.random.default_rng(seed)
    return generator.poisson(expected).astype(float)


def synthetic_decay(
    n_bins: int,
    lifetimes: Any,
    *,
    amplitudes: Any | None = None,
    bin_width: float = 1.0,
    start_bin: int = 0,
    irf: Any | None = None,
    period: float | None = None,
    time_shift: float = 0.0,
    normalize: bool = True,
    photon_count: float | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """Generate a causal multi-exponential fluorescence-decay histogram.

    This is the single canonical synthetic-decay generator: the ideal decay is
    built from the interleaved lifetime spectrum with the shared
    :func:`chisurf.core.fluorescence.general.calculate_fluorescence_decay`, IRF
    convolution uses the shared TCSPC kernel
    (:func:`chisurf.core.fluorescence.tcspc.convolve.convolve_decay_nb`, the same
    trapezoidal ``fconv`` family the fit models use), and finite-count sampling
    uses :func:`sample_decay_shot_noise` — so no exponential/convolution/noise
    mathematics is duplicated in callers.

    ``lifetimes`` and ``bin_width`` share a unit (normally ns). Multiple
    lifetimes with ``amplitudes`` give a discrete spectrum. When ``irf`` is
    supplied it is normalized (cropped/zero-padded to the window) and convolved
    with the ideal decay. ``time_shift`` applies a (fractional-bin) periodic
    colour shift to the IRF before convolution. ``period`` (ns) switches to a
    periodic convolution that models the finite laser repetition period — the
    unrelaxed decay of earlier pulses wraps into the window via the geometric
    inter-pulse tail; timing then comes from the IRF position rather than
    ``start_bin``. ``photon_count`` Poisson-samples a finite observation
    (``seed`` for reproducibility). ``normalize=True`` returns a unit-sum pattern.
    """
    from chisurf.core.fluorescence.general import calculate_fluorescence_decay

    n = int(n_bins)
    if n <= 0:
        raise ValueError("n_bins must be positive")
    if bin_width <= 0.0:
        raise ValueError("bin_width must be positive")
    if not 0 <= int(start_bin) < n:
        raise ValueError("start_bin must lie inside the decay histogram")

    taus = np.atleast_1d(np.asarray(lifetimes, dtype=float))
    if taus.ndim != 1 or taus.size == 0 or np.any(~np.isfinite(taus)) or np.any(taus <= 0.0):
        raise ValueError("lifetimes must contain positive finite values")

    if amplitudes is None:
        amps = np.ones(taus.size, dtype=float)
    else:
        amps = np.atleast_1d(np.asarray(amplitudes, dtype=float))
        if amps.size == 1 and taus.size > 1:
            amps = np.repeat(amps, taus.size)
        if amps.shape != taus.shape:
            raise ValueError("amplitudes must match lifetimes")
        if np.any(~np.isfinite(amps)) or np.any(amps < 0.0) or not np.any(amps > 0.0):
            raise ValueError("amplitudes must be finite, non-negative, and not all zero")

    time = (np.arange(n, dtype=float) - int(start_bin)) * float(bin_width)
    causal_time = np.maximum(time, 0.0)
    # Interleave (amp, tau, ...) for the shared spectrum→decay builder.
    spectrum = np.empty(taus.size * 2, dtype=float)
    spectrum[0::2] = amps
    spectrum[1::2] = taus
    _, decay = calculate_fluorescence_decay(spectrum, causal_time, normalize=False)
    decay = np.asarray(decay, dtype=float)
    decay[time < 0.0] = 0.0

    if irf is not None:
        from chisurf.core.fluorescence.tcspc.convolve import (
            convolve_decay_nb,
            convolve_lifetime_spectrum_periodic_nb,
            periodic_shift,
        )

        response = scattered_light_decay_pattern(irf, n)  # normalized, length n
        if time_shift:
            # Sub-bin IRF time shift (colour shift), wrapped over the window.
            response = periodic_shift(response, float(time_shift) / float(bin_width))
        if period is not None and float(period) > 0.0:
            # Finite laser repetition period: the decay from earlier pulses has
            # not fully relaxed and wraps into the window. The periodic kernel
            # adds the geometric inter-pulse tail (1/(1-exp(-period/tau))). Timing
            # here comes from the IRF position, not ``start_bin``.
            convolved = np.zeros(n, dtype=float)
            convolve_lifetime_spectrum_periodic_nb(
                convolved, spectrum, response, 0, n, n,
                float(period), float(bin_width), n,
            )
            decay = convolved
        else:
            decay = convolve_decay_nb(decay, response, 0, n, float(bin_width))
        decay = np.maximum(np.asarray(decay, dtype=float), 0.0)

    if photon_count is not None:
        decay = sample_decay_shot_noise(decay, photon_count=photon_count, seed=seed)

    if normalize:
        decay_sum = decay.sum()
        if decay_sum <= 0.0:
            raise ValueError("synthetic decay has zero integral")
        decay = decay / decay_sum
    return decay


def _gaussian_grid(mean: float, sigma: float, n_samples: int) -> tuple[np.ndarray, np.ndarray]:
    """Return a positive, normalized discretization of a normal distribution."""
    if not np.isfinite(mean) or mean <= 0.0:
        raise ValueError("distribution mean must be positive and finite")
    if not np.isfinite(sigma) or sigma < 0.0:
        raise ValueError("distribution sigma must be finite and non-negative")
    if sigma == 0.0:
        return np.array([mean]), np.array([1.0])
    count = max(int(n_samples), 3)
    lower = max(np.finfo(float).eps, mean - 4.0 * sigma)
    upper = mean + 4.0 * sigma
    values = np.linspace(lower, upper, count)
    weights = np.exp(-0.5 * ((values - mean) / sigma) ** 2)
    return values, weights / weights.sum()


def _distance_grid(
    mean: float,
    sigma: float,
    n_samples: int,
    distribution: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Discretize a scalar Gaussian or physical 3-D Gaussian distance model."""
    if distribution == "gaussian":
        return _gaussian_grid(mean, sigma, n_samples)
    if distribution != "gaussian_3d":
        raise ValueError("distance_distribution must be 'gaussian' or 'gaussian_3d'")
    if not np.isfinite(mean) or mean < 0.0:
        raise ValueError("mean distance must be finite and non-negative")
    if not np.isfinite(sigma) or sigma < 0.0:
        raise ValueError("distance sigma must be finite and non-negative")
    if sigma == 0.0:
        if mean <= 0.0:
            raise ValueError("a zero-width distance distribution requires a positive mean")
        return np.array([mean]), np.array([1.0])

    count = max(int(n_samples), 3)
    distances = np.linspace(np.finfo(float).eps, max(mean + 5.0 * sigma, 5.0 * sigma), count)
    from chisurf.core.math.functions.rdf import distance_between_gaussian

    weights = distance_between_gaussian(distances, mean, sigma, normalize=True)
    weights = np.clip(weights, 0.0, None)
    if weights.sum() <= 0.0:
        raise ValueError("distance distribution has zero integral")
    return distances, weights / weights.sum()


def synthetic_component_decay(
    n_bins: int,
    component: dict[str, Any],
    *,
    irf: Any | None = None,
) -> np.ndarray:
    """Generate a decay from a persisted synthetic-component definition.

    Supported models: ``lifetime`` (one exponential), ``lifetime_spectrum``
    (discrete amplitudes/lifetimes), ``gaussian_lifetime`` (a normal lifetime
    distribution truncated at zero), and ``gaussian_distance`` (a scalar Gaussian
    or physical 3-D Gaussian donor-acceptor distance distribution converted to
    FRET-shortened donor lifetimes). Builds on :func:`synthetic_decay`.
    """
    model = str(component.get("model", "lifetime"))
    bin_width = float(component.get("bin_width", 1.0))
    start_bin = int(component.get("start_bin", 0))
    n_samples = int(component.get("n_samples", 81))
    lifetimes: Any
    amplitudes: Any

    if model == "lifetime":
        lifetimes = float(component["lifetime"])
        amplitudes = None
    elif model == "lifetime_spectrum":
        lifetimes = np.asarray(component["lifetimes"], dtype=float)
        amplitudes = np.asarray(component.get("amplitudes", np.ones(lifetimes.size)), dtype=float)
    elif model == "gaussian_lifetime":
        lifetimes, amplitudes = _gaussian_grid(
            float(component["mean_lifetime"]),
            float(component["sigma_lifetime"]),
            n_samples,
        )
    elif model == "gaussian_distance":
        donor_lifetime = float(component["donor_lifetime"])
        forster_radius = float(component["forster_radius"])
        kappa2 = float(component.get("kappa2", 2.0 / 3.0))
        if donor_lifetime <= 0.0 or forster_radius <= 0.0 or kappa2 <= 0.0:
            raise ValueError("donor_lifetime, forster_radius, and kappa2 must be positive")
        distances, amplitudes = _distance_grid(
            float(component["mean_distance"]),
            float(component["sigma_distance"]),
            n_samples,
            str(component.get("distance_distribution", "gaussian")),
        )
        from chisurf.core.fluorescence.general import distance_to_fret_rate_constant

        fret_rates = distance_to_fret_rate_constant(
            distances, forster_radius, donor_lifetime, kappa2
        )
        lifetimes = 1.0 / (1.0 / donor_lifetime + fret_rates)
    else:
        raise ValueError(f"unsupported synthetic component model: {model}")

    period = component.get("period_ns")
    return synthetic_decay(
        n_bins,
        lifetimes,
        amplitudes=amplitudes,
        bin_width=bin_width,
        start_bin=start_bin,
        irf=irf,
        period=(float(period) if period else None),
        time_shift=float(component.get("time_shift_ns", 0.0)),
        photon_count=(
            float(component["photon_count"])
            if component.get("shot_noise", False) else None
        ),
        seed=(int(component.get("noise_seed", 0)) if component.get("shot_noise", False) else None),
    )


def validate_lifetime_spectrum(spectrum: Any) -> np.ndarray:
    """Return a validated interleaved ``(amplitude, lifetime, ...)`` spectrum."""
    values = np.asarray(spectrum, dtype=float).ravel()
    if values.size < 2 or values.size % 2:
        raise ValueError("lifetime spectrum must contain amplitude/lifetime pairs")
    if np.any(~np.isfinite(values)):
        raise ValueError("lifetime spectrum must contain only finite values")
    if np.any(values[1::2] <= 0.0):
        raise ValueError("lifetimes must be positive")
    if not np.any(values[0::2] != 0.0):
        raise ValueError("at least one lifetime amplitude must be non-zero")
    return values


def lifetime_spectrum_from_model(model: Any) -> np.ndarray:
    """Read the effective lifetime spectrum exposed by a ChiSurf model."""
    for attribute in ("lifetime_spectrum", "donor_lifetime_spectrum"):
        try:
            spectrum = getattr(model, attribute)
        except Exception:
            continue
        if spectrum is not None:
            return validate_lifetime_spectrum(spectrum)
    raise ValueError(f"{type(model).__name__} does not expose a lifetime spectrum")


def compute_model_decay(model: Any, lifetime_spectrum: Any | None = None) -> np.ndarray:
    """Compute one decay through a model while restoring its visible state.

    The model's own ``update_model`` implementation is deliberately used. This
    keeps detector- and experiment-specific corrections authoritative and avoids
    duplicating TCSPC forward-model mathematics in callers.
    """
    spectrum = (
        lifetime_spectrum_from_model(model)
        if lifetime_spectrum is None
        else validate_lifetime_spectrum(lifetime_spectrum)
    )
    update_model = getattr(model, "update_model", None)
    if not callable(update_model):
        raise ValueError(f"{type(model).__name__} cannot compute a decay")

    original_y = np.asarray(getattr(model, "y", []), dtype=float).copy()
    n0_parameter = getattr(getattr(model, "convolve", None), "_n0", None)
    n0_value = getattr(n0_parameter, "value", None)
    n0_fixed = getattr(n0_parameter, "fixed", None)
    try:
        update_model(lifetime_spectrum=spectrum)
        decay = np.asarray(getattr(model, "y"), dtype=float).ravel().copy()
    finally:
        if n0_parameter is not None and n0_value is not None:
            n0_parameter.value = n0_value
            if n0_fixed is not None:
                n0_parameter.fixed = n0_fixed
        if original_y.size:
            model.y = original_y

    if decay.size == 0 or np.any(~np.isfinite(decay)):
        raise ValueError("model produced an empty or non-finite decay")
    return np.maximum(decay, 0.0)


def _fit_members(fit: Any) -> list[Any]:
    grouped = getattr(fit, "grouped_fits", None)
    if isinstance(grouped, Iterable):
        members = list(grouped)
        if members:
            return members
    return [fit]


def compute_detector_patterns_from_fit(
    fit: Any,
    lifetime_spectrum: Any | None = None,
    detector_names: list[str] | None = None,
) -> dict[str, np.ndarray]:
    """Compute detector-resolved decay patterns from a Fit or FitGroup.

    Multi-output models may implement ``compute_detector_patterns`` directly.
    Otherwise each member of a grouped fit is treated as one detector-specific
    model. When ``detector_names`` matches the member count, those stable names
    are used; data-set names and ``__default__`` remain available as fallbacks.
    """
    model = getattr(fit, "model", None)
    multi_output = getattr(model, "compute_detector_patterns", None)
    if callable(multi_output):
        raw = multi_output(lifetime_spectrum=lifetime_spectrum)
        multi_patterns = {
            str(name): np.maximum(np.asarray(decay, dtype=float).ravel(), 0.0)
            for name, decay in dict(raw).items()
        }
        if multi_patterns:
            # ``__default__`` is an alias, not another detector observation.
            multi_patterns.setdefault("__default__", next(iter(multi_patterns.values())))
            return multi_patterns

    members = _fit_members(fit)
    names = list(detector_names or [])
    patterns: dict[str, np.ndarray] = {}
    for index, member in enumerate(members):
        member_model = getattr(member, "model", None)
        if member_model is None:
            continue
        decay = compute_model_decay(member_model, lifetime_spectrum)
        if len(names) == len(members):
            patterns[str(names[index])] = decay
        data_name = getattr(getattr(member, "data", None), "name", None)
        if data_name:
            patterns.setdefault(str(data_name), decay)
        patterns.setdefault(f"detector_{index}", decay)
        patterns.setdefault("__default__", decay)
    if not patterns:
        raise ValueError("fit does not contain a decay-producing model")
    return patterns


__all__ = [
    "afterpulse_decay_pattern",
    "compute_detector_patterns_from_fit",
    "compute_model_decay",
    "lifetime_spectrum_from_model",
    "optimize_synthetic_scatter_pattern",
    "sample_decay_shot_noise",
    "scattered_light_decay_pattern",
    "synthetic_component_decay",
    "synthetic_decay",
    "validate_lifetime_spectrum",
]
