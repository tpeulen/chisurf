"""The curves of a burst-MLE fit as they are displayed, computed once for every front end.

Every front end shows the same curves of the fit that last ran: the decay (data), the model, the IRF and the
background overlays, and the weighted residuals, each cut to the per-polarisation fit windows. :func:`decay_curves`
computes them as a pure function, so no front end draws a decay of its own. GUI-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class TailFitResult:
    """What the tail fit hands back: the free parameters in schema order and its quality, read by attribute.

    ``x`` is ``[tail_start, tau1, tau2, ...]``; ``twoIstar`` is the negative log-likelihood. The same two names a
    ``Fit2xResult`` carries, so ``update_fit_ui`` and ``_fit_diverged`` treat both alike.
    """

    x: list
    twoIstar: float


@dataclass(frozen=True)
class DecayCurves:
    """The displayed curves of the last fit, VV window followed by VH window (``x`` is the index into them)."""

    data: np.ndarray
    model: np.ndarray
    irf: np.ndarray | None
    background: np.ndarray
    residuals: np.ndarray
    #: Number of VV channels in the windowed curves (the VH window follows).
    n_vv: int
    #: The whole decay, VV half then VH half, and the overlays on the same axis and scale: the
    #: plot shows all of it, the fit window and the IRF range highlighted on it.
    data_full: np.ndarray = field(default_factory=lambda: np.zeros(0))
    model_full: np.ndarray = field(default_factory=lambda: np.zeros(0))
    irf_full: np.ndarray | None = None
    background_full: np.ndarray = field(default_factory=lambda: np.zeros(0))
    #: ``[(start, stop), ...]`` on the full axis: the fit window of the VV half, then of the VH half.
    fit_windows: tuple = ()
    #: ``[(start, stop), ...]`` on the full axis, per half: where the IRF the fit convolves with is
    #: not zero, inside the IRF clip (``irf_start``/``irf_stop``).
    irf_windows: tuple = ()

    @property
    def x(self) -> np.ndarray:
        """Channel index into the windowed curves."""
        return np.arange(self.data.size)

    @property
    def x_full(self) -> np.ndarray:
        """Channel index into the whole decay (VV half, then VH half)."""
        return np.arange(self.data_full.size)


def clamp_window(start: int, stop: int | None, n: int) -> tuple[int, int]:
    """Clamp a ``[start, stop)`` bin window to a half-histogram of *n* bins (``stop=None``: to the end)."""
    start = max(0, int(start))
    stop = min(n, int(stop)) if stop is not None else n
    return start, stop


def windowed(
    full: np.ndarray, ranges: tuple[int, int | None, int, int | None]
) -> tuple[np.ndarray, int]:
    """VV window then VH window of a two-halves array, and the VV length."""
    n = len(full) // 2
    vv_sb, vv_eb = clamp_window(ranges[0], ranges[1], n)
    vh_sb, vh_eb = clamp_window(ranges[2], ranges[3], n)
    vv = full[0:n][vv_sb:vv_eb]
    vh = full[n : 2 * n][vh_sb:vh_eb]
    return np.hstack([vv, vh]), int(vv.size)


def _overlay(arr: np.ndarray, total: float) -> np.ndarray:
    """Area-normalise *arr* to the data's total counts (display only; the shape is kept)."""
    s = float(np.sum(arr))
    return arr / s * total if (s > 0 and total > 0) else arr


