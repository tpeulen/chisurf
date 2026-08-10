"""Qt-free core for molecule-wise MLE lifetime analysis of TTTR imaging data.

Segments individual molecules from a confocal (CLSM) intensity image, builds a
polarisation-resolved micro-time histogram ("VV/VH" layout) per molecule, and
fits a single fluorescence lifetime + anisotropy per molecule by Poisson maximum
likelihood through the shared :class:`chisurf.core.fluorescence.mle.Fit2x`
harness (tttrlib ``Fit23``, the Maus-2001 ``2I*`` estimator).

This module contains no Qt and no ``click``: it is the single computational core
shared by the ``region_mle`` GUI, its RPC backend service, and its CLI, and it
is directly testable headlessly from a TTTR image or a *simulated* CLSM image
(see :mod:`test.test_region_mle_core`).  Unlike the previous monolithic script
it returns data (a :class:`RegionMleResult`) instead of writing plots/TSVs —
persisting outputs is the caller's job.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from chisurf.core.datastore import (
    as_store,
    column_names,
    column_values,
    row_count,
    store_from_arrays,
    store_from_rows,
    take_columns,
)
from chisurf.core.fluorescence.mle import (
    Fit2x,
    Fit2xModel,
    Fit2xSettings,
    assemble_vv_vh,
    interpolate_shift,
)

#: Callback signature ``(index, n_molecules)`` for per-molecule progress.
ProgressCallback = Callable[[int, int], None]


@dataclasses.dataclass
class RegionMleSettings:
    """Settings for a molecule-wise MLE lifetime fit.

    The detector channels are split even/odd into the parallel (VV) and
    perpendicular (VH) detection channels of the VV/VH layout every ``fit2x``
    estimator expects (``detector_chs[0::2]`` = parallel, ``detector_chs[1::2]``
    = perpendicular); a single channel is used for both.

    Parameters
    ----------
    detector_chs : sequence of int
        TTTR routing channels of the imaging detector(s).
    micro_time_range : tuple of int
        Fit window ``(start, stop)`` on the *binned* micro-time axis.
    micro_time_binning : int
        Integer down-binning applied to the micro-time axis before fitting.
    irf : numpy.ndarray, optional
        Instrument-response histogram in VV/VH layout, length
        ``2 * (stop - start)``.  When ``None`` it must be supplied by the file
        loader (:func:`fit_regions_from_files`).
    background : numpy.ndarray, optional
        Background histogram in VV/VH layout (same length as ``irf``).
    g_factor : float, optional
        Polarisation ``G`` factor (VV/VH detection-efficiency ratio).
    normalize_counts : int, optional
        VV/VH normalisation mode (``0`` none, ``1`` average rate, ``2`` per
        channel to unit area, ``3`` by acquisition time).
    threshold : float, optional
        Fraction of the per-channel maximum below which VV/VH bins are zeroed
        (``<= 0`` disables).
    tau, gamma, r0, rho : float
        Initial values for the ``Fit23`` parameters ``[tau, gamma, r0, rho]``.
    fix_tau, fix_gamma, fix_r0, fix_rho : bool
        Whether each parameter is held fixed during optimisation.
    l1, l2 : float, optional
        Polarisation mixing corrections of the objective.
    p2s_twoIstar : bool, optional
        Optimise ``P + 2S`` instead of ``P`` and ``S`` individually.
    soft_bifl_scatter : bool, optional
        Reduce ``Istar`` by the background contribution ("soft" BIFL scatter).
    regions : str, pathlib.Path, numpy.ndarray or sequence of ROI, optional
        Where the regions come from. A container path (or any file beside one)
        reads the label raster the spot finder wrote; a 2-D integer array is a
        label image directly; a list of regions is rasterised. **This tool does
        not segment.** Finding the regions is the spot finder's job, and doing
        it here as well is how the preview a user tunes stops being what gets
        fitted.
    region_set : str, optional
        Which detection in the container, when it holds more than one.
    min_photons : int, optional
        Molecules with fewer than this many photons in the fit window are not
        fitted (they yield NaN parameters).
    roi : ROI or dict, optional
        Region of the frame to look for molecules in — a
        :class:`chisurf.core.roi.ROI` or its serialised form (so it survives the
        trip through RPC). Everything outside is neither segmented nor counted
        as background, which is what confines an analysis to one cell, one
        illuminated patch, or a field with the bright edge cropped off.
    """

    detector_chs: Sequence[int] = (0, 1)
    micro_time_range: tuple[int, int] = (0, 256)
    micro_time_binning: int = 1

    irf: np.ndarray | None = None
    background: np.ndarray | None = None
    g_factor: float = 1.0
    #: When True (the default) and no IRF is supplied, the G-factor is estimated
    #: from the IRF tail. Set False to keep a G-factor supplied from the shared
    #: detector setup / calibration instead of overwriting it.
    auto_g_factor: bool = True

    normalize_counts: int = 0
    threshold: float = -1.0

    tau: float = 2.0
    gamma: float = 0.0
    r0: float = 0.38
    rho: float = 1.0
    fix_tau: bool = False
    fix_gamma: bool = False
    fix_r0: bool = True
    fix_rho: bool = False

    l1: float = 0.0
    l2: float = 0.0
    p2s_twoIstar: bool = True
    soft_bifl_scatter: bool = False

    regions: Any = None
    region_set: str = "spots"
    min_photons: int = 1
    roi: Any = None

    def analysis_roi(self):
        """Return :attr:`roi` as a :class:`chisurf.core.roi.ROI`, or ``None``.

        Returns
        -------
        chisurf.core.roi.ROI or None
            The region, rebuilt from its serialised form when the settings came
            over RPC.
        """
        from chisurf.core.roi import as_roi

        return as_roi(self.roi)

    @property
    def window(self) -> int:
        """Number of (binned) micro-time channels per detection channel."""
        return int(self.micro_time_range[1] - self.micro_time_range[0])

    def channel_groups(self) -> tuple[list[int], list[int]]:
        """Return the ``(parallel, perpendicular)`` channel lists."""
        chs = list(self.detector_chs)
        if len(chs) >= 2:
            return chs[0::2], chs[1::2]
        return chs, chs


def with_source_column(table, source) -> Any:
    """Return *table* with a leading ``source_ptu`` column naming its file.

    First, not appended: the joint TSV is read back by column order as well as
    by name, and this is what ``DataFrame.insert(0, ...)`` used to guarantee.

    Parameters
    ----------
    table : tttrlib.DataStore, pandas.DataFrame or mapping of str to array
        One row per molecule.
    source : path-like
        The imaging file the molecules came from.

    Returns
    -------
    tttrlib.DataStore
    """
    # Through the frame boundary: the docstring accepts a frame and `as_store`
    # refuses one, so the conversion belongs here rather than in the caller.
    from chisurf.core.fio.fluorescence.burst_container import as_table

    table = as_store(as_table(table))
    names = column_names(table)
    return take_columns(
        store_from_arrays({
            "source_ptu": np.full(row_count(table), str(source)),
            **{name: column_values(table, i) for i, name in enumerate(names)},
        }),
        ["source_ptu", *names],
    )


@dataclasses.dataclass
class RegionMleResult:
    """Result of a molecule-wise MLE lifetime analysis.

    Attributes
    ----------
    dataframe : tttrlib.DataStore
        One row per segmented molecule with region properties (centroid, area,
        eccentricity, ...) and fit parameters (``tau``, ``gamma``, ``r0``,
        ``rho``, ``2I*``, photon counts).
    intensity_image : numpy.ndarray
        The 2-D total-intensity image the molecules were segmented from.
    label_image : numpy.ndarray
        The integer watershed label image (0 = background).
    centroids : numpy.ndarray
        ``(n_molecules, 2)`` array of ``(row, col)`` molecule centroids.
    vv_vh_vectors : list of numpy.ndarray
        Per-molecule VV/VH decay histograms (only when ``keep_curves=True``).
    model_curves : list of numpy.ndarray
        Per-molecule fitted model histograms (only when ``keep_curves=True``).
    n_molecules : int
        Number of molecules fitted (rows in ``dataframe``).
    """

    dataframe: Any
    intensity_image: np.ndarray
    label_image: np.ndarray
    centroids: np.ndarray
    vv_vh_vectors: list[np.ndarray] = dataclasses.field(default_factory=list)
    model_curves: list[np.ndarray] = dataclasses.field(default_factory=list)
    #: The analysis region the molecules were searched in, if one was set.
    analysis_roi: Any = None

    @property
    def n_molecules(self) -> int:
        """Number of segmented and fitted molecules."""
        return row_count(self.dataframe)

    def molecule_rois(self, crop: bool = True) -> list:
        """Return each segmented molecule as a region of interest.

        The watershed labels are ChiSurf's other notion of a region, so this
        exposes them as the shared :class:`chisurf.core.roi.ROI` type. A
        molecule can then be gated against, combined with other regions,
        rasterised onto a different image, or stored — the same operations any
        drawn region supports.

        Parameters
        ----------
        crop : bool
            Store each region cropped to its bounding box (cheap for many small
            molecules) rather than as a full-frame mask.

        Returns
        -------
        list of chisurf.core.roi.MaskROI
            One region per molecule, named after its label value.
        """
        from chisurf.core.roi import labels_to_rois

        return labels_to_rois(self.label_image, crop=crop)

    def foreground_roi(self):
        """Return every segmented molecule as one region.

        Returns
        -------
        chisurf.core.roi.MaskROI
            The union of all labels — the signal-bearing part of the frame.
        """
        from chisurf.core.roi import MaskROI

        return MaskROI(self.label_image > 0, name="foreground")

    def background_roi(self, margin: int = 2):
        """Return the part of the frame that holds no molecule.

        The complement of the foreground is not a usable background: the pixels
        just outside a molecule still carry its point-spread-function tail, and
        including them biases the background rate upward. *margin* dilates the
        foreground before taking the complement, which is the standard local-
        background construction (and what PAM's MIA does with its rings).

        Parameters
        ----------
        margin : int
            Pixels of clearance to leave around every molecule. ``0`` takes the
            plain complement.

        Returns
        -------
        chisurf.core.roi.MaskROI
            The background region, further restricted to the analysis region
            when one was set.
        """
        from scipy import ndimage as ndi

        from chisurf.core.roi import MaskROI

        occupied = self.label_image > 0
        if margin > 0:
            occupied = ndi.binary_dilation(occupied, iterations=int(margin))
        background = ~occupied
        if self.analysis_roi is not None:
            background &= self.analysis_roi.to_mask(
                self.intensity_image.shape, image=self.intensity_image
            )
        return MaskROI(background, name="background")

    def background_rate(self, margin: int = 2) -> float:
        """Return the mean photon count per background pixel.

        The number to compare a molecule's brightness against, and the one that
        says whether a segmentation threshold was set sensibly.

        Parameters
        ----------
        margin : int
            Clearance around each molecule, as for :meth:`background_roi`.

        Returns
        -------
        float
            Mean intensity over the background region; ``nan`` if there is none.
        """
        props = self.background_roi(margin).properties(
            self.intensity_image.shape, image=self.intensity_image
        )
        return float("nan") if props is None else props.intensity_mean

    def region_properties(self):
        """Return the full region measurements of every molecule.

        The per-molecule table carries the handful of shape columns the fit
        report needs; this gives the complete set (hull, moments, Euler number,
        intensity statistics) for anything else.

        Returns
        -------
        list of chisurf.core.roi.RegionProperties
            One measurement set per molecule, in label order.
        """
        from chisurf.core.roi import regionprops

        return regionprops(self.label_image, self.intensity_image)


# ---------------------------------------------------------------------------
# Regions in, not regions found
# ---------------------------------------------------------------------------
def resolve_labels(settings: RegionMleSettings, shape) -> np.ndarray:
    """Return the label image this fit will use.

    This tool does not segment. It reads the regions somebody else found — the
    spot finder writing into the measurement's container, a saved label image,
    or regions handed over in memory — because a fit that derives its own
    regions cannot be shown what it is about to fit. That was the previous
    design: ``segmentation_preview()`` returned exactly the labels the fit
    would use, and the fit ignored them and segmented a second time, agreeing
    only for as long as every setting reached both paths.

    Parameters
    ----------
    settings : RegionMleSettings
        ``settings.regions`` is a container path, a label array, or regions.
    shape : tuple of int
        Shape of the image the regions belong to; a region given as geometry is
        rasterised onto it.

    Returns
    -------
    numpy.ndarray
        ``int32`` label image, ``0`` background.

    Raises
    ------
    ValueError
        If no regions were given, naming the spot finder — a fit with nothing
        to fit is a missing step, not an empty result.
    """
    source = settings.regions
    if source is None:
        raise ValueError(
            "no regions to fit: run the spot finder first (spot-finder detect), "
            "or set settings.regions to a container, a label image, or a list "
            "of regions"
        )

    if isinstance(source, np.ndarray):
        labels = np.asarray(source)
    elif isinstance(source, (str, Path)):
        labels = _labels_from_path(source, settings.region_set)
    else:
        # A sequence of regions: rasterise in order, later regions winning any
        # overlap, which is the same rule a label image already encodes.
        from chisurf.core.roi import as_roi

        labels = np.zeros(shape, dtype=np.int32)
        for index, item in enumerate(source, start=1):
            mask = as_roi(item).to_mask(shape)
            labels[mask] = index

    if labels.shape != tuple(shape):
        raise ValueError(
            f"the regions are {labels.shape} and the image is {tuple(shape)}; "
            "they are not the same field"
        )
    return np.ascontiguousarray(labels, dtype=np.int32)


def _labels_from_path(source, region_set: str) -> np.ndarray:
    """Read a label image from a container's detection, or from an image file."""
    from chisurf.core.fio.fluorescence.region_container import (
        list_region_sets,
        read_regions,
    )

    available = list_region_sets(source)
    if available:
        name = region_set if region_set in available else available[0]
        return np.asarray(read_regions(source, name=name).labels)

    # Not a container, or one holding no detection: a saved label image, a mask
    # or a region JSON, through the reader that already accepts all three.
    from chisurf.core.roi.io import load_regions

    path = Path(source)
    if path.suffix.lower() in (".tif", ".tiff"):
        from chisurf.core.fio.image import imread

        return np.asarray(imread(path))
    regions = load_regions(str(path), crop=False)
    if not regions:
        raise ValueError(f"{source} holds no regions")
    raise ValueError(
        f"{source} holds regions but not the image they belong to; pass them "
        "as settings.regions=[...] so they can be rasterised onto the frame"
    )


def _confine(labels, roi, intensity) -> np.ndarray:
    """Drop the parts of *labels* outside *roi*, renumbering what survives.

    The analysis region still applies — it confines *which of the regions found*
    are fitted — but it no longer sets a threshold, because nothing here
    thresholds. A region straddling the boundary is kept only where it is
    inside, and the renumbering is what stops a dropped label leaving a row that
    owns no pixel.
    """
    from chisurf.core.roi.segmentation import relabel_sequential

    inside = roi.to_mask(np.asarray(labels).shape, image=intensity)
    confined = np.where(inside, labels, 0)
    confined, _forward, _inverse = relabel_sequential(confined)
    return confined.astype(np.int32)


def region_photon_indices(clsm, labels) -> list[np.ndarray]:
    """Return the TTTR indices of every region's pixels, in label order.

    The seam between the two halves of what used to be one tool: regions are
    imaging, photons are spectroscopy, and this is the sentence that joins them.
    It was an inline double loop over ``prop.coords``, per region, per pixel.

    Parameters
    ----------
    clsm : tttrlib.CLSMImage
        The reconstructed image, filled, whose pixels carry their photons.
    labels : numpy.ndarray
        ``int32`` label image, contiguous from 1.

    Returns
    -------
    list of numpy.ndarray
        One index array per label, in label order.
    """
    labels = np.asarray(labels)
    n = int(labels.max())
    buckets: list[list] = [[] for _ in range(n)]
    frame = clsm[0]
    # One pass over the occupied pixels rather than one pass per region: the
    # per-region form re-walked the frame for every molecule, and a crowded
    # field holds thousands.
    rows, cols = np.nonzero(labels)
    for r, c in zip(rows.tolist(), cols.tolist()):
        buckets[labels[r, c] - 1].extend(frame[r][c].tttr_indices)
    return [np.asarray(b, dtype=np.int64) for b in buckets]


def _shape_columns(prop) -> dict:
    """Return the per-molecule shape columns of the result table.

    Parameters
    ----------
    prop : chisurf.core.roi.RegionProperties
        Measurements of one segmented molecule.

    Returns
    -------
    dict
        The morphology and brightness columns, shared by the fitted table and
        the un-fitted segmentation preview so the two stay in step.
    """
    row, col = prop.centroid
    columns = {
        "label": int(prop.label),
        "centroid_row": float(row),
        "centroid_col": float(col),
        "area": int(prop.area),
        "perimeter": float(prop.perimeter),
        "circularity": float(prop.circularity),
        "eccentricity": float(prop.eccentricity),
        "solidity": float(prop.solidity),
    }
    if prop.image_intensity is not None:
        columns["intensity_mean"] = float(prop.intensity_mean)
        columns["intensity_max"] = float(prop.intensity_max)
    return columns


def region_preview(
    intensity: np.ndarray, settings: RegionMleSettings
) -> RegionMleResult:
    """Measure the regions to be fitted, without fitting them.

    The cheap half of :func:`fit_regions`: what was found, how big, how bright,
    and what the background rate around it is — before committing to a full MLE
    run. It resolves the regions **the same way the fit does**, through
    :func:`resolve_labels`, which is the whole point: what is previewed is what
    is fitted, and there is no second segmentation to disagree with it.

    Parameters
    ----------
    intensity : numpy.ndarray
        2-D total-intensity image.
    settings : RegionMleSettings
        The region source; the estimator settings are ignored.

    Returns
    -------
    RegionMleResult
        A result with the labels, the region measurements and a ``tau`` column
        of NaN, browsable exactly like a fitted one.
    """
    from chisurf.core.roi import regionprops

    analysis_roi = settings.analysis_roi()
    labels = resolve_labels(settings, intensity.shape)
    if analysis_roi is not None:
        labels = _confine(labels, analysis_roi, intensity)
    props = regionprops(labels, intensity)
    rows = [{**_shape_columns(p), "tau": float("nan")} for p in props]
    centroids = [p.centroid for p in props]
    return RegionMleResult(
        dataframe=store_from_rows(rows),
        intensity_image=intensity,
        label_image=labels,
        centroids=np.asarray(centroids, dtype=float).reshape(-1, 2),
        analysis_roi=analysis_roi,
    )


# ---------------------------------------------------------------------------
# IRF preparation (Qt-free, no plotting)
# ---------------------------------------------------------------------------
def _microtime_component(
    tttr: Any,
    channels: Sequence[int],
    micro_time_range: tuple[int, int],
    binning: int,
) -> np.ndarray:
    """Binned micro-time histogram for a channel subset, sliced to the window.

    The length is **asked for**, not inferred. ``minlength=-1`` lets the file's
    header decide, and a header that under-reports its micro-time channels —
    a simulated stream says 1, and so does the PTU written from one — then
    yields a histogram shorter than the window, which slices down to a couple
    of bins. The caller knows the window; saying so is what makes this
    independent of whether the header was written properly.
    """
    start, stop = micro_time_range
    raw_start, raw_stop = start * binning, stop * binning
    mt = tttr.micro_times
    ch = tttr.routing_channels
    mask = (mt >= raw_start) & (mt <= raw_stop) & np.isin(ch, list(channels))
    sub = tttr[np.where(mask)[0]]
    hist, _ = sub.get_microtime_histogram(binning, minlength=int(raw_stop))
    hist = np.asarray(hist, dtype=np.float64)
    if hist.size < stop:
        # Still short (an empty channel gives an empty histogram): pad, so the
        # VV/VH layout keeps its shape and a missing detector reads as zeros
        # rather than as a differently-sized array nothing downstream expects.
        hist = np.pad(hist, (0, stop - hist.size))
    return hist[start:stop]




def build_irf_vv_vh(
    irf_tttr: Any,
    *,
    detector_chs: Sequence[int],
    micro_time_range: tuple[int, int],
    micro_time_binning: int = 1,
    shift_sp: float = 0.0,
    shift_ss: float = 0.0,
    irf_threshold_fraction: float = 0.08,
) -> tuple[np.ndarray, np.ndarray]:
    """Build the parallel/perpendicular IRF VV/VH histogram from an IRF TTTR.

    Parameters
    ----------
    irf_tttr : tttrlib.TTTR
        Instrument-response measurement.
    detector_chs : sequence of int
        Detector channels (split even/odd into parallel/perpendicular).
    micro_time_range : tuple of int
        Fit window on the binned micro-time axis.
    micro_time_binning : int, optional
        Micro-time down-binning factor.
    shift_sp, shift_ss : float, optional
        Circular shifts applied to the parallel / perpendicular IRF components.
    irf_threshold_fraction : float, optional
        IRF bins below this fraction of the IRF maximum are zeroed (denoising).

    Returns
    -------
    irf_full : numpy.ndarray
        Thresholded, area-normalised IRF in VV/VH layout (used as the IRF).
    raw_irf : numpy.ndarray
        Un-thresholded IRF in VV/VH layout (used as the ``fit2x`` background).
    """
    chs = list(detector_chs)
    sp_chs, ss_chs = (chs[0::2], chs[1::2]) if len(chs) >= 2 else (chs, chs)

    sp = _microtime_component(irf_tttr, sp_chs, micro_time_range, micro_time_binning)
    ss = _microtime_component(irf_tttr, ss_chs, micro_time_range, micro_time_binning)
    sp = interpolate_shift(sp, shift_sp)
    ss = interpolate_shift(ss, shift_ss)
    sp = sp / sp.sum() if sp.sum() > 0 else sp
    ss = ss / ss.sum() if ss.sum() > 0 else ss

    raw_irf = np.hstack([sp, ss])
    irf_full = raw_irf.copy()
    if irf_full.max() > 0:
        irf_full[irf_full < irf_threshold_fraction * irf_full.max()] = 0.0
        if irf_full.sum() > 0:
            irf_full = irf_full / irf_full.sum()
    return irf_full, raw_irf


def compute_g_factor(
    irf_tttr: Any,
    detector_chs: Sequence[int],
    micro_time_range: tuple[int, int],
    micro_time_binning: int = 1,
    tail_fraction: float = 0.8,
) -> float:
    """Estimate the polarisation ``G`` factor from the IRF tail (∑P / ∑S)."""
    chs = list(detector_chs)
    sp_chs, ss_chs = ([chs[0]], [chs[1]]) if len(chs) >= 2 else (chs, chs)
    p = _microtime_component(irf_tttr, sp_chs, micro_time_range, micro_time_binning)
    s = _microtime_component(irf_tttr, ss_chs, micro_time_range, micro_time_binning)
    tail = int(np.floor(tail_fraction * len(p)))
    sum_s = float(s[tail:].sum())
    return float(p[tail:].sum() / sum_s) if sum_s > 0 else 1.0


# ---------------------------------------------------------------------------
# Per-molecule VV/VH + fit
# ---------------------------------------------------------------------------
def _molecule_vv_vh(
    micro_times: np.ndarray,
    routing: np.ndarray,
    indices: np.ndarray,
    settings: RegionMleSettings,
) -> tuple[np.ndarray, int, int]:
    """Build one molecule's VV/VH histogram from its photon indices.

    Returns ``(vv_vh, n_parallel, n_perpendicular)``.
    """
    start, stop = settings.micro_time_range
    binning = max(1, int(settings.micro_time_binning))
    window = stop - start
    sp_chs, ss_chs = settings.channel_groups()

    mt = micro_times[indices] // binning
    ch = routing[indices]
    n_ch = int(mt.max()) + 1 if mt.size else stop

    def hist(sel_chs):
        sel = np.isin(ch, sel_chs)
        if not sel.any():
            return np.zeros(window, dtype=np.float64)
        h = np.bincount(mt[sel], minlength=max(n_ch, stop))[start:stop]
        return h.astype(np.float64)

    cp = hist(sp_chs)
    cs = hist(ss_chs)
    n_p, n_s = int(cp.sum()), int(cs.sum())

    if settings.threshold > 0:
        for arr in (cp, cs):
            if arr.max() > 0:
                arr[arr < settings.threshold * arr.max()] = 0.0

    if settings.normalize_counts == 1:
        ct = (cp.sum() + cs.sum()) / 2.0
        if ct > 0:
            cp, cs = cp / ct, cs / ct
    elif settings.normalize_counts == 2:
        if cp.sum() > 0:
            cp = cp / cp.sum()
        if cs.sum() > 0:
            cs = cs / cs.sum()

    return assemble_vv_vh(cp, cs), n_p, n_s


def _initial_and_fixed(s: RegionMleSettings) -> tuple[np.ndarray, np.ndarray]:
    x0 = np.array([s.tau, s.gamma, s.r0, s.rho], dtype=np.float64)
    fixed = np.array(
        [int(s.fix_tau), int(s.fix_gamma), int(s.fix_r0), int(s.fix_rho)],
        dtype=np.int16,
    )
    return x0, fixed


def fit_regions(
    tttr: Any,
    settings: RegionMleSettings,
    *,
    clsm: Any = None,
    dt: float | None = None,
    period: float | None = None,
    progress: ProgressCallback | None = None,
    keep_curves: bool = False,
) -> RegionMleResult:
    """Segment molecules from a CLSM TTTR image and MLE-fit each lifetime.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        The confocal (CLSM) photon stream to analyse.
    settings : RegionMleSettings
        Segmentation, channel, IRF and estimator settings.  ``settings.irf``
        must be set (see :func:`fit_regions_from_files` for the file path).
    clsm : tttrlib.CLSMImage, optional
        Pre-built confocal image.  When omitted a ``CLSMImage(tttr, channels,
        fill=True)`` is constructed with auto-detected markers (the normal path
        for PTU/HT3 imaging files).  Pass an explicitly-constructed image when
        the markers cannot be auto-detected (e.g. a simulated raster scan).
    dt : float, optional
        Width of one (binned) micro-time channel in nanoseconds.  Derived from
        the TTTR header when omitted.
    period : float, optional
        Excitation period (nanoseconds).  Derived from ``dt * window`` when
        omitted.
    progress : callable, optional
        Called as ``progress(index, n_molecules)`` after each molecule.
    keep_curves : bool, optional
        Also return the per-molecule VV/VH and model histograms.

    Returns
    -------
    RegionMleResult
    """
    import tttrlib

    from chisurf.core.roi import regionprops

    if settings.irf is None:
        raise ValueError("settings.irf must be set (VV/VH IRF); use fit_regions_from_files")
    irf = np.ascontiguousarray(settings.irf, dtype=np.float64)
    if irf.size != 2 * settings.window:
        raise ValueError(
            f"irf length {irf.size} != 2*window (2*{settings.window}={2 * settings.window})"
        )

    binning = max(1, int(settings.micro_time_binning))
    if dt is None:
        dt = float(tttr.header.micro_time_resolution) * 1e9 * binning
    if period is None:
        period = float(dt) * settings.window

    fit2x = Fit2x(
        Fit2xSettings(
            dt=float(dt),
            period=float(period),
            irf=irf,
            background=settings.background,
            g_factor=float(settings.g_factor),
            l1=float(settings.l1),
            l2=float(settings.l2),
            p2s_twoIstar=bool(settings.p2s_twoIstar),
            soft_bifl_scatter=bool(settings.soft_bifl_scatter),
        ),
        model=Fit2xModel.FIT23,
    )
    x0, fixed = _initial_and_fixed(settings)

    if clsm is None:
        clsm = tttrlib.CLSMImage(tttr, channels=list(settings.detector_chs), fill=True)
    intensity = np.asarray(clsm.intensity).sum(axis=0)

    analysis_roi = settings.analysis_roi()
    # Resolved, not derived. The regions were found by whatever found them --
    # the spot finder, a saved label image, a hand-drawn set -- and this fit
    # answers for those and no others.
    labels = resolve_labels(settings, intensity.shape)
    if analysis_roi is not None:
        labels = _confine(labels, analysis_roi, intensity)

    micro_times = tttr.micro_times
    routing = tttr.routing_channels

    props = regionprops(labels, intensity)
    n_props = len(props)
    photon_indices = region_photon_indices(clsm, labels)

    # Pass 1: build each region's VV/VH histogram; drop sub-threshold regions.
    kept: list[tuple] = []  # (prop, vv_vh, n_parallel, n_perpendicular)
    for i, prop in enumerate(props):
        indices = photon_indices[int(prop.label) - 1]
        vv_vh, n_p, n_s = _molecule_vv_vh(micro_times, routing, indices, settings)
        if n_p + n_s >= settings.min_photons:
            kept.append((prop, vv_vh, n_p, n_s))
        if progress is not None:
            progress(i, n_props)

    # Pass 2: fit. When the model curves are not needed, fit the whole batch in one
    # GIL-released C++ call (``fit_many``); otherwise fit per molecule so each
    # realised model histogram can be returned for plotting.
    batch = None
    if kept and not keep_curves:
        matrix = np.vstack([k[1] for k in kept])
        batch = fit2x.fit_many(matrix, initial_values=x0, fixed=fixed)

    rows: list[dict] = []
    centroids: list[tuple[float, float]] = []
    vv_vhs: list[np.ndarray] = []
    curves: list[np.ndarray] = []
    for j, (prop, vv_vh, n_p, n_s) in enumerate(kept):
        if batch is not None:
            tau, gamma, r0, rho, twoistar = (float(v) for v in batch[j])
            r_scatter = r_experimental = float("nan")
            model_curve = None
        else:
            res = fit2x.fit(vv_vh, initial_values=x0, fixed=fixed, include_model=keep_curves)
            tau, gamma, r0, rho = (float(res.x[k]) for k in range(4))
            twoistar = float(res.twoIstar)
            r_scatter, r_experimental = res.r_scatter, res.r_experimental
            model_curve = res.model_curve

        cy, cx = prop.centroid
        wy, wx = prop.centroid_weighted

        rows.append(
            {
                **_shape_columns(prop),
                "centroid_weighted_row": float(wy),
                "centroid_weighted_col": float(wx),
                "n_photons_total": n_p + n_s,
                "n_photons_parallel": n_p,
                "n_photons_perpendicular": n_s,
                "tau": tau,
                "gamma": gamma,
                "r0": r0,
                "rho": rho,
                "r_scatter": r_scatter,
                "r_experimental": r_experimental,
                "2I*": twoistar,
            }
        )
        centroids.append((float(cy), float(cx)))
        if keep_curves:
            vv_vhs.append(vv_vh)
            curves.append(model_curve if model_curve is not None else np.array([]))

    dataframe = store_from_rows(rows)
    return RegionMleResult(
        dataframe=dataframe,
        intensity_image=intensity,
        label_image=labels,
        centroids=np.asarray(centroids, dtype=float).reshape(-1, 2),
        vv_vh_vectors=vv_vhs,
        model_curves=curves,
        analysis_roi=analysis_roi,
    )


def fit_regions_from_files(
    ptu_path: str,
    irf_path: str,
    settings: RegionMleSettings,
    *,
    shift_sp: float = 0.0,
    shift_ss: float = 0.0,
    irf_threshold_fraction: float = 0.08,
    progress: ProgressCallback | None = None,
    keep_curves: bool = False,
) -> RegionMleResult:
    """Load a CLSM image + IRF from disk and run :func:`fit_regions`.

    The IRF VV/VH histogram, background and ``G`` factor are built from
    *irf_path* (unless ``settings.irf`` is already provided).

    Parameters
    ----------
    ptu_path : str
        Path to the confocal (CLSM) TTTR image.
    irf_path : str
        Path to the IRF TTTR measurement.
    settings : RegionMleSettings
        Analysis settings (segmentation, channels, estimator).
    shift_sp, shift_ss : float, optional
        Circular IRF shifts (parallel / perpendicular).
    irf_threshold_fraction : float, optional
        IRF denoising threshold fraction.
    progress : callable, optional
        Progress callback forwarded to :func:`fit_regions`.
    keep_curves : bool, optional
        Keep per-molecule curves in the result.

    Returns
    -------
    RegionMleResult
    """
    import tttrlib

    tttr = tttrlib.TTTR(ptu_path)
    if settings.irf is None:
        irf_tttr = tttrlib.TTTR(irf_path)
        irf_full, raw_irf = build_irf_vv_vh(
            irf_tttr,
            detector_chs=settings.detector_chs,
            micro_time_range=settings.micro_time_range,
            micro_time_binning=settings.micro_time_binning,
            shift_sp=shift_sp,
            shift_ss=shift_ss,
            irf_threshold_fraction=irf_threshold_fraction,
        )
        settings.irf = irf_full
        settings.background = raw_irf
        # Estimate the G-factor from the IRF tail only when the caller has not
        # supplied one from the shared detector setup / anisotropy calibration.
        if settings.auto_g_factor:
            settings.g_factor = compute_g_factor(
                irf_tttr,
                settings.detector_chs,
                settings.micro_time_range,
                settings.micro_time_binning,
            )
    return fit_regions(tttr, settings, progress=progress, keep_curves=keep_curves)
