"""Plot data of ebFRET's main window (``+ebfret/+plot`` and ``MainWindow/refresh.m``).

ebFRET computes every curve as a ``line`` property struct (``xdata``,
``ydata``, ``color``, ``linestyle``, ``marker``...) and hands the list to an
axis. This module is that computation, without an axis: each function returns
**line dicts** with the same keys, and :func:`refresh_series_plots` /
:func:`refresh_ensemble_plots` assemble what ``refresh('series')`` and
``refresh('ensemble')`` put on the six axes, including the axis limits the
reference derives from the data.

A line dict has

``xdata``, ``ydata``
    ``numpy.ndarray``; ``ydata`` may be 2-D ``(I, N)`` before
    :func:`mean_lines` averages it over traces.
``color``
    RGB tuple in ``0..1`` (or ``None``).
``linestyle``
    ``"-"``, ``"--"`` or ``"none"``.
``marker``
    ``"o"`` or ``None``.
``markersize``, ``markerfacecolor``, ``displayname``
    As MATLAB's line properties.

Nothing here imports a GUI toolkit; a renderer maps these dicts to its own
calls.
"""

from __future__ import annotations

import colorsys
import math
from collections.abc import Sequence

import numpy as np

from . import _matlab as ml
from . import dist
from .hmm import normalize
from .model import Analysis, Controls, Series

__all__ = [
    "get_bins",
    "get_lim",
    "line_colors",
    "mean_lines",
    "named_colors",
    "num_to_str",
    "refresh_ensemble_plots",
    "refresh_series_plots",
    "scale_lines",
    "spectrum",
    "state_dwell",
    "state_mean",
    "state_obs",
    "state_stdev",
    "time_series",
    "whist",
]


def _line(**props) -> dict:
    """A line dict with MATLAB's defaults for the keys not given.

    Parameters
    ----------
    **props
        Line properties.

    Returns
    -------
    dict
    """
    line = {
        "xdata": np.zeros(0),
        "ydata": np.zeros(0),
        "color": None,
        "linestyle": "-",
        "marker": None,
        "markersize": None,
        "markerfacecolor": None,
        "displayname": "",
    }
    line.update(props)
    return line


# --------------------------------------------------------------------------- #
# Colours
# --------------------------------------------------------------------------- #
def named_colors() -> dict:
    """The six default state colours, in order (``named_colors.m``).

    Returns
    -------
    dict
        ``name -> (r, g, b)`` in ``0..1``.
    """
    return {
        "cyan": (0.00, 0.66, 0.66),
        "blue": (0.00, 0.33, 0.66),
        "purple": (0.33, 0.00, 0.66),
        "orange": (0.75, 0.50, 0.00),
        "green": (0.33, 0.66, 0.00),
        "red": (0.66, 0.00, 0.00),
    }


def spectrum(
    m: int, min_hue: float = 0.3, max_hue: float = 1.1, min_vel: float = 0.66, max_vel: float = 0.66
) -> np.ndarray:
    """Dark rainbow colormap (``spectrum.m``).

    Parameters
    ----------
    m : int
        Number of colours.
    min_hue, max_hue : float
        Hue range (wrapped modulo 1).
    min_vel, max_vel : float
        Value at the ends and in the middle.

    Returns
    -------
    numpy.ndarray
        ``(m, 3)`` RGB in ``0..1``.
    """
    if m <= 0:
        return np.zeros((0, 3))
    h = np.mod(np.linspace(min_hue, max_hue, m), 1)
    v = max_vel - (max_vel - min_vel) * np.linspace(-1, 1, m) ** 2
    return np.array([colorsys.hsv_to_rgb(hh, 1.0, vv) for hh, vv in zip(h, v)])


def line_colors(num: int) -> list[tuple]:
    """Colours for ``num`` states (``line_colors.m``).

    Parameters
    ----------
    num : int
        Number of states.

    Returns
    -------
    list of tuple
        The named colours for up to six states, the spectrum beyond.
    """
    if num <= 6:
        return list(named_colors().values())[:num]
    return [tuple(row) for row in spectrum(num)]