def decay_curves(
    data: np.ndarray,
    model: np.ndarray,
    irf: np.ndarray,
    background: np.ndarray,
    ranges: tuple[int, int | None, int, int | None],
    *,
    tail: bool = False,
    diverged: bool = False,
    irf_range: tuple[int, int] = (-1, -1),
    data_all: np.ndarray | None = None,
) -> DecayCurves:
    """Window and scale the fit's data, model, IRF and background for display.

    Parameters
    ----------
    data, model : numpy.ndarray
        The fitted decay and the model curve, VV half then VH half.
    irf, background : numpy.ndarray
        The IRF and background patterns of the current detector, same layout.
    ranges : tuple
        ``(vv_start, vv_stop, vh_start, vh_stop)`` in histogram bins.
    tail : bool
        The tail fit does not deconvolve an IRF, so none is returned.
    diverged : bool
        A diverged fit returns a model whose amplitude ran away; the displayed model is clipped to ten times the
        data maximum so the panel stays readable (the fitted parameters are untouched).
    irf_range : tuple of int
        ``(irf_start, irf_stop)`` of the IRF clip in bins of one half (``-1``: that edge is open).
    data_all : numpy.ndarray, optional
        The decay with every channel, not cut to the fit window (same layout): the data shown.
    """
    data_full = np.asarray(data, dtype=float)
    model_full = np.asarray(model, dtype=float)
    data_rng, n_vv = windowed(data_full, ranges)
    model_rng, _ = windowed(model_full, ranges)
    model_disp = np.nan_to_num(model_rng, nan=0.0, posinf=0.0, neginf=0.0)
    if diverged and data_rng.size:
        cap = float(np.nanmax(data_rng)) * 10.0
        if cap > 0:
            model_disp = np.clip(model_disp, 0.0, cap)

    s_dat = float(np.sum(data_rng)) if data_rng.size else 0.0
    irf_rng, _ = windowed(np.asarray(irf, dtype=np.float64), ranges)
    bg_rng, _ = windowed(np.asarray(background, dtype=np.float64), ranges)

    resid = np.zeros_like(data_full, dtype=float)
    mask = data_full > 0
    resid[mask] = (data_full[mask] - model_full[mask]) / np.sqrt(data_full[mask])
    resid_rng, _ = windowed(resid, ranges)

    half = data_full.size // 2
    vv = clamp_window(ranges[0], ranges[1], half)
    vh = clamp_window(ranges[2], ranges[3], half)
    start, stop = int(irf_range[0]), int(irf_range[1])
    irf_lo = max(0, start) if start >= 0 else 0
    irf_hi = min(half, stop + 1) if stop >= 0 else half
    model_full_disp = np.nan_to_num(model_full, nan=0.0, posinf=0.0, neginf=0.0)
    if diverged and data_rng.size:
        cap = float(np.nanmax(data_rng)) * 10.0
        if cap > 0:
            model_full_disp = np.clip(model_full_disp, 0.0, cap)

    def scaled(full: np.ndarray, rng: np.ndarray) -> np.ndarray:
        # the factor the windowed overlay got, so both agree inside the window
        s = float(np.sum(rng))
        return full * (s_dat / s) if (s > 0 and s_dat > 0) else full

    irf_arr = np.asarray(irf, dtype=np.float64)
    bg_arr = np.asarray(background, dtype=np.float64)

    def support(lo: int, hi: int, offset: int) -> tuple[int, int]:
        # the IRF range used: where the IRF the fit convolves with is not zero, inside the clip
        part = irf_arr[offset + lo : offset + hi] if irf_arr.size == data_full.size else np.zeros(0)
        nonzero = np.flatnonzero(part > 0)
        if nonzero.size == 0:
            return offset + lo, offset + hi
        return offset + lo + int(nonzero[0]), offset + lo + int(nonzero[-1]) + 1
    return DecayCurves(
        data=data_rng,
        model=model_disp,
        irf=None if tail else _overlay(irf_rng, s_dat),
        background=_overlay(bg_rng, s_dat),
        residuals=resid_rng,
        n_vv=n_vv,
        data_full=(
            np.asarray(data_all, dtype=float)
            if data_all is not None and np.size(data_all) == data_full.size
            else data_full
        ),
        model_full=model_full_disp,
        irf_full=None if tail else scaled(irf_arr, irf_rng),
        background_full=scaled(bg_arr, bg_rng),
        fit_windows=(vv, (half + vh[0], half + vh[1])),
        irf_windows=() if tail else (support(irf_lo, irf_hi, 0), support(irf_lo, irf_hi, half)),
    )
