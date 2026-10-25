"""Agent tools for the single-molecule burst workflow.

The chain this group composes — *find the bursts, pick the species, take the
species' decay, fit a distance distribution to it* — is the everyday
single-molecule analysis, and every step of it already exists as plugin
machinery: the FRET check detects the experiment and finds bursts with
apparent E/S (``chisurf.plugins.burst.fret_check``), the burst-selection API
persists a burst table as a run of the measurement's container
(``write_container``) and pools a selection's photons into a sub-ensemble
decay (``write_decay_container``), and the BFF-backed TCSPC fits a Gaussian
distance-distribution model (``decay_fit_model.fit_fret_model``).  The tools
here are thin wrappers over exactly those seams — no analysis code lives in
them — so the model drives the same code the GUI buttons drive, and the
results land where the rest of ChiSurf looks for them: the burst table and
the decay inside the measurement's ``.pto``, with lineage back to the
photons; the fit in the session's fit list.

State between the steps rides the context: ``run_burst_analysis`` caches the
burst table it found, ``select_species`` caches the gate it applied, and
``extract_subensemble_decay`` caches the dataset index it registered — each
tool says in its result what the next one will pick up.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import SAFETY_READ, SAFETY_WRITE, ToolError, ToolRegistry
from chisurf.core.agent.tools._dto import _round

logger = logging.getLogger(__name__)

registry = ToolRegistry()

#: Context-extras key holding the cached analysis of the current measurement.
_CACHE_KEY = "burst_analysis"

#: Column aliases a model or user plausibly uses for the two species columns.
_E_ALIASES = ("e", "fret", "proximity ratio", "proximity_ratio", "e_app")
_S_ALIASES = ("s", "stoichiometry", "s_app")


# ── cached-state helpers ──────────────────────────────────────────────


def _cached(context: AgentContext, what: str = "the burst analysis") -> dict:
    """Return the cached analysis, or say which tool has to run first."""
    cached = context.extras.get(_CACHE_KEY)
    if not cached:
        raise ToolError(
            f"no burst analysis in this session yet — run run_burst_analysis "
            f"on the measurement before asking for {what}"
        )
    return cached


def _quantiles(
    values: np.ndarray, probabilities=(5, 25, 50, 75, 95)
) -> dict[str, float | None]:
    """Return rounded percentiles of *values*, tolerating empties."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {}
    return {
        f"p{p}": _round(float(np.percentile(values, p)))
        for p in probabilities
    }


def _column_for(context: AgentContext, name: str) -> tuple[np.ndarray, str]:
    """Resolve a column reference against the cached burst table.

    Parameters
    ----------
    context : AgentContext
        Execution context holding the cached analysis.
    name : str
        A column name, or a canonical alias (``E``/``S``, corrected variants).

    Returns
    -------
    tuple of (ndarray, str)
        The column's values and its canonical name.

    Raises
    ------
    ToolError
        When nothing matches; the error lists what does.
    """
    cached = _cached(context, "a species selection")
    columns: dict[str, np.ndarray] = cached["columns"]
    wanted = str(name).strip().lower()
    corrected = wanted.endswith("*") or "_corrected" in wanted or corrected_requested(wanted)
    if corrected and "E_corrected" in columns:
        wanted = wanted.replace("*", "").replace("_corrected", "").strip()
        canonical = "E_corrected" if wanted in _E_ALIASES else "S_corrected"
        return np.asarray(columns[canonical], dtype=float), canonical
    if wanted in _E_ALIASES:
        return np.asarray(columns["Proximity ratio"], dtype=float), "Proximity ratio (E)"
    if wanted in _S_ALIASES:
        key = "Stoichiometry" if "Stoichiometry" in columns else None
        if key is None:
            raise ToolError(
                "this measurement has no stoichiometry — S needs alternating "
                "(PIE / ALEX) excitation. Gate on E (the proximity ratio) instead."
            )
        return np.asarray(columns[key], dtype=float), key
    for candidate in columns:
        if candidate.lower() == wanted:
            return np.asarray(columns[candidate], dtype=float), candidate
    matches = [candidate for candidate in columns if wanted in candidate.lower()]
    if len(matches) == 1:
        return np.asarray(columns[matches[0]], dtype=float), matches[0]
    raise ToolError(
        f"no burst column matches {name!r}. Available: {sorted(columns)}"
    )


def corrected_requested(name: str) -> bool:
    """Whether *name* asks for the corrected E/S rather than the apparent one."""
    lowered = str(name).strip().lower()
    return "corrected" in lowered or lowered.endswith("*")