# --------------------------------------------------------------------------- #
# Limits, bins, histograms
# --------------------------------------------------------------------------- #
def get_bins(x, num_bins: int | None = None, threshold: float = 0.001) -> np.ndarray:
    """Histogram bin centres insensitive to outliers (``get_bins.m``).

    Medians of the lower (upper) half are taken repeatedly until the fraction
    of samples beyond drops to ``threshold``.

    Parameters
    ----------
    x : array_like
        Samples; non-finite ones are ignored.
    num_bins : int, optional
        Number of bins; ``max(10, min(200, round(N / 10)))`` by default.
    threshold : float
        Outlier fraction to stop at.

    Returns
    -------
    numpy.ndarray
    """
    x = np.asarray(x, dtype=float).ravel()
    x = x[np.isfinite(x)]
    if num_bins is None:
        num_bins = max(10, min(200, int(round(x.size / 10))))
    xm = ml.median(x)
    # the reference leaves xl/xr unset when the loops do not run; the median
    # is what they would converge from
    xl = xr = xm
    lower = x[x < xm]
    while x.size and lower.size / x.size > threshold:
        xl = ml.median(lower)
        lower = x[x < xl]
    upper = x[x > xm]
    while x.size and upper.size / x.size > threshold:
        xr = ml.median(upper)
        upper = x[x > xr]
    return ml.linspace(xl, xr, num_bins)


def get_lim(lines: Sequence[dict], threshold: float = 0.0, pad=0.2):
    """Axis limits enclosing a set of lines (``get_lim.m``).

    Parameters
    ----------
    lines : sequence of dict
        Line dicts.
    threshold : float
        With ``threshold > 0`` the x range covers only where a line exceeds
        ``y_min + threshold * y_max``.
    pad : float or sequence of 4 float
        Padding ``(left, bottom, right, top)`` as fractions of the range.

    Returns
    -------
    x_lim, y_lim : tuple of float
    """
    pad = [float(pad)] * 4 if np.ndim(pad) == 0 else [float(p) for p in pad]
    y_mins, y_maxs, means = [], [], []
    for line in lines:
        y = np.asarray(line["ydata"], dtype=float)
        y = y.mean(axis=1) if y.ndim == 2 else y.reshape(-1)
        means.append(y)
        y_mins.append(np.nanmin(y) if y.size and not np.all(np.isnan(y)) else np.nan)
        y_maxs.append(np.nanmax(y) if y.size and not np.all(np.isnan(y)) else np.nan)
    y_min = _nan_reduce(np.nanmin, y_mins)
    y_max = _nan_reduce(np.nanmax, y_maxs)
    x_mins, x_maxs = [], []
    for line, y in zip(lines, means):
        xdata = np.asarray(line["xdata"], dtype=float).reshape(-1)
        if threshold > 0:
            msk = y > (y_min + threshold * y_max)
            idx = np.flatnonzero(msk)
            if idx.size:
                x_mins.append(xdata[idx[0]])
                x_maxs.append(xdata[idx[-1]])
            else:
                x_mins.append(np.inf)
                x_maxs.append(-np.inf)
        else:
            x_mins.append(_nan_reduce(np.nanmin, xdata))
            x_maxs.append(_nan_reduce(np.nanmax, xdata))
    lo = _nan_reduce(np.nanmin, x_mins)
    hi = _nan_reduce(np.nanmax, x_maxs)
    with np.errstate(invalid="ignore"):
        x_range = hi - lo
        y_range = y_max - y_min
        x_lim = (lo - pad[0] * x_range, hi + pad[2] * x_range)
        y_lim = (y_min - pad[1] * y_range, y_max + pad[3] * y_range)
    return tuple(float(v) for v in x_lim), tuple(float(v) for v in y_lim)


def _nan_reduce(func, values) -> float:
    """Apply a NaN-ignoring reduction, returning NaN for no finite input.

    Parameters
    ----------
    func : callable
        ``numpy.nanmin`` or ``numpy.nanmax``.
    values : array_like
        Values.

    Returns
    -------
    float
    """
    v = np.asarray(values, dtype=float).ravel()
    if v.size == 0 or np.all(np.isnan(v)):
        return float("nan")
    return float(func(v))


