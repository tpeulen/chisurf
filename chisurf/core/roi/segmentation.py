"""Segmentation primitives: threshold, find seeds, flood, clean up.

Five functions, and between them they are the whole of what the imaging tools
need to turn an intensity image into a label image that
:func:`~chisurf.core.roi.regionprops` can measure:

``gaussian``
    Smooth, so that shot noise does not become a local maximum.
``threshold_otsu``
    Choose the intensity that best separates foreground from background, by
    maximising the between-class variance of a 256-bin histogram.
``clear_border``
    Drop objects that touch the frame edge — they are cut off, so every
    measurement of them is wrong.
``peak_local_max``
    One seed per object, from the local maxima of the distance transform.
``watershed``
    Flood from those seeds to split objects that touch.

The names and signatures are scikit-image's, for the subset that is used, so a
call site ported from it changes by an import line and someone arriving from its
documentation finds the argument they expect. Where a parameter is not
implemented it *raises*; nothing here silently ignores an argument, because a
segmentation that quietly used a different neighbourhood than you asked for is
not something a later assertion would catch.

The watershed is the interesting one, and its behaviour rests on a detail worth
stating: the priority queue is keyed on ``(value, age)``, where age is the order
of entry. That single tie-break does two jobs — a pixel joins the neighbour it
is steepest towards, and a plateau is divided evenly between the markers on
either side of it instead of going wholesale to whichever was queued first.
"""

from __future__ import annotations

from typing import Optional, Union

import numpy as np

__all__ = [
    # thresholding and smoothing
    "gaussian",
    "threshold_otsu",
    "difference_of_gaussians",
    "white_tophat",
    # finding
    "peak_local_max",
    "blob_dog",
    "blob_log",
    "watershed",
    # cleaning up and describing a label image
    "clear_border",
    "remove_small_objects",
    "remove_small_holes",
    "relabel_sequential",
    "expand_labels",
    "find_boundaries",
    "find_contours",
]


# ---------------------------------------------------------------------------
# Smoothing and thresholding
# ---------------------------------------------------------------------------


def gaussian(image, sigma=1.0, *, mode: str = "nearest", cval: float = 0.0,
             truncate: float = 4.0):
    """Gaussian-smooth ``image``.

    Parameters
    ----------
    image : numpy.ndarray
        Input image; converted to float.
    sigma : float or sequence of float
        Standard deviation, per axis if a sequence.
    mode : str
        Edge handling, as :func:`scipy.ndimage.gaussian_filter` spells it.
        ``'nearest'`` — the default here and in scikit-image — extends the edge
        pixel, which is what keeps a bright object at the frame edge from being
        pulled towards zero and dropping below the threshold.
    cval : float
        Fill value for ``mode='constant'``.
    truncate : float
        Kernel radius in standard deviations.

    Returns
    -------
    numpy.ndarray
        The smoothed image, as float.
    """
    from scipy import ndimage

    return ndimage.gaussian_filter(
        np.asarray(image, dtype=float), sigma, mode=mode, cval=cval, truncate=truncate
    )


