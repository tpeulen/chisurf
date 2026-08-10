"""What a VV/VH decay fit looks like on screen, decided without a screen.

A burst and a region are the same measurement seen through different membership
rules: photons go into a VV|VH micro-time stack, a single-lifetime MLE fits it,
and what a person then wants to see is the data, the model, the IRF, the
background and the weighted residuals — on a log axis, with the residuals
sharing the time axis above them.

The two tools that do this grew the display logic separately, and it is not
decoration. Four of the decisions below exist because the obvious version
produces a panel that is unreadable exactly when something has gone wrong:

* a **diverged** fit returns a model whose amplitude has run away by orders of
  magnitude, and plotted raw it takes the log view to ~1e6 and hides the data;
* the IRF and the background have to be **area**-normalised to overlay legibly,
  never peak-normalised — one hot bin then decides the whole scaling;
* the y-range must be pinned to the *data*, because a background-dominated fit
  can span 1e±27 and the auto-range obligingly shows all of it;
* the residuals need a symmetric band, or one bad channel sets the scale and
  every other residual becomes a flat line.

Nothing here imports Qt. The widget that draws it is
:mod:`chisurf.gui.widgets.decay_panel`.
"""

from __future__ import annotations

import dataclasses

import numpy as np

__all__ = [
    "DecayCurves",
    "decay_curves",
    "decay_ylim",
    "overlay_scaled",
    "residual_ylim",
    "vv_vh_window",
    "weighted_residuals",
]


def vv_vh_window(stack, vv=(0, None), vh=(0, None)):
    """Return the VV|VH *stack* with a window applied to each half separately.

    A VV/VH array is two decays laid end to end, and they do not share a fit
    window: the perpendicular channel's useful range starts and ends elsewhere.
    Slicing the concatenated array as one is the mistake this exists to prevent
    — it takes the window out of the wrong half and leaves a decay that looks
    fine and is one channel's tail glued to the other's rise.

    Parameters
    ----------
    stack : array-like
        ``2n`` values: the parallel decay followed by the perpendicular one.
    vv, vh : tuple of int
        ``(start, stop)`` per half; ``None`` for stop means to the end.

    Returns
    -------
    numpy.ndarray
        The two windows concatenated.
    """
    values = np.asarray(stack, dtype=float)
    n = values.size // 2
    vv_start = max(0, int(vv[0]))
    vv_stop = n if vv[1] is None else min(n, int(vv[1]))
    vh_start = max(0, int(vh[0]))
    vh_stop = n if vh[1] is None else min(n, int(vh[1]))
    return np.hstack([values[0:n][vv_start:vv_stop], values[n:2 * n][vh_start:vh_stop]])


def overlay_scaled(curve, data):
    """Scale *curve* to the total of *data*, for display only.

    The IRF and the background are shown to be *compared*, not to be believed:
    both keep their shape and are area-matched to the data so they overlay
    legibly without swamping the decay. Peak normalisation is the tempting
    alternative and is wrong — a single hot bin then sets the scale for the
    whole curve. The background's actual weight in the fit is the scatter
    parameter, never this scaling.

    Parameters
    ----------
    curve : array-like
        The IRF or background to overlay.
    data : array-like
        The measured decay whose total it is matched to.

    Returns
    -------
    numpy.ndarray
        *curve*, scaled; unchanged when either total is non-positive.
    """
    curve = np.asarray(curve, dtype=float)
    total = float(np.sum(curve))
    target = float(np.sum(np.asarray(data, dtype=float)))
    if total > 0 and target > 0:
        return curve / total * target
    return curve


def weighted_residuals(data, model):
    """Return ``(data - model) / sqrt(data)``, zero where there are no counts.

    Poisson weighting, and the zero matters: a channel with no photons has no
    uncertainty to divide by, and letting it through produces an infinity that
    takes the residual panel's range with it.

    Parameters
    ----------
    data : array-like
        Measured counts.
    model : array-like
        The fitted decay, same length.

    Returns
    -------
    numpy.ndarray
    """
    data = np.asarray(data, dtype=float)
    model = np.asarray(model, dtype=float)
    residuals = np.zeros_like(data, dtype=float)
    counted = data > 0
    residuals[counted] = (data[counted] - model[counted]) / np.sqrt(data[counted])
    return residuals