def whist(x, bins=None, weights=None, state=None, num_states: int | None = None):
    """Histogram of observations per state (``whist.m``).

    Parameters
    ----------
    x : array_like
        Observations, ``(T,)``.
    bins : int or array_like, optional
        Number of bins or bin centres.
    weights : array_like, optional
        ``(T, K)`` state weights.
    state : array_like, optional
        1-based state per observation; ``0`` counts towards every state.
    num_states : int, optional
        Number of states.

    Returns
    -------
    counts : numpy.ndarray
        ``(B, K)``.
    bins : numpy.ndarray
        Bin centres.
    """
    x = np.asarray(x, dtype=float).ravel()
    if bins is None or (np.ndim(bins) > 0 and len(bins) == 0):
        bins = max(10, min(x.size / 10, 200))
    if np.ndim(bins) == 0:
        _, centers = ml.hist(x, int(bins))
    else:
        centers = np.asarray(bins, dtype=float).ravel()
    if weights is not None:
        weights = np.asarray(weights, dtype=float)
        x_bin = np.argmin(np.abs(x[:, None] - centers[None, :]), axis=1)
        counts = np.zeros((centers.size, weights.shape[1]))
        for b in range(centers.size):
            counts[b] = weights[x_bin == b].sum(axis=0)
        return counts, centers
    state = np.ones(x.size, dtype=int) if state is None else np.asarray(state).ravel()
    if num_states is None:
        num_states = int(np.max(state)) if state.size else 0
    counts = np.zeros((centers.size, num_states))
    for k in range(1, num_states + 1):
        counts[:, k - 1] = ml.hist(x[state == k], centers)[0]
    counts = counts + ml.hist(x[state == 0], centers)[0][:, None]
    return counts, centers


# --------------------------------------------------------------------------- #
# Ensemble curves
# --------------------------------------------------------------------------- #
def _state_lines(K: int, color, linestyle: str) -> list[dict]:
    """``K`` empty line dicts carrying per-state colours and names.

    Parameters
    ----------
    K : int
        Number of states.
    color : sequence of tuple or tuple or None
        Per-state colours, or one for all.
    linestyle : str
        Line style.

    Returns
    -------
    list of dict
    """
    if color is not None and len(color) and np.ndim(color[0]) > 0:
        colours = list(color)
    else:
        colours = [color] * K
    return [
        _line(
            color=colours[k] if k < len(colours) else None,
            linestyle=linestyle,
            displayname="state %d" % (k + 1),
        )
        for k in range(K)
    ]


def state_obs(
    x,
    xdata=None,
    weights=None,
    state=None,
    num_states: int | None = None,
    color=None,
    linestyle: str = "-",
) -> list[dict]:
    """Normalised per-state histograms of the observations (``state_obs.m``).

    Parameters
    ----------
    x : array_like
        Observations.
    xdata : array_like, optional
        Bin centres.
    weights, state, num_states
        As :func:`whist`.
    color : sequence of tuple, optional
        State colours.
    linestyle : str
        Line style.

    Returns
    -------
    list of dict
        One line per state; the histograms together integrate to one.
    """
    x = np.asarray(x, dtype=float).ravel()
    if weights is None and state is None:
        state = np.ones(x.size, dtype=int)
        num_states = 1
    if num_states is None:
        num_states = np.asarray(weights).shape[1] if weights is not None else int(np.max(state))
    lines = _state_lines(num_states, color, linestyle)
    counts, centers = whist(x, xdata, weights=weights, state=state, num_states=num_states)
    for k, line in enumerate(lines):
        line["xdata"] = centers.copy()
        line["ydata"] = counts[:, k].copy()
    total = counts.sum()
    for line in lines:
        dx = np.mean(np.diff(line["xdata"])) if line["xdata"].size > 1 else float("nan")
        with np.errstate(divide="ignore", invalid="ignore"):
            line["ydata"] = line["ydata"] / (dx * total)
    return lines


def _as_kn(value, K: int) -> np.ndarray:
    """Reshape hyperparameters to MATLAB's ``[K N]``.

    Parameters
    ----------
    value : array_like
        ``(K,)`` or ``(K, N)``.
    K : int
        Number of states.

    Returns
    -------
    numpy.ndarray
    """
    return np.asarray(value, dtype=float).reshape(K, -1)


