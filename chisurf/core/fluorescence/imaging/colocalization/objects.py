"""Object-based colocalization: count particles, not pixel intensities.

For punctate signal — vesicles, granules, foci — the pixel-wise coefficients
answer the wrong question. Two channels of sparse puncta sit mostly on empty
background, so their correlation is dominated by the co-occurrence of *nothing*,
and a Pearson coefficient can be near zero for perfectly coincident spots or
respectably high for spots that merely share a crowded region.

The object-based approach segments each channel into discrete objects and then
asks countable questions (Bolte & Cordelières, *A guided tour into subcellular
colocalization analysis in light microscopy*, J. Microsc. 224:213, 2006):

* how far is each object from the nearest object of the other channel?
* what fraction of them have a partner within a distance tolerance (the optical
  resolution, typically)?
* what fraction of their centres fall *inside* an object of the other channel?
* how much of each object's area is covered by the other channel?

The distance tolerance is the one honest parameter: two objects cannot be
localised better than the PSF, so "coincident" means "closer than the resolution",
not "identical centroid".
"""

from __future__ import annotations

import dataclasses

import numpy as np

__all__ = [
    "ObjectSet",
    "object_colocalization",
    "object_distance_histogram",
    "segment_objects",
]


@dataclasses.dataclass
class ObjectSet:
    """Discrete objects segmented from one channel.

    Attributes
    ----------
    labels : numpy.ndarray
        Integer label image (``0`` = background, ``1…n`` = objects).
    centroids : numpy.ndarray
        ``(n, 2)`` array of intensity-weighted ``(y, x)`` centres.
    areas : numpy.ndarray
        Pixel area of each object.
    intensities : numpy.ndarray
        Integrated intensity of each object.
    properties : list of chisurf.core.roi.RegionProperties
        The full measurements of each object — shape, hull, moments, intensity
        statistics — from which the arrays above are the four most-used
        columns. Empty when the set was built without them.
    """

    labels: np.ndarray
    centroids: np.ndarray
    areas: np.ndarray
    intensities: np.ndarray
    properties: list = dataclasses.field(default_factory=list)

    @property
    def count(self) -> int:
        """Return the number of objects."""
        return int(self.centroids.shape[0])

    @property
    def mask(self) -> np.ndarray:
        """Return the boolean footprint of all objects."""
        return self.labels > 0

    def rois(self) -> list:
        """Return each object as a region of interest.

        Returns
        -------
        list of chisurf.core.roi.MaskROI
            One region per object, ready to gate, combine or store — the same
            type a hand-drawn selection produces.
        """
        from chisurf.core.roi import labels_to_rois

        return labels_to_rois(self.labels)


