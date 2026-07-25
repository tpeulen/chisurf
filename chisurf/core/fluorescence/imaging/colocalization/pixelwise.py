"""Pixel-wise colocalization coefficients for microscopy images.

Qt-free NumPy implementations of the standard pixel-intensity colocalization
coefficients used to judge whether two fluorescence channels report on the same
structures. The reference set follows Dunn, Kamocka & McDonald (2011), *A
practical guide to evaluating colocalization in biological microscopy*, Am. J.
Physiol. Cell Physiol. 300(4):C723 — Pearson's correlation, Manders' overlap and
split fractions, Costes' automatic thresholds and randomization significance
test, Li's intensity-correlation quotient, Spearman's rank correlation, and van
Steensel's cross-correlation shift profile.

Every function takes plain arrays and returns plain numbers/arrays, so the same
code backs the GUI tool, the CLI, and the tests. For punctate signal, where these
coefficients answer the wrong question, see :mod:`~.objects`.
"""

from __future__ import annotations

import dataclasses

import numpy as np

__all__ = [
    "ColocalizationResult",
    "colocalization_metrics",
    "costes_significance",
    "costes_threshold",
    "cross_correlation_2d",
    "estimate_background",
    "joint_histogram",
    "li_icq",
    "manders_fractions",
    "manders_overlap",
    "orthogonal_regression",
    "pearson",
    "pearson_profile",
    "spearman",
    "van_steensel",
]


def _pair(a, b) -> tuple[np.ndarray, np.ndarray]:
    """Return *a* and *b* as matching-length 1-D float arrays with NaNs dropped."""
    x = np.asarray(a, dtype=float).ravel()
    y = np.asarray(b, dtype=float).ravel()
    if x.size != y.size:
        raise ValueError(f"channel size mismatch: {x.size} vs {y.size}")
    good = np.isfinite(x) & np.isfinite(y)
    return x[good], y[good]


def estimate_background(image, quantile: float = 0.05) -> float:
    """Return a background intensity estimated as a low quantile of the image.

    The heuristic used by the reference implementation: the lower 5 % quantile of
    all pixel values is taken as the (dark + out-of-cell) background of a channel.

    Parameters
    ----------
    image : array_like
        Channel image (any shape); NaNs are ignored.
    quantile : float
        Quantile in ``[0, 1]`` used as the background estimate.

    Returns
    -------
    float
        The estimated background intensity (``0.0`` for an empty image).
    """
    values = np.asarray(image, dtype=float).ravel()
    values = values[np.isfinite(values)]
    if values.size == 0:
        return 0.0
    return float(np.quantile(values, float(quantile)))


def pearson(a, b) -> float:
    """Return Pearson's correlation coefficient (PCC) of two channels.

    ``PCC = Σ(aᵢ − ā)(bᵢ − b̄) / sqrt(Σ(aᵢ − ā)² · Σ(bᵢ − b̄)²)``, in ``[-1, 1]``;
    it measures the *covariance* of the two channels and is insensitive to a
    common intensity scaling but sensitive to background offsets.

    Parameters
    ----------
    a, b : array_like
        The two channels; flattened and matched element-wise.

    Returns
    -------
    float
        The correlation coefficient, or NaN if either channel is constant.
    """
    x, y = _pair(a, b)
    if x.size < 2:
        return float("nan")
    dx = x - x.mean()
    dy = y - y.mean()
    denom = np.sqrt(float(dx @ dx) * float(dy @ dy))
    if denom <= 0.0:
        return float("nan")
    return float((dx @ dy) / denom)


def spearman(a, b) -> float:
    """Return Spearman's rank correlation coefficient of two channels.

    Pearson's coefficient computed on the *ranks*, so it detects monotonic but
    non-linear channel relations (e.g. detector saturation) that PCC underrates.

    Parameters
    ----------
    a, b : array_like
        The two channels.

    Returns
    -------
    float
        The rank correlation coefficient, or NaN when undefined.
    """
    x, y = _pair(a, b)
    if x.size < 2:
        return float("nan")
    from scipy.stats import rankdata

    return pearson(rankdata(x), rankdata(y))