def _ydata(values: np.ndarray) -> np.ndarray:
    """Return ``(I, 1)`` as ``(I,)``, leaving ``(I, N)`` as is.

    Parameters
    ----------
    values : numpy.ndarray
        Curve values.

    Returns
    -------
    numpy.ndarray
    """
    return values[:, 0] if values.ndim == 2 and values.shape[1] == 1 else values


def state_mean(m, beta, a, b, xdata=None, color=None, linestyle: str = "-") -> list[dict]:
    """Marginal density of each state mean, a Student t (``state_mean.m``).

    Parameters
    ----------
    m, beta, a, b : array_like
        Normal-Gamma parameters, ``(K,)`` or ``(K, N)``.
    xdata : sequence of array_like, optional
        Per-state abscissae; ``mean +- 4 sd`` over 101 points by default.
    color : sequence of tuple, optional
        State colours.
    linestyle : str
        Line style.

    Returns
    -------
    list of dict
        ``ydata`` is ``(I,)`` for ``(K,)`` input, ``(I, N)`` otherwise.
    """
    K = np.asarray(m).shape[0]
    m, beta, a, b = (_as_kn(v, K) for v in (m, beta, a, b))
    lines = _state_lines(K, color, linestyle)
    for k, line in enumerate(lines):
        if xdata is not None:
            xs = np.asarray(xdata[k], dtype=float).reshape(-1)
        else:
            e_mu = m[k]
            with np.errstate(divide="ignore", invalid="ignore"):
                v_mu = b[k] / (beta[k] * a[k])
            xs = np.linspace(np.nanmin(e_mu - 4 * v_mu**0.5), np.nanmax(e_mu + 4 * v_mu**0.5), 101)
        line["xdata"] = xs
        with np.errstate(divide="ignore", invalid="ignore"):
            line["ydata"] = _ydata(
                np.exp(
                    dist.studt_log_pdf(
                        xs[:, None],
                        m[k][None, :],
                        (beta[k] * a[k] / b[k])[None, :],
                        (2 * a[k])[None, :],
                    )
                )
            )
    return lines


def state_stdev(a, b, xdata=None, color=None, linestyle: str = "-") -> list[dict]:
    """Density of each state's noise ``sigma = lambda^-1/2`` (``state_stdev.m``).

    Parameters
    ----------
    a, b : array_like
        Gamma parameters of the precision, ``(K,)`` or ``(K, N)``.
    xdata : sequence of array_like, optional
        Per-state abscissae; ``(0, mean + 4 sd]`` over 100 points by default.
    color : sequence of tuple, optional
        State colours.
    linestyle : str
        Line style.

    Returns
    -------
    list of dict
    """
    K = np.asarray(a).shape[0]
    a, b = _as_kn(a, K), _as_kn(b, K)
    lines = _state_lines(K, color, linestyle)
    for k, line in enumerate(lines):
        if xdata is not None:
            xs = np.asarray(xdata[k], dtype=float).reshape(-1)
        else:
            e_l = a[k] / b[k]
            var_l = a[k] / b[k] ** 2
            e_sigma = e_l**-0.5
            var_sigma = 0.25 * e_l**-3 * var_l
            xs = np.linspace(0, np.nanmax(e_sigma + 4 * var_sigma**0.5), 101)[1:]
        line["xdata"] = xs
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            line["ydata"] = _ydata(
                2
                * xs[:, None] ** -3
                * np.exp(dist.gamma_log_pdf(xs[:, None] ** -2, a[k][None, :], b[k][None, :]))
            )
    return lines


