"""Coarse grid scan over fitting parameters: find the valley before descending.

A least-squares optimiser is local. It goes downhill from where it starts and
reports where it stops, which is the right answer only when the start was in
the right basin. Two situations in this codebase routinely break that:

* **Degenerate pairs.** A detection-correction factor scales the data and a
  lifetime scales the model curve, so the two trade off along a valley; the
  optimiser slides a little way along it and stops.
* **Rough objectives.** Anything reduced from counts (a burst population's
  ridge, a histogram) is not smooth at the scale of a finite-difference step.

The remedy is the oldest one: evaluate the objective on a coarse grid first and
start the local fit at the best point. :func:`grid_scan` does that for any list
of :class:`~chisurf.core.fitting.parameter.FittingParameter` objects and any
cost callable, spending a **fixed** number of evaluations
(:data:`DEFAULT_BUDGET`) however many parameters there are.

The grid comes from the parameters themselves: their bounds when armed, and
otherwise a factor either side of where they sit — a lifetime, a correction
factor or an amplitude is a *scale*, so the fallback grid is geometric. The
current value is always one of the points, so a scan can never return something
worse than the start.

:meth:`chisurf.core.fitting.fit.Fit.grid_scan` wires this to a fit's own free
parameters with chi2 as the cost; :mod:`chisurf.core.fitting.support_plane` is
the other, different thing — a *one*-parameter profile scan for confidence
intervals, not a search for a starting point.

Qt-free and headless.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = [
    "DEFAULT_BUDGET",
    "GridScanResult",
    "ScanAborted",
    "grid_scan",
    "scan_axis",
]

#: Model evaluations a scan may spend, whatever the number of parameters.
DEFAULT_BUDGET = 240

#: Most parameters a grid is attempted for. Beyond this a grid is too coarse in
#: each direction to mean anything, and the caller is better served by its own
#: start.
MAX_PARAMETERS = 4

#: Factor either side of the current value when a parameter has no bounds.
DEFAULT_SPAN = 4.0


class ScanAborted(RuntimeError):
    """Raised out of a scan when the caller's cost function asks it to stop."""


@dataclass
class GridScanResult:
    """Outcome of a :func:`grid_scan`.

    Attributes
    ----------
    values : ndarray or None
        The best point found, in the order of the scanned parameters. ``None``
        when nothing was evaluated (too many parameters, or every evaluation
        failed).
    cost : float
        The cost there.
    evaluations : int
        How many grid points were evaluated.
    improved : bool
        Whether the best point is better than the one the parameters started at.
    axes : list of ndarray
        The values tried for each parameter, for a caller that wants to show or
        re-use the grid.
    """

    values: np.ndarray | None = None
    cost: float = float("inf")
    evaluations: int = 0
    improved: bool = False
    axes: list[np.ndarray] = field(default_factory=list)

    def __bool__(self) -> bool:  # noqa: D105
        return self.values is not None

    def apply(self) -> bool:
        """Write the best point into the parameters it came from.

        Returns
        -------
        bool
            Whether anything was written.
        """
        if self.values is None or not self._parameters:
            return False
        for parameter, value in zip(self._parameters, self.values):
            parameter.value = float(value)
        return True

    #: The parameters the result belongs to; set by :func:`grid_scan`.
    _parameters: Sequence[Any] = field(default_factory=tuple, repr=False)


def _bounds(parameter: Any) -> tuple:
    """``(lo, hi)`` of a parameter, ``inf`` where no bound is armed."""
    if not bool(getattr(parameter, "bounds_on", False)):
        return -np.inf, np.inf
    return float(getattr(parameter, "lb", -np.inf)), float(getattr(parameter, "ub", np.inf))


def scan_axis(parameter: Any, points: int, span: float = DEFAULT_SPAN) -> np.ndarray:
    """Values to try for one parameter.

    Inside its bounds when it has them, and otherwise a factor ``span`` either
    side of where it is — geometrically, because an unbounded fitting parameter
    is almost always a scale and a scale is searched in ratios, not in
    increments. The current value is always included, so the scan cannot return
    a point worse than the start.

    Parameters
    ----------
    parameter : FittingParameter
        The parameter to build a grid axis for.
    points : int
        How many values to try.
    span : float, optional
        Factor either side of the current value when there are no bounds.

    Returns
    -------
    ndarray
        Ascending, de-duplicated values including ``parameter.value``.
    """
    value = float(parameter.value)
    lo, hi = _bounds(parameter)
    points = max(2, int(points))
    if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
        grid = np.linspace(lo, hi, points)
    elif value > 0:
        grid = np.geomspace(value / span, value * span, points)
    elif value < 0:
        grid = -np.geomspace(-value / span, -value * span, points)
    else:
        # No scale to work from: a unit window around zero is as good a guess
        # as any, and the start is in it.
        grid = np.linspace(-1.0, 1.0, points)
    return np.unique(np.append(grid, value))


def grid_scan(
    parameters: Sequence[Any],
    cost: Callable[[np.ndarray], float],
    *,
    budget: int = DEFAULT_BUDGET,
    points: int | None = None,
    span: float = DEFAULT_SPAN,
    max_parameters: int = MAX_PARAMETERS,
    apply_best: bool = False,
) -> GridScanResult:
    """Evaluate ``cost`` on a coarse grid over ``parameters`` and return the best.

    Parameters
    ----------
    parameters : sequence of FittingParameter
        The parameters to scan. Their current values are restored before the
        result is returned unless ``apply_best`` is set.
    cost : callable
        ``cost(values) -> float``, lower is better. It is called with one array
        per grid point, in the order of ``parameters``; a point whose cost
        raises (or is not finite) is skipped, so a model that cannot be
        evaluated somewhere does not end the scan. Raise :class:`ScanAborted`
        from it to stop the scan (a Cancel button, typically).
    budget : int, optional
        Roughly how many points to evaluate in total. The per-parameter
        resolution follows from it: ``budget ** (1 / n)``.
    points : int, optional
        Fixed number of values per parameter, overriding ``budget``.
    span : float, optional
        Factor either side of an unbounded parameter's current value.
    max_parameters : int, optional
        Skip the scan above this many parameters (the grid would be 2-3 points
        per direction, which says nothing).
    apply_best : bool, optional
        Leave the parameters at the best point instead of restoring them.

    Returns
    -------
    GridScanResult
        Empty (falsy) when no grid was run.
    """
    parameters = list(parameters)
    if not parameters or len(parameters) > int(max_parameters):
        return GridScanResult(axes=[], _parameters=parameters)

    per_axis = int(points) if points else max(3, int(budget ** (1.0 / len(parameters))))
    axes = [scan_axis(p, per_axis, span) for p in parameters]
    start = np.array([float(p.value) for p in parameters], dtype=float)

    best: np.ndarray | None = None
    best_cost = np.inf
    start_cost = np.inf
    evaluations = 0
    try:
        for point in itertools.product(*axes):
            values = np.array(point, dtype=float)
            try:
                current = float(cost(values))
            except ScanAborted:
                raise
            except Exception:
                continue
            evaluations += 1
            if np.allclose(values, start):
                start_cost = current
            if np.isfinite(current) and current < best_cost:
                best, best_cost = values, current
    finally:
        if not apply_best or best is None:
            for parameter, value in zip(parameters, start):
                parameter.value = float(value)

    result = GridScanResult(
        values=best,
        cost=best_cost,
        evaluations=evaluations,
        improved=bool(best is not None and best_cost < start_cost),
        axes=axes,
        _parameters=parameters,
    )
    if apply_best:
        result.apply()
    return result