def segment_objects(
    image,
    *,
    threshold: float | None = None,
    min_size: int = 4,
    smoothing: float = 0.0,
    split: bool = False,
    mask=None,
) -> ObjectSet:
    """Segment *image* into discrete objects.

    Parameters
    ----------
    image : array_like
        2-D channel image (background-subtracted).
    threshold : float, optional
        Intensity above which a pixel belongs to an object. ``None`` uses
        ``mean + 2·std`` of the (masked) image — a plain, stated default rather
        than a hidden one.
    min_size : int
        Objects smaller than this many pixels are discarded as noise.
    smoothing : float
        Gaussian smoothing (σ in pixels) applied before thresholding; useful when
        shot noise fragments objects.
    split : bool
        Split touching objects with a distance-transform watershed. Off by
        default: it helps dense puncta and hurts irregular shapes.
    mask : array_like of bool, optional
        Restrict segmentation to this region.

    Returns
    -------
    ObjectSet
        The segmented objects (possibly empty).
    """
    from scipy import ndimage

    data = np.asarray(image, dtype=float)
    if data.ndim != 2:
        raise ValueError("object segmentation needs a 2-D image")
    region = None if mask is None else np.asarray(mask, dtype=bool)
    if smoothing and smoothing > 0:
        data = ndimage.gaussian_filter(data, float(smoothing))
    values = data if region is None else data[region]
    values = values[np.isfinite(values)]
    if threshold is None:
        threshold = float(values.mean() + 2.0 * values.std()) if values.size else 0.0

    binary = np.isfinite(data) & (data > float(threshold))
    if region is not None:
        binary &= region

    labels, _ = ndimage.label(binary)
    if split and labels.max() > 0:
        labels = _watershed_split(binary)

    if labels.max() == 0:
        empty2 = np.zeros((0, 2), dtype=float)
        empty1 = np.zeros(0, dtype=float)
        return ObjectSet(labels=labels, centroids=empty2, areas=empty1, intensities=empty1)

    index = np.arange(1, labels.max() + 1)
    areas = np.asarray(ndimage.sum(np.ones_like(data), labels, index), dtype=float)
    keep = index[areas >= int(min_size)]
    if keep.size == 0:
        empty2 = np.zeros((0, 2), dtype=float)
        empty1 = np.zeros(0, dtype=float)
        return ObjectSet(
            labels=np.zeros_like(labels), centroids=empty2, areas=empty1, intensities=empty1
        )

    # Relabel 1…n so the label image, the centroids and the areas stay aligned.
    remap = np.zeros(labels.max() + 1, dtype=int)
    remap[keep] = np.arange(1, keep.size + 1)
    labels = remap[labels]

    # One pass of the shared region measurements, rather than one ndimage
    # reduction per quantity: the same numbers every other imaging tool reports.
    # Negative pixels (a background-subtracted image has them) are clipped, or
    # they would pull an object's centre of mass away from its own signal.
    from chisurf.core.roi import regionprops

    props = regionprops(labels, np.clip(data, 0.0, None))
    return ObjectSet(
        labels=labels,
        centroids=np.asarray([p.centroid_weighted for p in props], dtype=float).reshape(-1, 2),
        areas=np.asarray([p.area for p in props], dtype=float),
        intensities=np.asarray([p.intensity_sum for p in props], dtype=float),
        properties=props,
    )


def _watershed_split(binary: np.ndarray) -> np.ndarray:
    """Split touching objects with a distance-transform watershed."""
    from scipy import ndimage

    distance = ndimage.distance_transform_edt(binary)
    try:
        from skimage.feature import peak_local_max
        from skimage.segmentation import watershed
    except ImportError:  # pragma: no cover - optional dependency
        labels, _ = ndimage.label(binary)
        return labels
    coordinates = peak_local_max(distance, labels=binary, min_distance=2, exclude_border=False)
    markers = np.zeros(binary.shape, dtype=int)
    for i, (y, x) in enumerate(coordinates, start=1):
        markers[y, x] = i
    if markers.max() == 0:
        labels, _ = ndimage.label(binary)
        return labels
    return watershed(-distance, markers, mask=binary)