def state_dwell(alpha, xdata=None, color=None, linestyle: str = "-") -> list[dict]:
    """Density of each state's dwell time from the transition Dirichlets.

    Port of ``state_dwell.m``: ``rho = A_kk`` is Beta-distributed and
    ``tau = -1 / log(rho)``.

    Parameters
    ----------
    alpha : array_like
        ``(K, K)`` or ``(K, K, N)`` Dirichlet parameters.
    xdata : sequence of array_like, optional
        Per-state abscissae; log-spaced over ``[0.01, 100] * median E[tau]``.
    color : sequence of tuple, optional
        State colours.
    linestyle : str
        Line style.

    Returns
    -------
    list of dict
    """
    alpha = np.asarray(alpha, dtype=float)
    K = alpha.shape[0]
    alpha = alpha.reshape(K, K, -1)
    a = np.stack([alpha[k, k, :] for k in range(K)], axis=0)
    b = alpha.sum(axis=1) - a
    lines = _state_lines(K, color, linestyle)
    for k, line in enumerate(lines):
        if xdata is not None:
            xs = np.asarray(xdata[k], dtype=float).reshape(-1)
        else:
            with np.errstate(divide="ignore", invalid="ignore"):
                e_rho = a[k] / (a[k] + b[k])
                e_tau = -1.0 / np.log(e_rho)
            med = np.median(e_tau)
            xs = np.exp(np.linspace(np.log(0.01 * med), np.log(100 * med), 101))
        line["xdata"] = xs
        rho = np.exp(-1.0 / xs)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            line["ydata"] = _ydata(
                (rho / xs**2)[:, None]
                * np.exp(dist.beta_log_pdf(rho[:, None], a[k][None, :], b[k][None, :]))
            )
    return lines


def mean_lines(lines: Sequence[dict]) -> list[dict]:
    """Average each line's ``ydata`` over traces (``+plot/mean.m``).

    Parameters
    ----------
    lines : sequence of dict
        Lines with ``(I, N)`` ``ydata``.

    Returns
    -------
    list of dict
    """
    out = []
    for line in lines:
        y = np.asarray(line["ydata"], dtype=float)
        new = dict(line)
        new["ydata"] = y.mean(axis=1) if y.ndim == 2 else y
        out.append(new)
    return out


def scale_lines(lines: Sequence[dict], s) -> list[dict]:
    """Multiply the ``ydata`` of line ``l`` by ``s[l]`` (``+plot/scale.m``).

    Parameters
    ----------
    lines : sequence of dict
        Lines.
    s : float or array_like
        One factor for all, or one per line.

    Returns
    -------
    list of dict
    """
    factors = (
        np.broadcast_to(np.asarray(s, dtype=float).reshape(-1), (len(lines),))
        if np.size(s) in (1, len(lines))
        else np.asarray(s, dtype=float).reshape(-1)
    )
    out = []
    for line, f in zip(lines, factors):
        new = dict(line)
        new["ydata"] = f * np.asarray(line["ydata"], dtype=float)
        out.append(new)
    return out


