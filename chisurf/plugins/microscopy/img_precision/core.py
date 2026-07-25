"""Qt-free compute for the scan-precision planner.

Wraps :mod:`chisurf.core.experiments.ics.precision` with the one operation a
planning tool actually needs: a **sweep**. A single predicted error tells you how
good your current settings are but not which way to move; scanning the dwell
time shows the trade-off and where its minimum lies.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from chisurf.core.experiments.ics.precision import (
    RicsPrecision,
    UnrealisableScan,
    rics_precision,
)


def _or_none(value: float) -> float | None:
    """Return ``value`` as a float, or ``None`` when it is not finite.

    JSON has no NaN: emitting one yields a payload that a strict reader in
    another language rejects, so a dwell time the estimator could not evaluate
    is reported as a null instead.
    """
    number = float(value)
    return number if np.isfinite(number) else None


@dataclasses.dataclass
class PrecisionSweep:
    """Predicted precision across a range of pixel dwell times.

    Attributes
    ----------
    dwell : numpy.ndarray
        Pixel dwell times swept, in seconds.
    relative_error : numpy.ndarray
        Predicted relative error of the fitted ``D`` at each dwell.
    line_time : numpy.ndarray
        Line time used at each dwell.
    current : RicsPrecision or None
        The prediction at the settings the user actually entered.
    """

    dwell: np.ndarray
    relative_error: np.ndarray
    line_time: np.ndarray
    current: RicsPrecision | None = None

    @property
    def best_dwell(self) -> float:
        """Return the dwell time with the smallest predicted error, in seconds.

        Read it as an order of magnitude, not a setting to dial in: the
        underlying estimate is a Monte-Carlo quantity, so neighbouring points on
        a flat stretch of the curve can swap places.
        """
        e = np.asarray(self.relative_error, dtype=float)
        good = np.isfinite(e)
        if not good.any():
            return float("nan")
        return float(np.asarray(self.dwell)[good][int(np.argmin(e[good]))])

    @property
    def best_error(self) -> float:
        """Return the smallest predicted error in the sweep."""
        e = np.asarray(self.relative_error, dtype=float)
        e = e[np.isfinite(e)]
        return float(e.min()) if e.size else float("nan")

    def to_dict(self) -> dict:
        """Return the sweep as a JSON-friendly dictionary.

        Points the estimator could not evaluate come back as ``None`` rather
        than NaN, so the payload parses under a strict JSON reader.
        """
        return {
            "dwell_s": np.asarray(self.dwell, dtype=float).tolist(),
            "relative_error": [
                _or_none(e) for e in np.asarray(self.relative_error, dtype=float)
            ],
            "best_dwell_s": _or_none(self.best_dwell),
            "best_error": _or_none(self.best_error),
            "current": self.current.to_dict() if self.current is not None else None,
        }


def predict(
    diffusion_coefficient: float,
    pixel_time: float,
    line_time: float,
    **kwargs: Any,
) -> RicsPrecision:
    """Predict the precision of one acquisition.

    Parameters
    ----------
    diffusion_coefficient : float
        Expected ``D`` in µm²/s.
    pixel_time, line_time : float
        Scan timing in seconds.
    **kwargs
        Passed to :func:`~chisurf.core.experiments.ics.precision.rics_precision`.

    Returns
    -------
    RicsPrecision
        The prediction.
    """
    return rics_precision(
        diffusion_coefficient, pixel_time=pixel_time, line_time=line_time, **kwargs
    )


def line_time_for(dwell: float, nx: int, overhead: float = 1.2, floor: float = 0.0) -> float:
    """Return a plausible line time for a given dwell.

    A line must at least contain its pixels; real scanners add flyback on top.
    Sweeping dwell time with a *fixed* line time would be unphysical — the line
    cannot stay short as the pixels grow — so the sweep scales it.

    Parameters
    ----------
    dwell : float
        Pixel dwell time in seconds.
    nx : int
        Pixels per line.
    overhead : float
        Multiplier for flyback and settling.
    floor : float
        Minimum line time, for scanners with a fixed line period.

    Returns
    -------
    float
        Line time in seconds.
    """
    return max(float(dwell) * int(nx) * float(overhead), float(floor))


def sweep_dwell(
    diffusion_coefficient: float,
    dwell_times: Sequence[float],
    *,
    nx: int = 64,
    line_overhead: float = 1.2,
    line_floor: float = 0.0,
    current_dwell: float | None = None,
    current_line_time: float | None = None,
    progress: Callable[[float, str], None] | None = None,
    **kwargs: Any,
) -> PrecisionSweep:
    """Predict the precision across a range of pixel dwell times.

    Parameters
    ----------
    diffusion_coefficient : float
        Expected ``D`` in µm²/s.
    dwell_times : sequence of float
        Dwell times to evaluate, in seconds.
    nx : int
        Pixels per line; also used to derive each line time.
    line_overhead, line_floor
        Passed to :func:`line_time_for`.
    current_dwell, current_line_time : float, optional
        The user's own settings, evaluated separately so the sweep can mark
        where they sit.
    progress : callable, optional
        Called with ``(fraction, message)`` as the sweep proceeds.
    **kwargs
        Passed through to the predictor.

    Returns
    -------
    PrecisionSweep
        The curve, and the prediction at the current settings. A dwell time the
        estimator cannot realise is left as NaN rather than taking the sweep
        down with it.

    Raises
    ------
    ValueError
        If no acquisition in the sweep could satisfy the request — an image
        that cannot hold the requested lags. Reported rather than left as a
        gap, because the alternative is a curve of NaNs with no explanation.
    """
    dwell = np.asarray(list(dwell_times), dtype=float)
    errors = np.full(dwell.shape, np.nan)
    lines = np.array([line_time_for(d, nx, line_overhead, line_floor) for d in dwell])

    for i, (d, lt) in enumerate(zip(dwell, lines)):
        if progress:
            progress(i / max(len(dwell), 1), f"{d * 1e6:.3g} µs")
        try:
            errors[i] = rics_precision(
                diffusion_coefficient, pixel_time=float(d), line_time=float(lt),
                nx=nx, **kwargs
            ).relative_error
        except UnrealisableScan:
            # An acquisition that cannot be performed -- a line shorter than the
            # pixels it holds -- is left as NaN so the rest of the sweep still
            # runs. Only that: a request no acquisition satisfies (an n_lags
            # larger than the image can hold) fails at every point alike, and
            # swallowing it would turn a clear error into a curve of NaNs.
            errors[i] = np.nan

    current = None
    if current_dwell:
        lt = current_line_time or line_time_for(current_dwell, nx, line_overhead, line_floor)
        try:
            current = rics_precision(
                diffusion_coefficient, pixel_time=float(current_dwell),
                line_time=float(lt), nx=nx, **kwargs
            )
        except UnrealisableScan:
            # The user's own settings may describe no realisable acquisition;
            # the sweep is still worth showing, so this one point is absent.
            current = None

    if progress:
        progress(1.0, "done")
    return PrecisionSweep(
        dwell=dwell, relative_error=errors, line_time=lines, current=current
    )


def default_dwell_range(n: int = 9, low: float = 5e-7, high: float = 5e-4) -> list[float]:
    """Return a logarithmically spaced default dwell range, in seconds.

    Spans roughly 0.5 µs to 0.5 ms, which brackets the useful range for a
    confocal raster scan of anything from a free dye to a membrane protein.

    Parameters
    ----------
    n : int
        Number of points.
    low, high : float
        Range limits in seconds.

    Returns
    -------
    list of float
        The dwell times.
    """
    return list(np.logspace(np.log10(low), np.log10(high), int(n)))
