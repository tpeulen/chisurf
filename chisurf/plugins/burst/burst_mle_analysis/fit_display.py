"""The curves of a burst-MLE fit as they are displayed, computed once for every front end.

The Qt wizard's ``plot_fit_result`` and the emtk app both show the same four curves of the fit that last ran:
the decay (data), the model, the IRF and the background overlays, and the weighted residuals, each cut to the
per-polarisation fit windows. They used to be computed inside the wizard only; the emtk app then drew an invented
decay instead. :func:`decay_curves` is that computation as a pure function so both draw the same numbers, and the
parity test compares them with the wizard's own plot.

Qt-free and emtk-free.
"""

from __future__ import annotations

from dataclasses import dataclass

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

    @property
    def x(self) -> np.ndarray:
        """Channel index into the windowed curves."""
        return np.arange(self.data.size)


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

    return DecayCurves(
        data=data_rng,
        model=model_disp,
        irf=None if tail else _overlay(irf_rng, s_dat),
        background=_overlay(bg_rng, s_dat),
        residuals=resid_rng,
        n_vv=n_vv,
    )
