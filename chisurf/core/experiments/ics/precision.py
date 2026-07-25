r"""How precisely can a raster scan measure D? (MIA ``RICSPE`` port)

Every image-correlation measurement has a scan speed, and the choice is not
free. Scan too fast and a molecule barely moves between neighbouring pixels, so
the correlation carries almost no information about :math:`D`. Scan too slowly
and it has decorrelated before the second pixel is read. Somewhere between,
there is a dwell time that measures a given diffusion coefficient best — and it
depends on :math:`D` itself, on the beam waist, on the pixel size and on how
bright the sample is.

This module answers that before the experiment: given the acquisition settings
and the :math:`D` you expect, it predicts the **relative error** on the fitted
:math:`D`.

How it works
------------
1. The **covariance of the correlation estimator** is computed analytically over
   the fitted lag range (:func:`correlation_covariance`). Correlation values at
   different lags are not independent — they are built from the same pixels — so
   this is a full matrix, not a set of per-lag variances. Ignoring the
   off-diagonal terms would badly understate the error.
2. Noise is drawn from that covariance, added to the noiseless correlation, and
   the result is fitted for :math:`D` exactly as a real measurement would be.
3. The spread of the fitted values over many realisations gives the mean squared
   relative error.

The covariance follows Sanguigno et al.'s treatment of RICS estimator noise: a
shot-noise term involving the three-point correlation :func:`triple_correlation`
on the diagonal, plus two terms that sum products of two-point correlations over
every pixel pair, weighted by how many pairs share each separation.

Reading the result
------------------
The returned error is itself a Monte-Carlo estimate, with a relative
uncertainty of roughly :math:`1/\sqrt{2 n_\text{repeats}}` — about 10 % at the
default. That is fine for "is this acquisition usable?", but it means the
**position of the minimum is not resolved to one step** of a dwell-time scan:
along a flat stretch the argmin moves between neighbouring points from noise
alone. Compare the errors themselves, or raise ``n_repeats``, rather than
trusting a single argmin.

The cost is dominated by :func:`correlation_covariance`, which is
:math:`O(n_\text{lags}^4)` with an inner sum over the image. Doubling
``n_lags`` costs sixteen times as much, so the default here is smaller than the
reference's 15.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Optional, Sequence, Tuple

import numpy as np


@dataclasses.dataclass
class RicsPrecision:
    """Predicted precision of a RICS diffusion measurement.

    Attributes
    ----------
    relative_error : float
        Root mean squared relative error of the fitted ``D``: 0.1 means the
        measurement recovers ``D`` to about 10 %.
    msre : float
        Mean squared relative error, the quantity the reference reports.
    diffusion_coefficient : float
        The ``D`` the prediction was made for.
    pixel_time : float
        Pixel dwell time, in seconds.
    line_time : float
        Line time, in seconds.
    n_images : int
        Number of frames assumed.
    fitted : numpy.ndarray
        The individual fitted ``D`` values, for inspecting the distribution
        rather than only its width.
    """

    relative_error: float
    msre: float
    diffusion_coefficient: float
    pixel_time: float
    line_time: float
    n_images: int = 1
    fitted: np.ndarray = dataclasses.field(default_factory=lambda: np.zeros(0))

    @property
    def bias(self) -> float:
        """Return the fractional bias of the fitted ``D``.

        Separated from the spread because they mean different things: a biased
        estimator is not fixed by averaging more images, while a noisy one is.
        """
        f = np.asarray(self.fitted, dtype=float)
        f = f[np.isfinite(f)]
        if f.size == 0 or self.diffusion_coefficient == 0:
            return float("nan")
        return float(f.mean() / self.diffusion_coefficient - 1.0)

    def to_dict(self) -> dict:
        """Return the prediction as a JSON-friendly dictionary."""
        return {
            "relative_error": float(self.relative_error),
            "msre": float(self.msre),
            "bias": float(self.bias),
            "diffusion_coefficient": float(self.diffusion_coefficient),
            "pixel_time": float(self.pixel_time),
            "line_time": float(self.line_time),
            "n_images": int(self.n_images),
        }


def gamma_factors(two_d: bool = False) -> Tuple[float, float, float, float]:
    """Return the shape factors :math:`\\gamma_1..\\gamma_4` of the detection volume.

    They are the normalised moments of the detection profile and set how each
    order of correlation scales with molecular brightness.

    Parameters
    ----------
    two_d : bool
        Membrane/2-D geometry rather than a 3-D Gaussian focus.

    Returns
    -------
    tuple of float
        ``(gamma1, gamma2, gamma3, gamma4)``.
    """
    if two_d:
        g1 = 0.5
        return g1, g1 / 2.0, g1 / 3.0, g1 / 4.0
    g1 = 1.0 / (2.0 * math.sqrt(2.0))
    return g1, g1 / (2.0 * math.sqrt(2.0)), g1 / (3.0 * math.sqrt(3.0)), g1 / 8.0


def correlation_grid(
    xi: np.ndarray,
    psi: np.ndarray,
    d: float,
    w: float,
    alpha: float,
    pixel_time: float,
    line_time: float,
    pixel_size: float,
) -> np.ndarray:
    r"""Return the normalised RICS correlation shape on a lag grid.

    :math:`g(\xi,\psi) = \frac{\exp[-a^2(\xi^2+\psi^2)/(w^2+4D\tau)]}
    {(1 + 4D\tau/w^2)\sqrt{1 + 4D\tau/(\alpha w)^2}}` with
    :math:`\tau = |\xi T_p + \psi T_l|`.

    Parameters
    ----------
    xi, psi : numpy.ndarray
        Lag grids, in pixels and lines.
    d : float
        Diffusion coefficient.
    w : float
        Lateral waist.
    alpha : float
        Aspect ratio :math:`w_z/w_r`.
    pixel_time, line_time : float
        Scan timing, in seconds.
    pixel_size : float
        Pixel size, in the length unit of *w*.

    Returns
    -------
    numpy.ndarray
        The correlation shape, unnormalised by amplitude.
    """
    tau = np.abs(pixel_time * xi + line_time * psi)
    c1 = -((pixel_size * xi) ** 2 + (pixel_size * psi) ** 2) / w ** 2
    c2 = 4.0 * tau / w ** 2
    c3 = 4.0 * tau / (alpha * w) ** 2
    denom = (1.0 + d * c2) * np.sqrt(1.0 + d * c3)
    return np.exp(c1 / (1.0 + d * c2)) / denom


def triple_correlation(
    rho1: Sequence[float],
    rho2: Sequence[float],
    rho3: Sequence[float],
    d: float,
    w: float,
    alpha: float,
    pixel_time: float,
    line_time: float,
    pixel_size: float,
) -> float:
    """Return the three-point correlation entering the shot-noise variance.

    The variance of a correlation estimate depends on the *third* moment of the
    intensity, not only the second — which is why a full noise model needs this
    and a naive "variance = signal" estimate is wrong.

    Parameters
    ----------
    rho1, rho2, rho3 : sequence of float
        The three lag vectors, in pixels/lines.
    d, w, alpha, pixel_time, line_time, pixel_size
        As for :func:`correlation_grid`.

    Returns
    -------
    float
        The three-point correlation value.
    """
    r1 = np.asarray(rho1, dtype=float) * pixel_size
    r2 = np.asarray(rho2, dtype=float) * pixel_size
    r3 = np.asarray(rho3, dtype=float) * pixel_size

    t1 = abs(rho1[0] * pixel_time + rho1[1] * line_time)
    t2 = abs(rho2[0] * pixel_time + rho2[1] * line_time)
    t3 = abs(rho3[0] * pixel_time + rho3[1] * line_time)

    a1, a2, a3 = (1 + 4 * d * t / w ** 2 for t in (t1, t2, t3))
    b1, b2, b3 = (1 + 4 * d * t / (alpha * w) ** 2 for t in (t1, t2, t3))

    term7 = 8 * a1 * a2 * a3 - 8 * d * (t1 + t3) / w ** 2 - 4
    term8 = 8 * b1 * b2 * b3 - 8 * d * (t1 + t3) / (alpha * w) ** 2 - 4

    t9 = w ** 2 / 4 + 2 * d * t1
    t10 = w ** 2 / 4 + 2 * d * t2
    t11 = w ** 2 / 4 + 2 * d * t3
    t12 = w ** 2 / 2 + 2 * d * t3

    e1 = math.exp(-0.5 * float(np.dot(r2 - r3, r2 - r3)) / t12)

    v13 = r1 * t12 - r3 * w ** 2 / 4 + r2 * t10
    t14 = t12 * (t10 * t12 + w ** 2 / 4 * t11)
    e2 = math.exp(-0.5 * float(np.dot(v13, v13)) / t14)

    v15 = r1 * (w ** 2 / 4 * t11 + 2 * d * t2 * t12) + r3 * w ** 4 / 16 + r2 * t11
    t16 = t9 * (t10 * t12 + w ** 2 / 4 * t11)
    t17 = t16 * w ** 6 / 64 * term7
    e3 = math.exp(-0.5 * float(np.dot(v15, v15)) / t17)

    return 8.0 * e1 * e2 * e3 * term7 ** -1.0 * term8 ** -0.5


def _pair_counts(n: int) -> np.ndarray:
    """Return how many pixel pairs share each separation along one axis.

    For ``n`` pixels there are ``n - |d|`` pairs at separation ``d``. The
    reference builds this with a meshgrid difference and a unique-count; the
    closed form is identical and avoids an ``O(n²)`` intermediate.

    Parameters
    ----------
    n : int
        Number of pixels along the axis.

    Returns
    -------
    numpy.ndarray
        Counts for separations ``-(n-1) .. (n-1)``.
    """
    d = np.arange(-(n - 1), n, dtype=float)
    return n - np.abs(d)


def correlation_covariance(
    n_lags: int,
    nx: int,
    ny: int,
    d: float,
    f: float,
    w: float,
    alpha: float,
    pixel_time: float,
    line_time: float,
    pixel_size: float,
    m: float,
    q: float,
    gamma: Sequence[float],
) -> np.ndarray:
    """Return the covariance matrix of the RICS correlation estimator.

    Correlation values at different lags share pixels, so they are correlated
    with each other. This returns the full ``(n_lags+1)² × (n_lags+1)²`` matrix
    over lag pairs, ordered so that lag ``(xi, psi)`` is row
    ``xi + (n_lags+1) * psi``.

    Parameters
    ----------
    n_lags : int
        Largest lag included, on both axes.
    nx, ny : int
        Image size in pixels and lines.
    d : float
        Diffusion coefficient.
    f : float
        Mean detected count rate.
    w : float
        Lateral waist.
    alpha : float
        Aspect ratio.
    pixel_time, line_time : float
        Scan timing, in seconds.
    pixel_size : float
        Pixel size.
    m : float
        Mean number of molecules in the detection volume.
    q : float
        Photons per molecule per pixel dwell.
    gamma : sequence of float
        The four shape factors from :func:`gamma_factors`.

    Returns
    -------
    numpy.ndarray
        The symmetric covariance matrix.

    Notes
    -----
    Every two-point correlation needed here is the same function evaluated at a
    shifted integer lag, so it is computed **once** on a master grid spanning
    every reachable separation and then sliced. The reference recomputes it
    inside the innermost of four nested loops, which is what makes the literal
    algorithm impractical for realistic image sizes.
    """
    size = n_lags + 1
    cov = np.zeros((size * size, size * size), dtype=float)
    g1, g2, g3, g4 = (float(v) for v in gamma)

    # Master grid of the two-point correlation over every separation that any
    # lag combination can reach, so the inner loops only slice.
    span_x = np.arange(-(nx - 1) - n_lags, nx + n_lags, dtype=float)
    span_y = np.arange(-(ny - 1) - n_lags, ny + n_lags, dtype=float)
    gx, gy = np.meshgrid(span_x, span_y)
    master = m * q ** 2 * g2 * correlation_grid(
        gx, gy, d, w, alpha, pixel_time, line_time, pixel_size
    )
    x0 = int(np.flatnonzero(span_x == 0)[0])
    y0 = int(np.flatnonzero(span_y == 0)[0])
    shot = m * q * g1                      # the self-term added at zero separation

    def block(off_x: int, off_y: int, half_x: int, half_y: int, zero: bool) -> np.ndarray:
        """Return the correlation over a lag window, offset and shot-corrected."""
        sx = x0 + off_x - half_x
        sy = y0 + off_y - half_y
        out = master[sy:sy + 2 * half_y + 1, sx:sx + 2 * half_x + 1].copy()
        if zero:
            # the self-correlation sits where the *separation* is zero
            iy, ix = half_y - off_y, half_x - off_x
            if 0 <= iy < out.shape[0] and 0 <= ix < out.shape[1]:
                out[iy, ix] += shot
        return out

    for psi in range(size):
        for xi in range(size):
            row = xi + size * psi
            hx, hy = nx - xi - 1, ny - psi - 1
            counts = np.outer(_pair_counts(ny - psi), _pair_counts(nx - xi))

            g_a = block(0, 0, hx, hy, zero=True)          # rho = (X, Y)
            g_c = block(-xi, -psi, hx, hy, zero=True)     # rho = (X - xi, Y - psi)

            for mu in range(size):
                for nu in range(size):
                    col = nu + size * mu
                    if col < row:
                        continue
                    if xi == 0 and psi == 0 and nu == 0 and mu == 0:
                        continue

                    term1 = 0.0
                    if nu == xi and mu == psi:
                        term1 = 2 * (nx - 2 * xi) * (ny - 2 * psi) * (
                            m * q ** 4 * g4 * triple_correlation(
                                (xi, psi), (0, 0), (xi, psi),
                                d, w, alpha, pixel_time, line_time, pixel_size,
                            )
                        )

                    g_b = block(nu - xi, mu - psi, hx, hy, zero=True)
                    g_d = block(nu, mu, hx, hy, zero=True)

                    term2 = float(np.sum(counts * g_a * g_b))
                    term3 = float(np.sum(counts * g_d * g_c))

                    denom = (nx - xi) * (nx - nu) * (ny - psi) * (ny - mu) * f ** 4
                    cov[row, col] = (term1 + term2 + term3) / denom

    return cov + np.triu(cov, 1).T


def nearest_spd(a: np.ndarray, floor: float = 1e-12) -> np.ndarray:
    """Return the nearest symmetric positive-definite matrix to *a*.

    The analytic covariance is symmetric by construction but picks up small
    negative eigenvalues from finite precision, and drawing correlated noise
    requires a genuinely positive-definite matrix.

    Symmetrise, then clip the eigenvalues at a small positive floor. Higham's
    iterative construction was tried first and produced matrices that passed
    its own Cholesky check yet were still rejected downstream once scaled;
    clipping is both simpler and unconditionally definite.

    Parameters
    ----------
    a : numpy.ndarray
        A square, approximately symmetric matrix.
    floor : float
        Smallest eigenvalue kept, as a fraction of the largest.

    Returns
    -------
    numpy.ndarray
        A symmetric positive-definite matrix.
    """
    b = (a + a.T) / 2.0
    values, vectors = np.linalg.eigh(b)
    smallest = max(float(np.max(values)) * float(floor), np.finfo(float).tiny)
    values = np.maximum(values, smallest)
    out = (vectors * values) @ vectors.T
    return (out + out.T) / 2.0


def rics_precision(
    diffusion_coefficient: float,
    *,
    pixel_time: float,
    line_time: float,
    pixel_size: float,
    nx: int = 64,
    ny: int = 64,
    n_particles: float = 10.0,
    w_r: float = 0.25,
    w_z: float = 1.25,
    brightness: float = 1e4,
    n_images: int = 1,
    n_lags: int = 6,
    n_repeats: int = 60,
    two_d: bool = False,
    seed: int = 0,
) -> RicsPrecision:
    """Predict the relative error on ``D`` for a given acquisition.

    Parameters
    ----------
    diffusion_coefficient : float
        The diffusion coefficient to be measured, in µm²/s.
    pixel_time, line_time : float
        Pixel dwell and line time, in seconds. A scan is only meaningful when
        ``pixel_time * nx <= line_time``.
    pixel_size : float
        Pixel size in µm.
    nx, ny : int
        Image size.
    n_particles : float
        Number of molecules in the illuminated region.
    w_r, w_z : float
        Beam waists in µm.
    brightness : float
        Molecular brightness in photons per second per molecule.
    n_images : int
        Frames averaged; the covariance scales as ``1/n_images``.
    n_lags : int
        Largest lag fitted, on both axes. Cost grows as ``n_lags⁴``, so the
        default is smaller than the reference's 15.
    n_repeats : int
        Monte-Carlo realisations used to estimate the spread.
    two_d : bool
        Membrane geometry.
    seed : int
        Random seed, so a prediction is reproducible.

    Returns
    -------
    RicsPrecision
        The predicted error and the fitted values behind it.

    Raises
    ------
    ValueError
        If the scan timing is inconsistent (a line cannot be shorter than the
        pixels it contains).
    """
    from scipy.optimize import least_squares

    if pixel_time * nx > line_time:
        raise ValueError(
            f"a line of {nx} pixels at {pixel_time} s each cannot fit in {line_time} s"
        )

    gamma = gamma_factors(two_d)
    alpha = float(w_z) / float(w_r)
    d = float(diffusion_coefficient)

    if two_d:
        volume = (nx * pixel_size + 2) * (ny * pixel_size + 2)
        omega = math.pi * w_r ** 2
        q = brightness * pixel_time
        m = n_particles * omega / volume
    else:
        volume = (nx * pixel_size + 2) * (ny * pixel_size + 2) * ((nx + ny) / 2 * pixel_size)
        omega = math.pi ** 1.5 * w_r ** 3 * alpha
        beta = 1.0 / alpha ** 2
        tau_c = w_r ** 2 / (4.0 * d)
        fact = math.sqrt(1.0 + beta * pixel_time / tau_c)
        root = math.sqrt(1.0 - beta)
        # Photons per molecule per dwell, corrected for the motion that happens
        # during the dwell itself: a molecule does not sit still while it is read.
        q = brightness * 4 * tau_c ** 2 * (
            beta * (1 + pixel_time / tau_c)
            * math.atanh(root * (fact - 1) / (beta + fact - 1))
            - root * (fact - 1)
        ) / (pixel_time * beta * root)
        n_apparent = n_particles * brightness * pixel_time / q
        m = n_apparent * omega / volume
    f = (n_particles if two_d else n_apparent) * q * omega * gamma[0] / volume

    cov = correlation_covariance(
        n_lags, nx, ny, d, f, w_r, alpha, pixel_time, line_time, pixel_size, m, q, gamma
    )

    size = n_lags + 1
    # The (0,0) lag is not fitted -- it carries the shot-noise spike, not the
    # diffusion -- so it is dropped from the covariance before drawing noise.
    cov_fit = nearest_spd(cov[1:, 1:]) / max(int(n_images), 1)
    ste = np.concatenate([[0.0], np.sqrt(np.diag(cov_fit))]).reshape(size, size)

    xi, psi = np.meshgrid(np.arange(size, dtype=float), np.arange(size, dtype=float))
    shape = correlation_grid(xi, psi, d, w_r, alpha, pixel_time, line_time, pixel_size)
    ideal = shape / m

    rng = np.random.default_rng(seed)
    noise = rng.multivariate_normal(
        np.zeros(size * size - 1), cov_fit, size=int(n_repeats), method="eigh"
    )

    with np.errstate(divide="ignore", invalid="ignore"):
        weight = np.where(ste > 0, 1.0 / ste, 0.0)
    weight[0, 0] = 0.0

    fitted = np.empty(int(n_repeats), dtype=float)
    for k in range(int(n_repeats)):
        realisation = ideal + np.concatenate([[0.0], noise[k]]).reshape(size, size)
        target = (realisation * weight).ravel()

        def residual(p):
            model = p[1] * correlation_grid(
                xi, psi, p[0], w_r, alpha, pixel_time, line_time, pixel_size
            ) + p[2]
            return (model * weight).ravel() - target

        fit = least_squares(
            residual, [d, 1.0 / m, 0.0],
            bounds=([1e-12, 0.0, -np.inf], [np.inf, np.inf, np.inf]),
        )
        fitted[k] = fit.x[0]

    msre = float(np.mean(((fitted - d) / d) ** 2))
    return RicsPrecision(
        relative_error=float(math.sqrt(msre)),
        msre=msre,
        diffusion_coefficient=d,
        pixel_time=float(pixel_time),
        line_time=float(line_time),
        n_images=int(n_images),
        fitted=fitted,
    )