def _experiment_summary(experiment: Any) -> dict[str, Any]:
    """The detected experiment, as the model should see it."""
    return {
        "kind": str(getattr(experiment, "kind", "")),
        "excitation": str(getattr(experiment, "excitation", "")),
        "donor_channels": [int(c) for c in getattr(experiment, "donor_channels", [])],
        "acceptor_channels": [int(c) for c in getattr(experiment, "acceptor_channels", [])],
        "n_photons": int(getattr(experiment, "n_photons", 0)),
        "duration_s": _round(float(getattr(experiment, "duration_s", 0.0) or 0.0)),
        "warnings": [str(w) for w in getattr(experiment, "warnings", [])],
    }


def _donor_stream(context: AgentContext) -> dict[str, Any]:
    """The stream definition of the donor decay: donor channels, donor window."""
    experiment = _cached(context)["experiment"]
    channels = [int(c) for c in experiment.donor_channels]
    ranges: list[list[int]] = []
    if str(getattr(experiment, "excitation", "")) == "alternating":
        for window in experiment.windows or []:
            if str(getattr(window, "name", "")) == "donor":
                ranges = [[int(window.start), int(window.stop)]]
                break
    return {"channels": channels, "micro_time_ranges": ranges}


def _table_summary(bursts: Any, corrected: dict | None) -> dict[str, Any]:
    """What ``inspect_bursts`` reports about one burst table."""
    columns = bursts.columns()
    summary: dict[str, Any] = {
        "n_bursts": int(bursts.n),
        "columns": sorted(columns),
        "photon_count": _quantiles(columns["Number of Photons"]),
        "duration_ms": _quantiles(columns["Duration (ms)"]),
        "E": _quantiles(columns["Proximity ratio"]),
    }
    if "Stoichiometry" in columns:
        summary["S"] = _quantiles(columns["Stoichiometry"])
    if corrected:
        summary["E_corrected"] = _quantiles(corrected["E"])
        if corrected.get("S") is not None:
            summary["S_corrected"] = _quantiles(corrected["S"])
    return summary


# ── the tools ─────────────────────────────────────────────────────────


@registry.add(
    name="detect_smfret",
    description=(
        "Open a single-molecule TTTR measurement and detect what it is: the "
        "excitation scheme (cw, PIE, µsALEX), which routing channels are the "
        "donor and acceptor detectors, and the micro-time windows. Run this "
        "first on unknown burst data — every later step uses the roles it "
        "reports, and the detection's warnings name what a user should confirm."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The measurement file (.ht3, .ptu, .spc, .pto, ...).",
            },
        },
        "required": ["path"],
    },
    safety=SAFETY_READ,
)
def detect_smfret(context: AgentContext, path: str) -> dict[str, Any]:
    """Detect the experiment recorded in *path*."""
    from chisurf.plugins.burst.fret_check import entry as fret_check
    from chisurf.plugins.burst.fret_check import jobs as fret_jobs

    resolved = context.resolve_path(str(path))
    if not resolved.exists():
        raise ToolError(f"no such file: {resolved}. The {context.describe_working_directory()}")
    detected = fret_check.detect(path=str(resolved))
    experiment = fret_jobs.experiment_from_dict(detected)
    return {
        "ok": True,
        "path": str(resolved),
        "detected": _experiment_summary(experiment),
        "channel_counts": {
            str(ch): int(count)
            for ch, count in (detected.get("channel_counts") or {}).items()
        },
    }