def threshold_otsu(image=None, nbins: int = 256, *, hist=None) -> float:
    """Return the intensity that best separates ``image`` into two classes.

    Otsu's method: histogram the image, then take the threshold that maximises
    the variance *between* the two classes it produces — equivalently, that
    minimises the variance within them.

    Parameters
    ----------
    image : numpy.ndarray, optional
        Grayscale image. Ignored when ``hist`` is given.
    nbins : int
        Histogram bins. Only meaningful for a float image; an integer image is
        binned on its own values.
    hist : tuple, optional
        ``(counts, bin_centers)`` to use instead of histogramming ``image``.

    Returns
    -------
    float
        The threshold. Pixels *strictly greater* are conventionally foreground.

    Raises
    ------
    ValueError
        If the image holds a single value, where no threshold separates
        anything and the answer would otherwise be silently arbitrary.
    """
    if hist is not None:
        counts, bin_centers = hist
        counts = np.asarray(counts, dtype=np.float64)
        bin_centers = np.asarray(bin_centers, dtype=np.float64)
    else:
        image = np.asarray(image)
        flat = image.reshape(-1)
        if flat.size and flat.min() == flat.max():
            raise ValueError(
                "threshold_otsu is not defined for an image with one value "
                f"({flat.min()}); it has no two classes to separate."
            )
        counts, edges = np.histogram(flat, bins=nbins, range=(flat.min(), flat.max()))
        counts = counts.astype(np.float64)
        bin_centers = (edges[:-1] + edges[1:]) / 2.0

    # Empty leading and trailing bins carry no information and would only shift
    # the index of the maximum; scikit-image trims them for the same reason.
    nonzero = counts > 0
    if nonzero.any():
        start = int(np.argmax(nonzero))
        stop = nonzero.size - int(np.argmax(nonzero[::-1]))
        counts, bin_centers = counts[start:stop], bin_centers[start:stop]

    weight1 = np.cumsum(counts)
    weight2 = np.cumsum(counts[::-1])[::-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        mean1 = np.cumsum(counts * bin_centers) / weight1
        mean2 = (np.cumsum((counts * bin_centers)[::-1]) / weight2[::-1])[::-1]
    # The last entry of class 1 pairs with a class 2 that does not exist, hence
    # the clipped ends.
    variance12 = weight1[:-1] * weight2[1:] * (mean1[:-1] - mean2[1:]) ** 2
    return float(bin_centers[int(np.argmax(variance12))])


# ---------------------------------------------------------------------------
# Cleaning up a label image
# ---------------------------------------------------------------------------


def clear_border(labels, buffer_size: int = 0, bgval: int = 0, mask=None, *, out=None):
    """Remove every object that touches the border of ``labels``.

    An object crossing the frame edge is cut off, so its area, its centroid and
    every shape measurement of it describe the visible fragment rather than the
    object — which is why the convention is to discard it rather than to report
    it with a caveat nobody reads.

    Parameters
    ----------
    labels : numpy.ndarray
        Label image or boolean mask.
    buffer_size : int
        Widen the border by this many pixels.
    bgval : int
        Value written where an object is removed.
    mask : numpy.ndarray, optional
        Boolean image whose ``False`` region is treated as the border, instead
        of the frame edge.
    out : numpy.ndarray, optional
        Write into this array rather than a copy.

    Returns
    -------
    numpy.ndarray
        ``labels`` with the border-touching objects set to ``bgval``.
    """
    from scipy import ndimage

    labels = np.asarray(labels)
    if mask is None and any(buffer_size >= size for size in labels.shape):
        raise ValueError("buffer_size may not be as large as the image")
    if out is None:
        out = labels.copy()

    if mask is not None:
        mask = np.asarray(mask)
        if mask.dtype != bool:
            raise TypeError("mask must be boolean")
        if out.shape != mask.shape:
            raise ValueError(
                f"labels and mask must have the same shape, got {out.shape} and "
                f"{mask.shape}"
            )
        borders = ~mask
    else:
        borders = np.zeros(out.shape, dtype=bool)
        extent = buffer_size + 1
        slices = [slice(None)] * out.ndim
        for axis in range(out.ndim):
            slices[axis] = slice(extent)
            borders[tuple(slices)] = True
            slices[axis] = slice(-extent, None)
            borders[tuple(slices)] = True
            slices[axis] = slice(None)

    # Relabelled first, so that a boolean mask works and so that two objects
    # sharing a label are judged separately.
    connected, count = ndimage.label(out != 0)
    touching = np.unique(connected[borders])
    remove = np.isin(np.arange(count + 1), touching)
    out[remove[connected]] = bgval
    return out


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------


def _ensure_spacing(coordinates, spacing, p_norm, max_out):
    """Keep the first of every group of points closer together than ``spacing``.

    The points arrive brightest-first, so "the first" is "the brightest", which
    is what makes this a peak selection rather than an arbitrary thinning.
    """
    from scipy.spatial import cKDTree, distance

    tree = cKDTree(coordinates)
    candidates_per_point = tree.query_ball_point(coordinates, r=spacing, p=p_norm)
    rejected: set[int] = set()
    accepted = 0
    for index, candidates in enumerate(candidates_per_point):
        if index in rejected:
            continue
        candidates = list(candidates)
        candidates.remove(index)
        # Points at *exactly* `spacing` are kept: the parameter is the minimum
        # allowed separation, not a radius of exclusion.
        distances = distance.cdist(
            [coordinates[index]], coordinates[candidates], "minkowski", p=p_norm
        ).reshape(-1)
        rejected.update(c for c, d in zip(candidates, distances) if d < spacing)
        accepted += 1
        if max_out is not None and accepted >= max_out:
            break

    output = np.delete(coordinates, tuple(rejected), axis=0)
    return output[:max_out] if max_out is not None else output


def _spaced(coordinates, spacing, p_norm, max_out, min_split_size=50, max_split_size=2000):
    """``_ensure_spacing`` in growing batches, to bound the pairwise memory."""
    if not len(coordinates):
        return coordinates
    coordinates = np.atleast_2d(coordinates)
    if min_split_size is None:
        batches = [coordinates]
    else:
        split_at = [min_split_size]
        size = min_split_size
        while len(coordinates) - split_at[-1] > max_split_size:
            size *= 2
            split_at.append(split_at[-1] + min(size, max_split_size))
        batches = np.array_split(coordinates, split_at)

    output = np.zeros((0, coordinates.shape[1]), dtype=coordinates.dtype)
    for batch in batches:
        output = _ensure_spacing(np.vstack([output, batch]), spacing, p_norm, max_out)
        if max_out is not None and len(output) >= max_out:
            break
    return output


def _peak_mask(image, footprint, threshold, mask=None):
    """Boolean image of the pixels that equal their neighbourhood maximum."""
    from scipy import ndimage

    if footprint.size == 1 or image.size == 1:
        return image > threshold

    maxima = ndimage.maximum_filter(image, footprint=footprint, mode="nearest")
    out = image == maxima

    # A flat image is *all* maximum, which is not a set of peaks. The one
    # exception is a single isolated pixel inside a mask: it has no neighbour to
    # tie with, so it is a genuine peak.
    trivial = np.all(out) if mask is None else np.all(out[mask])
    if trivial:
        out[:] = False
        if mask is not None:
            isolated = np.logical_xor(mask, ndimage.binary_opening(mask))
            out[isolated] = True

    out &= image > threshold
    return out


def _zero_border(label, border_width):
    """Zero ``border_width`` pixels along every edge, per axis."""
    for axis, width in enumerate(border_width):
        if width == 0:
            continue
        label[(slice(None),) * axis + (slice(None, width),)] = 0
        label[(slice(None),) * axis + (slice(-width, None),)] = 0
    return label


def _border_width(image, min_distance, exclude_border):
    """Resolve ``exclude_border`` to one width per axis."""
    if isinstance(exclude_border, bool):
        return (min_distance if exclude_border else 0,) * image.ndim
    if isinstance(exclude_border, int):
        if exclude_border < 0:
            raise ValueError("exclude_border cannot be negative")
        return (exclude_border,) * image.ndim
    if isinstance(exclude_border, tuple):
        if len(exclude_border) != image.ndim:
            raise ValueError(
                "exclude_border must have one entry per image dimension"
            )
        for width in exclude_border:
            if not isinstance(width, int) or width < 0:
                raise ValueError("exclude_border entries must be non-negative ints")
        return exclude_border
    raise TypeError("exclude_border must be a bool, an int, or a tuple of ints")


def peak_local_max(
    image,
    min_distance: int = 1,
    threshold_abs: Optional[float] = None,
    threshold_rel: Optional[float] = None,
    exclude_border: Union[bool, int, tuple] = True,
    num_peaks=np.inf,
    footprint=None,
    labels=None,
    num_peaks_per_label=np.inf,
    p_norm: float = np.inf,
):
    """Return the coordinates of the local maxima of ``image``.

    Peaks are pixels that equal the maximum of their neighbourhood — a square of
    side ``2 * min_distance + 1`` unless ``footprint`` says otherwise — and that
    are separated from each other by at least ``min_distance``.

    Parameters
    ----------
    image : numpy.ndarray
        Image to search. For seeding a watershed this is the distance transform
        of the mask, whose maxima are the object centres.
    min_distance : int
        Minimum separation between returned peaks.
    threshold_abs : float, optional
        Minimum peak intensity. Defaults to the image minimum.
    threshold_rel : float, optional
        Minimum peak intensity as a fraction of the image maximum; the larger of
        the two thresholds wins.
    exclude_border : bool, int or tuple
        Width of the frame margin in which peaks are ignored. ``True`` means
        ``min_distance``.
    num_peaks : int
        Keep only this many, brightest first.
    footprint : numpy.ndarray, optional
        Boolean neighbourhood, instead of the square implied by
        ``min_distance``.
    labels : numpy.ndarray, optional
        Search each labelled region separately, so that one bright object cannot
        suppress the peak of a dim neighbour.
    num_peaks_per_label : int
        Keep only this many peaks per label.
    p_norm : float
        Minkowski norm for the separation. ``inf`` is the Chebyshev distance.

    Returns
    -------
    numpy.ndarray
        ``(n_peaks, image.ndim)`` integer coordinates, brightest first.
    """
    from scipy import ndimage

    image = np.asarray(image)
    if image.size == 0:
        return np.empty((0, image.ndim), dtype=int)

    border_width = _border_width(image, min_distance, exclude_border)
    threshold = _threshold(image, threshold_abs, threshold_rel)

    if footprint is None:
        size = 2 * min_distance + 1
        footprint = np.ones((size,) * image.ndim, dtype=bool)
    else:
        footprint = np.asarray(footprint, dtype=bool)

    if labels is None:
        mask = _zero_border(_peak_mask(image, footprint, threshold), border_width)
        return _brightest(image, mask, num_peaks, min_distance, p_norm)

    labels = np.asarray(labels)
    bounded = _zero_border(labels.astype(int, casting="safe"), border_width)
    if np.issubdtype(image.dtype, np.floating):
        background = np.finfo(image.dtype).min
    else:
        background = np.iinfo(image.dtype).min

    per_label = []
    for index, region in enumerate(ndimage.find_objects(bounded)):
        if region is None:
            continue
        inside = labels[region] == index + 1
        window = image[region].copy()
        # Outside the label the value must not be able to win a maximum, or a
        # neighbouring object would suppress this one's peak.
        window[~inside] = background
        mask = _peak_mask(window, footprint, threshold, inside)
        coordinates = _brightest(
            window, mask, num_peaks_per_label, min_distance, p_norm
        )
        for axis, piece in enumerate(region):
            coordinates[:, axis] += piece.start
        per_label.append(coordinates)

    if per_label:
        coordinates = np.vstack(per_label)
    else:
        coordinates = np.empty((0, image.ndim), dtype=int)

    if len(coordinates) > num_peaks:
        selected = np.zeros(image.shape, dtype=bool)
        selected[tuple(coordinates.T)] = True
        coordinates = _brightest(image, selected, num_peaks, min_distance, p_norm)
    return coordinates


def _threshold(image, threshold_abs, threshold_rel):
    """Resolve the absolute and relative thresholds to one value."""
    threshold = threshold_abs if threshold_abs is not None else image.min()
    if threshold_rel is not None:
        threshold = max(threshold, threshold_rel * image.max())
    return threshold


def _brightest(image, mask, num_peaks, min_distance, p_norm):
    """Return the masked coordinates, brightest first and at least ``min_distance`` apart."""
    coordinates = np.nonzero(mask)
    intensities = image[coordinates]
    # A stable sort so that equally bright peaks keep image order, which is what
    # makes the result reproducible rather than dependent on the sort algorithm.
    order = np.argsort(-intensities, kind="stable")
    coordinates = np.transpose(coordinates)[order]

    max_out = int(num_peaks) if np.isfinite(num_peaks) else None
    if min_distance > 1:
        coordinates = _spaced(coordinates, min_distance, p_norm, max_out)
    if len(coordinates) > num_peaks:
        coordinates = coordinates[: int(num_peaks)]
    return coordinates


# ---------------------------------------------------------------------------
# Watershed
# ---------------------------------------------------------------------------


def _flood(image, marker_locations, offsets, mask, output):
    """Flood the image from the markers, cheapest pixel first.

    A binary heap ordered on ``(value, age)``. The value is the image at the
    pixel, raised to at least the value of the pixel it was reached from — a
    basin cannot be entered more cheaply than it was left, which stops one
    marker taking a basin from an equally good rival merely because it spilled
    in one step earlier. The age is the order of entry, and it is what divides a
    plateau evenly between the markers on either side of it rather than giving
    it wholesale to whichever arrived first.

    ``mask`` must be zero on every border pixel: the neighbour offsets are
    applied without bounds checks, and that is what keeps them in range.
    """
    capacity = 8 * marker_locations.shape[0] + 64
    heap_value = np.empty(capacity, dtype=np.float64)
    heap_age = np.empty(capacity, dtype=np.int64)
    heap_index = np.empty(capacity, dtype=np.int64)
    heap_source = np.empty(capacity, dtype=np.int64)
    size = 0

    for i in range(marker_locations.shape[0]):
        index = marker_locations[i]
        if size == heap_value.shape[0]:
            heap_value, heap_age, heap_index, heap_source = _grow(
                heap_value, heap_age, heap_index, heap_source
            )
        # sift up
        position = size
        value = image[index]
        age = 0
        while position > 0:
            parent = (position - 1) // 2
            if heap_value[parent] < value or (
                heap_value[parent] == value and heap_age[parent] <= age
            ):
                break
            heap_value[position] = heap_value[parent]
            heap_age[position] = heap_age[parent]
            heap_index[position] = heap_index[parent]
            heap_source[position] = heap_source[parent]
            position = parent
        heap_value[position] = value
        heap_age[position] = age
        heap_index[position] = index
        heap_source[position] = index
        size += 1

    age_counter = 1
    while size > 0:
        value = heap_value[0]
        index = heap_index[0]
        source = heap_source[0]
        # sift down the last element into the hole at the root
        size -= 1
        last_value = heap_value[size]
        last_age = heap_age[size]
        last_index = heap_index[size]
        last_source = heap_source[size]
        position = 0
        while True:
            child = 2 * position + 1
            if child >= size:
                break
            if child + 1 < size and (
                heap_value[child + 1] < heap_value[child]
                or (
                    heap_value[child + 1] == heap_value[child]
                    and heap_age[child + 1] < heap_age[child]
                )
            ):
                child += 1
            if last_value < heap_value[child] or (
                last_value == heap_value[child] and last_age <= heap_age[child]
            ):
                break
            heap_value[position] = heap_value[child]
            heap_age[position] = heap_age[child]
            heap_index[position] = heap_index[child]
            heap_source[position] = heap_source[child]
            position = child
        if size > 0:
            heap_value[position] = last_value
            heap_age[position] = last_age
            heap_index[position] = last_index
            heap_source[position] = last_source

        for k in range(offsets.shape[0]):
            neighbour = index + offsets[k]
            if not mask[neighbour]:
                continue
            if output[neighbour] != 0:
                continue
            age_counter += 1
            neighbour_value = image[neighbour]
            if neighbour_value < value:
                neighbour_value = value
            # Labelled at push time. In this, the plain watershed, a pixel can
            # never be reached more cheaply later, so waiting until it comes off
            # the heap would only cost a second visit.
            output[neighbour] = output[index]

            if size == heap_value.shape[0]:
                heap_value, heap_age, heap_index, heap_source = _grow(
                    heap_value, heap_age, heap_index, heap_source
                )
            position = size
            while position > 0:
                parent = (position - 1) // 2
                if heap_value[parent] < neighbour_value or (
                    heap_value[parent] == neighbour_value
                    and heap_age[parent] <= age_counter
                ):
                    break
                heap_value[position] = heap_value[parent]
                heap_age[position] = heap_age[parent]
                heap_index[position] = heap_index[parent]
                heap_source[position] = heap_source[parent]
                position = parent
            heap_value[position] = neighbour_value
            heap_age[position] = age_counter
            heap_index[position] = neighbour
            heap_source[position] = source
            size += 1


def _grow(value, age, index, source):
    """Double the heap arrays."""
    n = value.shape[0]
    new_value = np.empty(2 * n, dtype=np.float64)
    new_age = np.empty(2 * n, dtype=np.int64)
    new_index = np.empty(2 * n, dtype=np.int64)
    new_source = np.empty(2 * n, dtype=np.int64)
    new_value[:n] = value
    new_age[:n] = age
    new_index[:n] = index
    new_source[:n] = source
    return new_value, new_age, new_index, new_source


def _raveled_neighbour_offsets(shape, footprint, center=None):
    """Flat index offsets of a pixel's neighbours, ordered nearest first.

    The *order* is part of the algorithm, not a detail. Every push onto the
    watershed's queue takes the next age, and age is what breaks ties on a
    plateau — so visiting neighbours in a different order divides a plateau
    differently. Sorted by Euclidean distance with a *stable* sort, which leaves
    equidistant neighbours in the footprint's own C order.
    """
    footprint = np.asarray(footprint, dtype=bool)
    ndim = len(shape)
    if center is None:
        center = tuple(size // 2 for size in footprint.shape)
    offsets = np.stack(
        [index - c for index, c in zip(np.nonzero(footprint), center)], axis=-1
    )
    ravel_factors = np.cumprod((tuple(shape[1:]) + (1,))[::-1])[::-1]
    raveled = (offsets * ravel_factors).sum(axis=1)
    distances = np.sqrt(np.sum(offsets.astype(float) ** 2, axis=1))
    order = np.argsort(distances, kind="stable")
    # The first is the centre itself, at distance zero.
    return np.ascontiguousarray(raveled[order][1:].astype(np.int64))


def watershed(
    image,
    markers=None,
    connectivity: int = 1,
    offset=None,
    mask=None,
    compactness: float = 0.0,
    watershed_line: bool = False,
):
    """Flood ``image`` from ``markers``, assigning every pixel to a basin.

    The image is a landscape and the markers are sources; each pixel joins the
    marker whose flood reaches it first, where "first" is by increasing image
    value. Seeded on the *negated* distance transform of a binary mask, this
    splits touching objects at their narrowest point, which is what it is used
    for here.

    Parameters
    ----------
    image : numpy.ndarray
        The landscape to flood. Low is early.
    markers : numpy.ndarray or int
        Label image of sources; a plain integer means "place that many minima
        automatically", which is not implemented here.
    connectivity : int or numpy.ndarray
        Neighbourhood order (1 = faces, 2 = faces and edges), or an explicit
        boolean structuring element.
    offset : sequence of int, optional
        Centre of an explicit ``connectivity`` array.
    mask : numpy.ndarray, optional
        Only ``True`` pixels are flooded; the rest stay 0.
    compactness : float
        Not implemented. Non-zero raises.
    watershed_line : bool
        Not implemented. ``True`` raises.

    Returns
    -------
    numpy.ndarray
        Label image of the same shape as ``image``.
    """
    from scipy import ndimage

    if compactness:
        raise NotImplementedError(
            "compact watershed is not implemented; pass compactness=0"
        )
    if watershed_line:
        raise NotImplementedError(
            "watershed lines are not implemented; pass watershed_line=False"
        )

    image = np.asarray(image, dtype=np.float64)
    if markers is None or np.isscalar(markers):
        raise NotImplementedError(
            "automatic markers are not implemented; pass a label image, "
            "typically ndimage.label() of the local maxima"
        )
    markers = np.asarray(markers)
    if markers.shape != image.shape:
        raise ValueError(
            f"markers {markers.shape} and image {image.shape} must have the "
            "same shape"
        )

    if mask is None:
        mask = np.ones(image.shape, dtype=bool)
    else:
        mask = np.asarray(mask, dtype=bool)
        if mask.shape != image.shape:
            raise ValueError(
                f"mask {mask.shape} and image {image.shape} must have the same shape"
            )
        # A marker outside the mask would flood nothing and, worse, would leave
        # a label in the output that no pixel belongs to.
        markers = np.where(mask, markers, 0)

    if isinstance(connectivity, (int, np.integer)):
        if not 1 <= connectivity <= image.ndim:
            raise ValueError(
                f"connectivity must be between 1 and {image.ndim}, got {connectivity}"
            )
        structure = ndimage.generate_binary_structure(image.ndim, int(connectivity))
        centre = None
    else:
        structure = np.asarray(connectivity, dtype=bool)
        if structure.ndim != image.ndim:
            raise ValueError("connectivity must have the same rank as the image")
        if any(size % 2 == 0 for size in structure.shape):
            raise ValueError("connectivity must have odd dimensions")
        centre = None if offset is None else tuple(np.asarray(offset, dtype=int))
    pad = max(structure.shape) // 2

    # Padding is what lets the flood use raw offsets: the border is masked off,
    # so a neighbour index can never leave the array.
    pad_width = [(pad, pad)] * image.ndim
    padded_image = np.pad(image, pad_width, mode="constant")
    padded_mask = np.pad(mask, pad_width, mode="constant").ravel()
    output = np.pad(markers, pad_width, mode="constant").astype(np.int64)

    offsets = _raveled_neighbour_offsets(padded_image.shape, structure, centre)

    flat_output = output.ravel()
    marker_locations = np.flatnonzero(flat_output).astype(np.int64)
    if marker_locations.size:
        _flood(
            np.ascontiguousarray(padded_image.ravel()),
            marker_locations,
            offsets,
            padded_mask.astype(np.uint8),
            flat_output,
        )

    cropped = output[tuple(slice(pad, -pad) for _ in range(image.ndim))]
    return np.ascontiguousarray(cropped).astype(markers.dtype, copy=False)


# ---------------------------------------------------------------------------
# Cleaning up a segmentation
# ---------------------------------------------------------------------------


def remove_small_objects(labels, min_size: int = 64, connectivity: int = 1, *, out=None):
    """Drop connected components smaller than ``min_size`` pixels.

    One ``bincount`` over the label image and one lookup, rather than a pass
    over the whole frame per label — the difference between ``O(frame)`` and
    ``O(n_labels × frame)``, which on a segmentation holding a few thousand
    molecules is the difference between instant and a coffee.

    Parameters
    ----------
    labels : numpy.ndarray
        Label image, or a boolean mask (which is labelled first).
    min_size : int
        Components with strictly fewer pixels than this are removed.
    connectivity : int
        Neighbourhood order used when a boolean mask has to be labelled.
    out : numpy.ndarray, optional
        Write into this array rather than a copy.

    Returns
    -------
    numpy.ndarray
        The input with the small components set to 0.
    """
    from scipy import ndimage

    labels = np.asarray(labels)
    if labels.dtype != bool and not np.issubdtype(labels.dtype, np.integer):
        raise TypeError(f"labels must be integer or boolean, got {labels.dtype}")
    if out is None:
        out = labels.copy()
    else:
        out[:] = labels

    if out.dtype == bool:
        structure = ndimage.generate_binary_structure(labels.ndim, connectivity)
        components = np.zeros(labels.shape, dtype=np.int32)
        ndimage.label(labels, structure, output=components)
    else:
        if out.min() < 0:
            raise ValueError("negative labels are not supported")
        components = out

    sizes = np.bincount(components.ravel())
    out[(sizes < min_size)[components]] = 0
    return out


def remove_small_holes(mask, area_threshold: int = 64, connectivity: int = 1, *, out=None):
    """Fill holes in ``mask`` smaller than ``area_threshold`` pixels.

    The complement of :func:`remove_small_objects`: a hole is a small component
    of the background. A molecule whose centre is dim enough to fall below the
    threshold segments as an annulus, and every shape measurement of an annulus
    — area, centroid, eccentricity — is wrong.

    Parameters
    ----------
    mask : numpy.ndarray
        Boolean image.
    area_threshold : int
        Holes with strictly fewer pixels than this are filled.
    connectivity : int
        Neighbourhood order for the background components.
    out : numpy.ndarray, optional
        Write into this array rather than a copy.

    Returns
    -------
    numpy.ndarray
        Boolean image with the small holes filled.
    """
    mask = np.asarray(mask)
    if out is None:
        out = mask.astype(bool, copy=True)
    elif out.dtype != bool:
        raise TypeError("out must be boolean")
    np.logical_not(mask, out=out)
    out = remove_small_objects(out, area_threshold, connectivity, out=out)
    np.logical_not(out, out=out)
    return out


def relabel_sequential(labels, offset: int = 1):
    """Renumber ``labels`` to a gap-free ``offset..offset + n - 1``.

    Removing objects leaves gaps, and a gap is not cosmetic: every consumer that
    treats a label image as "the labels are 1 to max" — :func:`regionprops`
    among them — then reports empty regions that no pixel belongs to. Anything
    that deletes labels should renumber afterwards.

    Parameters
    ----------
    labels : numpy.ndarray
        Label image with non-negative integer labels; 0 stays 0.
    offset : int
        First label of the output.

    Returns
    -------
    relabelled : numpy.ndarray
        The renumbered image.
    forward : numpy.ndarray
        Lookup from old label to new, so a per-label table can follow.
    inverse : numpy.ndarray
        Lookup from new label back to old.
    """
    labels = np.asarray(labels)
    if not np.issubdtype(labels.dtype, np.integer):
        raise TypeError("labels must have an integer dtype")
    if offset <= 0:
        raise ValueError("offset must be strictly positive")
    if labels.size and labels.min() < 0:
        raise ValueError("negative labels are not supported")

    present = np.unique(labels)
    if present.size and present[0] == 0:
        renumbered = np.concatenate(
            [[0], np.arange(offset, offset + present.size - 1)]
        )
    else:
        renumbered = np.arange(offset, offset + present.size)

    forward = np.zeros(int(labels.max()) + 1 if labels.size else 1, dtype=np.intp)
    forward[present] = renumbered
    inverse = np.zeros(int(renumbered[-1]) + 1 if renumbered.size else 1, dtype=np.intp)
    inverse[renumbered] = present
    return forward[labels].astype(labels.dtype, copy=False), forward, inverse


def expand_labels(labels, distance: float = 1.0, spacing=None):
    """Grow every label outwards by ``distance``, without merging neighbours.

    Each background pixel within ``distance`` of a label joins the *nearest*
    one, so two objects growing towards each other meet at the midline instead
    of fusing. That is what makes this the honest way to put a background
    annulus around each molecule.

    Parameters
    ----------
    labels : numpy.ndarray
        Label image; 0 is background.
    distance : float
        Growth radius, in pixels unless ``spacing`` says otherwise.
    spacing : sequence of float, optional
        Physical pixel size per axis, so an anisotropic stack grows isotropically
        in space rather than in pixels.

    Returns
    -------
    numpy.ndarray
        The grown label image.
    """
    from scipy import ndimage

    labels = np.asarray(labels)
    distances, indices = ndimage.distance_transform_edt(
        labels == 0, sampling=spacing, return_indices=True
    )
    grown = np.zeros_like(labels)
    within = distances <= distance
    nearest = labels[tuple(axis[within] for axis in indices)]
    grown[within] = nearest
    return grown


def find_boundaries(labels, connectivity: int = 1, mode: str = "thick", background: int = 0):
    """Return the pixels where ``labels`` changes value.

    Parameters
    ----------
    labels : numpy.ndarray
        Label image or boolean mask.
    connectivity : int
        Neighbourhood order.
    mode : {'thick', 'inner', 'outer'}
        ``'thick'`` marks both sides of every boundary; ``'inner'`` only the
        object side, which is what an overlay that must not spill outside the
        object wants; ``'outer'`` only the background side.
    background : int
        Label treated as background for ``'inner'`` and ``'outer'``.

    Returns
    -------
    numpy.ndarray
        Boolean image of the boundary pixels.
    """
    from scipy import ndimage

    labels = np.asarray(labels)
    if labels.dtype == bool:
        labels = labels.astype(np.uint8)
    structure = ndimage.generate_binary_structure(labels.ndim, connectivity)
    # A pixel is on a boundary when the neighbourhood maximum and minimum
    # disagree — the grey dilation/erosion pair, which works on labels and not
    # just on a mask.
    boundaries = ndimage.grey_dilation(
        labels, footprint=structure
    ) != ndimage.grey_erosion(labels, footprint=structure)
    if mode == "thick":
        return boundaries
    if mode == "inner":
        return boundaries & (labels != background)
    if mode == "outer":
        # Not simply "the background half of the boundary". Two objects that
        # touch have no background between them, and an outline that dropped
        # those pixels would draw them as one blob — so a pixel inside an object
        # that is adjacent to a *different* object counts as outer too.
        is_background = labels == background
        full = ndimage.generate_binary_structure(labels.ndim, labels.ndim)
        sentinel = np.iinfo(labels.dtype).max
        without_background = np.array(labels, copy=True)
        without_background[is_background] = sentinel
        adjacent_to_another = (
            ndimage.grey_dilation(labels, footprint=full)
            != ndimage.grey_erosion(without_background, footprint=full)
        ) & ~is_background
        return boundaries & (is_background | adjacent_to_another)
    raise ValueError(f"mode must be 'thick', 'inner' or 'outer', got {mode!r}")


# ---------------------------------------------------------------------------
# Enhancing what is to be found
# ---------------------------------------------------------------------------


def difference_of_gaussians(image, low_sigma, high_sigma=None, *, mode: str = "nearest",
                            cval: float = 0.0, truncate: float = 4.0):
    """Band-pass ``image`` by subtracting two Gaussian blurs.

    One pass removes both nuisances at once: the narrow blur keeps structure at
    the scale of interest while the wide blur carries the slowly varying
    background, and their difference has neither the shot noise below
    ``low_sigma`` nor the illumination gradient above ``high_sigma``. It is the
    natural pre-filter for finding spots, and a close approximation of the
    Laplacian of a Gaussian at that scale.

    Parameters
    ----------
    image : numpy.ndarray
        Input image.
    low_sigma : float or sequence of float
        Standard deviation of the narrow blur — the smallest feature kept.
    high_sigma : float or sequence of float, optional
        Standard deviation of the wide blur; defaults to ``1.6 * low_sigma``,
        the ratio that best approximates the Laplacian of a Gaussian.
    mode, cval, truncate
        Passed to :func:`gaussian`.

    Returns
    -------
    numpy.ndarray
        The band-passed image, as float.

    Raises
    ------
    ValueError
        If any ``high_sigma`` is below its ``low_sigma``, which would invert the
        band and silently return the negative of what was asked for.
    """
    image = np.asarray(image, dtype=float)
    low = np.array(low_sigma, dtype=float, ndmin=1)
    high = low * 1.6 if high_sigma is None else np.array(high_sigma, dtype=float, ndmin=1)
    low = low * np.ones(image.ndim)
    high = high * np.ones(image.ndim)
    if np.any(high < low):
        raise ValueError(
            "high_sigma must be at least low_sigma, or the band is inverted"
        )
    narrow = gaussian(image, low, mode=mode, cval=cval, truncate=truncate)
    wide = gaussian(image, high, mode=mode, cval=cval, truncate=truncate)
    return narrow - wide


def white_tophat(image, footprint=None, size: int = 15):
    """Return ``image`` minus its morphological opening — the small bright detail.

    The opening is what survives sliding the footprint under the surface, which
    is a background estimate that follows uneven illumination instead of
    assuming it is flat. Subtracting it leaves the features smaller than the
    footprint, which is what a fluorescence image's spots are.

    Parameters
    ----------
    image : numpy.ndarray
        Input image.
    footprint : numpy.ndarray, optional
        Structuring element. Defaults to a square of side ``size``, which must
        be comfortably larger than the features to keep and smaller than the
        illumination variation to remove.
    size : int
        Side of the default square footprint.

    Returns
    -------
    numpy.ndarray
        The background-subtracted image, never negative.
    """
    from scipy import ndimage

    image = np.asarray(image, dtype=float)
    if footprint is None:
        footprint = np.ones((size,) * image.ndim, dtype=bool)
    opened = ndimage.grey_opening(image, footprint=np.asarray(footprint, dtype=bool))
    return image - opened


# ---------------------------------------------------------------------------
# Multi-scale spot detection
# ---------------------------------------------------------------------------


def _blob_overlap(first, second) -> float:
    """Fraction of the smaller disc's area shared with the larger one."""
    radius_a, radius_b = first[-1] * np.sqrt(2), second[-1] * np.sqrt(2)
    separation = float(np.linalg.norm(first[:-1] - second[:-1]))
    if separation > radius_a + radius_b:
        return 0.0
    if separation <= abs(radius_a - radius_b):
        return 1.0
    if separation == 0:
        return 1.0
    # Circle-circle lens area, normalised by the smaller disc.
    ratio_a = np.clip(
        (separation**2 + radius_a**2 - radius_b**2) / (2 * separation * radius_a), -1, 1
    )
    ratio_b = np.clip(
        (separation**2 + radius_b**2 - radius_a**2) / (2 * separation * radius_b), -1, 1
    )
    area = (
        radius_a**2 * (np.arccos(ratio_a) - ratio_a * np.sqrt(1 - ratio_a**2))
        + radius_b**2 * (np.arccos(ratio_b) - ratio_b * np.sqrt(1 - ratio_b**2))
    )
    return float(area / (np.pi * min(radius_a, radius_b) ** 2))


def _prune_blobs(blobs, overlap: float):
    """Drop the smaller of any two blobs overlapping by more than ``overlap``.

    A spot is found once per scale it survives, so the same molecule appears
    several times at neighbouring sigmas; without this a detector returns three
    copies of everything.
    """
    from scipy import spatial

    if len(blobs) < 2:
        return blobs
    largest_sigma = blobs[:, -1].max()
    reach = 2 * largest_sigma * np.sqrt(blobs.shape[1] - 1)
    tree = spatial.cKDTree(blobs[:, :-1])
    pairs = np.array(list(tree.query_pairs(reach)))
    if len(pairs) == 0:
        return blobs
    for i, j in pairs:
        first, second = blobs[i], blobs[j]
        if _blob_overlap(first, second) > overlap:
            # The sigmas increase together, so "larger sigma wins" is the same
            # decision in every dimension.
            if first[-1] > second[-1]:
                second[-1] = 0
            else:
                first[-1] = 0
    kept = blobs[blobs[:, -1] > 0]
    return kept if len(kept) else np.empty((0, blobs.shape[1]))


def blob_dog(image, min_sigma: float = 1.0, max_sigma: float = 50.0,
             sigma_ratio: float = 1.6, threshold: float = 0.5,
             overlap: float = 0.5):
    """Find bright round spots by a difference-of-Gaussians scale space.

    The image is band-passed at a geometric ladder of scales; a spot registers
    most strongly at the scale matching its own width, so the *position of the
    maximum along the ladder* estimates its size. That is what a fixed-scale
    detector cannot do, and what an image of unknown focus needs.

    Parameters
    ----------
    image : numpy.ndarray
        Grayscale image; bright spots on a dark background.
    min_sigma, max_sigma : float
        Smallest and largest spot width to look for, as a Gaussian sigma. A
        diffraction-limited spot has sigma ≈ 0.21 λ / NA, in pixels.
    sigma_ratio : float
        Spacing of the scale ladder. Must exceed 1.
    threshold : float
        Minimum response. Scale-normalised, so it does not follow the image
        units — read it off a run rather than guessing.
    overlap : float
        Two spots overlapping by more than this fraction are merged, keeping
        the larger.

    Returns
    -------
    numpy.ndarray
        ``(n_blobs, image.ndim + 1)``: coordinates then sigma.
    """
    from scipy import ndimage

    image = np.asarray(image, dtype=float)
    if sigma_ratio <= 1.0:
        raise ValueError("sigma_ratio must be greater than 1")
    n_scales = int(np.mean(np.log(max_sigma / min_sigma) / np.log(sigma_ratio) + 1))
    sigmas = np.array([min_sigma * (sigma_ratio**i) for i in range(n_scales + 1)])

    cube = np.empty(image.shape + (n_scales,), dtype=float)
    previous = ndimage.gaussian_filter(image, sigmas[0], mode="reflect")
    for index, sigma in enumerate(sigmas[1:]):
        current = ndimage.gaussian_filter(image, sigma, mode="reflect")
        # Normalised so that a spot of any width gives the same response, which
        # is what makes one threshold usable across the whole ladder.
        cube[..., index] = (previous - current) / (sigma_ratio - 1)
        previous = current

    return _blobs_from_cube(cube, sigmas, threshold, overlap, image.ndim)


def blob_log(image, min_sigma: float = 1.0, max_sigma: float = 50.0,
             num_sigma: int = 10, threshold: float = 0.2, overlap: float = 0.5,
             log_scale: bool = False):
    """Find bright round spots by a Laplacian-of-Gaussian scale space.

    The exact form of what :func:`blob_dog` approximates: slower, because every
    scale is a separate filter rather than a difference of two, and more
    accurate about the size it reports.

    Parameters
    ----------
    image : numpy.ndarray
        Grayscale image; bright spots on a dark background.
    min_sigma, max_sigma : float
        Smallest and largest spot width, as a Gaussian sigma.
    num_sigma : int
        Number of scales between them.
    threshold : float
        Minimum scale-normalised response.
    overlap : float
        Merge threshold, as in :func:`blob_dog`.
    log_scale : bool
        Space the scales geometrically rather than linearly, which is the right
        choice when ``max_sigma / min_sigma`` is large.

    Returns
    -------
    numpy.ndarray
        ``(n_blobs, image.ndim + 1)``: coordinates then sigma.
    """
    from scipy import ndimage

    image = np.asarray(image, dtype=float)
    if log_scale:
        sigmas = np.logspace(np.log10(min_sigma), np.log10(max_sigma), num_sigma)
    else:
        sigmas = np.linspace(min_sigma, max_sigma, num_sigma)

    cube = np.empty(image.shape + (len(sigmas),), dtype=float)
    for index, sigma in enumerate(sigmas):
        # Negated, so a bright spot is a maximum rather than a minimum, and
        # scale-normalised by sigma**2 so one threshold spans the ladder.
        cube[..., index] = -ndimage.gaussian_laplace(image, sigma) * sigma**2

    return _blobs_from_cube(cube, sigmas, threshold, overlap, image.ndim)


def _blobs_from_cube(cube, sigmas, threshold, overlap, ndim):
    """Local maxima of a scale-space cube, as ``(coordinates..., sigma)`` rows."""
    peaks = peak_local_max(
        cube,
        threshold_abs=threshold,
        footprint=np.ones((3,) * cube.ndim, dtype=bool),
        exclude_border=False,
    )
    if not len(peaks):
        return np.empty((0, ndim + 1))
    blobs = np.column_stack(
        [peaks[:, :ndim].astype(float), sigmas[peaks[:, -1]].astype(float)]
    )
    return _prune_blobs(blobs, overlap)


# ---------------------------------------------------------------------------
# From a mask back to geometry
# ---------------------------------------------------------------------------


def find_contours(image, level: Optional[float] = None,
                  fully_connected: str = "low", positive_orientation: str = "low"):
    """Trace iso-value contours through ``image`` by marching squares.

    This is the way back from a raster to geometry: a segmentation traced into
    polygons can become a :class:`~chisurf.core.roi.PolygonROI`, which is
    resolution-independent and editable, rather than a mask that is neither.

    Parameters
    ----------
    image : numpy.ndarray
        2-D array.
    level : float, optional
        Contour value. Defaults to halfway between the image's extremes, which
        is the sensible choice for a boolean mask.
    fully_connected : {'low', 'high'}
        Which side of an ambiguous saddle is treated as connected.
    positive_orientation : {'low', 'high'}
        Whether the traced polygon winds with the low or the high side on its
        left, which decides the sign of an enclosed area.

    Returns
    -------
    list of numpy.ndarray
        One ``(n_points, 2)`` array of ``(row, column)`` coordinates per
        contour, in continuous coordinates — a contour runs *between* pixels.
    """
    image = np.asarray(image, dtype=float)
    if image.ndim != 2:
        raise ValueError(f"find_contours needs a 2-D image, got {image.ndim}-D")
    if fully_connected not in ("low", "high"):
        raise ValueError("fully_connected must be 'low' or 'high'")
    if positive_orientation not in ("low", "high"):
        raise ValueError("positive_orientation must be 'low' or 'high'")
    if level is None:
        level = (float(np.nanmin(image)) + float(np.nanmax(image))) / 2.0

    segments = _marching_squares(image, float(level), fully_connected == "high")
    contours = _assemble_contours(segments)
    if positive_orientation == "high":
        contours = [contour[::-1] for contour in contours]
    return contours


def _marching_squares(image, level, vertex_connect_high):
    """Return the contour segments of one iso-level, as ``(n, 4)`` endpoint pairs.

    Each 2x2 block of pixels is classified by which of its corners lie above the
    level — sixteen cases, of which fourteen give one or two segments. The two
    ambiguous ones are the diagonals, where the block can be read as two corners
    joined or two corners separated; ``vertex_connect_high`` chooses, and the
    choice must be consistent across the image or the contours do not close.

    Endpoints are placed by linear interpolation along the block's edges, which
    is what makes the contour sub-pixel rather than a staircase.
    """
    n_rows, n_columns = image.shape
    segments = np.empty((4 * (n_rows - 1) * (n_columns - 1), 4), dtype=np.float64)
    count = 0
    for r in range(n_rows - 1):
        for c in range(n_columns - 1):
            upper_left = image[r, c]
            upper_right = image[r, c + 1]
            lower_left = image[r + 1, c]
            lower_right = image[r + 1, c + 1]
            if (
                np.isnan(upper_left)
                or np.isnan(upper_right)
                or np.isnan(lower_left)
                or np.isnan(lower_right)
            ):
                continue

            square_case = 0
            if upper_left > level:
                square_case += 1
            if upper_right > level:
                square_case += 2
            if lower_right > level:
                square_case += 4
            if lower_left > level:
                square_case += 8
            if square_case == 0 or square_case == 15:
                continue

            top = (r, c + _fraction(upper_left, upper_right, level))
            bottom = (r + 1, c + _fraction(lower_left, lower_right, level))
            left = (r + _fraction(upper_left, lower_left, level), c)
            right = (r + _fraction(upper_right, lower_right, level), c + 1)

            if square_case == 1:
                count = _emit(segments, count, top, left)
            elif square_case == 2:
                count = _emit(segments, count, right, top)
            elif square_case == 3:
                count = _emit(segments, count, right, left)
            elif square_case == 4:
                count = _emit(segments, count, bottom, right)
            elif square_case == 5:
                if vertex_connect_high:
                    count = _emit(segments, count, top, left)
                    count = _emit(segments, count, bottom, right)
                else:
                    count = _emit(segments, count, top, right)
                    count = _emit(segments, count, bottom, left)
            elif square_case == 6:
                count = _emit(segments, count, bottom, top)
            elif square_case == 7:
                count = _emit(segments, count, bottom, left)
            elif square_case == 8:
                count = _emit(segments, count, left, bottom)
            elif square_case == 9:
                count = _emit(segments, count, top, bottom)
            elif square_case == 10:
                if vertex_connect_high:
                    count = _emit(segments, count, right, bottom)
                    count = _emit(segments, count, left, top)
                else:
                    count = _emit(segments, count, right, top)
                    count = _emit(segments, count, left, bottom)
            elif square_case == 11:
                count = _emit(segments, count, right, bottom)
            elif square_case == 12:
                count = _emit(segments, count, left, right)
            elif square_case == 13:
                count = _emit(segments, count, top, right)
            elif square_case == 14:
                count = _emit(segments, count, left, top)
    return segments[:count]


def _fraction(low_value, high_value, level):
    """Where between two corner values the level falls, in [0, 1]."""
    if high_value == low_value:
        return 0.0
    return (level - low_value) / (high_value - low_value)


def _emit(segments, count, start, end):
    """Append one segment and return the new count."""
    segments[count, 0] = start[0]
    segments[count, 1] = start[1]
    segments[count, 2] = end[0]
    segments[count, 3] = end[1]
    return count + 1


def _assemble_contours(segments):
    """Join segments end to end into contours.

    Segments leave the grid in raster order, not in path order, so they have to
    be chained. Two dictionaries keyed on the free endpoints turn what would be
    a quadratic search into one linear pass: each new segment either extends a
    chain, joins two chains, closes a loop, or starts a chain of its own.
    """
    from collections import deque

    contours: dict[int, deque] = {}
    starts: dict[tuple, tuple] = {}
    ends: dict[tuple, tuple] = {}
    next_index = 0

    for row in segments:
        first = (row[0], row[1])
        second = (row[2], row[3])
        if first == second:
            continue

        tail, tail_index = starts.pop(second, (None, None))
        head, head_index = ends.pop(first, (None, None))

        if tail is not None and head is not None:
            if tail is head:
                # The segment closes the chain it belongs to.
                head.append(second)
            else:
                # It bridges two chains; keep the one that started first, which
                # is what makes the output order deterministic.
                if tail_index > head_index:
                    head.extend(tail)
                    contours.pop(tail_index)
                    starts[head[0]] = (head, head_index)
                    ends[head[-1]] = (head, head_index)
                else:
                    tail.extendleft(reversed(head))
                    starts.pop(head[0], None)
                    contours.pop(head_index)
                    starts[tail[0]] = (tail, tail_index)
                    ends[tail[-1]] = (tail, tail_index)
        elif tail is None and head is None:
            new_contour = deque([first, second])
            contours[next_index] = new_contour
            starts[first] = (new_contour, next_index)
            ends[second] = (new_contour, next_index)
            next_index += 1
        elif head is None:
            tail.appendleft(first)
            starts[first] = (tail, tail_index)
        else:
            head.append(second)
            ends[second] = (head, head_index)

    return [np.array(contour) for _, contour in sorted(contours.items())]