def _nearest_distances(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Return each *source* centroid's distance to the nearest *target* centroid."""
    if source.size == 0 or target.size == 0:
        return np.full(source.shape[0], np.nan)
    from scipy.spatial import cKDTree

    distances, _ = cKDTree(target).query(source, k=1)
    return np.asarray(distances, dtype=float)


def _centroids_inside(centroids: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Return, per centroid, whether it falls inside a labelled object."""
    if centroids.size == 0:
        return np.zeros(0, dtype=bool)
    ny, nx = labels.shape
    rows = np.clip(np.rint(centroids[:, 0]).astype(int), 0, ny - 1)
    cols = np.clip(np.rint(centroids[:, 1]).astype(int), 0, nx - 1)
    return labels[rows, cols] > 0


def _overlap_fractions(objects: ObjectSet, other_mask: np.ndarray) -> np.ndarray:
    """Return, per object, the fraction of its area covered by *other_mask*."""
    from scipy import ndimage

    if objects.count == 0:
        return np.zeros(0, dtype=float)
    index = np.arange(1, objects.count + 1)
    covered = np.asarray(ndimage.sum(other_mask.astype(float), objects.labels, index), dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(objects.areas > 0, covered / objects.areas, np.nan)


def object_colocalization(
    image_a,
    image_b,
    *,
    threshold_a: float | None = None,
    threshold_b: float | None = None,
    min_size: int = 4,
    smoothing: float = 0.0,
    split: bool = False,
    distance: float = 3.0,
    mask=None,
) -> dict:
    """Segment both channels into objects and score their coincidence.

    Parameters
    ----------
    image_a, image_b : array_like
        The two channel images (background-subtracted), 2-D and of equal shape.
    threshold_a, threshold_b : float, optional
        Segmentation thresholds; ``None`` uses ``mean + 2·std`` per channel.
    min_size : int
        Minimum object size in pixels.
    smoothing : float
        Gaussian σ applied before thresholding.
    split : bool
        Split touching objects by watershed.
    distance : float
        Distance tolerance (pixels) within which two object centres count as
        coincident — set it to the optical resolution, since nothing can be
        localised better than that.
    mask : array_like of bool, optional
        Spatial region to restrict the analysis to.

    Returns
    -------
    dict
        ``{"objects_a", "objects_b", "metrics", "distances_a", "distances_b"}``
        with the two :class:`ObjectSet`s, the scalar coefficients, and the
        per-object nearest-neighbour distances in both directions.
    """
    a = np.asarray(image_a, dtype=float)
    b = np.asarray(image_b, dtype=float)
    if a.shape != b.shape or a.ndim != 2:
        raise ValueError("object colocalization needs two 2-D images of equal shape")

    objects_a = segment_objects(
        a, threshold=threshold_a, min_size=min_size, smoothing=smoothing, split=split, mask=mask
    )
    objects_b = segment_objects(
        b, threshold=threshold_b, min_size=min_size, smoothing=smoothing, split=split, mask=mask
    )

    distances_a = _nearest_distances(objects_a.centroids, objects_b.centroids)
    distances_b = _nearest_distances(objects_b.centroids, objects_a.centroids)
    inside_a = _centroids_inside(objects_a.centroids, objects_b.labels)
    inside_b = _centroids_inside(objects_b.centroids, objects_a.labels)
    overlap_a = _overlap_fractions(objects_a, objects_b.mask)
    overlap_b = _overlap_fractions(objects_b, objects_a.mask)

    def _fraction(values, predicate) -> float:
        """Return the fraction of finite *values* satisfying *predicate*."""
        finite = values[np.isfinite(values)] if values.size else values
        if finite.size == 0:
            return float("nan")
        return float(np.count_nonzero(predicate(finite)) / finite.size)

    metrics = {
        "n_objects_a": objects_a.count,
        "n_objects_b": objects_b.count,
        "object_distance": float(distance),
        "object_fraction_a_near_b": _fraction(distances_a, lambda d: d <= float(distance)),
        "object_fraction_b_near_a": _fraction(distances_b, lambda d: d <= float(distance)),
        "object_fraction_a_in_b": float(np.mean(inside_a)) if inside_a.size else float("nan"),
        "object_fraction_b_in_a": float(np.mean(inside_b)) if inside_b.size else float("nan"),
        "object_median_distance_a": (
            float(np.nanmedian(distances_a)) if distances_a.size else float("nan")
        ),
        "object_median_distance_b": (
            float(np.nanmedian(distances_b)) if distances_b.size else float("nan")
        ),
        "object_mean_overlap_a": (float(np.nanmean(overlap_a)) if overlap_a.size else float("nan")),
        "object_mean_overlap_b": (float(np.nanmean(overlap_b)) if overlap_b.size else float("nan")),
    }
    return {
        "objects_a": objects_a,
        "objects_b": objects_b,
        "metrics": metrics,
        "distances_a": distances_a,
        "distances_b": distances_b,
    }


def object_distance_histogram(distances, *, bins: int = 20, maximum: float | None = None) -> dict:
    """Return a histogram of nearest-neighbour object distances.

    The distribution is the object-based counterpart of the intensity scatter:
    a peak at short distance is real coincidence, a broad distribution centred on
    the mean inter-object spacing is chance.

    Parameters
    ----------
    distances : array_like
        Nearest-neighbour distances (pixels).
    bins : int
        Number of histogram bins.
    maximum : float, optional
        Upper edge; defaults to the largest finite distance.

    Returns
    -------
    dict
        ``{"x", "counts"}`` with bin centres and counts.
    """
    values = np.asarray(distances, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"x": np.zeros(int(bins)), "counts": np.zeros(int(bins), dtype=int)}
    top = float(maximum) if maximum else float(values.max())
    if top <= 0:
        top = 1.0
    counts, edges = np.histogram(values, bins=int(bins), range=(0.0, top))
    return {"x": 0.5 * (edges[:-1] + edges[1:]), "counts": counts}
