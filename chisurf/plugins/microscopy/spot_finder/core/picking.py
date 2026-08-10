"""Pick a spot by clicking it, and let a Gaussian say where it actually is.

A threshold finds every spot or none; a person looking at a field can see the
one that matters and the three that are artefacts. So the picker is the third
way in, beside a batch detector and a drawn region: click, and the spot under
the cursor becomes a region.

The click is the *seed*, never the answer. A click lands a pixel or two off
centre, and a region built on it would be off centre too — with a biased
centroid and a brightness measured over the wrong pixels. So the click selects
a window, the brightest pixel in that window seeds a 2-D Gaussian, and the
**fit** decides where the spot is and how wide it is. That is also what makes
the picked region comparable to a detected one: `log`/`dog` report a spot's
width from a scale space, and this reports it from a fit, but both report a
measurement rather than a setting.

A pick that does not converge is **refused, with a reason**. An ellipse placed
where a fit failed looks exactly like one placed where it succeeded, and the
difference only shows up later as a lifetime nobody can explain.
"""

from __future__ import annotations

import dataclasses

import numpy as np

__all__ = ["PickedSpot", "fit_gaussian_spot", "spot_roi"]

#: How many sigmas the region's radius covers. Two takes ~86% of a 2-D
#: Gaussian's photons, which is the usual compromise: wider drags in background
#: that dilutes a lifetime, narrower throws away signal the fit needs.
SIGMA_TO_RADIUS = 2.0


@dataclasses.dataclass
class PickedSpot:
    """One clicked spot, as the fit found it.

    Attributes
    ----------
    y, x : float
        Fitted centre, in pixels, in image coordinates.
    sigma_y, sigma_x : float
        Fitted widths.
    amplitude : float
        Peak height above the local background.
    background : float
        Fitted local background level.
    success : bool
        Whether the fit converged *and* passed the sanity checks below.
    reason : str
        Why not, when it did not.
    """

    y: float
    x: float
    sigma_y: float = float("nan")
    sigma_x: float = float("nan")
    amplitude: float = float("nan")
    background: float = float("nan")
    success: bool = False
    reason: str = ""

    @property
    def sigma(self) -> float:
        """Geometric mean width, the single number a spot is usually quoted by."""
        return float(np.sqrt(self.sigma_y * self.sigma_x))

    def to_roi(self, name: str = ""):
        """Return the region this spot occupies.

        Returns
        -------
        chisurf.core.roi.EllipseROI
        """
        return spot_roi(self, name=name)


def fit_gaussian_spot(image, y, x, *, window: int = 9,
                      max_shift: float | None = None) -> PickedSpot:
    """Fit a 2-D Gaussian to the spot near ``(y, x)``.

    Parameters
    ----------
    image : numpy.ndarray
        2-D image.
    y, x : float
        Where the user clicked, in pixels.
    window : int, optional
        Side of the square window the fit sees. It has to be wide enough to
        hold background as well as the spot — a window cropped to the spot has
        no baseline to separate amplitude from offset — and narrow enough not to
        contain the *neighbouring* spot, which is what pulls a fit sideways.
    max_shift : float, optional
        How far the fitted centre may move from the click before the pick is
        refused, in pixels. Defaults to half the window: further than that and
        the fit has locked onto something other than what was clicked.

    Returns
    -------
    PickedSpot
        With ``success`` false and a ``reason`` when the fit did not converge,
        wandered off, or returned a width the image cannot support.
    """
    from scipy.optimize import least_squares

    image = np.asarray(image, dtype=float)
    if image.ndim != 2:
        raise ValueError(f"expected a 2-D image, got shape {image.shape}")
    ny, nx = image.shape
    y, x = float(y), float(x)
    if not (0 <= y < ny and 0 <= x < nx):
        return PickedSpot(y, x, reason="the click is outside the image")

    half = max(2, int(window) // 2)
    r0, r1 = max(0, int(round(y)) - half), min(ny, int(round(y)) + half + 1)
    c0, c1 = max(0, int(round(x)) - half), min(nx, int(round(x)) + half + 1)
    patch = image[r0:r1, c0:c1]
    if patch.size < 9:
        return PickedSpot(y, x, reason="too close to the edge to fit a spot")
    if not np.isfinite(patch).all():
        return PickedSpot(y, x, reason="the window holds non-finite values")

    background = float(np.median(patch))
    peak = float(patch.max())
    if peak <= background:
        return PickedSpot(y, x, reason="nothing brighter than the background here")

    # Seeded from the brightest pixel in the window, not from the click: a click
    # is a couple of pixels approximate and the fit should not start there.
    local = np.unravel_index(int(np.argmax(patch)), patch.shape)
    rows, cols = np.indices(patch.shape)
    coords_y, coords_x = rows.ravel(), cols.ravel()
    values = patch.ravel()

    p0 = np.array([
        float(local[0]), float(local[1]),
        max(1.0, patch.shape[0] / 5.0), max(1.0, patch.shape[1] / 5.0),
        peak - background, background,
    ])

    def residuals(p):
        cy, cx, sy, sx, amp, off = p
        model = amp * np.exp(
            -0.5 * (((coords_y - cy) / sy) ** 2 + ((coords_x - cx) / sx) ** 2)
        ) + off
        return model - values

    result = least_squares(
        residuals, p0,
        bounds=(
            [0.0, 0.0, 0.4, 0.4, 0.0, -np.inf],
            [patch.shape[0] - 1.0, patch.shape[1] - 1.0,
             float(patch.shape[0]), float(patch.shape[1]), np.inf, np.inf],
        ),
        max_nfev=400,
    )
    cy, cx, sy, sx, amp, off = (float(v) for v in result.x)
    fitted_y, fitted_x = r0 + cy, c0 + cx

    limit = float(max_shift) if max_shift is not None else half
    shift = float(np.hypot(fitted_y - y, fitted_x - x))
    spot = PickedSpot(
        y=fitted_y, x=fitted_x, sigma_y=sy, sigma_x=sx,
        amplitude=amp, background=off, success=True,
    )
    if not result.success:
        spot.success, spot.reason = False, "the fit did not converge"
    elif shift > limit:
        spot.success = False
        spot.reason = (
            f"the fitted centre is {shift:.1f} px from the click — it locked "
            "onto something else; click closer or narrow the window"
        )
    elif amp <= 0:
        spot.success, spot.reason = False, "the fit found no peak above background"
    elif max(sy, sx) >= min(patch.shape) / 2.0:
        # A width the window cannot support is a fit that has spread out over
        # the whole patch rather than found a spot in it.
        spot.success = False
        spot.reason = "the fitted width fills the window — no spot here"
    return spot


def spot_roi(spot: PickedSpot, name: str = "", *, radius_sigmas: float = SIGMA_TO_RADIUS):
    """Return the elliptical region a fitted spot occupies.

    Parameters
    ----------
    spot : PickedSpot
        A converged fit.
    name : str, optional
        Region name.
    radius_sigmas : float, optional
        Radius in units of the fitted sigma.

    Returns
    -------
    chisurf.core.roi.EllipseROI
    """
    from chisurf.core.roi import EllipseROI

    return EllipseROI(
        float(spot.x), float(spot.y),
        max(1.0, radius_sigmas * float(spot.sigma_x)),
        max(1.0, radius_sigmas * float(spot.sigma_y)),
        name=name or "picked",
    )