@registry.add(
    name="run_burst_analysis",
    description=(
        "Run the burstwise analysis of a single-molecule measurement: burst "
        "search, per-burst counts, apparent FRET efficiency E and "
        "stoichiometry S, and quality checks. The burst table is stored as a "
        "run of the measurement's .pto container (beside the file), so later "
        "steps — species selection, the sub-ensemble decay — work on the same "
        "bursts and stay traceable to the photons. Returns how many bursts "
        "were found and the E/S distributions; inspect_bursts and "
        "select_species operate on this analysis."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The measurement file. One measurement at a time; "
                "a new path replaces the cached analysis.",
            },
            "min_photons_burst": {
                "type": "integer",
                "description": "Minimum photons per burst. Default 30 — lower it only "
                "for dim samples, and say so in your answer.",
            },
            "window_ms": {
                "type": "number",
                "description": "Sliding-window length T of the burst search, in "
                "milliseconds. Default 0.5.",
            },
            "correct": {
                "type": "boolean",
                "description": "Also compute corrected E/S from the given factors.",
            },
            "factors": {
                "type": "object",
                "description": "Correction factors for accurate E/S: gamma, alpha "
                "(leakage), delta (direct excitation), beta. Missing ones stay "
                "uncorrected.",
            },
        },
        "required": ["path"],
    },
    safety=SAFETY_WRITE,
)
def run_burst_analysis(
    context: AgentContext,
    path: str,
    min_photons_burst: int = 30,
    window_ms: float = 0.5,
    correct: bool = False,
    factors: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Burst search + E/S + QC over *path*, cached for the following tools."""
    from chisurf.plugins.burst.burst_selection.api.io import write_container
    from chisurf.plugins.burst.fret_check import entry as fret_check
    from chisurf.plugins.burst.fret_check import jobs as fret_jobs

    resolved = context.resolve_path(str(path))
    if not resolved.exists():
        raise ToolError(f"no such file: {resolved}. The {context.describe_working_directory()}")
    settings = {
        "min_photons": int(min_photons_burst),
        "T": float(window_ms) * 1e-3,
    }
    result = fret_check.analyse(
        path=str(resolved),
        key=str(resolved),
        settings=settings,
        correct=bool(correct),
        factors=dict(factors or {}),
    )
    bursts = fret_jobs.bursts_from_dict(result["bursts"])
    experiment = fret_jobs.experiment_from_dict(result["experiment"])
    corrected = result.get("corrected") or None
    if corrected:
        corrected = {
            "E": fret_jobs.unpack(corrected.get("E")),
            "S": fret_jobs.unpack(corrected.get("S")),
        }

    # The burst table as a run of the measurement's container: the product
    # representation every other tool (run picker, ndX, the decay below)
    # reads — not a private cache format.
    n = bursts.n
    table = {**bursts.columns(), "First File": [resolved.name] * n}
    parameters = {"min_photons": int(min_photons_burst), "T_s": float(window_ms) * 1e-3}
    if factors:
        parameters["factors"] = {k: float(v) for k, v in factors.items() if v is not None}
    container = write_container(resolved, table, parameters=parameters, run="burstwise")
    run_path = f"{container}/burstwise"

    qc = result.get("qc") or {}
    flags = fret_jobs.unpack(qc.get("flags")) if qc.get("flags") else None
    cached = {
        "path": str(resolved),
        "experiment": experiment,
        "bursts": bursts,
        "corrected": corrected,
        "columns": table,
        "run_path": run_path,
        "selection": None,
        "settings": settings,
    }
    context.extras[_CACHE_KEY] = cached

    return {
        "ok": True,
        "path": str(resolved),
        "detected": _experiment_summary(experiment),
        "n_bursts": n,
        "E": _quantiles(bursts.E),
        "S": _quantiles(bursts.S) if bursts.S is not None else None,
        "n_flagged_by_qc": int(np.count_nonzero(flags)) if flags is not None else None,
        "container": str(container),
        "next": (
            "inspect_bursts to see the distributions, then select_species to "
            "gate the population you want (e.g. FRET-active: E above 0.5, or "
            "with PIE an S window that excludes donor-only and acceptor-only)."
        ),
    }


@registry.add(
    name="inspect_bursts",
    description=(
        "Summarise the current burst analysis: how many bursts, which columns "
        "exist, and the distributions of photon count, duration, E (and S when "
        "alternating). Use it to choose a species gate — where one population "
        "ends and the next begins — before selecting."
    ),
    parameters={"type": "object", "properties": {}},
    safety=SAFETY_READ,
)
def inspect_bursts(context: AgentContext) -> dict[str, Any]:
    """Return the summary statistics of the cached burst table."""
    cached = _cached(context, "inspection")
    return {
        "ok": True,
        "path": cached["path"],
        **_table_summary(cached["bursts"], cached.get("corrected")),
        "selection": _selection_report(cached),
    }


def _selection_report(cached: dict) -> dict[str, Any] | None:
    """What the current selection (if any) keeps."""
    mask = cached.get("selection")
    if mask is None:
        return None
    columns = cached["columns"]
    keep = np.asarray(mask, dtype=bool)
    return {
        "n_selected": int(keep.sum()),
        "n_total": int(keep.size),
        "E_of_selection": _quantiles(columns["Proximity ratio"][keep]),
    }


@registry.add(
    name="select_species",
    description=(
        "Gate the bursts of the current analysis to one species, by a range on "
        "one column — 'E' (proximity ratio) and 'S' (stoichiometry) are the "
        "canonical names; any burst-table column works. A FRET-active species "
        "is typically E above 0.5; with PIE/ALEX data an S window (say 0.3-0.8) "
        "additionally excludes donor-only and acceptor-only molecules. The "
        "selection is remembered; extract_subensemble_decay takes it."
    ),
    parameters={
        "type": "object",
        "properties": {
            "column": {
                "type": "string",
                "description": "Column to gate on: 'E', 'S', 'E_corrected', or any "
                "burst-table column name. Default 'E'.",
            },
            "min": {"type": "number", "description": "Inclusive lower bound. Omit for no bound."},
            "max": {"type": "number", "description": "Inclusive upper bound. Omit for no bound."},
        },
    },
    safety=SAFETY_WRITE,
)
def select_species(
    context: AgentContext,
    column: str = "E",
    min: float | None = None,
    max: float | None = None,
) -> dict[str, Any]:
    """Apply a range gate on one burst column; cache it as the selection."""
    if min is None and max is None:
        raise ToolError(
            "an empty gate keeps every burst — give at least one bound "
            "(min or max), or say in your answer that you took all bursts"
        )
    values, canonical = _column_for(context, column)
    cached = _cached(context, "a species selection")
    mask = np.ones(values.size, dtype=bool)
    if min is not None:
        mask &= values >= float(min)
    if max is not None:
        mask &= values <= float(max)
    cached["selection"] = mask
    if not mask.any():
        cached["selection"] = None
        raise ToolError(
            f"the gate {canonical} in [{min}, {max}] selects no burst — look at "
            f"inspect_bursts' distribution and widen it"
        )
    return {
        "ok": True,
        "column": canonical,
        "gate": [min, max],
        "n_selected": int(mask.sum()),
        "n_total": int(values.size),
        "E_of_selection": _quantiles(
            np.asarray(cached["columns"]["Proximity ratio"], dtype=float)[mask]
        ),
        "next": (
            "extract_subensemble_decay to pool the selected bursts' donor "
            "photons into one TCSPC decay."
        ),
    }


@registry.add(
    name="extract_subensemble_decay",
    description=(
        "Pool the selected bursts' donor photons into one TCSPC decay (a "
        "sub-ensemble decay) and register it as a dataset, ready for a fit. "
        "Without a selection, all bursts are used. For PIE/ALEX data the "
        "donor-excitation donor-emission window is used automatically. The "
        "decay is written into the measurement's container beside the burst "
        "run it was selected from."
    ),
    parameters={
        "type": "object",
        "properties": {
            "n_bins": {
                "type": "integer",
                "description": "Histogram bins; 0 keeps the instrument's micro-time "
                "channels. Default 0.",
            },
        },
    },
    safety=SAFETY_WRITE,
)
def extract_subensemble_decay(context: AgentContext, n_bins: int = 0) -> dict[str, Any]:
    """Decay of the selected bursts, registered as a dataset."""
    from chisurf.plugins.burst.burst_selection.api.io import write_decay_container

    cached = _cached(context, "the sub-ensemble decay")
    mask = cached.get("selection")
    try:
        outcome = write_decay_container(
            cached["run_path"],
            mask,
            int(n_bins),
            stream=_donor_stream(context),
            parameters={"tool": "extract_subensemble_decay"},
        )
    except Exception as error:  # noqa: BLE001 - the model should see why, not a traceback
        raise ToolError(f"the sub-ensemble decay failed: {error}") from error
    if outcome.get("dataset_index") is None:
        raise ToolError(
            "the decay was written to the container but could not be registered "
            "as a dataset for fitting"
        )
    cached["decay"] = outcome
    selection_note = (
        f"{outcome['bursts']} selected bursts" if mask is not None else "all bursts"
    )
    return {
        "ok": True,
        "photons": outcome["photons"],
        "n_bursts_used": outcome["bursts"],
        "selection": selection_note,
        "n_bins": outcome["bins"],
        "container": outcome["container"],
        "dataset_index": outcome["dataset_index"],
        "next": (
            "fit_distance_distribution on this dataset (index "
            f"{outcome['dataset_index']}) for the Gaussian distance "
            "distribution; a plain lifetime fit uses create_fit + run_fit."
        ),
    }


@registry.add(
    name="fit_distance_distribution",
    description=(
        "Fit a decay with the software's Gaussian distance-distribution FRET "
        "model (each component a Gaussian donor-acceptor distance against a "
        "fixed Förster radius R0 and donor-only lifetime) and report the "
        "fitted mean distances, widths, fractions and per-state efficiencies. "
        "The distribution width is fitted unless asked to hold it. R0, the "
        "donor-only lifetime and the number of components are the user's "
        "choices — when the request does not state them, ask (ask_user) "
        "instead of assuming, and report the values used next to the result."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dataset": {
                "type": ["integer", "string"],
                "description": "The decay dataset to fit (index or name). Default: "
                "the sub-ensemble decay this session extracted last.",
            },
            "n_states": {
                "type": "integer",
                "description": "Number of Gaussian components, as the user specifies. Default 1.",
            },
            "forster_radius": {
                "type": "number",
                "description": "Förster radius R0 in Ångström, as the user specifies. Default 52.",
            },
            "donor_lifetime": {
                "type": "number",
                "description": "Donor-only lifetime τ_D0 in ns, as the user specifies. Default 4.0.",
            },
            "sigma": {
                "type": "number",
                "description": "Starting Gaussian width in Å. Default 5.",
            },
            "fit_sigma": {
                "type": "boolean",
                "description": "Fit the distribution width (default) or hold it at `sigma`. "
                "A held width biases the mean distance; say which mode you used.",
            },
        },
    },
    safety=SAFETY_WRITE,
)
def fit_distance_distribution(
    context: AgentContext,
    dataset: Any = None,
    n_states: int = 1,
    forster_radius: float = 52.0,
    donor_lifetime: float = 4.0,
    sigma: float = 5.0,
    fit_sigma: bool = True,
) -> dict[str, Any]:
    """Fit the Gaussian distance-distribution model to a decay dataset."""
    import chisurf as cs
    from chisurf.core.fluorescence.decay_fit_model import fit_fret_model

    if dataset is None:
        cached = context.extras.get(_CACHE_KEY) or {}
        dataset = (cached.get("decay") or {}).get("dataset_index")
        if dataset is None:
            raise ToolError(
                "no decay to fit — run extract_subensemble_decay first, or name "
                "a dataset (index or name)"
            )
    obj, index = context.resolve_dataset(dataset)
    x = np.asarray(getattr(obj, "x", None), dtype=float).ravel()
    y = np.asarray(getattr(obj, "y", None), dtype=float).ravel()
    if y.size < 8:
        raise ToolError(f"dataset {index} has {y.size} bins — too few to fit")
    bin_width = float(x[1] - x[0]) if x.size > 1 else 0.0
    if not bin_width > 0:
        raise ToolError(
            f"dataset {index} has no usable time axis; fit it as a plain decay "
            "with create_fit instead"
        )
    # The amplitude model is not convolved with the instrument response, so it
    # cannot describe the prompt — the fit window starts at the response's
    # peak (the pulse), the standard range for an un-convolved fit.
    start_bin = int(np.argmax(y))
    try:
        result = fit_fret_model(
            y,
            bin_width=bin_width,
            n_states=max(1, int(n_states)),
            donor_lifetime=float(donor_lifetime),
            forster_radius=float(forster_radius),
            sigma=float(sigma),
            fit_sigma=bool(fit_sigma),
            start_bin=start_bin,
        )
    except Exception as error:  # noqa: BLE001 - the model should see why
        raise ToolError(f"the distance-distribution fit failed: {error}") from error

    fit = result["fit"]
    name = f"{getattr(obj, 'name', 'decay')} — distance distribution"
    try:
        fit.name = name
    except Exception:  # noqa: BLE001 - naming is cosmetic
        pass
    cs.fits.append(fit)
    fit_index = len(cs.fits) - 1

    return {
        "ok": True,
        "dataset": index,
        "fit_index": fit_index,
        "chi2_reduced": _round(result["chi2_reduced"]),
        "distances_A": [_round(float(v)) for v in result["distances"]],
        "sigma_A": [_round(float(v)) for v in result["sigmas"]],
        "fractions": [_round(float(v), 4) for v in result["fractions"]],
        "efficiencies": [_round(float(v), 4) for v in result["efficiencies"]],
        "donor_only_fraction": _round(float(result["donor_only_fraction"]), 4),
        "forster_radius_A": _round(float(result["forster_radius"])),
        "donor_lifetime_ns": _round(float(result["donor_lifetime"])),
        "bin_width_ns": _round(bin_width),
        "fit_window_start_ns": _round(start_bin * bin_width),
        "width_mode": "fitted" if fit_sigma else f"held at {sigma:g} A",
        "stated_assumptions": (
            f"R0 = {forster_radius:g} A, donor-only lifetime = "
            f"{donor_lifetime:g} ns, {int(n_states)} Gaussian component(s), "
            f"width {'fitted' if fit_sigma else 'held at %g A' % sigma}"
        ),
        "next": (
            "report these parameters (with chi2_reduced and the assumptions) "
            "and plot the fit with plot_fit."
        ),
    }