def manders_overlap(a, b) -> float:
    """Return Manders' overlap coefficient (MOC) of two channels.

    ``MOC = Σ(aᵢ·bᵢ) / sqrt(Σaᵢ² · Σbᵢ²)``, in ``[0, 1]`` for non-negative data.
    Unlike PCC it does not subtract the means, so it reports co-occurrence of
    signal rather than co-variation, but it is correspondingly sensitive to
    background.

    Parameters
    ----------
    a, b : array_like
        The two channels.

    Returns
    -------
    float
        The overlap coefficient, or NaN if either channel is all-zero.
    """
    x, y = _pair(a, b)
    denom = np.sqrt(float(x @ x) * float(y @ y))
    if denom <= 0.0:
        return float("nan")
    return float((x @ y) / denom)


def manders_fractions(
    a, b, threshold_a: float = 0.0, threshold_b: float = 0.0
) -> tuple[float, float]:
    """Return Manders' split colocalization coefficients ``(M1, M2)``.

    ``M1 = Σ{aᵢ : bᵢ > tb} / Σaᵢ`` is the fraction of channel-A intensity that
    sits in pixels where channel B is above its threshold, and ``M2`` is the
    mirror quantity. They answer "how much of A is with B" independently for each
    channel, which PCC cannot express.

    Parameters
    ----------
    a, b : array_like
        The two channels.
    threshold_a, threshold_b : float
        Intensity thresholds above which a channel counts as present.

    Returns
    -------
    tuple of float
        ``(M1, M2)``; a component is NaN when the corresponding channel sums to 0.
    """
    x, y = _pair(a, b)
    sum_a = float(x.sum())
    sum_b = float(y.sum())
    m1 = float(x[y > threshold_b].sum() / sum_a) if sum_a > 0 else float("nan")
    m2 = float(y[x > threshold_a].sum() / sum_b) if sum_b > 0 else float("nan")
    return m1, m2


def li_icq(a, b) -> float:
    """Return Li's intensity correlation quotient (ICQ) of two channels.

    ICQ is the fraction of pixels whose intensity deviations from the two channel
    means have the same sign, shifted to ``[-0.5, 0.5]``: ``+0.5`` is perfect
    dependent staining, ``0`` random, negative segregated. It is a robust,
    distribution-free companion to PCC.

    Parameters
    ----------
    a, b : array_like
        The two channels.

    Returns
    -------
    float
        The intensity correlation quotient, or NaN for an empty selection.
    """
    x, y = _pair(a, b)
    if x.size == 0:
        return float("nan")
    product = (x - x.mean()) * (y - y.mean())
    return float(np.count_nonzero(product > 0) / product.size - 0.5)


def orthogonal_regression(a, b) -> tuple[float, float]:
    """Return the total-least-squares line ``b = slope·a + intercept``.

    Costes' threshold search regresses one channel on the other with an
    *orthogonal* (reduced-major-axis) fit rather than ordinary least squares,
    because neither channel is an error-free predictor of the other.

    Parameters
    ----------
    a, b : array_like
        The two channels.

    Returns
    -------
    tuple of float
        ``(slope, intercept)``; ``(nan, nan)`` when the fit is degenerate.
    """
    x, y = _pair(a, b)
    if x.size < 2:
        return float("nan"), float("nan")
    var_x = float(np.var(x))
    var_y = float(np.var(y))
    cov = float(np.cov(x, y, bias=True)[0, 1])
    if cov == 0.0:
        return float("nan"), float("nan")
    slope = (var_y - var_x + np.sqrt((var_y - var_x) ** 2 + 4.0 * cov**2)) / (2.0 * cov)
    intercept = float(y.mean() - slope * x.mean())
    return float(slope), intercept


