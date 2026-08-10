"""Qt-free spot and region detection for imaging data.

Detection is its own step. It was not: the molecule-wise MLE segmented the
image inside the same function that fitted it, with one fixed algorithm, and
threw the regions away afterwards — so a segmentation could not be reviewed,
corrected, compared between parameter sets, or produced by anything else. This
module is that step on its own, writing what it found through the shared
contract in :mod:`chisurf.core.fio.fluorescence.region_container` so that the
fit reads regions rather than deriving them.

Four detectors, all on the in-tree primitives in
:mod:`chisurf.core.roi.segmentation` — no new algorithms here, only a choice
between the ones the tree already has:

``watershed``
    Smooth, threshold (Otsu or fixed), clear border, split touching objects by
    a distance-transform watershed seeded on local maxima. What the molecule
    MLE always did, and the right default for objects that touch.
``threshold``
    The same without the splitting: connected components of the thresholded
    image. Faster, and correct when objects are well separated — the watershed
    can only ever *over*-split a lone spot.
``log`` / ``dog``
    Laplacian- and difference-of-Gaussian scale spaces. These return centres
    **and widths**, which a single threshold cannot: a spot registers most
    strongly at the scale matching its own size. That is what an image of
    unknown focus needs, and it is why the detected ``sigma`` travels with the
    region as a column of its own.

A blob detector returns points, and the contract needs pixels, so its spots are
rasterised into discs of radius ``sqrt(2) * sigma`` — the width the detector
measured rather than one chosen in advance. Contested pixels go to the nearer
centre, so the labels stay disjoint and no pixel's photons are counted twice.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Any

import numpy as np

__all__ = [
    "METHODS",
    "SpotFinderResult",
    "SpotFinderSettings",
    "detect",
    "detect_labels",
]

#: Detector names, in the order a person should try them.
METHODS = ("watershed", "threshold", "log", "dog")


@dataclasses.dataclass
class SpotFinderSettings:
    """Settings for one detection.

    Parameters
    ----------
    method : str
        One of :data:`METHODS`.
    sigma : float, optional
        Gaussian smoothing applied before thresholding (``watershed`` and
        ``threshold`` only). Smoothing before a threshold is what stops a
        single noisy pixel becoming an object.
    threshold : float, optional
        Fixed intensity threshold for ``watershed`` / ``threshold``; ``< 0``
        computes an Otsu level. For ``log`` / ``dog`` this is the minimum
        scale-normalised response instead, which does **not** follow the image
        units — read it off a run rather than guessing it.
    peak_footprint_size : int, optional
        Side of the square footprint for the watershed's local-maxima seeds.
        Larger merges nearby seeds, which is how over-splitting is cured.
    min_area : int, optional
        Regions smaller than this many pixels are dropped. ``2`` is what
        separates an object from a hot camera pixel: a spot covers several
        pixels, a defect covers exactly one.
    max_area : int, optional
        Regions larger than this are dropped; ``0`` disables. An aggregate or a
        saturated patch is not a molecule, and it is the one that dominates a
        brightness histogram.
    clear_border : bool, optional
        Drop regions touching the frame edge. A partly-imaged object has a
        truncated area and a biased centroid, so it is worse than absent — but
        for a densely covered field it can remove most of the data, which is
        why it is a setting and not a rule.
    min_sigma, max_sigma : float, optional
        Spot-width range for ``log`` / ``dog``, as a Gaussian sigma in pixels.
        A diffraction-limited spot has sigma ~ 0.21 * lambda / NA.
    num_sigma : int, optional
        Number of scales for ``log``.
    overlap : float, optional
        Blobs overlapping by more than this fraction are merged, larger kept.
    roi : chisurf.core.roi.ROI or dict, optional
        Confine the search to a region. Applied **before** the threshold, so an
        Otsu level is computed from the region's own pixels — the point of
        restricting an analysis to one cell is that the rest of the frame does
        not set its threshold. Accepts the serialised form, so it survives RPC.
    workflow : str, optional
        Name of the workflow these settings came from
        (:mod:`..core.workflow`). Recorded with the detection so a stored
        result says which recipe produced it.
    """

    #: The defaults below **are** the ``single_molecule`` workflow, which is the
    #: standard one: constructing settings with no arguments and loading the
    #: shipped document must give the same detection, and a test says so. Change
    #: one and change the other.
    method: str = "watershed"

    sigma: float = 1.0
    threshold: float = -1.0
    peak_footprint_size: int = 6

    min_area: int = 1
    max_area: int = 0
    clear_border: bool = True

    min_sigma: float = 1.0
    max_sigma: float = 5.0
    num_sigma: int = 10
    overlap: float = 0.5

    roi: Any = None

    #: Name of the workflow these settings came from, carried into the
    #: container's parameters so a stored detection says which recipe made it
    #: rather than only what the recipe evaluated to.
    workflow: str = "single_molecule"

    def analysis_roi(self):
        """Return :attr:`roi` as a :class:`~chisurf.core.roi.ROI`, or ``None``.

        Returns
        -------
        chisurf.core.roi.ROI or None
            Rebuilt from the serialised form when the settings came over RPC.
        """
        from chisurf.core.roi import as_roi

        return as_roi(self.roi)

    def validated(self) -> SpotFinderSettings:
        """Return self, having checked the method name.

        Returns
        -------
        SpotFinderSettings

        Raises
        ------
        ValueError
            If :attr:`method` is not one of :data:`METHODS`. Named rather than
            silently falling back, because a misspelled detector that quietly
            ran the default would be discovered as a difference in the results.
        """
        if self.method not in METHODS:
            raise ValueError(
                f"unknown detection method {self.method!r}; "
                f"expected one of {', '.join(METHODS)}"
            )
        return self


@dataclasses.dataclass
class SpotFinderResult:
    """One detection, before it is written anywhere.

    Attributes
    ----------
    labels : numpy.ndarray
        ``int32`` label image, contiguous from 1, ``0`` background.
    table : tttrlib.DataStore
        One row per region, ``label`` first — the contract's table half.
    intensity : numpy.ndarray
        The image the regions were found in.
    settings : SpotFinderSettings
        What produced it.
    analysis_roi : chisurf.core.roi.ROI or None
        The region the search was confined to.
    """

    labels: np.ndarray
    table: Any
    intensity: np.ndarray
    settings: SpotFinderSettings
    analysis_roi: Any = None

    @property
    def n_regions(self) -> int:
        """Number of regions found."""
        from chisurf.core.datastore import row_count

        return int(row_count(self.table))

    def background_rate(self, margin: int = 2) -> float:
        """Return the mean image value per background pixel.

        The number a region's brightness is compared against, and the one that
        says whether a threshold was set sensibly. The background is the
        *dilated* foreground's complement: the pixels touching a spot still
        carry its tail, and counting them as background biases it upwards.

        Parameters
        ----------
        margin : int, optional
            Pixels of clearance to leave around every region.

        Returns
        -------
        float
            ``nan`` when there is no background left.
        """
        from scipy import ndimage as ndi

        occupied = self.labels > 0
        if margin > 0:
            occupied = ndi.binary_dilation(occupied, iterations=int(margin))
        background = ~occupied
        if self.analysis_roi is not None:
            background &= self.analysis_roi.to_mask(
                self.intensity.shape, image=self.intensity
            )
        if not background.any():
            return float("nan")
        return float(np.asarray(self.intensity)[background].mean())

    def write(self, source, *, name: str = "spots", out_dir=None) -> str:
        """Write this detection into the measurement's container.

        Parameters
        ----------
        source : str or Path
            The image or photon file the regions were found in, or a container.
        name : str, optional
            Stem for the raster/table pair.
        out_dir : str or Path, optional
            Directory the container lives in. Defaults to beside *source*.

        Returns
        -------
        str
            Path of the container written.
        """
        from chisurf.core.fio.fluorescence.region_container import write_regions

        return write_regions(
            source,
            self.labels,
            self.intensity,
            name=name,
            table=self.table,
            parameters=dataclasses.asdict(self.settings),
            out_dir=out_dir,
        )


def detect_labels(image, settings: SpotFinderSettings) -> tuple[np.ndarray, dict]:
    """Detect regions in *image* and return the label raster.

    The half of :func:`detect` that decides *which pixels are a region*, split
    out because it is the half a caller may want to filter or hand-correct
    before it is measured.

    Parameters
    ----------
    image : numpy.ndarray
        2-D image; bright objects on a dark background.
    settings : SpotFinderSettings
        Detection settings.

    Returns
    -------
    labels : numpy.ndarray
        ``int32`` label image, contiguous from 1.
    extra : dict
        Detector-specific per-region columns (``spot.sigma`` for the blob
        detectors), aligned with the labels 1..n. Empty for the others.
    """
    from chisurf.core.roi.segmentation import gaussian, relabel_sequential

    settings.validated()
    image = np.asarray(image, dtype=float)
    if image.ndim != 2:
        raise ValueError(f"expected a 2-D image, got shape {image.shape}")

    inside = None
    roi = settings.analysis_roi()
    if roi is not None:
        inside = roi.to_mask(image.shape, image=image)
        if not inside.any():
            return np.zeros(image.shape, dtype=np.int32), {}

    if settings.method in ("watershed", "threshold"):
        smoothed = gaussian(image, sigma=settings.sigma)
        if smoothed.max() <= 0:
            return np.zeros(image.shape, dtype=np.int32), {}
        labels = _by_threshold(smoothed, settings, inside)
        extra: dict = {}
    else:
        labels, extra = _by_blobs(image, settings, inside)

    labels, extra = _filter(labels, extra, settings, image.shape)
    labels, _forward, _inverse = relabel_sequential(labels)
    return labels.astype(np.int32), extra


def detect(image, settings: SpotFinderSettings) -> SpotFinderResult:
    """Detect regions in *image* and measure them.

    Parameters
    ----------
    image : numpy.ndarray
        2-D image; bright objects on a dark background.
    settings : SpotFinderSettings
        Detection settings.

    Returns
    -------
    SpotFinderResult
    """
    from chisurf.core.fio.fluorescence.region_container import region_table

    labels, extra = detect_labels(image, settings)
    table = region_table(labels, np.asarray(image, dtype=float), extra=extra or None)
    return SpotFinderResult(
        labels=labels,
        table=table,
        intensity=np.asarray(image, dtype=float),
        settings=settings,
        analysis_roi=settings.analysis_roi(),
    )


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------
def _by_threshold(smoothed, settings: SpotFinderSettings, inside) -> np.ndarray:
    """Threshold, then either connected components or a seeded watershed."""
    from scipy import ndimage as ndi

    from chisurf.core.roi.segmentation import (
        clear_border,
        peak_local_max,
        threshold_otsu,
        watershed,
    )

    if settings.threshold > 0:
        level = settings.threshold
    else:
        # From the region's own pixels when there is one: the point of
        # confining an analysis to one cell is that the rest of the frame
        # should not set its threshold.
        values = smoothed if inside is None else smoothed[inside]
        # An empty frame is an ordinary input — a blank tile, a field the
        # sample missed, one entry in a batch — and Otsu is undefined on it
        # (no two classes to separate). Finding nothing is the right answer;
        # raising here would become a dropped file in a batch, which is how a
        # blank frame turns into a silently shorter result set.
        if np.unique(values).size < 2:
            return np.zeros(smoothed.shape, dtype=np.int32)
        level = threshold_otsu(values)

    binary = smoothed > level
    if settings.clear_border:
        binary = clear_border(binary)
    if inside is not None:
        binary &= inside
    if not binary.any():
        return np.zeros(smoothed.shape, dtype=np.int32)

    if settings.method == "threshold":
        labels, _n = ndi.label(binary)
        return labels

    distance = ndi.distance_transform_edt(binary)
    footprint = np.ones(
        (settings.peak_footprint_size, settings.peak_footprint_size), dtype=bool
    )
    coords = peak_local_max(distance, footprint=footprint, labels=binary)
    seeds = np.zeros(distance.shape, dtype=bool)
    seeds[tuple(coords.T)] = True
    markers, _n = ndi.label(seeds)
    return watershed(-distance, markers, mask=binary)


def _by_blobs(image, settings: SpotFinderSettings, inside):
    """Detect blobs in a scale space and rasterise each into a disc.

    A blob detector answers *where and how wide*, not *which pixels*, and the
    contract needs pixels. The disc radius is ``sqrt(2) * sigma`` — the width
    the detector measured, at the scale where the spot responded most strongly,
    rather than one fixed in advance. Contested pixels go to the nearer centre,
    so two overlapping discs stay two disjoint regions and no pixel's photons
    are counted for both.
    """
    from chisurf.core.roi.segmentation import blob_dog, blob_log

    search = image if inside is None else np.where(inside, image, 0.0)
    if settings.method == "log":
        blobs = blob_log(
            search,
            min_sigma=settings.min_sigma,
            max_sigma=settings.max_sigma,
            num_sigma=settings.num_sigma,
            threshold=settings.threshold if settings.threshold > 0 else 0.2,
            overlap=settings.overlap,
        )
    else:
        blobs = blob_dog(
            search,
            min_sigma=settings.min_sigma,
            max_sigma=settings.max_sigma,
            threshold=settings.threshold if settings.threshold > 0 else 0.5,
            overlap=settings.overlap,
        )

    blobs = np.asarray(blobs, dtype=float).reshape(-1, 3)
    if blobs.size == 0:
        return np.zeros(image.shape, dtype=np.int32), {}

    centres = blobs[:, :2]
    sigmas = blobs[:, 2]
    radii = np.sqrt(2.0) * sigmas

    # A distance field per blob is what resolves a contested pixel honestly: a
    # loop that paints discs in order gives the last one written, which depends
    # on detection order and not on geometry. Kept to each disc's own bounding
    # box, because the full-frame version is O(n_spots x H x W) and a crowded
    # 512-square field holds thousands of spots.
    height, width = image.shape
    best = np.full(image.shape, np.inf)
    labels = np.zeros(image.shape, dtype=np.int32)
    for index, ((cy, cx), radius) in enumerate(zip(centres, radii), start=1):
        radius = max(float(radius), 1.0)
        reach = int(np.ceil(radius))
        r0, r1 = max(0, int(cy) - reach), min(height, int(cy) + reach + 2)
        c0, c1 = max(0, int(cx) - reach), min(width, int(cx) + reach + 2)
        if r0 >= r1 or c0 >= c1:
            continue
        rows, cols = np.ogrid[r0:r1, c0:c1]
        distance = np.hypot(rows - cy, cols - cx)
        window = best[r0:r1, c0:c1]
        closer = (distance <= radius) & (distance < window)
        labels[r0:r1, c0:c1][closer] = index
        window[closer] = distance[closer]

    if inside is not None:
        labels[~inside] = 0
    if settings.clear_border:
        from chisurf.core.roi.segmentation import clear_border

        labels = clear_border(labels)

    # Keyed by the label a blob was painted with, so the filtering below can
    # drop rows and keep the sigmas aligned.
    return labels, {"spot.sigma": {index: float(s) for index, s in enumerate(sigmas, 1)}}


def _filter(labels, extra, settings: SpotFinderSettings, shape):
    """Drop regions outside the area limits, keeping any extra columns aligned."""
    labels = np.asarray(labels)
    if labels.max() == 0:
        return labels, {}

    counts = np.bincount(labels.ravel())
    keep = np.ones(counts.size, dtype=bool)
    keep[0] = False
    keep &= counts >= max(1, int(settings.min_area))
    if settings.max_area > 0:
        keep &= counts <= int(settings.max_area)

    if not keep[1:].all():
        labels = np.where(keep[labels], labels, 0)

    surviving = [index for index in range(1, counts.size) if keep[index]]
    out: dict = {}
    for name, by_label in (extra or {}).items():
        out[name] = np.asarray(
            [by_label.get(index, float("nan")) for index in surviving], dtype=float
        )
    return labels, out


def detect_from_file(path: str, settings: SpotFinderSettings, *,
                     channels: Sequence[int] | None = None,
                     frame: int = -1) -> SpotFinderResult:
    """Load an image or photon file and detect in it.

    Parameters
    ----------
    path : str
        A TIFF stack, or a TTTR imaging file (PTU/HT3) which is reconstructed
        into a CLSM intensity image.
    settings : SpotFinderSettings
        Detection settings.
    channels : sequence of int, optional
        Routing channels for a photon file. Defaults to every channel present.
    frame : int, optional
        Frame to detect in; ``-1`` sums every frame, which is what a
        single-molecule field wants and a moving sample does not.

    Returns
    -------
    SpotFinderResult
    """
    image = load_intensity(path, channels=channels, frame=frame)
    return detect(image, settings)


def load_intensity(path: str, *, channels: Sequence[int] | None = None,
                   frame: int = -1) -> np.ndarray:
    """Return the 2-D intensity image of an imaging file.

    Parameters
    ----------
    path : str
        TIFF stack or TTTR imaging file.
    channels : sequence of int, optional
        Routing channels for a photon file.
    frame : int, optional
        Frame index, or ``-1`` to sum over frames.

    Returns
    -------
    numpy.ndarray
        2-D image.
    """
    from pathlib import Path

    suffix = Path(path).suffix.lower()
    if suffix in (".tif", ".tiff"):
        from chisurf.core.fio.image import imread

        data = np.asarray(imread(path), dtype=float)
    else:
        import tttrlib

        tttr = tttrlib.TTTR(str(path))
        if channels is None:
            channels = sorted({int(c) for c in np.asarray(tttr.routing_channels)})
        clsm = tttrlib.CLSMImage(tttr, channels=list(channels), fill=True)
        data = np.asarray(clsm.intensity, dtype=float)

    while data.ndim > 3:
        data = data.sum(axis=0)
    if data.ndim == 3:
        data = data.sum(axis=0) if frame < 0 else data[int(frame)]
    return data