def decay_ylim(data, *, fallback=(0.1, 1.0e5)):
    """Return ``(lo, hi)`` limits **in counts**, pinned to the data's own range.

    Anchoring to the data rather than to everything drawn is what keeps the
    panel readable when the model or the scaled background has run away: an
    auto-ranged log axis will happily show 1e-277 to 1e27 and reduce the decay
    to a flat line at the top.

    **Counts, not log10.** ``chiplot``'s ``set_ylim`` takes data units on every
    axis and does the log conversion itself, so handing it log10 values logs
    them twice and produces a view a few counts high — which is what the burst
    tool was doing, and why the decay sat off the top of its own panel.

    Parameters
    ----------
    data : array-like
        The measured decay, in counts.
    fallback : tuple of float
        Used when nothing is positive and finite.

    Returns
    -------
    tuple of float
        Limits in counts, for an axis that may be log-scaled.
    """
    values = np.asarray(data, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if not values.size:
        return fallback
    lo = max(float(values.min()) * 0.5, 1e-2)
    hi = float(values.max()) * 3.0
    return (lo, hi if hi > lo else lo * 10.0)


def residual_ylim(residuals, *, minimum: float = 5.0, percentile: float = 99.0):
    """Return a symmetric ``(-span, span)`` band for the residual panel.

    The percentile, not the maximum: one bad channel otherwise sets the scale
    and flattens every other residual into a line through zero. The floor keeps
    a *good* fit from being magnified until its noise looks like structure.

    Parameters
    ----------
    residuals : array-like
        The weighted residuals to be shown.
    minimum : float
        Smallest half-height of the band.
    percentile : float
        Which percentile of ``|residual|`` sets it.

    Returns
    -------
    tuple of float
    """
    values = np.asarray(residuals, dtype=float)
    values = values[np.isfinite(values)]
    span = float(np.percentile(np.abs(values), percentile)) if values.size else minimum
    span = max(span, minimum)
    return (-span, span)


@dataclasses.dataclass
class DecayCurves:
    """Everything a decay panel draws, already in display units.

    Attributes
    ----------
    channels : numpy.ndarray
        X values for the windowed data/model.
    data, model : numpy.ndarray
        The measured decay and the fitted one, windowed.
    irf, background : numpy.ndarray or None
        Overlays, area-matched to the data. ``None`` when not applicable — a
        tail fit does not deconvolve, so an IRF overlay there would be a
        statement the fit did not make.
    residuals : numpy.ndarray
        Weighted residuals over the same window.
    decay_ylim : tuple of float
        Pinned range for the decay panel, **in counts**.
    residual_ylim : tuple of float
        Pinned symmetric band for the residual panel.
    diverged : bool
        Whether the model was clipped for display.
    """

    channels: np.ndarray
    data: np.ndarray
    model: np.ndarray
    residuals: np.ndarray
    irf: np.ndarray | None = None
    background: np.ndarray | None = None
    decay_ylim: tuple = (0.1, 1.0e5)
    residual_ylim: tuple = (-5.0, 5.0)
    diverged: bool = False


def decay_curves(data, model, *, irf=None, background=None,
                 vv=(0, None), vh=(0, None), deconvolved: bool = True,
                 clip_factor: float = 10.0, diverged: bool | None = None) -> DecayCurves:
    """Assemble everything a VV/VH decay panel draws.

    Parameters
    ----------
    data, model : array-like
        Full VV|VH stacks, as the estimator produced them.
    irf, background : array-like, optional
        Full VV|VH stacks; overlaid area-matched to the data.
    vv, vh : tuple of int
        Per-half display windows.
    deconvolved : bool
        False for a tail fit, which does not deconvolve — the IRF is then
        dropped rather than drawn beside a model that never used it.
    clip_factor : float
        A model exceeding this multiple of the data's maximum is clipped for
        display. The fitted parameters are untouched: the clipping is about
        what can be seen, not what was found.
    diverged : bool, optional
        Say so when the *fit* knows — a parameter pinned at its bound is a fact
        about the fit, where a large drawn amplitude is only a symptom, and the
        two do not always coincide. Left unset, divergence is inferred from the
        amplitude alone.

    Returns
    -------
    DecayCurves
    """
    data_rng = vv_vh_window(data, vv, vh)
    model_rng = vv_vh_window(model, vv, vh)

    shown = np.nan_to_num(model_rng, nan=0.0, posinf=0.0, neginf=0.0)
    ran_away = False
    if data_rng.size:
        cap = float(np.nanmax(data_rng)) * float(clip_factor)
        if cap > 0 and float(np.nanmax(shown, initial=0.0)) > cap:
            shown = np.clip(shown, 0.0, cap)
            ran_away = True
    diverged = ran_away if diverged is None else bool(diverged)

    irf_rng = None
    if irf is not None and deconvolved:
        irf_rng = overlay_scaled(vv_vh_window(irf, vv, vh), data_rng)
    background_rng = None
    if background is not None:
        background_rng = overlay_scaled(vv_vh_window(background, vv, vh), data_rng)

    # Residuals from the *full* stacks, then windowed: computing them on the
    # windowed arrays would pair a data channel with the model channel that
    # happens to sit at the same offset in a differently-cropped array.
    residuals = vv_vh_window(weighted_residuals(data, model), vv, vh)

    return DecayCurves(
        channels=np.arange(data_rng.size, dtype=float),
        data=data_rng,
        model=shown,
        residuals=residuals,
        irf=irf_rng,
        background=background_rng,
        decay_ylim=decay_ylim(data_rng),
        residual_ylim=residual_ylim(residuals),
        diverged=diverged,
    )