# --------------------------------------------------------------------------- #
# Time series
# --------------------------------------------------------------------------- #
def time_series(
    x,
    t=None,
    crop_min: int | None = None,
    crop_max: int | None = None,
    state=None,
    num_states: int | None = None,
    mean=None,
    colors=None,
    markersize: float | None = None,
) -> list[dict]:
    """Trace with its state path and cropped-out regions (``time_series.m``).

    The list has the reference's layout: the analysed signal first, then
    (with a state path) the per-state mean line and one marker line per
    state, then a dashed line for each cropped-out end longer than one frame.
    As in the reference, a colour list longer than the lines drawn still
    creates those (empty) lines, so indices stay aligned with ``colors``.

    Parameters
    ----------
    x : array_like
        Signal, ``(T,)``.
    t : array_like, optional
        Time per frame; ``0..T-1`` by default.
    crop_min, crop_max : int, optional
        Inclusive 1-based analysed range.
    state : array_like, optional
        1-based state per analysed frame.
    num_states : int, optional
        Number of states.
    mean : array_like, optional
        State level per analysed frame; the per-state mean of ``x`` when
        omitted.
    colors : sequence of tuple, optional
        ``[signal, mean line, state 1, ...]``.
    markersize : float, optional
        Marker size of every line.

    Returns
    -------
    list of dict
    """
    x = np.asarray(x, dtype=float).ravel()
    T = x.size
    t = np.arange(T, dtype=float) if t is None or len(t) == 0 else np.asarray(t).ravel()
    state = None if state is None or len(state) == 0 else np.asarray(state).ravel().astype(int)
    mean = None if mean is None or len(mean) == 0 else np.asarray(mean, dtype=float).ravel()
    if num_states is not None:
        K = int(num_states)
    elif state is not None:
        K = int(state.max())
    elif mean is not None:
        K = int(np.unique(mean).size)
    else:
        K = 0
    weights = None
    if state is not None:
        weights = (state[:, None] == np.arange(1, K + 1)[None, :]).astype(float)

    if crop_min is not None and crop_max is not None:
        inside = np.arange(crop_min - 1, crop_max)
        outside = [np.arange(0, crop_min), np.arange(crop_max - 1, T)]
    else:
        inside = np.arange(T)
        outside = [np.zeros(0, dtype=int), np.zeros(0, dtype=int)]

    colors = list(colors) if colors else []
    n_initial = max(len(colors), 1)
    lines = [
        _line(color=colors[i] if i < len(colors) else None, markersize=markersize)
        for i in range(n_initial)
    ]

    def ensure(index: int) -> dict:
        while len(lines) <= index:
            lines.append(_line(markersize=markersize))
        return lines[index]

    if inside.size:
        first = ensure(0)
        first["ydata"] = x[inside]
        first["xdata"] = t[inside]
        first["displayname"] = "signal"
        if mean is None and weights is not None:
            with np.errstate(divide="ignore", invalid="ignore"):
                e_x = (x[inside][:, None] * weights).sum(axis=0) / weights.sum(axis=0)
            mean = e_x[state - 1]
        if mean is not None:
            second = ensure(1)
            second["ydata"] = mean
            second["xdata"] = first["xdata"]
            second["displayname"] = "state mean"
            for k in range(1, K + 1):
                marks = ensure(k + 1)
                sel = state == k
                marks["xdata"] = second["xdata"][sel]
                marks["ydata"] = second["ydata"][sel]
                marks["marker"] = "o"
                marks["linestyle"] = "none"
                marks["displayname"] = "state %d" % k
                marks["markerfacecolor"] = marks["color"]
    for out in outside:
        if out.size > 1:
            lines.append(
                _line(
                    ydata=x[out],
                    xdata=t[out],
                    linestyle="--",
                    color=lines[0]["color"],
                    markersize=markersize,
                )
            )
    return lines


# --------------------------------------------------------------------------- #
# refresh.m
# --------------------------------------------------------------------------- #
def refresh_series_plots(
    series: Sequence[Series],
    analysis: Analysis | None,
    controls: Controls,
    colors: dict,
    signal_ylim: tuple | None = None,
) -> dict:
    """What ``refresh('series')`` draws for the selected series.

    Parameters
    ----------
    series : sequence of Series
        All series of the session.
    analysis : Analysis or None
        The analysis shown (``analysis(controls.ensemble_value)``).
    controls : Controls
        Uses ``series_value`` (1-based), ``show_viterbi`` and ``crop_margin``.
    colors : dict
        ``obs``, ``viterbi``, ``donor``, ``acceptor`` RGB tuples.
    signal_ylim : tuple, optional
        Signal-axis y limits set by the ensemble refresh (its histogram range).

    Returns
    -------
    dict
        ``{"signal": {...}, "raw": {...}}``, each with ``lines``, ``xlim``,
        ``ylim`` (``None`` = automatic) and ``xscale``; empty when there is no
        series to show.
    """
    n = int(controls.series_value)
    if not series or n <= 0:
        return {}
    s = series[n - 1]
    if not s.exclude:
        crop_max = int(s.crop_max)
    else:
        crop_max = s.length
    colours = [colors["obs"]]
    state = None
    num_states = None
    if controls.show_viterbi and analysis is not None and n - 1 < len(analysis.viterbi):
        # refresh.m wraps this in try/catch: without an analysis entry for the
        # series it falls back to the bare signal colour
        vit = analysis.viterbi[n - 1]
        colours = [colors["obs"], colors["viterbi"], *line_colors(analysis.states)]
        num_states = analysis.states
        state = None if vit is None else vit.state
    kwargs = dict(
        crop_min=int(s.crop_min),
        crop_max=int(s.crop_max),
        state=state,
        num_states=num_states,
        markersize=4,
    )
    signal = time_series(s.signal, s.time, colors=colours, **kwargs)
    colours_d = [colors["donor"], *colours[1:]]
    colours_a = [colors["acceptor"], *colours[1:]]
    donor = time_series(s.donor, s.time, colors=colours_d, **kwargs)
    acceptor = time_series(s.acceptor, s.time, colors=colours_a, **kwargs)
    if controls.show_viterbi:
        # drops the state-mean line; with no state path this drops whatever sits
        # at index 1 instead, as the reference does
        raw = [donor[0], *donor[2:], acceptor[0], *acceptor[2:]]
    else:
        raw = [*donor, *acceptor]
    time = np.asarray(s.time, dtype=float).ravel()
    t_min = float(np.min(time))
    t_max = float(time[min(s.length, crop_max + int(controls.crop_margin)) - 1])
    return {
        "signal": {
            "lines": signal,
            "xlim": (t_min, t_max),
            "ylim": signal_ylim,
            "xscale": "linear",
        },
        "raw": {"lines": raw, "xlim": (t_min, t_max), "ylim": None, "xscale": "linear"},
    }


