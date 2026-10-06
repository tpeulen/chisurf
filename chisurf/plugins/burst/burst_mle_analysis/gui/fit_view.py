"""What the emtk burst-MLE windows show, read from the wizard that computed it.

The wizard owns the fit. This module reads its state and nothing else: the curves ``plot_fit_result`` last drew
(``wizard.fit_curves``), the fit-parameter rows, the per-burst lifetimes of the last ``process_bursts`` run
(``wizard.burst_results``) and the pooled state lifetimes. With no fit (or no batch run) each function returns
``None`` / an empty list and the windows draw an empty-state message: nothing is ever invented (PRD-153 rule 8a).

Qt-free: the wizard is read through its public attributes only, so the tests can feed a stand-in object.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..fit_display import DecayCurves

#: Bins of the lifetime histogram.
LIFETIME_BINS = 30

_TAU_COLUMN = re.compile(r"^Tau(?: S(?P<state>\d+))? \((?P<colour>.+)\)$")


@dataclass(frozen=True)
class ParameterRow:
    """One fit parameter as the wizard holds it: start value, whether it is held fixed, and the fitted value."""

    name: str
    initial: float
    fixed: bool
    result: float


def fit_curves(wizard: Any) -> DecayCurves | None:
    """The curves of the fit that last ran (``None`` before the first fit or when it could not be drawn)."""
    return getattr(wizard, "fit_curves", None)


def parameter_rows(wizard: Any) -> list[ParameterRow]:
    """The fit parameters of the selected model with their start, fix flag and fitted value."""
    dyn = getattr(wizard, "_dyn_params", None)
    if getattr(wizard, "fit_model", "fit23") != "fit23" and dyn is not None and len(dyn):
        return [
            ParameterRow(str(n), float(v), bool(f), float(r))
            for n, v, f, r in zip(dyn.names, dyn.values, dyn.fixed, dyn.results)
        ]
    try:
        return [
            ParameterRow("tau", float(wizard.tau), bool(wizard.fix_tau), float(wizard.tau_result)),
            ParameterRow("gamma", float(wizard.gamma), bool(wizard.fix_gamma), float(wizard.gamma_result)),
            ParameterRow("r0", float(wizard.r0), bool(wizard.fix_r0), float(wizard.r0_result)),
            ParameterRow("rho", float(wizard.rho), bool(wizard.fix_rho), float(wizard.rho_result)),
        ]
    except AttributeError:
        return []


def burst_lifetimes(rows: list[dict] | None) -> dict[str, np.ndarray]:
    """Per-burst lifetimes by series from the rows of the last batch run.

    The key is the detection colour (``"green"``) or, in the segment-level analysis, ``"S0 green"``. Only finite
    values are kept; a column nobody filled is left out.
    """
    series: dict[str, list[float]] = {}
    for row in rows or []:
        for column, value in row.items():
            match = _TAU_COLUMN.match(str(column))
            if match is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(number):
                continue
            key = match["colour"] if match["state"] is None else f"S{match['state']} {match['colour']}"
            series.setdefault(key, []).append(number)
    # Sorted by series: the batch rows arrive in worker order; the plot must not depend on it.
    return {
        key: np.asarray(values, dtype=np.float64) for key, values in sorted(series.items()) if values
    }


def lifetime_histograms(
    lifetimes: dict[str, np.ndarray], bins: int = LIFETIME_BINS
) -> list[tuple[str, np.ndarray, np.ndarray, float]]:
    """``(label, bin centres, counts, bar width)`` per series, on one common bin grid."""
    if not lifetimes:
        return []
    everything = np.concatenate(list(lifetimes.values()))
    lo, hi = float(everything.min()), float(everything.max())
    if hi <= lo:
        hi = lo + 1.0
    edges = np.linspace(lo, hi, bins + 1)
    centres = (edges[:-1] + edges[1:]) / 2.0
    width = float(edges[1] - edges[0])
    return [(key, centres, np.histogram(values, bins=edges)[0].astype(np.float64), width) for key, values in lifetimes.items()]


def state_lifetime_rows(wizard: Any) -> list[dict]:
    """The pooled per-state lifetimes of the last segment-level run (empty before one)."""
    return list(getattr(wizard, "state_lifetimes", None) or [])


def burst_file_count(wizard: Any) -> int:
    """How many burst files the wizard has selected."""
    files = getattr(wizard, "burst_files_list", None)
    if files is None:
        return 0
    try:
        return len(files.get_selected_files())
    except Exception:
        return 0


def irf_background_ready(wizard: Any) -> bool:
    """Whether the current detector has both an IRF and a background loaded."""
    det = getattr(wizard, "current_detector", "")
    irf, bg = getattr(wizard, "irf_np", {}), getattr(wizard, "bg_np", {})
    return bool(det) and det in irf and det in bg and np.asarray(irf[det]).size > 0 and np.asarray(bg[det]).size > 0
