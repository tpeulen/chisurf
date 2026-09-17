r"""Rectangle FRAP: recovery after photobleaching, fitted in space and time.

Bleach a rectangle into a fluorescent sample and watch it fill back in. How fast
it fills gives the diffusion coefficient; how *completely* it fills gives the
mobile fraction — the part of the population that can move at all.

The model here is the closed-form rectangle-FRAP (rFRAP) solution. What
distinguishes it from the familiar "recovery curve" analysis is that it fits the
**whole image over time** rather than a single averaged intensity per frame:

.. math::

    F(x, y, t) = F_0 - \tfrac{1}{4} K_0 F_0\,
        \Bigl[\operatorname{erf}\tfrac{x + L_x/2}{N(t)}
             - \operatorname{erf}\tfrac{x - L_x/2}{N(t)}\Bigr]
        \Bigl[\operatorname{erf}\tfrac{y + L_y/2}{N(t)}
             - \operatorname{erf}\tfrac{y - L_y/2}{N(t)}\Bigr]

with :math:`N(t) = \sqrt{4 D t + r^2}`. The bleached rectangle enters through
its edges: a sharp rectangle convolved with a Gaussian gives the difference of
two error functions per axis, and diffusion simply widens that Gaussian with
time. Fitting the spatial profile at every time point uses far more of the data
than collapsing each frame to one number, and it separates the bleach geometry
(:math:`L_x, L_y, r`) from the transport (:math:`D`) instead of entangling them.

Recovering to less than the pre-bleach level means part of the population never
returns; that is the mobile fraction :math:`k`, applied as

.. math::  F_\mathrm{obs} = F(t{=}0) + k\,[F(t) - F(t{=}0)]
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Any

import numpy as np


@dataclasses.dataclass
class FrapResult:
    """Outcome of a rectangle-FRAP fit.

    Attributes
    ----------
    diffusion_coefficient : float
        Fitted :math:`D`, in the squared length unit of the coordinates per unit
        time (µm²/s when the pixel size is given in µm and times in seconds).
    bleach_depth : float
        Fitted :math:`K_0`: the fraction of fluorophores destroyed at the centre
        of the bleached rectangle. 0 is no bleach, 1 is complete.
    mobile_fraction : float
        Fitted :math:`k` in ``[0, 1]``. The part of the population free to
        exchange; ``1 - k`` never recovers.
    edge_width : float
        Fitted :math:`\\sqrt{r^2}`, the effective blur of the bleach edge — the
        combined optical resolution and any diffusion during the bleach itself.
    success : bool
        Whether the optimiser converged.
    chi2 : float
        Sum of squared residuals at the optimum.
    n_points : int
        Number of (pixel, frame) observations fitted.
    message : str
        Optimiser status message.
    """

    diffusion_coefficient: float
    bleach_depth: float
    mobile_fraction: float
    edge_width: float
    success: bool = True
    chi2: float = float("nan")
    n_points: int = 0
    message: str = ""

    @property
    def half_time(self) -> float:
        """Return the nominal recovery half-time of the bleached region.

        The time at which diffusion has spread over half the bleach width, i.e.
        :math:`t_{1/2} = L^2 / (16 D)` for a rectangle of mean edge ``L``. It is
        reported only because it is the number the classic curve analysis
        quotes; the fitted ``D`` is the primary result and does not depend on
        it.

        Returns
        -------
        float
            Half-time in the time unit of the fit, or ``nan`` without a
            recorded bleach size.
        """
        length = getattr(self, "_mean_length", float("nan"))
        d = self.diffusion_coefficient
        if not np.isfinite(length) or d <= 0:
            return float("nan")
        return float(length**2 / (16.0 * d))

    def to_dict(self) -> dict:
        """Return the fit as a JSON-friendly dictionary."""
        return {
            "diffusion_coefficient": float(self.diffusion_coefficient),
            "bleach_depth": float(self.bleach_depth),
            "mobile_fraction": float(self.mobile_fraction),
            "edge_width": float(self.edge_width),
            "success": bool(self.success),
            "chi2": float(self.chi2),
            "n_points": int(self.n_points),
            "message": self.message,
        }


def rfrap_model(
    x: np.ndarray,
    y: np.ndarray,
    t: np.ndarray,
    diffusion_coefficient: float,
    bleach_depth: float,
    mobile_fraction: float = 1.0,
    edge_width: float = 0.5,
    lx: float = 1.0,
    ly: float = 1.0,
    f0: float = 1.0,
) -> np.ndarray:
    r"""Evaluate the rectangle-FRAP recovery model.

    Parameters
    ----------
    x, y : numpy.ndarray
        Coordinates relative to the **centre** of the bleached rectangle, in the
        same length unit as ``lx``/``ly``.
    t : numpy.ndarray
        Time since the bleach. ``t = 0`` gives the immediate post-bleach
        profile.
    diffusion_coefficient : float
        :math:`D`, in length²/time.
    bleach_depth : float
        :math:`K_0`, the bleached fraction at the rectangle centre.
    mobile_fraction : float
        :math:`k`; 1 recovers fully, 0 not at all.
    edge_width : float
        :math:`\sqrt{r^2}`, the effective blur of the bleach edge.
    lx, ly : float
        Side lengths of the bleached rectangle.
    f0 : float
        Pre-bleach intensity level (1 for a normalised stack).

    Returns
    -------
    numpy.ndarray
        Predicted intensity, broadcast over the inputs.

    Examples
    --------
    At the centre of a freshly bleached rectangle the intensity is reduced by
    (very nearly) the full bleach depth, and it recovers towards ``f0``:

    >>> big = dict(lx=20.0, ly=20.0, edge_width=0.3, f0=1.0)
    >>> float(rfrap_model(0.0, 0.0, 0.0, 1.0, 0.5, **big)).__round__(3)
    0.5
    >>> late = float(rfrap_model(0.0, 0.0, 1e6, 1.0, 0.5, **big))
    >>> bool(late > 0.99)
    True
    """
    from scipy.special import erf

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    t = np.asarray(t, dtype=float)

    d = abs(float(diffusion_coefficient))
    r2 = float(edge_width) ** 2
    amp = 0.25 * float(bleach_depth) * float(f0)

    def profile(width: np.ndarray) -> np.ndarray:
        """Return the bleach profile for a given Gaussian width."""
        w = np.maximum(width, 1e-12)
        fx = erf((x + lx / 2.0) / w) - erf((x - lx / 2.0) / w)
        fy = erf((y + ly / 2.0) / w) - erf((y - ly / 2.0) / w)
        return float(f0) - amp * fx * fy

    # The immediate post-bleach profile, and the profile diffusion has reached
    # by time t. Only the difference between them recovers, and only the mobile
    # fraction of it.
    initial = profile(np.sqrt(max(r2, 1e-24)))
    spread = profile(np.sqrt(4.0 * d * np.maximum(t, 0.0) + r2))
    return initial + float(mobile_fraction) * (spread - initial)


def normalise_frap_stack(
    images: np.ndarray,
    n_prebleach: int,
    background: Any = None,
    median_size: int = 5,
) -> np.ndarray:
    """Normalise a FRAP stack against background and its own pre-bleach frames.

    Two corrections, in the order the reference implementation applies them:

    1. **Background** — every frame is divided by the mean intensity inside a
       background region of that frame. This removes lamp drift and detector
       gain changes, which would otherwise look like recovery.
    2. **Pre-bleach** — every frame is divided, pixel by pixel, by the average
       of the pre-bleach frames. This removes the sample's own uneven
       illumination and staining, so the bleached rectangle sits in a field of
       1.0 and the fitted ``f0`` is meaningfully fixed at unity.

    The pre-bleach average is median-filtered first: without it, shot noise in
    the reference frames is *divided into* every later frame and inflates the
    residuals everywhere.

    Parameters
    ----------
    images : numpy.ndarray
        Stack ``(n_frames, ny, nx)``.
    n_prebleach : int
        Number of leading frames recorded before the bleach.
    background : ROI or numpy.ndarray, optional
        Region used for the background correction. Omit to skip step 1.
    median_size : int
        Size of the median filter applied to the pre-bleach average. Zero
        disables it.

    Returns
    -------
    numpy.ndarray
        The normalised stack, float.

    Raises
    ------
    ValueError
        If the stack is not 3-D or has too few pre-bleach frames.
    """
    stack = np.asarray(images, dtype=float)
    if stack.ndim != 3:
        raise ValueError(f"FRAP needs a (n_frames, ny, nx) stack; got {stack.shape}")
    if n_prebleach < 1 or n_prebleach >= stack.shape[0]:
        raise ValueError(
            f"n_prebleach must be between 1 and {stack.shape[0] - 1}; got {n_prebleach}"
        )

    out = stack.copy()

    if background is not None:
        from chisurf.core.roi import ROI

        if isinstance(background, ROI):
            mask = background.to_mask(stack.shape[1:], image=stack)
        else:
            mask = np.asarray(background, dtype=bool)
        if mask.shape != stack.shape[1:]:
            raise ValueError("the background region must match the frame shape")
        if mask.any():
            levels = out[:, mask].mean(axis=1)
            levels[levels == 0] = 1.0
            out = out / levels[:, None, None]

    reference = out[:n_prebleach].mean(axis=0)
    if median_size and median_size > 1:
        from scipy.ndimage import median_filter

        reference = median_filter(reference, size=int(median_size), mode="nearest")
    reference = np.where(reference == 0, 1.0, reference)
    return out / reference[None, ...]


def recovery_curve(
    images: np.ndarray, roi: Any, times: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Return the classic mean-intensity recovery curve inside a region.

    Kept because it is the standard way to *look* at a FRAP experiment, and
    because a curve that never rises tells you at a glance that the fit below
    will not converge. The fit itself uses the full spatial profile, which
    constrains ``D`` far better than this average.

    Parameters
    ----------
    images : numpy.ndarray
        Stack ``(n_frames, ny, nx)``.
    roi : ROI or numpy.ndarray
        The bleached region.
    times : numpy.ndarray, optional
        Frame times; defaults to the frame index.

    Returns
    -------
    tuple of numpy.ndarray
        ``(times, mean_intensity)``.
    """
    from chisurf.core.roi import ROI

    stack = np.asarray(images, dtype=float)
    if isinstance(roi, ROI):
        mask = roi.to_mask(stack.shape[1:], image=stack)
    else:
        mask = np.asarray(roi, dtype=bool)
    t = np.arange(stack.shape[0], dtype=float) if times is None else np.asarray(times, float)
    return t, stack[:, mask].mean(axis=1)