def costes_threshold(a, b, *, steps: int = 256, min_pixels: int = 16) -> dict:
    """Return Costes' automatic intensity thresholds for a channel pair.

    Walks the orthogonal-regression line downwards from the brightest pixel and
    stops at the highest threshold pair ``(tₐ, t_b = slope·tₐ + intercept)`` for
    which the pixels *below* both thresholds are no longer positively correlated.
    Everything below that point is, by construction, indistinguishable from
    uncorrelated background, so the thresholds are derived from the data instead
    of being chosen by hand.

    Parameters
    ----------
    a, b : array_like
        The two channels.
    steps : int
        Number of coarse scan points along the regression line; a bisection
        refines the bracket afterwards.
    min_pixels : int
        Minimum number of below-threshold pixels required to evaluate a
        correlation.

    Returns
    -------
    dict
        ``{"threshold_a", "threshold_b", "slope", "intercept", "r_below"}``. The
        thresholds are NaN when the regression is degenerate or no crossing is
        found (fully correlated data).
    """
    x, y = _pair(a, b)
    slope, intercept = orthogonal_regression(x, y)
    out = {
        "threshold_a": float("nan"),
        "threshold_b": float("nan"),
        "slope": slope,
        "intercept": intercept,
        "r_below": float("nan"),
    }
    if not np.isfinite(slope) or x.size < min_pixels:
        return out

    def r_below(t_a: float) -> float:
        """Return the correlation of the pixels below the threshold pair at *t_a*."""
        below = (x <= t_a) & (y <= slope * t_a + intercept)
        if np.count_nonzero(below) < min_pixels:
            return float("nan")
        return pearson(x[below], y[below])

    hi = float(x.max())
    lo = float(x.min())
    if not np.isfinite(hi) or hi <= lo:
        return out
    grid = np.linspace(hi, lo, max(int(steps), 8))
    prev_t = grid[0]
    for t in grid[1:]:
        r = r_below(t)
        if np.isfinite(r) and r <= 0.0:
            # Refine the bracket [t, prev_t] where the correlation crosses zero.
            low, high = t, prev_t
            for _ in range(32):
                mid = 0.5 * (low + high)
                r_mid = r_below(mid)
                if np.isfinite(r_mid) and r_mid <= 0.0:
                    low = mid
                else:
                    high = mid
            out["threshold_a"] = float(high)
            out["threshold_b"] = float(slope * high + intercept)
            out["r_below"] = r_below(high)
            return out
        prev_t = t
    return out


def _block_shuffle(image: np.ndarray, block: int, rng: np.random.Generator) -> np.ndarray:
    """Return *image* with its ``block``×``block`` tiles randomly permuted."""
    ny, nx = image.shape
    block = max(int(block), 1)
    n_y = ny // block
    n_x = nx // block
    if n_y < 2 or n_x < 2:
        flat = rng.permutation(image.ravel())
        return flat.reshape(image.shape)
    cropped = image[: n_y * block, : n_x * block]
    tiles = (
        cropped.reshape(n_y, block, n_x, block)
        .transpose(0, 2, 1, 3)
        .reshape(n_y * n_x, block, block)
    )
    tiles = tiles[rng.permutation(n_y * n_x)]
    shuffled = (
        tiles.reshape(n_y, n_x, block, block)
        .transpose(0, 2, 1, 3)
        .reshape(n_y * block, n_x * block)
    )
    out = image.copy()
    out[: n_y * block, : n_x * block] = shuffled
    return out


