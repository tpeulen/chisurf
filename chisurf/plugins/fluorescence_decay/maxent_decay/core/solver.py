"""Maximum-entropy TCSPC analysis for the MaxEnt decay tool, run by BFF.

The inversion is the engine's (``tcspc_maxent_lifetime`` / ``tcspc_maxent_fret``:
a MaxEntSpectrum over TCSPCDecay's basis, IMP.bff's Skilling-Bryan programme
underneath, ported from tttrlib); the MEM TCSPC model that used to live in tttrlib, with its own
convolution and IRF shift, is gone. This module keeps the tool's contract --
the arguments the GUI passes and the result dictionary the plots, the sampler
and the saved JSON read -- and translates both ways.

What the translation fixes: ``lamp_scatter`` multiplies the lamp as given
(after the lamp background is taken off), as it always did; ``timeshift``
keeps the tool's sign (TCSPCDecay shifts the other way); a single excitation (``period`` None or <= 0) is a period long
enough that no earlier pulse is left. The nuisance search is BFF's fit of the
free instrument parameters instead of a coordinate walk.
"""

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

MIN_PROB = 1e-12


def load_tcspc_two_column(path: str) -> np.ndarray:
    """Load a two-column TCSPC text file ("Chan  Data") like extract2c.c.

    This function scans all lines, attempts to parse two numbers from the
    beginning of each line, and returns the second column (counts) as a
    1D float array. Header/comment lines are ignored.
    """
    chan = []
    data = []
    with open(path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            try:
                x = float(parts[0])
                y = float(parts[1])
            except ValueError:
                continue
            chan.append(x)
            data.append(y)
    if not data:
        return np.zeros(0, dtype=float)
    return np.asarray(data, dtype=float)


def autofitrange(lamp: np.ndarray, decay: np.ndarray, threshold: float = 10.0) -> tuple[int, int]:
    """Port of gfit/autofitrange.m.

    Parameters
    ----------
    lamp, decay : array_like
        1D arrays of instrument response and decay counts.
    threshold : float
        Intensity threshold for the decay tail (default 100, as in MATLAB).

    Returns
    -------
    start, stop : int
        0-based inclusive indices defining the fit range.
    """
    lamp = np.asarray(lamp, dtype=float).ravel()
    decay = np.asarray(decay, dtype=float).ravel()
    if lamp.size == 0 or decay.size == 0:
        return 0, max(0, min(lamp.size, decay.size) - 1)

    start = int(np.argmax(lamp))
    peak = int(np.argmax(decay))

    below = np.nonzero(decay < threshold)[0]
    if below.size == 0:
        candidates = np.array([decay.size - 1], dtype=int)
    else:
        candidates = np.concatenate((below, np.array([decay.size - 1], dtype=int)))

    greater = candidates[candidates > peak]
    if greater.size == 0:
        stop = int(candidates[-1])
    else:
        stop = int(greater[0])

    if stop < start:
        stop = start
    return start, stop


def auto_fit_range_tcspc(
    decay: np.ndarray,
    count_threshold: float = 10.0,
    area: float = 0.999,
    start_fraction: float = 0.9,
    start_at_peak: bool = True,
    skip_first: int = 0,
    skip_last: int = 0,
) -> tuple[int, int]:
    """Auto fit range similar to chisurf.core.fluorescence.tcspc.initial_fit_range.

    Parameters
    ----------
    decay : array_like
        1D decay counts.
    count_threshold : float
        Minimum counts to consider a channel as part of the fit.
    area : float
        Fraction of total counts (from the start index onward) to include.
    start_fraction : float
        Fraction of the peak at which to start when ``start_at_peak`` is True.
    start_at_peak : bool
        If True, start where ``decay > start_fraction * max(decay)``; otherwise
        start where ``decay > count_threshold``.
    skip_first, skip_last : int
        Extra channels to skip at the beginning / end of the fit range.
    """
    decay = np.asarray(decay, dtype=float).ravel()
    n = decay.size
    if n == 0:
        return 0, 0

    if start_at_peak and decay.max() > 0.0:
        lvl = start_fraction * float(decay.max())
        idx = np.nonzero(decay > lvl)[0]
    else:
        idx = np.nonzero(decay > count_threshold)[0]
    if idx.size == 0:
        start = 0
    else:
        start = int(idx[0])

    if start >= n - 1:
        return max(0, n - 1), max(0, n - 1)

    tail = decay[start:]
    s_total = float(np.sum(tail))
    if s_total <= 0.0:
        stop = n - 1
    else:
        cumsum = np.cumsum(tail, dtype=float)
        area_idx = np.nonzero(cumsum >= area * s_total)[0]
        if area_idx.size == 0:
            stop = n - 1
        else:
            stop = int(start + area_idx[0])

    stop = min(max(stop, start), n - 1)

    if decay[stop] < count_threshold:
        rev = np.nonzero(decay[::-1] >= count_threshold)[0]
        if rev.size > 0:
            stop = n - int(rev[0]) - 1

    while (stop + 1) < n and decay[stop] >= count_threshold:
        stop += 1

    start = min(start + int(skip_first), n - 1)
    stop = min(max(stop - int(skip_last), start), n - 1)
    return start, stop


def _lamp_background(lamp: np.ndarray, irf_background: float | None) -> float:
    """The constant under the lamp: the tail median, unless given."""
    if irf_background is not None:
        return float(irf_background)
    tail = lamp[-min(500, lamp.size) :]
    return float(np.median(tail)) if tail.size else 0.0


def _fit_window(decay: np.ndarray, fitrange, fit_start_fraction: float) -> tuple[int, int]:
    if fitrange is None:
        return auto_fit_range_tcspc(
            decay,
            count_threshold=100.0,
            area=0.999,
            start_fraction=float(fit_start_fraction),
            start_at_peak=True,
        )
    start, stop = int(fitrange[0]), int(fitrange[1])
    return max(0, start), min(decay.size - 1, stop)


def _grid(values: np.ndarray, what: str) -> tuple[float, float, int]:
    values = np.asarray(values, dtype=float).ravel()
    values = values[values > 0.0]
    if values.size < 2:
        raise ValueError(f"the {what} grid needs at least two positive points")
    if not np.allclose(np.diff(values), values[1] - values[0], rtol=1e-6, atol=1e-12):
        raise ValueError(f"the {what} grid must be evenly spaced")
    return float(values[0]), float(values[-1]), int(values.size)


def _solve(
    family: str,
    decay,
    lamp,
    dt,
    grid,
    fitrange,
    fit_start_fraction,
    period,
    nu,
    max_iter,
    prior,
    timeshift,
    background,
    lamp_scatter,
    irf_background,
    optimize_nuisance,
    extra_parameters: dict[str, tuple[float, bool, float, float]],
    scalars: dict[str, float] | None = None,
):
    import IMP.bff as bff

    decay = np.asarray(decay, dtype=float).ravel()
    lamp = np.asarray(lamp, dtype=float).ravel()
    n = decay.size
    if lamp.size != n:
        lamp = np.resize(lamp, n)
    start, stop = _fit_window(decay, fitrange, fit_start_fraction)
    lamp_bg = _lamp_background(lamp, irf_background)
    lamp_area = float(np.clip(lamp - lamp_bg, 0.0, None).sum())
    low, high, bins = _grid(grid, "lifetime" if family.endswith("lifetime") else "distance")

    data = bff.FitDataset()
    data.set_values_array(np.ascontiguousarray(decay))
    data.set_noise_family(bff.FIT_NOISE_FAMILY_POISSON)
    mask = np.zeros(n)
    mask[start : stop + 1] = 1.0
    data.set_mask_array(np.ascontiguousarray(mask))
    response = bff.FitDataset()
    response.set_values_array(np.ascontiguousarray(lamp))

    spec = bff.ModelSearchSpec.from_name(family)
    spec.set_dataset("decay", data)
    spec.set_dataset("response", response)
    spec.set_scalar("dt", float(dt))
    single_shot = period is None or float(period) <= 0.0
    spec.set_scalar("period", 1.0e3 * n * float(dt) if single_shot else float(period))
    spec.set_scalar("max_iterations", float(max_iter))
    for name, value in (scalars or {}).items():
        spec.set_scalar(name, float(value))
    prior_port = bff.GraphPort([0.0])
    spec.set_port("maxent_prior", prior_port)
    free = bool(optimize_nuisance)
    parameters = {
        "maxent.log10_nu": (np.log10(float(nu)), False, -12.0, 6.0),
        "maxent.grid_from": (low, False, 0.0, 1e9),
        "maxent.grid_to": (high, False, 0.0, 1e9),
        "maxent.grid_bins": (float(bins), False, 2.0, 1e5),
        # The tool's shift moves the lamp the other way from TCSPCDecay's.
        "instrument.timeshift": (-float(timeshift), free, -20.0, 20.0),
        "instrument.background": (float(background), free, 0.0, 1e12),
        "instrument.response_background": (lamp_bg, free, 0.0, 1e12),
        "instrument.scatter": (float(lamp_scatter) * lamp_area, False, -1e12, 1e12),
        **extra_parameters,
    }
    for canonical, (value, is_free, lower, upper) in parameters.items():
        spec.set_parameter(canonical, float(value), bool(is_free), float(lower), float(upper))
    problem = spec.build()
    key = problem.get_structure_keys()[0]
    problem.activate_structure(key)
    for canonical, (value, _, _, _) in parameters.items():
        port = problem.get_parameter(canonical)
        held = port.fixed
        port.fixed = False
        port.value = float(value)
        port.fixed = held
    if prior is not None:
        prior_vec = np.asarray(prior, dtype=float).ravel()
        if prior_vec.size != bins:
            raise ValueError("prior must have same length as the grid")
        prior_port.set_value_vector(list(prior_vec))
    if free:
        config = bff.ModelSearchConfig()
        config.set_number_of_simulations(1)
        config.set_seed(0)
        search = bff.ModelSearch(problem)
        search.set_config(config)
        problem.activate_state(search.run().get_best_state())

    def port(node, name):
        return np.asarray(problem.get_structure_port(key, f"{key}.{node}", name), dtype=float)

    # The spectrum the basis was built over: the grid, or the FRET-quenched donor.
    source = "fret" if family.endswith("fret") else "grid"
    spectrum = np.asarray(problem.get_structure_output(key, f"{key}.{source}"), dtype=float)
    basis = port("basis", "basis").reshape(n, -1)
    amplitudes = port("maxent", "amplitudes")

    def value(canonical):
        return float(problem.get_parameter(canonical).value)

    return problem, key, port, spectrum, basis, amplitudes, (start, stop), value


def _result(decay, design, amplitudes, prepared, window, value, port, nu_input, prior, bins, dt):
    start, stop = window
    y = np.asarray(decay, dtype=float)[start : stop + 1]
    sigma = np.sqrt(np.maximum(y, 1.0))
    fit_additive = (
        value("instrument.background") + value("instrument.scatter") * prepared[start : stop + 1]
    )
    Fi = design[start : stop + 1] / sigma[:, None]
    M = float(y.size)
    y_w = (y - fit_additive) / sigma
    chisq = float(port("maxent", "chisq")[0])
    entropy = float(port("maxent", "entropy")[0])
    nu = float(port("maxent", "nu")[0])
    lamp_scatter = 0.0
    prior_vec = (
        np.full(bins, 1.0 / bins)
        if prior is None
        else np.maximum(np.asarray(prior, dtype=float), MIN_PROB)
        / np.sum(np.maximum(prior, MIN_PROB))
    )
    return {
        "p": amplitudes,
        "chisq": chisq,
        "S": entropy,
        "Q": chisq - 0.5 * nu * entropy,
        "chisq_pearson": float(port("maxent", "chisq_pearson")[0]),
        "converged": bool(port("maxent", "converged")[0]),
        "nu": nu,
        "nu_input": float(nu_input),
        "fitrange": (int(start), int(stop)),
        "dt": float(dt),
        "timeshift": -value("instrument.timeshift"),
        "background": value("instrument.background"),
        "irf_background": value("instrument.response_background"),
        "lamp_scatter": lamp_scatter,
        "fit_additive": fit_additive,
        "H": (2.0 / M) * (Fi.T @ Fi),
        "g0": (2.0 / M) * (y_w @ Fi),
        "y": y,
        "sigma": sigma,
        "Fi": Fi,
        "prior": prior_vec,
    }


def solve_lifetime_mem(
    decay: Sequence[float],
    lamp: Sequence[float],
    dt: float,
    tau: Sequence[float] | None = None,
    timeshift: float = 0.0,
    background: float = 0.0,
    lamp_scatter: float = 0.0,
    fitrange: tuple[int, int] | None = None,
    irf_background: float | None = None,
    fit_start_fraction: float = 0.9,
    nu: float = 1e-5,
    progress_cb: Callable[[int, float, float, float, float], None] | None = None,
    max_iter: int = 200,
    tol: float = 1e-4,
    period: float | None = None,
    optimize_nuisance: bool = False,
    nuisance_max_iter: int = 20,
    nuisance_step_timeshift: float | None = None,
    nuisance_step_background: float | None = None,
    nuisance_step_irf_background: float | None = None,
    nuisance_step_x_donly: float | None = None,
    nuisance_param_tol: float = 1e-3,
    prior: Sequence[float] | None = None,
) -> dict[str, Any]:
    """MEM analysis of TCSPC lifetimes over an evenly spaced lifetime grid.

    The default grid spans 1.0–4.0 ns in 0.01 ns steps. ``timeshift`` is the
    IRF shift in channels. With ``optimize_nuisance`` the timeshift, the
    background and the lamp background are fitted around the inversion.
    Returns the tool's result dictionary (``p``, ``tau``, ``Fi``, ``H``, ``g0``,
    ``y``, ``sigma``, ``fitrange``, ``fit_additive``, the instrument values used).
    """
    tau_arr = (
        np.arange(1.0, 4.0 + 1e-9, 0.01) if tau is None else np.asarray(tau, dtype=float).ravel()
    )
    problem, key, port, spectrum, basis, amplitudes, window, value = _solve(
        "tcspc_maxent_lifetime",
        decay,
        lamp,
        dt,
        tau_arr,
        fitrange,
        fit_start_fraction,
        period,
        nu,
        max_iter,
        prior,
        timeshift,
        background,
        lamp_scatter,
        irf_background,
        optimize_nuisance,
        {},
    )
    prepared = port("basis", "prepared_response")
    result = _result(
        decay, basis, amplitudes, prepared, window, value, port, nu, prior, amplitudes.size, dt
    )
    result.update(
        {
            "tau": port("maxent", "distribution")[1::2],
            "lamp_scatter": float(lamp_scatter),
            "nuisance_optimized": bool(optimize_nuisance),
        }
    )
    return result


def solve_fret_mem(
    decay: Sequence[float],
    lamp: Sequence[float],
    dt: float,
    R: Sequence[float] | None = None,
    tau0: float = 4.1,
    R0: float = 52.0,
    donly: Sequence[float] | None = None,
    x_donly: float = 0.0,
    timeshift: float = 0.0,
    background: float = 0.0,
    lamp_scatter: float = 0.0,
    fitrange: tuple[int, int] | None = None,
    irf_background: float | None = None,
    fit_start_fraction: float = 0.9,
    nu: float = 1e-5,
    progress_cb: Callable[[int, float, float, float, float], None] | None = None,
    max_iter: int = 200,
    tol: float = 1e-4,
    period: float | None = None,
    optimize_nuisance: bool = False,
    nuisance_max_iter: int = 20,
    nuisance_step_timeshift: float | None = None,
    nuisance_step_background: float | None = None,
    nuisance_step_irf_background: float | None = None,
    nuisance_step_x_donly: float | None = None,
    nuisance_param_tol: float = 1e-3,
    prior: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Maximum-entropy inversion of a FRET decay to a distance distribution.

    Each grid distance quenches the donor (``donly`` pairs ``[c1, tau1, ...]``,
    default ``[1, tau0]``) at ``k = (1/tau0)(R0/R)^6``; ``x_donly`` of the sample
    is donor only. The default grid is 18:0.5:120 Å, as in me_vin4_E.m.
    """
    R_arr = np.arange(18.0, 120.0 + 1e-9, 0.5) if R is None else np.asarray(R, dtype=float).ravel()
    donly_arr = (
        np.array([1.0, float(tau0)]) if donly is None else np.asarray(donly, dtype=float).ravel()
    )
    extra = {
        "fret.tau0": (float(tau0), False, 1e-9, 1e9),
        "fret.forster_radius": (float(R0), False, 1e-9, 1e9),
        "fret.kappa2": (2.0 / 3.0, False, 0.0, 4.0),
        "fret.x_donly": (float(x_donly), bool(optimize_nuisance), 0.0, 1.0),
    }
    for i in range(donly_arr.size // 2):
        extra[f"donor.amplitude.{i}"] = (float(donly_arr[2 * i]), False, 0.0, 1e12)
        extra[f"donor.tau.{i}"] = (float(donly_arr[2 * i + 1]), False, 1e-9, 1e9)
    problem, key, port, spectrum, basis, amplitudes, window, value = _solve(
        "tcspc_maxent_fret",
        decay,
        lamp,
        dt,
        R_arr,
        fitrange,
        fit_start_fraction,
        period,
        nu,
        max_iter,
        prior,
        timeshift,
        background,
        lamp_scatter,
        irf_background,
        optimize_nuisance,
        extra,
        scalars={"donor_lifetimes": donly_arr.size // 2},
    )
    # The design, per distance: the quenched donor species with their
    # amplitudes, plus the donor-only part (FRETSpectrumNode's layout).
    per = donly_arr.size // 2
    distances = amplitudes.size
    weights = spectrum[0::2]
    quenched = (
        (basis[:, : distances * per] * weights[: distances * per])
        .reshape(basis.shape[0], distances, per)
        .sum(2)
    )
    design = quenched + (basis[:, distances * per :] @ weights[distances * per :])[:, None]
    prepared = port("basis", "prepared_response")
    result = _result(
        decay, design, amplitudes, prepared, window, value, port, nu, prior, distances, dt
    )
    result.update(
        {
            "R": port("maxent", "distribution")[1::2],
            "tau0": float(tau0),
            "R0": float(R0),
            "donly": donly_arr,
            "x_donly": value("fret.x_donly"),
            "lamp_scatter": float(lamp_scatter),
            "nuisance_optimized": bool(optimize_nuisance),
        }
    )
    return result
