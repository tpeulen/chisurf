"""Pick a spot by clicking it, and let a Gaussian say where it actually is.

A threshold finds every spot or none; a person looking at a field can see the
one that matters and the three that are artefacts. So the picker is the third
way a region gets made, beside a batch detector and a drawn shape: click, and
the spot under the cursor becomes a region.

It lives here, with the rest of the ROI subsystem, because what it produces is
a **region** — the plotting layer offers the gesture and a plugin consumes the
result, but neither owns the science of deciding where a spot is.

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

__all__ = [
    "PickedCluster",
    "PickedSpot",
    "cluster_roi",
    "fit_gaussian_cluster",
    "fit_gaussian_spot",
    "spot_roi",
]

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


# ---------------------------------------------------------------------------
# The same gesture on a point cloud
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class PickedCluster:
    """One clicked population on a plane of points, as the fit found it.

    The point-cloud twin of :class:`PickedSpot`. An image has a value at every
    pixel and a population has a *density*, so what is fitted is a mean and a
    covariance rather than an amplitude and a width — but the principle is the
    same one: the click is a seed and the fit decides.

    Attributes
    ----------
    mu : numpy.ndarray
        Fitted centre, ``(x, y)`` in the plane's own units.
    cov : numpy.ndarray
        ``(2, 2)`` covariance of the points that belong to it.
    n_points : int
        How many points the estimate rests on. A gate fitted to nine points is
        a gate to distrust, and this is what says so.
    success : bool
    reason : str
    """

    mu: np.ndarray
    cov: np.ndarray
    n_points: int = 0
    success: bool = False
    reason: str = ""


def fit_gaussian_cluster(points, x, y, *, radius: float, iterations: int = 3,
                         min_points: int = 10) -> PickedCluster:
    """Fit a 2-D Gaussian to the population clicked at ``(x, y)``.

    Where :func:`fit_gaussian_spot` fits pixel values, this fits point density,
    which is what a parameter plane carries: a burst or a molecule is a point,
    a population is a cloud of them, and a gate around one is an ellipse of
    constant Mahalanobis distance.

    The estimate **re-centres**. A first pass takes the points within *radius*
    of the click and their mean; the next pass takes the points within the same
    radius of *that* mean, and so on. A click on the shoulder of a population
    otherwise returns a centre on the shoulder, and a covariance inflated by the
    empty half of the disc it sampled.

    Parameters
    ----------
    points : array-like
        ``(N, 2)`` or ``(2, N)`` coordinates on the plane, in the same units as
        the click. Non-finite rows are dropped.
    x, y : float
        Where the user clicked.
    radius : float
        Capture radius, in plane units. It is a *setting* rather than something
        fitted, because a density has no edge — the same cloud is one population
        or three depending on how far one is willing to look.
    iterations : int, optional
        Re-centring passes.
    min_points : int, optional
        Fewer points than this refuses the pick: a covariance from a handful of
        points is noise with an ellipse drawn round it.

    Returns
    -------
    PickedCluster
    """
    data = np.asarray(points, dtype=float)
    if data.ndim != 2:
        raise ValueError(f"expected a 2-D array of points, got shape {data.shape}")
    if data.shape[0] == 2 and data.shape[1] != 2:
        data = data.T
    data = data[np.isfinite(data).all(axis=1)]

    centre = np.array([float(x), float(y)])
    if data.size == 0:
        return PickedCluster(centre, np.zeros((2, 2)), reason="no points on this plane")

    inside = np.zeros(len(data), dtype=bool)
    for _ in range(max(1, int(iterations))):
        inside = np.hypot(*(data - centre).T) <= float(radius)
        if inside.sum() < max(2, min_points):
            break
        centre = data[inside].mean(axis=0)

    n = int(inside.sum())
    if n < max(2, min_points):
        return PickedCluster(
            centre, np.zeros((2, 2)), n_points=n,
            reason=f"only {n} point(s) within {radius:g} of the click — "
                   "widen the radius or click where the population is",
        )

    cov = np.cov(data[inside].T)
    if not np.isfinite(cov).all() or np.linalg.det(cov) <= 0:
        return PickedCluster(
            centre, np.zeros((2, 2)), n_points=n,
            reason="the points are collinear — no ellipse describes them",
        )
    return PickedCluster(mu=centre, cov=np.asarray(cov, dtype=float),
                         n_points=n, success=True)


def cluster_roi(cluster: PickedCluster, name: str = "", *, sigma: float = 2.0):
    """Return the ellipse of constant Mahalanobis distance around a cluster.

    Parameters
    ----------
    cluster : PickedCluster
        A converged fit.
    name : str, optional
        Region name.
    sigma : float, optional
        How many standard deviations the ellipse encloses.

    Returns
    -------
    chisurf.core.roi.EllipseROI
        Oriented along the covariance's principal axes — an axis-aligned
        ellipse around a correlated population either leaks in the corners or
        cuts the population's own diagonal off. The conversion is
        :func:`chisurf.core.roi.ellipse_from_covariance`, which the exploration
        tool's Gaussian gates already go through: one implementation, so a gate
        drawn here and a gate drawn there are the same ellipse.
    """
    from chisurf.core.roi.selections import ellipse_from_covariance

    return ellipse_from_covariance(
        cluster.mu, cluster.cov, sigma=sigma, name=name or "picked"
    )