def costes_significance(
    image_a,
    image_b,
    *,
    block: int = 4,
    n_randomizations: int = 200,
    seed: int = 0,
    mask=None,
) -> dict:
    """Return Costes' randomization significance test for a colocalization.

    One channel is repeatedly scrambled in PSF-sized blocks — destroying any real
    spatial relationship while preserving the intensity distribution and the
    local texture — and the observed PCC is compared against the resulting null
    distribution. The colocalization is conventionally called significant when
    the observed PCC exceeds ~95 % of the randomized values.

    Parameters
    ----------
    image_a, image_b : array_like
        The two channel images, both 2-D and of equal shape.
    block : int
        Edge length (pixels) of the scrambled blocks; use the PSF width.
    n_randomizations : int
        Number of scrambles forming the null distribution.
    seed : int
        Seed of the random generator, so the p-value is reproducible.
    mask : array_like of bool, optional
        Pixels to include; when given, only these enter every correlation.

    Returns
    -------
    dict
        ``{"p_value", "r_observed", "r_random_mean", "r_random_std", "block",
        "n_randomizations"}``; ``p_value`` is the fraction of randomized PCCs
        below the observed one.
    """
    a = np.asarray(image_a, dtype=float)
    b = np.asarray(image_b, dtype=float)
    if a.shape != b.shape or a.ndim != 2:
        raise ValueError("Costes randomization needs two 2-D images of equal shape")
    sel = None if mask is None else np.asarray(mask, dtype=bool)
    r_obs = pearson(a if sel is None else a[sel], b if sel is None else b[sel])
    rng = np.random.default_rng(int(seed))
    randomized = np.empty(int(n_randomizations), dtype=float)
    for i in range(int(n_randomizations)):
        scrambled = _block_shuffle(b, block, rng)
        randomized[i] = pearson(
            a if sel is None else a[sel], scrambled if sel is None else scrambled[sel]
        )
    finite = randomized[np.isfinite(randomized)]
    p_value = float(np.count_nonzero(finite < r_obs) / finite.size) if finite.size else float("nan")
    return {
        "p_value": p_value,
        "r_observed": float(r_obs),
        "r_random_mean": float(finite.mean()) if finite.size else float("nan"),
        "r_random_std": float(finite.std()) if finite.size else float("nan"),
        "block": int(block),
        "n_randomizations": int(n_randomizations),
    }


def van_steensel(image_a, image_b, *, max_shift: int = 20) -> dict:
    """Return van Steensel's cross-correlation-function shift profile.

    Channel B is translated horizontally by ``±max_shift`` pixels and the PCC is
    recomputed at every offset. True colocalization peaks at zero shift and falls
    off symmetrically; a peak *away* from zero exposes a chromatic/registration
    offset, and a flat profile indicates no spatial relation at all.

    Parameters
    ----------
    image_a, image_b : array_like
        The two channel images, both 2-D and of equal shape.
    max_shift : int
        Largest absolute pixel shift evaluated.

    Returns
    -------
    dict
        ``{"shift", "ccf", "peak_shift", "peak_ccf"}`` with ``shift``/``ccf`` as
        arrays over the scanned offsets. ``ccf[s] = corr(A(x), B(x + s))``, so a
        positive ``peak_shift`` means channel B sits that many pixels ahead of A.
    """
    a = np.asarray(image_a, dtype=float)
    b = np.asarray(image_b, dtype=float)
    if a.shape != b.shape or a.ndim != 2:
        raise ValueError("van Steensel CCF needs two 2-D images of equal shape")
    max_shift = int(max(0, min(int(max_shift), a.shape[1] - 1)))
    shifts = np.arange(-max_shift, max_shift + 1, dtype=int)
    ccf = np.empty(shifts.size, dtype=float)
    for i, s in enumerate(shifts):
        # ccf[s] = corr(A(x), B(x + s)): a positive peak means channel B sits
        # *ahead* of channel A by that many pixels.
        if s >= 0:
            ref, shifted = a[:, : a.shape[1] - s if s else a.shape[1]], b[:, s:]
        else:
            ref, shifted = a[:, -s:], b[:, : b.shape[1] + s]
        ccf[i] = pearson(ref, shifted)
    peak = int(np.nanargmax(ccf)) if np.any(np.isfinite(ccf)) else 0
    return {
        "shift": shifts,
        "ccf": ccf,
        "peak_shift": int(shifts[peak]),
        "peak_ccf": float(ccf[peak]),
    }


