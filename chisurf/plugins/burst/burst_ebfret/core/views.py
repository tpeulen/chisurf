"""What the ebFRET window draws, as plain JSON-able data.

``refresh.m`` computes the plot lines and then hands them to MATLAB axes. The
computation is :mod:`.plots`; this module runs it for a session the way
``refresh('ensemble', 'series')`` does -- ensemble first, because the signal
axis borrows the histogram's range -- and turns the result into lists and
floats, so the same view can cross an RPC boundary and be drawn by any
front-end. Nothing here draws.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from . import plots
from .model import COLORS

__all__ = ["session_view", "jsonable_axes", "series_table", "states_table"]


def _num(value: Any) -> float | None:
    """A finite float, else ``None`` (JSON has no NaN)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _series_list(values: Any) -> list:
    """An array as a list of floats with non-finite samples as ``None``.

    ``None`` keeps a gap a gap: a curve with a hole in it must not be joined
    across the hole by whoever draws it.
    """
    arr = np.asarray(values, dtype=float).ravel()
    return [float(v) if math.isfinite(v) else float("nan") for v in arr]


def jsonable_axes(axes: dict) -> dict:
    """Convert :mod:`.plots` axis dicts into lists and floats.

    Parameters
    ----------
    axes : dict
        ``name -> {"lines", "xlim", "ylim", "xscale"}``.

    Returns
    -------
    dict
        The same structure; each line is ``{"x", "y", "color", "linestyle",
        "marker", "markersize", "label"}``.
    """
    out = {}
    for name, axis in axes.items():
        if not isinstance(axis, dict) or "lines" not in axis:
            continue
        lines = []
        for line in axis.get("lines") or []:
            x = _series_list(line.get("xdata", []))
            y = _series_list(line.get("ydata", []))
            if not x:
                continue
            colour = line.get("markerfacecolor") or line.get("color")
            lines.append(
                {
                    "x": x,
                    "y": y,
                    "color": None if colour is None else [float(c) for c in list(colour)[:3]],
                    "linestyle": line.get("linestyle") or "-",
                    "marker": line.get("marker"),
                    "markersize": _num(line.get("markersize")),
                    "label": str(line.get("displayname") or ""),
                }
            )
        xlim, ylim = axis.get("xlim"), axis.get("ylim")
        out[name] = {
            "lines": lines,
            "xlim": None if xlim is None else [_num(xlim[0]), _num(xlim[1])],
            "ylim": None if ylim is None else [_num(ylim[0]), _num(ylim[1])],
            "xscale": axis.get("xscale", "linear"),
        }
    return out


def session_view(session: Any) -> dict:
    """Everything the main window shows for the session's current selection.

    Parameters
    ----------
    session : Session
        The session; the caller holds its lock.

    Returns
    -------
    dict
        ``controls``, ``n_series``, ``series`` (the current one's label, file,
        group, length, crop and exclusion), ``analysis`` (the shown model's
        states, lower bound and number of analysed series) and ``plots`` --
        ``signal``, ``raw``, ``obs``, ``mean``, ``noise``, ``dwell``.
    """
    c = session.controls
    view: dict = {
        "controls": session.controls_dict(),
        "n_series": len(session.series),
        "series": {},
        "analysis": {},
        "plots": {},
    }
    if not session.series:
        return view
    n = int(c.series_value)
    if 1 <= n <= len(session.series):
        s = session.series[n - 1]
        view["series"] = {
            "index": n,
            "label": s.label,
            "file": s.file,
            "group": s.group,
            "length": s.length,
            "crop_min": int(s.crop_min),
            "crop_max": int(s.crop_max),
            "exclude": bool(s.exclude),
        }
    analysis = session.analysis.get(int(c.ensemble_value))
    signals = [x if x.size else None for x in session.get_signal()]
    ensemble = plots.refresh_ensemble_plots(session.series, analysis, c, signals)
    series_axes = plots.refresh_series_plots(
        session.series, analysis, c, COLORS, signal_ylim=ensemble.get("signal_ylim")
    )
    view["plots"] = jsonable_axes({**series_axes, **ensemble})
    view["series_table"] = series_table(session, analysis)
    view["states_table"] = states_table(analysis)
    if analysis is not None:
        analysed = [lb for lb, e in zip(analysis.lowerbound, analysis.expect) if e is not None]
        view["analysis"] = {
            "states": analysis.states,
            "lowerbound": _num(np.sum(analysed)) if analysed else None,
            "analysed": len(analysed),
        }
    return view


def series_table(session: Any, analysis: Any) -> list[dict]:
    """Rows of the *Series List*: one per loaded series.

    Parameters
    ----------
    session : Session
        The session.
    analysis : Analysis or None
        The selected model, for the per-series lower bound.

    Returns
    -------
    list of dict
    """
    rows = []
    for n, s in enumerate(session.series):
        lowerbound = None
        if analysis is not None and n < len(analysis.expect) and analysis.expect[n] is not None:
            lowerbound = _num(analysis.lowerbound[n])
        rows.append(
            {
                "index": n + 1,
                "label": s.label,
                "file": s.file,
                "group": s.group,
                "length": s.length,
                "crop_min": int(s.crop_min),
                "crop_max": int(s.crop_max),
                "exclude": bool(s.exclude),
                "lowerbound": lowerbound,
            }
        )
    return rows


def states_table(analysis: Any) -> list[dict]:
    """Rows of the *States Table*: the selected model, one row per state.

    The same quantities ``report.m`` writes to the Analysis Summary: the
    occupancy from the expected state counts, and the prior's center (with its
    spread), noise and most likely dwell time.

    Parameters
    ----------
    analysis : Analysis or None
        The selected model.

    Returns
    -------
    list of dict
    """
    if analysis is None or analysis.prior is None:
        return []
    from . import dist

    u = analysis.prior
    a = 0.5 * np.asarray(u.nu, dtype=float)
    b = 0.5 / np.asarray(u.W, dtype=float)
    beta = np.asarray(u.beta, dtype=float)
    z = [np.ravel(e.z) for e in analysis.expect if e is not None and np.size(e.z)]
    total = np.sum(z, axis=0) if z else np.full(a.size, np.nan)
    occupancy = total / np.sum(total) if z and np.sum(total) > 0 else total
    with np.errstate(divide="ignore", invalid="ignore"):
        center_std = np.sqrt(b / (beta * (a - 1.0)))
        noise = (a / b) ** -0.5
    dwell = np.ravel(dist.dirichlet_tau(np.asarray(u.A, dtype=float)))
    return [
        {
            "state": k + 1,
            "occupancy": _num(occupancy[k]),
            "center": _num(u.mu[k]),
            "center_std": _num(center_std[k]),
            "noise": _num(noise[k]),
            "dwell": _num(dwell[k]),
        }
        for k in range(a.size)
    ]
