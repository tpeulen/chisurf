"""The TCSPC instrument's scatter and background, as counts or as fractions.

BFF's TCSPC models take scatter and background as *fractions of the
fluorescence total* sum(F) and n0 as counts per unit of the convolved decay
(``internal/TCSPCInstrument.h``, shared with the Bayesian decay model). ChiSurf
used to take them as absolute counts. These helpers convert, at the model's
current curve, through BFF's own conversion -- for a caller that has absolute
numbers (a classic project, a reference) or reports them.
"""
from __future__ import annotations

__all__ = ["fluorescence_total", "set_absolute_instrument", "absolute_instrument"]


def _set(problem, canonical: str, value: float) -> None:
    port = problem.get_parameter(canonical)
    held = port.fixed
    port.fixed = False
    port.value = float(value)
    port.fixed = held


def _channels(model) -> int:
    return int(len(model.fit.data.y))


def fluorescence_total(model) -> float:
    """sum(F) of the model's convolved decay at its current parameters."""
    problem = model.problem
    if problem is None:
        raise ValueError("the model is incomplete: missing " + ", ".join(model.missing))
    return float(problem.get_output("fluorescence_total")[0])


def set_absolute_instrument(model, n0: float, scatter: float = 0.0, background: float = 0.0) -> None:
    """Set n0 and the scatter/background fractions from absolute counts.

    ``scatter`` multiplies the unit-sum response and ``background`` is counts per
    channel, both as ChiSurf's classic models took them. Exact at the curve the
    model has now; set the decay's own parameters first.
    """
    import IMP.bff

    problem = model.problem
    scale, scatter_fraction, _, background_fraction = IMP.bff.tcspc_fractions_from_absolute(
        float(n0), float(scatter), float(background), fluorescence_total(model), _channels(model))
    _set(problem, "instrument.n0", scale)
    _set(problem, "instrument.scatter", scatter_fraction)
    _set(problem, "instrument.background", background_fraction)


def absolute_instrument(model) -> dict:
    """n0, and scatter and background as absolute counts, at the current curve."""
    problem = model.problem
    total = fluorescence_total(model)
    n0 = float(problem.get_parameter("instrument.n0").value)
    return {
        "n0": n0,
        "scatter": float(problem.get_parameter("instrument.scatter").value) * total,
        "background": float(problem.get_parameter("instrument.background").value) * n0 * total / _channels(model),
    }