def cross_correlation_2d(image_a, image_b, *, max_shift: int = 0) -> dict:
    """Return the full 2-D cross-correlation map of two channels.

    The plane version of :func:`van_steensel`: channel B is displaced by every
    ``(dy, dx)`` at once (computed by FFT) and each displacement is scored by the
    same normalisation Pearson uses — mean-subtracted product divided by the two
    standard deviations. A registration offset therefore shows up as a peak away
    from the centre in *either* direction, which a horizontal-only profile can
    miss entirely (a purely vertical chromatic shift looks like "no
    colocalization" in 1-D).

    Parameters
    ----------
    image_a, image_b : array_like
        The two channel images, both 2-D and of equal shape.
    max_shift : int
        When > 0, crop the returned map to ``±max_shift`` pixels around zero
        shift; ``0`` returns the full plane.

    Returns
    -------
    dict
        ``{"map", "dx", "dy", "peak_dx", "peak_dy", "peak"}`` — the correlation
        plane indexed ``[dy, dx]``, the shift axes, and the peak position/value.
    """
    a = np.asarray(image_a, dtype=float)
    b = np.asarray(image_b, dtype=float)
    if a.shape != b.shape or a.ndim != 2:
        raise ValueError("the 2-D cross-correlation needs two 2-D images of equal shape")
    ny, nx = a.shape
    da = a - a.mean()
    db = b - b.mean()
    denom = float(a.std()) * float(b.std()) * a.size
    if denom <= 0.0:
        plane = np.full(a.shape, np.nan)
    else:
        # conj(A)·B — the same convention as the 1-D profile,
        # ``plane[dy, dx] = corr(A(y, x), B(y + dy, x + dx))``.
        plane = (
            np.fft.fftshift(np.real(np.fft.ifft2(np.conj(np.fft.fft2(da)) * np.fft.fft2(db))))
            / denom
        )
    dy = np.arange(ny) - ny // 2
    dx = np.arange(nx) - nx // 2
    if max_shift and max_shift > 0:
        keep_y = np.abs(dy) <= int(max_shift)
        keep_x = np.abs(dx) <= int(max_shift)
        plane = plane[np.ix_(keep_y, keep_x)]
        dy, dx = dy[keep_y], dx[keep_x]
    if np.any(np.isfinite(plane)):
        iy, ix = np.unravel_index(int(np.nanargmax(plane)), plane.shape)
        peak_dy, peak_dx, peak = int(dy[iy]), int(dx[ix]), float(plane[iy, ix])
    else:
        peak_dy = peak_dx = 0
        peak = float("nan")
    return {
        "map": plane,
        "dx": dx,
        "dy": dy,
        "peak_dx": peak_dx,
        "peak_dy": peak_dy,
        "peak": peak,
    }