def fit_rfrap(
    images: np.ndarray,
    times: np.ndarray,
    bleach_rect: Sequence[float],
    pixel_size: float = 1.0,
    *,
    diffusion_coefficient: float = 1.0,
    bleach_depth: float = 0.5,
    mobile_fraction: float = 1.0,
    edge_width: float = 0.5,
    fit_mobile_fraction: bool = True,
    fit_edge_width: bool = True,
    f0: float = 1.0,
) -> FrapResult:
    """Fit the rectangle-FRAP model to a normalised post-bleach stack.

    Parameters
    ----------
    images : numpy.ndarray
        Normalised post-bleach stack ``(n_frames, ny, nx)`` — the output of
        :func:`normalise_frap_stack` with its pre-bleach frames removed.
    times : numpy.ndarray
        Time of each frame since the bleach, same length as the stack.
    bleach_rect : sequence of float
        The bleached rectangle as ``(row0, col0, row1, col1)`` in **pixels**,
        upper bounds exclusive — the form
        :meth:`chisurf.core.roi.ROI.bounding_box` returns.
    pixel_size : float
        Physical size of a pixel. ``D`` comes out in this unit squared per unit
        time.
    diffusion_coefficient, bleach_depth, mobile_fraction, edge_width : float
        Starting values.
    fit_mobile_fraction, fit_edge_width : bool
        Release these parameters. Fixing the mobile fraction at 1 is the right
        choice when the sample is known to recover completely; fixing the edge
        width helps when the bleach is much larger than the resolution and the
        two are nearly degenerate.
    f0 : float
        Pre-bleach level; 1 for a normalised stack.

    Returns
    -------
    FrapResult
        The fitted parameters.

    Raises
    ------
    ValueError
        If the stack and time axis disagree, or the rectangle is degenerate.
    """
    from scipy.optimize import least_squares

    stack = np.asarray(images, dtype=float)
    t = np.asarray(times, dtype=float)
    if stack.ndim != 3:
        raise ValueError(f"expected a (n_frames, ny, nx) stack; got {stack.shape}")
    if t.shape[0] != stack.shape[0]:
        raise ValueError(f"{t.shape[0]} times for {stack.shape[0]} frames")

    r0, c0, r1, c1 = (float(v) for v in bleach_rect)
    lx = (c1 - c0) * pixel_size
    ly = (r1 - r0) * pixel_size
    if lx <= 0 or ly <= 0:
        raise ValueError(f"the bleach rectangle is degenerate: {tuple(bleach_rect)}")

    ny, nx = stack.shape[1:]
    # Coordinates of the pixel centres, with the origin at the rectangle centre.
    cx = (c0 + c1) / 2.0
    cy = (r0 + r1) / 2.0
    xs = (np.arange(nx, dtype=float) + 0.5 - cx) * pixel_size
    ys = (np.arange(ny, dtype=float) + 0.5 - cy) * pixel_size
    gx, gy = np.meshgrid(xs, ys)

    x3 = np.broadcast_to(gx[None, ...], stack.shape)
    y3 = np.broadcast_to(gy[None, ...], stack.shape)
    t3 = np.broadcast_to(t[:, None, None], stack.shape)

    # Pack only the released parameters, so a fixed one cannot drift.
    free = ["D", "K0"]
    start = [float(diffusion_coefficient), float(bleach_depth)]
    if fit_mobile_fraction:
        free.append("k")
        start.append(float(mobile_fraction))
    if fit_edge_width:
        free.append("r")
        start.append(float(edge_width))

    def unpack(p: np.ndarray) -> dict:
        """Return the full parameter set from the free vector."""
        values = dict(zip(free, p))
        return {
            "diffusion_coefficient": values["D"],
            "bleach_depth": values["K0"],
            "mobile_fraction": values.get("k", mobile_fraction),
            "edge_width": values.get("r", edge_width),
        }

    def residual(p: np.ndarray) -> np.ndarray:
        model = rfrap_model(x3, y3, t3, lx=lx, ly=ly, f0=f0, **unpack(p))
        return (model - stack).ravel()

    lower = (
        [1e-12, 0.0] + ([0.0] if fit_mobile_fraction else []) + ([1e-6] if fit_edge_width else [])
    )
    upper = (
        [np.inf, 1.0]
        + ([1.0] if fit_mobile_fraction else [])
        + ([np.inf] if fit_edge_width else [])
    )

    fit = least_squares(residual, start, bounds=(lower, upper))
    params = unpack(fit.x)

    result = FrapResult(
        diffusion_coefficient=float(params["diffusion_coefficient"]),
        bleach_depth=float(params["bleach_depth"]),
        mobile_fraction=float(params["mobile_fraction"]),
        edge_width=float(params["edge_width"]),
        success=bool(fit.success),
        chi2=float(np.sum(fit.fun**2)),
        n_points=int(stack.size),
        message=str(fit.message),
    )
    # Recorded for the nominal half-time, which needs the bleach geometry.
    result._mean_length = float(0.5 * (lx + ly))  # type: ignore[attr-defined]
    return result