def refresh_ensemble_plots(
    series: Sequence[Series], analysis: Analysis | None, controls: Controls, signals: Sequence
) -> dict:
    """What ``refresh('ensemble')`` draws for the selected number of states.

    Parameters
    ----------
    series : sequence of Series
        All series (only ``exclude`` is read).
    analysis : Analysis or None
        The analysis shown.
    controls : Controls
        Uses ``show_prior``, ``show_posterior`` and ``scale_plots``.
    signals : sequence of array_like or None
        ``get_signal()``: cropped, clipped signal per series, ``None`` for an
        excluded one.

    Returns
    -------
    dict
        ``obs``, ``mean``, ``noise``, ``dwell`` axes (``lines``, ``xlim``,
        ``ylim``, ``xscale``) and ``signal_ylim`` for the time-series axis;
        empty when the reference clears the panel (no series, no analysis, or
        every series excluded).
    """
    if not series or analysis is None or analysis.prior is None or all(s.exclude for s in series):
        return {}
    K = analysis.states
    colours = line_colors(K)

    xs, states = [], []
    for n, s in enumerate(series):
        x_n = signals[n] if n < len(signals) else None
        x_n = np.zeros(0) if x_n is None else np.asarray(x_n, dtype=float).ravel()
        vit = analysis.viterbi[n] if n < len(analysis.viterbi) else None
        if not s.exclude and vit is not None and len(vit.state):
            st = np.asarray(vit.state).ravel().astype(int)
        else:
            st = np.zeros(x_n.size, dtype=int)
        xs.append(x_n)
        states.append(st)
    x = np.concatenate(xs) if xs else np.zeros(0)
    state = np.concatenate(states) if states else np.zeros(0, dtype=int)
    keep = np.isfinite(x)
    x, state = x[keep], state[keep]
    n_included = sum(not s.exclude for s in series)
    x_bins = get_bins(x, 200, min(0.5 / n_included, 1e-2))
    obs = state_obs(x, xdata=x_bins, state=state, num_states=K, color=colours, linestyle="-")

    prior_lines: dict = {}
    if controls.show_prior:
        u = analysis.prior
        u_a = 0.5 * np.asarray(u.nu, dtype=float)
        u_b = 0.5 / np.asarray(u.W, dtype=float)
        # refresh.m first tries to reuse the posterior curves' abscissae, which
        # do not exist yet at that point, so its fallback -- automatic
        # abscissae -- is what always runs.
        try:
            prior_lines["mean"] = state_mean(u.mu, u.beta, u_a, u_b, color=colours, linestyle="--")
            prior_lines["noise"] = state_stdev(u_a, u_b, color=colours, linestyle="--")
            prior_lines["dwell"] = state_dwell(u.A, color=colours, linestyle="--")
        except (ValueError, FloatingPointError, IndexError):
            prior_lines = {}

    posterior_lines: dict = {}
    if controls.show_posterior:
        ns = [
            n
            for n, s in enumerate(series)
            if not s.exclude and n < len(analysis.posterior) and analysis.posterior[n] is not None
        ]
        if ns:
            post = [analysis.posterior[n] for n in ns]
            w_m = np.stack([np.ravel(w.mu) for w in post], axis=1)
            w_beta = np.stack([np.ravel(w.beta) for w in post], axis=1)
            w_a = 0.5 * np.stack([np.ravel(w.nu) for w in post], axis=1)
            w_b = 0.5 / np.stack([np.ravel(w.W) for w in post], axis=1)
            w_alpha = np.stack([np.asarray(w.A, dtype=float).reshape(K, K) for w in post], axis=2)
            posterior_lines["mean"] = mean_lines(
                state_mean(w_m, w_beta, w_a, w_b, color=colours, linestyle="-")
            )
            posterior_lines["noise"] = mean_lines(
                state_stdev(w_a, w_b, color=colours, linestyle="-")
            )
            with np.errstate(divide="ignore"):
                e_tau = -1.0 / np.log(np.diag(normalize(w_alpha.mean(axis=2), axis=1)[0]))
            xdata = [
                np.exp(np.linspace(np.log(0.01 * tau), np.log(100 * tau), 101)) for tau in e_tau
            ]
            posterior_lines["dwell"] = mean_lines(
                state_dwell(w_alpha, xdata=xdata, color=colours, linestyle="-")
            )

    result: dict = {}
    x_lim, y_lim = get_lim(obs, 1e-2, [0.05, 0.05, 0.05, 0.15])
    result["obs"] = {"lines": obs, "xlim": x_lim, "ylim": y_lim, "xscale": "linear"}
    result["signal_ylim"] = x_lim

    scale = 1.0
    if controls.scale_plots:
        zs = [np.ravel(e.z) for e in analysis.expect if e is not None and np.size(e.z)]
        if zs:
            scale = np.stack(zs, axis=1).mean(axis=1)

    for name, threshold in (("mean", 0.02), ("noise", 0.02), ("dwell", 0.001)):
        ax_lines: list = []
        if name in prior_lines:
            ax_lines += scale_lines(prior_lines[name], scale)
        if name in posterior_lines:
            ax_lines += scale_lines(posterior_lines[name], scale)
        entry = {
            "lines": ax_lines,
            "xlim": None,
            "ylim": None,
            "xscale": "log" if name == "dwell" else "linear",
        }
        if ax_lines:
            x_lim, y_lim = get_lim(ax_lines, threshold, [0.05, 0.05, 0.05, 0.25])
            if name == "dwell":
                x_lim = (ml.nan_max(1e-4 * x_lim[1], x_lim[0]), x_lim[1])
            if all(math.isfinite(v) for v in x_lim):
                entry["xlim"] = x_lim
            if all(math.isfinite(v) for v in y_lim):
                entry["ylim"] = y_lim
        result[name] = entry
    return result


def num_to_str(num, max_length: int = 4) -> list[str]:
    """Short tick labels (``num_to_str.m``).

    Fixed-point with trailing zeros stripped, unless any label is longer than
    ``max_length``, in which case all use a one-decimal scientific form.

    Parameters
    ----------
    num : float or array_like
        Values.
    max_length : int
        Longest fixed-point label allowed.

    Returns
    -------
    list of str
    """
    values = np.atleast_1d(np.asarray(num, dtype=float)).ravel()

    def strip_zero(text: str) -> str:
        stripped = text.rstrip("0")
        if stripped.endswith("."):
            stripped = stripped[:-1]
        return stripped

    def format_sci(value: float) -> str:
        if value == 0:
            return "0"
        sign = "-" if value < 0 else ""
        value = abs(value)
        dec = math.floor(math.log(value) / math.log(10))
        fl = value / 10**dec
        if dec != 0:
            return sign + ("%de%d" % (fl, dec) if round(fl) == fl else "%.1fe%d" % (fl, dec))
        return sign + ("%d" % fl if round(fl) == fl else f"{fl:.1f}")

    labels = [strip_zero(f"{v:f}") for v in values]
    if any(len(label) > max_length for label in labels):
        labels = [format_sci(v) for v in values]
    return labels