def pearson_profile(a, b, *, bins: int = 50, versus: str = "a", min_pixels: int = 16) -> dict:
    """Return Pearson's coefficient resolved along an intensity axis.

    A single PCC averages over everything, so it cannot say *where* the
    correlation lives. Binning the pixels by brightness — or by the channel
    ratio — and computing PCC inside each bin does: correlation that only appears
    in bright pixels points at structures on an uncorrelated background, and
    correlation that collapses at high intensity points at detector saturation.

    Parameters
    ----------
    a, b : array_like
        The two channels.
    bins : int
        Number of intensity bins.
    versus : {"a", "b", "ratio"}
        Bin by channel A, by channel B, or by the ``a / b`` intensity ratio.
    min_pixels : int
        Bins with fewer pixels report NaN instead of a meaningless coefficient.

    Returns
    -------
    dict
        ``{"x", "pearson", "error", "counts", "versus"}`` — bin centres, the
        per-bin coefficient, its standard error ``(1 - r²)/√(n - 3)``, and the
        pixel count per bin.
    """
    x, y = _pair(a, b)
    if versus == "b":
        driver = y
    elif versus == "ratio":
        with np.errstate(divide="ignore", invalid="ignore"):
            driver = np.where(y != 0, x / y, np.nan)
    else:
        driver = x
    good = np.isfinite(driver)
    x, y, driver = x[good], y[good], driver[good]
    n_bins = max(int(bins), 2)
    empty = np.full(n_bins, np.nan)
    if driver.size < min_pixels:
        return {
            "x": empty,
            "pearson": empty.copy(),
            "error": empty.copy(),
            "counts": np.zeros(n_bins, dtype=int),
            "versus": versus,
        }
    edges = np.linspace(float(driver.min()), float(driver.max()), n_bins + 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    values = np.full(n_bins, np.nan)
    errors = np.full(n_bins, np.nan)
    counts = np.zeros(n_bins, dtype=int)
    index = np.clip(np.digitize(driver, edges) - 1, 0, n_bins - 1)
    for i in range(n_bins):
        sel = index == i
        n = int(np.count_nonzero(sel))
        counts[i] = n
        if n < min_pixels:
            continue
        r = pearson(x[sel], y[sel])
        values[i] = r
        if np.isfinite(r) and n > 3:
            errors[i] = (1.0 - r**2) / np.sqrt(n - 3)
    return {"x": centres, "pearson": values, "error": errors, "counts": counts, "versus": versus}


def joint_histogram(a, b, *, bins: int = 128, range_a=None, range_b=None) -> dict:
    """Return the 2-D intensity joint histogram (scatter density) of two channels.

    The histogram *is* the colocalization scatter plot: colocalized structures
    form a diagonal cloud, segregated ones sit on the axes. Gating a rectangle in
    this plane selects a pixel population (see :func:`colocalization_metrics`).

    Parameters
    ----------
    a, b : array_like
        The two channels.
    bins : int
        Number of bins per axis.
    range_a, range_b : tuple of float, optional
        Explicit ``(min, max)`` per axis; defaults to the data range.

    Returns
    -------
    dict
        ``{"histogram", "edges_a", "edges_b"}`` with ``histogram`` shaped
        ``(bins, bins)`` and indexed ``[channel A, channel B]``.
    """
    x, y = _pair(a, b)
    if x.size == 0:
        empty = np.zeros((int(bins), int(bins)), dtype=float)
        return {
            "histogram": empty,
            "edges_a": np.zeros(int(bins) + 1),
            "edges_b": np.zeros(int(bins) + 1),
        }
    ra = tuple(range_a) if range_a is not None else (float(x.min()), float(x.max()))
    rb = tuple(range_b) if range_b is not None else (float(y.min()), float(y.max()))
    if ra[1] <= ra[0]:
        ra = (ra[0], ra[0] + 1.0)
    if rb[1] <= rb[0]:
        rb = (rb[0], rb[0] + 1.0)
    hist, edges_a, edges_b = np.histogram2d(x, y, bins=int(bins), range=[ra, rb])
    return {"histogram": hist, "edges_a": edges_a, "edges_b": edges_b}


@dataclasses.dataclass
class ColocalizationResult:
    """Colocalization coefficients plus the pixel maps they were computed from.

    Attributes
    ----------
    metrics : dict
        Scalar coefficients (PCC, MOC, M1/M2, ICQ, Spearman, thresholds, …).
    image_a, image_b : numpy.ndarray
        The background-subtracted channel maps actually analysed.
    mask : numpy.ndarray
        Boolean map of the pixels that entered the coefficients.
    coloc_mask : numpy.ndarray
        Boolean map of pixels above *both* thresholds (the colocalized pixels).
    histogram : dict
        The joint histogram (see :func:`joint_histogram`).
    ccf : dict
        The van Steensel shift profile, or an empty dict when not requested.
    ccf_map : dict
        The full 2-D cross-correlation plane (see :func:`cross_correlation_2d`),
        or an empty dict when not requested.
    profiles : dict
        Intensity-resolved correlation profiles keyed ``"a"``, ``"b"`` and
        ``"ratio"`` (see :func:`pearson_profile`), or empty when not requested.
    roi : numpy.ndarray or None
        The spatial region the analysis was restricted to, when one was given.
    objects : dict
        The object-based analysis (see
        :func:`~.objects.object_colocalization`), or empty when not requested.
    """

    metrics: dict
    image_a: np.ndarray
    image_b: np.ndarray
    mask: np.ndarray
    coloc_mask: np.ndarray
    histogram: dict
    ccf: dict = dataclasses.field(default_factory=dict)
    ccf_map: dict = dataclasses.field(default_factory=dict)
    profiles: dict = dataclasses.field(default_factory=dict)
    roi: np.ndarray | None = None
    objects: dict = dataclasses.field(default_factory=dict)


def colocalization_metrics(
    image_a,
    image_b,
    *,
    background_a: float = 0.0,
    background_b: float = 0.0,
    threshold_a: float = 0.0,
    threshold_b: float = 0.0,
    auto_threshold: bool = False,
    gate: tuple[float, float, float, float] | None = None,
    bins: int = 128,
    costes_test: bool = False,
    costes_block: int = 4,
    costes_randomizations: int = 200,
    costes_seed: int = 0,
    ccf_max_shift: int = 0,
    ccf_2d: bool = False,
    profiles: bool = False,
    profile_bins: int = 50,
    roi=None,
    object_analysis: bool = False,
    object_min_size: int = 4,
    object_smoothing: float = 0.0,
    object_split: bool = False,
    object_distance: float = 3.0,
) -> ColocalizationResult:
    """Compute the full colocalization coefficient set for a channel pair.

    The pipeline mirrors the established one: subtract a per-channel background,
    keep the pixels above the per-channel thresholds (optionally derived by
    Costes' method), optionally restrict further to a rectangular gate in the
    intensity-vs-intensity plane, then evaluate every coefficient on that
    selection.

    Parameters
    ----------
    image_a, image_b : array_like
        The two channel images, 2-D and of equal shape.
    background_a, background_b : float
        Per-channel background subtracted before anything else.
    threshold_a, threshold_b : float
        Manual per-channel thresholds applied to the background-subtracted data.
    auto_threshold : bool
        Replace the manual thresholds with Costes' automatic ones.
    gate : tuple of float, optional
        ``(a_min, a_max, b_min, b_max)`` rectangle in the scatter plane; only
        pixels inside it enter the *gated* coefficients.
    bins : int
        Bin count per axis of the returned joint histogram.
    costes_test : bool
        Run the block-scramble randomization significance test.
    costes_block, costes_randomizations, costes_seed : int
        Parameters of that test (see :func:`costes_significance`).
    ccf_max_shift : int
        When > 0, also compute the van Steensel shift profile up to this shift.
    ccf_2d : bool
        Also compute the full 2-D cross-correlation plane (cropped to
        ``ccf_max_shift`` when that is set), which exposes vertical
        misregistration the horizontal profile cannot see.
    profiles : bool
        Also compute intensity-resolved correlation profiles (versus channel A,
        channel B and the A/B ratio).
    profile_bins : int
        Number of bins in those profiles.
    roi : ROI or array_like of bool, optional
        Spatial region to restrict the whole analysis to: any
        :class:`chisurf.core.roi.ROI` (so a painted mask, a polygon, or
        "inside this shape and above this intensity" all work) or a ready-made
        boolean mask. Pixels outside it are excluded from every coefficient.
    object_analysis : bool
        Also segment both channels into discrete objects and score their
        coincidence — the right regime for punctate signal, where the
        coefficients above are dominated by the empty background between spots.
    object_min_size, object_smoothing, object_split, object_distance
        Segmentation and coincidence parameters (see
        :func:`~.objects.object_colocalization`). The per-channel thresholds are
        the ones already in force, so objects and coefficients see the same
        "present" definition.

    Returns
    -------
    ColocalizationResult
        Coefficients, the analysed maps, the selection masks, and the histogram.
    """
    a = np.asarray(image_a, dtype=float) - float(background_a)
    b = np.asarray(image_b, dtype=float) - float(background_b)
    if a.shape != b.shape or a.ndim != 2:
        raise ValueError("colocalization needs two 2-D images of equal shape")

    region = None
    if roi is not None:
        from chisurf.core.roi import ROI

        if isinstance(roi, ROI):
            region = roi.to_mask(a.shape, image=a)
        else:
            region = np.asarray(roi, dtype=bool)
        if region.shape != a.shape:
            raise ValueError("the ROI mask must have the same shape as the images")
        if not region.any():
            region = None

    metrics: dict = {
        "background_a": float(background_a),
        "background_b": float(background_b),
        "n_pixels_total": int(a.size if region is None else np.count_nonzero(region)),
    }
    if region is not None:
        metrics["roi_area_fraction"] = float(np.count_nonzero(region) / region.size)

    # Everything below is evaluated inside the ROI when one is given: the
    # thresholds, the coefficients and the null model must all see the same
    # pixels, or a hand-drawn region would change the numbers twice over.
    roi_a = a if region is None else a[region]
    roi_b = b if region is None else b[region]

    if auto_threshold:
        costes = costes_threshold(roi_a, roi_b)
        metrics.update(
            {
                "costes_threshold_a": costes["threshold_a"],
                "costes_threshold_b": costes["threshold_b"],
                "costes_slope": costes["slope"],
                "costes_intercept": costes["intercept"],
            }
        )
        if np.isfinite(costes["threshold_a"]):
            threshold_a = costes["threshold_a"]
            threshold_b = costes["threshold_b"]
    metrics["threshold_a"] = float(threshold_a)
    metrics["threshold_b"] = float(threshold_b)

    mask = np.isfinite(a) & np.isfinite(b) & (a > threshold_a) & (b > threshold_b)
    if region is not None:
        mask &= region
    metrics["n_pixels"] = int(np.count_nonzero(mask))
    sel_a = a[mask]
    sel_b = b[mask]

    metrics["pearson"] = pearson(sel_a, sel_b)
    metrics["pearson_all"] = pearson(roi_a, roi_b)
    metrics["manders_overlap"] = manders_overlap(sel_a, sel_b)
    m1, m2 = manders_fractions(roi_a, roi_b, threshold_a, threshold_b)
    metrics["manders_m1"] = m1
    metrics["manders_m2"] = m2
    metrics["li_icq"] = li_icq(sel_a, sel_b)
    metrics["spearman"] = spearman(sel_a, sel_b)
    coloc_mask = mask
    area = coloc_mask.size if region is None else np.count_nonzero(region)
    metrics["coloc_area_fraction"] = float(np.count_nonzero(coloc_mask) / max(area, 1))

    if gate is not None:
        a_min, a_max, b_min, b_max = (float(v) for v in gate)
        gated = mask & (a >= a_min) & (a <= a_max) & (b >= b_min) & (b <= b_max)
        metrics["gate"] = (a_min, a_max, b_min, b_max)
        metrics["n_pixels_gated"] = int(np.count_nonzero(gated))
        metrics["gated_pearson"] = pearson(a[gated], b[gated])
        metrics["gated_manders_overlap"] = manders_overlap(a[gated], b[gated])
        mask = gated

    if costes_test:
        metrics.update(
            {
                f"costes_{k}": v
                for k, v in costes_significance(
                    a,
                    b,
                    block=costes_block,
                    n_randomizations=costes_randomizations,
                    seed=costes_seed,
                    mask=region,
                ).items()
            }
        )

    ccf: dict = {}
    if ccf_max_shift and ccf_max_shift > 0:
        ccf = van_steensel(a, b, max_shift=int(ccf_max_shift))
        metrics["ccf_peak_shift"] = ccf["peak_shift"]
        metrics["ccf_peak"] = ccf["peak_ccf"]

    ccf_plane: dict = {}
    if ccf_2d:
        ccf_plane = cross_correlation_2d(a, b, max_shift=int(ccf_max_shift or 0))
        metrics["ccf2d_peak_dx"] = ccf_plane["peak_dx"]
        metrics["ccf2d_peak_dy"] = ccf_plane["peak_dy"]
        metrics["ccf2d_peak"] = ccf_plane["peak"]

    profile_set: dict = {}
    if profiles:
        profile_set = {
            key: pearson_profile(sel_a, sel_b, bins=int(profile_bins), versus=key)
            for key in ("a", "b", "ratio")
        }

    object_result: dict = {}
    if object_analysis:
        from .objects import object_colocalization

        object_result = object_colocalization(
            a,
            b,
            threshold_a=threshold_a if threshold_a else None,
            threshold_b=threshold_b if threshold_b else None,
            min_size=int(object_min_size),
            smoothing=float(object_smoothing),
            split=bool(object_split),
            distance=float(object_distance),
            mask=region,
        )
        metrics.update(object_result["metrics"])

    return ColocalizationResult(
        metrics=metrics,
        image_a=a,
        image_b=b,
        mask=mask,
        coloc_mask=coloc_mask,
        histogram=joint_histogram(sel_a, sel_b, bins=bins),
        ccf=ccf,
        ccf_map=ccf_plane,
        profiles=profile_set,
        roi=region,
        objects=object_result,
    )
