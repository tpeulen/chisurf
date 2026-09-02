from __future__ import annotations

from itertools import tee
from chisurf import typing

import copy
from math import floor

import numpy as np


def distance_between_gaussian(
        distances: np.ndarray,
        separation_distance: float,
        sigma: float,
        normalize: bool = False
) -> np.ndarray:
    """Calculate a Gaussian distribution of distances.

    Parameters
    ----------
    distances : np.ndarray
        Array of distances for which to calculate the Gaussian distribution
    separation_distance : float
        Mean of the Gaussian distribution
    sigma : float
        Standard deviation of the Gaussian distribution
    normalize : bool
        If True, normalize the distribution to sum to 1

    Returns
    -------
    np.ndarray
        Gaussian distribution of distances. Non-finite distances carry zero
        weight, so a single NaN cannot turn the whole distribution into NaN.
    .. warning::

       **This is not the function its name suggests, and there are two others
       with the same name that are.** This returns a plain Gaussian centred at
       ``separation_distance``. ``chisurf.core.math.functions.distributions``
       and ``...functions.rdf`` both define ``distance_between_gaussian`` as
       the distribution of the *distance between two Gaussian clouds*, which
       carries an extra ``r/separation`` factor and an antisymmetric second
       term; on a typical axis the two are 0.93 apart in relative terms. They
       are different functions, not copies that drifted.

       It has no callers outside this module's own test. It is kept rather than
       deleted only because that test exists; do not reach for it. Confusing
       these two is what produced the worm-like-chain linker bug -- see
       ``okf/log.md`` 2026-09-02 (21) in imp.bff. Renaming it to say what it
       is (a Gaussian weight) would end the collision, and is worth doing.
    """
    result = np.exp(-(distances - separation_distance) ** 2 / (2 * sigma ** 2))
    result = np.where(np.isfinite(result), result, 0.0)
    s = np.sum(result)
    if normalize and s > 0:
        result = result / s
    return result


def histogram_rebin(
        bin_edges: np.ndarray,
        counts: np.ndarray,
        new_bin_edges: np.ndarray
):
    """Interpolates a histogram to a new set of bin edges.

    This function returns the histogram values corresponding to a new set of bin edges.
    If a new bin edge is outside the range of the original histogram's bin edges, the value
    is set to 0. This is useful for changing the bin spacing of a histogram.

    Bins are half-open, ``[edge_i, edge_i+1)``, except for the last one, which is
    closed on the right as in :func:`numpy.histogram`: a new edge that coincides
    with the largest original edge is inside the histogram and takes the last count.

    :param bin_edges: array
        The bin edges of the original histogram.
    :param counts: array
        Histogram values corresponding to the bins defined by bin_edges.
    :param new_bin_edges: array
        The new bin edges for which to interpolate the histogram.
    :return: list or float
        A list of histogram values corresponding to new_bin_edges if its length > 1,
        otherwise a single value.

    Examples
    --------
    >>> counts = np.array([0, 2, 1])
    >>> bin_edges = np.array([0, 5, 10, 15])
    >>> new_bin_edges = np.linspace(-5, 20, 17)
    >>> histogram_rebin(bin_edges, counts, new_bin_edges)
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 2.0, 2.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0]
    >>> histogram_rebin(bin_edges, counts, np.array([15.0]))
    1.0
    """
    lower = float(np.min(bin_edges))
    upper = float(np.max(bin_edges))
    re = list()
    for xi in new_bin_edges.flatten():
        if xi < lower or xi > upper:
            re.append(0.0)
        elif xi == upper:
            re.append(float(counts[-1]))
        else:
            sel = np.where(xi < bin_edges)
            re.append(float(counts[sel[0][0] - 1]))
    if len(re) == 1:
        return re[0]
    else:
        return re


def overlapping_region(
        dataset1,
        dataset2
):
    """Find the overlapping region between two datasets based on their x-values.

    Each dataset is a tuple of (x, y) arrays. This function computes the common x-range
    where both datasets overlap and masks out data points outside this range. The resulting
    overlapping segments of the datasets are returned.

    :param dataset1: tuple
        A tuple containing two numpy arrays (x and y values) for the first dataset.
    :param dataset2: tuple
        A tuple containing two numpy arrays (x and y values) for the second dataset.
    :return: tuple of tuples
        Two tuples corresponding to the overlapping regions of dataset1 and dataset2.
        Each tuple contains the x and y values within the overlapping range.

    Examples
    --------
    >>> import matplotlib.pylab as p
    >>> x1 = np.linspace(-1, 12, 10)
    >>> y1 = np.cos(x1)
    >>> a1 = (x1, y1)
    >>> x2 = np.linspace(-1, 12, 11)
    >>> y2 = np.sin(x2)
    >>> a2 = (x2, y2)
    >>> (rx1, ry1), (rx2, ry2) = overlapping_region(a1, a2)
    >>> _ = p.plot(x1, y1, 'r')
    >>> _ = p.plot(rx1, ry1, 'k')
    >>> _ = p.plot(x2, y2, 'g')
    >>> _ = p.plot(rx2, ry2, 'b')
    >>> p.show()
    """
    x1, y1 = dataset1
    x2, y2 = dataset2

    # Sort the arrays in ascending order in x
    x1 = np.array(x1)
    y1 = np.array(y1)
    inds = x1.argsort()
    x1 = x1[inds]
    y1 = y1[inds]
    x1 = np.ma.array(x1)
    y1 = np.ma.array(y1)

    x2 = np.array(x2)
    y2 = np.array(y2)
    inds = x2.argsort()
    x2 = x2[inds]
    y2 = y2[inds]
    x2 = np.ma.array(x2)
    y2 = np.ma.array(y2)

    # Calculate range for adjustment of spacing
    rng = (max(min(x1), min(x2)), min(max(x1), max(x2)))

    # Mask the irrelevant parts
    m1l = x1.data < rng[0]
    m1u = x1.data > rng[1]
    m1 = m1l + m1u
    x1.mask = m1
    y1.mask = m1

    m2l = x2.data < rng[0]
    m2u = x2.data > rng[1]
    m2 = m2l + m2u
    x2.mask = m2
    y2.mask = m2

    # Create new lists for the overlapping regions
    ox1 = x1.compressed()
    oy1 = y1.compressed()
    ox2 = x2.compressed()
    oy2 = y2.compressed()

    return (ox1, oy1), (ox2, oy2)


def align_x_spacing(
        dataset1: typing.Tuple[np.ndarray, np.ndarray],
        dataset2: typing.Tuple[np.ndarray, np.ndarray],
        method: str = 'linear-close'
) -> typing.Tuple[
    typing.Tuple[np.ndarray, np.ndarray],
    typing.Tuple[np.ndarray, np.ndarray]
]:
    """Align the x-spacing of two datasets using a template and rescaling method.

    This function takes two datasets (each a tuple of (x, y) arrays) and aligns the x-values of the dataset
    with more points to match the x-spacing of the dataset with fewer points. The default method ('linear-close')
    uses linear interpolation between nearby data points.

    :param dataset1: tuple of np.ndarray
        The first dataset as a tuple (x, y).
    :param dataset2: tuple of np.ndarray
        The second dataset as a tuple (x, y).
    :param method: str, optional
        The method used for alignment. Currently supports 'linear-close'.
    :return: tuple of tuples
        Two tuples corresponding to the aligned datasets (x, y) for dataset1 and dataset2.

    Examples
    --------
    >>> import numpy as np
    >>> x1 = np.linspace(-5, 5, 10)
    >>> y1 = np.sin(x1)
    >>> a1 = (x1, y1)
    >>> x2 = np.linspace(0, 10, 10)
    >>> y2 = np.sin(x2)
    >>> a2 = (x2, y2)
    >>> (rx1, ry1), (rx2, ry2) = align_x_spacing(a1, a2)
    """
    (ox1, oy1), (ox2, oy2) = dataset1, dataset2
    # Assume that data is more or less equally spaced
    # t - template array, r - rescale array
    if len(ox1) < len(ox2):
        tx = ox1
        ty = oy1
        rx = ox2
        ry = oy2
        cm = "r2"
    else:
        tx = ox2
        ty = oy2
        rx = ox1
        ry = oy1
        cm = "r1"

    # Create template arrays as new arrays - n
    nx = copy.deepcopy(tx)
    ny = copy.deepcopy(ty)

    if method == 'linear-close':
        j = 0  # counter for template array
        ry1 = ry[0]
        rx1 = rx[0]
        for i, rxi in enumerate(rx):
            if j < len(tx) - 1:
                if rxi > tx[j]:
                    rx2 = rxi
                    ry2 = ry[i]
                    if ry2 - ry1 != 0 and rx1 - rx2 != 0:
                        m = (ry2 - ry1) / (rx1 - rx2)
                        ny[j] = m * tx[j] + ry1 - m * rx1
                    else:
                        ny[j] = ry1
                    j += 1
                elif rxi == tx[j]:
                    ny[j] = ry[i]
                    j += 1
                else:
                    ry1 = ry[i]
                    rx1 = rx[i]
            else:
                ny[j] = ry[i:].mean()
    if cm == "r1":
        rx1 = nx
        ry1 = ny
        rx2 = tx
        ry2 = ty
    elif cm == "r2":
        rx2 = nx
        ry2 = ny
        rx1 = tx
        ry1 = ty
    return (rx1, ry1), (rx2, ry2)


def bin_count(
        data: np.ndarray,
        bin_width: int = 16,
        bin_min: int = 0,
        bin_max: int = 4095
):
    """
    Count the number of occurrences of each value in an array of non-negative integers.

    The data is binned into intervals of width bin_width, starting from bin_min up to bin_max.
    The function returns the bin values and the counts for each bin.

    :param data: array_like
        1-dimensional input array of non-negative integers.
    :param bin_width: int, optional
        The width of each bin. Default is 16.
    :param bin_min: int, optional
        The minimum value to consider for binning. Default is 0.
    :param bin_max: int, optional
        The maximum value to consider for binning. Default is 4095.
    :return: tuple (bins, count)
        bins: numpy array of bin starting values.
        count: numpy array of counts for each bin.
    """
    n_min = np.rint(bin_min / bin_width)
    n_max = np.rint(bin_max / bin_width)
    n_bins = int(n_max - n_min)
    count = np.zeros(n_bins, dtype=np.float32)
    bins = np.arange(n_min, n_max, dtype=np.float32)
    bins *= bin_width
    for i in range(data.shape[0]):
        bin_index = int(np.rint((data[i] / bin_width)) - n_min)
        if bin_index < n_bins:
            count[bin_index] += 1
    return bins, count


def minmax(
        x: np.ndarray,
        ignore_zero: bool = False
):
    """Compute the minimum and maximum values of an array.

    If ignore_zero is True, zeros in the array will be ignored when computing the minimum value.

    :param x: array or list
        The input array.
    :param ignore_zero: bool, optional
        Whether to ignore zero values when computing the minimum. Default is False.
    :return: tuple (min, max)
        The minimum and maximum values in the array.
    """
    x = np.asarray(x)
    if x.size == 0:
        return np.inf, -np.inf

    # `ignore_zero` is asymmetric, and deliberately so: the original loop
    # updates the maximum *before* the `continue`, so a zero can still be the
    # largest value while being excluded from the minimum. Masking both ends
    # would change the answer for an all-non-positive array.
    max_v = x.max()
    if ignore_zero:
        nonzero = x[x != 0]
        min_v = nonzero.min() if nonzero.size else np.inf
    else:
        min_v = x.min()
    return min_v, max_v


def histogram1D(
        values,
        weights,
        n_bins: int = 101,
        tth_max: float = -1e12,
        tth_min: float = 1e12
):
    """Compute a 1D histogram with linear binning between specified limits.

    The histogram is computed by linearly binning the input values between tth_min and tth_max
    into n_bins bins. The weights associated with each value are summed in the corresponding bin.

    :param values: array_like
        The values to be binned.
    :param weights: array_like
        The weights for each value.
    :param n_bins: int, optional
        Number of bins in the histogram. Default is 101.
    :param tth_max: float, optional
        The maximum value for binning. Default is -1e12.
    :param tth_min: float, optional
        The minimum value for binning. Default is 1e12.
    :return: tuple (axis, hist)
        axis: numpy array representing the bin centers.
        hist: numpy array containing the weighted counts for each bin.
    """
    bin_width = (n_bins - 1.0) / (tth_max - tth_min)
    axis = np.arange(n_bins, dtype=np.float64) / bin_width + tth_min

    values = np.asarray(values)
    inside = (values >= tth_min) & (values <= tth_max)
    # floor(), matching the original: at v == tth_max the index is exactly
    # n_bins - 1, so the top bin is closed and nothing lands out of range.
    index = np.floor((values[inside] - tth_min) * bin_width).astype(np.intp)
    hist = np.bincount(
        index, weights=np.asarray(weights)[inside], minlength=n_bins
    ).astype(np.float64)
    return axis, hist


def discriminate(
        values: np.ndarray,
        weights: np.ndarray,
        discriminator: float
):
    """Filter values and weights based on a discriminator threshold.

    This function selects elements from the input arrays where the corresponding weight is greater than
    the given discriminator value.

    :param values: array_like
        Array of values.
    :param weights: array_like
        Array of weights corresponding to the values.
    :param discriminator: float
        The threshold value for weights.
    :return: tuple (filtered_values, filtered_weights)
        Arrays containing the values and weights that passed the discriminator threshold.
    """
    keep = np.asarray(weights) > discriminator
    return np.asarray(values)[keep], np.asarray(weights)[keep]


def smooth(
        x: np.ndarray,
        m: int
) -> np.ndarray:
    """Smooth an array with a centred moving average.

    Output element `i` is the mean of the input samples in the window
    ``[i - m, i + m]``. Windows are clipped to the array bounds rather than
    wrapped, so the leading and trailing `m` elements average over fewer
    samples instead of mixing in values from the opposite end of the array.

    Parameters
    ----------
    x : np.ndarray
        Input array to be smoothed.
    m : int
        Half-window size. The full window is ``2 * m + 1`` samples wide; a
        non-positive `m` returns an unmodified copy of the input.

    Returns
    -------
    np.ndarray
        Smoothed array with the same length as `x`.

    Examples
    --------
    >>> smooth(np.ones(5), 1)
    array([1., 1., 1., 1., 1.])
    >>> np.round(smooth(np.array([0., 0., 1., 0., 0.]), 1), 6)
    array([0.      , 0.333333, 0.333333, 0.333333, 0.      ])
    """
    x = np.asarray(x, dtype=np.float64)
    if m <= 0 or x.size == 0:
        return x.copy()
    i = np.arange(x.size)
    lo = np.clip(i - m, 0, x.size)
    hi = np.clip(i + m + 1, 0, x.size)
    cumulative = np.concatenate((np.zeros(1), np.cumsum(x)))
    return (cumulative[hi] - cumulative[lo]) / (hi - lo)


def first_distribution_pair(
        d: np.ndarray,
        sort: bool = False
) -> typing.Tuple[np.ndarray, np.ndarray]:
    """Return the (density, axis) pair of the first entry of a distribution array.

    A model's `distance_distribution` is shaped ``(n_distributions, 2, n_bins)``
    -- density first, axis second. Distribution plots draw the first entry, so
    this is the named, JSON-referenceable form of what a view spec would
    otherwise need a lambda for.

    Parameters
    ----------
    d : numpy.ndarray
        Distribution array; only ``d[0]`` is read.
    sort : bool
        Accepted and ignored. Distribution axes are already ordered, and every
        accessor is called with the same keyword arguments.

    Returns
    -------
    tuple of numpy.ndarray
        ``(density, axis)``.

    Examples
    --------
    >>> import numpy as np
    >>> d = np.array([[[0.1, 0.9], [40.0, 60.0]]])
    >>> density, axis = first_distribution_pair(d)
    >>> axis.tolist()
    [40.0, 60.0]
    """
    return d[0][0], d[0][1]


def distribution_pair(
        d: typing.Tuple[np.ndarray, np.ndarray],
        sort: bool = False
) -> typing.Tuple[np.ndarray, np.ndarray]:
    """Return a ``(density, axis)`` pair unchanged.

    The identity accessor. A model attribute that already *is* the
    ``(density, axis)`` pair a distribution plot draws still needs an accessor
    named in its view spec, because the plot calls one unconditionally -- this is
    that name, so such a model needs neither a lambda (which JSON cannot hold)
    nor a wrapper property whose only job is to be reshaped back.

    Parameters
    ----------
    d : tuple of numpy.ndarray
        The ``(density, axis)`` pair.
    sort : bool
        Accepted and ignored, so every accessor takes the same keywords.

    Returns
    -------
    tuple of numpy.ndarray
        ``d`` itself.
    """
    return d


def interleaved_to_two_columns(
        ls: np.ndarray,
        sort: bool = False
) -> typing.Tuple[np.ndarray, np.ndarray]:
    """
    Convert an interleaved spectrum into two-column data.

    The interleaved spectrum is assumed to alternate between amplitude and lifetime values.
    Optionally, the resulting data can be sorted by the lifetime values.

    :param ls: numpy array
        The interleaved spectrum (alternating amplitude and lifetime values).
    :param sort: bool, optional
        If True, the resulting columns are sorted by lifetime values. Default is False.
    :return: tuple (amplitudes, lifetimes)
        Two numpy arrays representing amplitudes and lifetimes respectively.

    Examples
    --------
    >>> import numpy as np
    >>> lifetime_spectrum = np.array([0.25, 1, 0.75, 4])
    >>> amplitudes, lifetimes = interleaved_to_two_columns(lifetime_spectrum)
    """
    lt = ls.reshape((ls.shape[0] // 2, 2))
    if sort:
        s = lt[np.argsort(lt[:, 1])]
        y = s[:, 0]
        x = s[:, 1]
        return y, x
    else:
        return lt[:, 0], lt[:, 1]


def two_column_to_interleaved(
        x: np.ndarray,
        t: np.ndarray
) -> np.ndarray:
    """Convert two-column lifetime spectra into an interleaved format.

    The two input arrays (amplitudes and lifetimes) are interleaved to form a single array.

    :param x: numpy array
        Array of amplitudes.
    :param t: numpy array
        Array of lifetimes (or rate constants).
    :return: numpy array
        Interleaved array containing amplitude and lifetime values.
    """
    c = np.vstack((x, t)).reshape(-1, order='F')
    return c


def elte2(
        e1: np.array,
        e2: np.array
) -> np.array:
    """
    Combine two interleaved lifetime spectra into a new spectrum.

    For each pair of corresponding elements in the two spectra, the resulting amplitude is the product
    of the amplitudes, and the resulting lifetime is computed as the harmonic mean:
    1 / (1/l1 + 1/l2).

    :param e1: array_like
        First interleaved lifetime spectrum in the format (a1, l1, a2, l2, ...).
    :param e2: array_like
        Second interleaved lifetime spectrum in the same format as e1.
    :return: numpy array
        A new interleaved lifetime spectrum of the form (a1*a1, harmonic_mean(l1, l2), ...).

    Examples
    --------
    >>> import numpy as np
    >>> e1 = np.array([1, 2, 3, 4])
    >>> e2 = np.array([5, 6, 7, 8])
    >>> elte2(e1, e2)
    array([ 5.        ,  1.5       ,  7.        ,  1.6       , 15.        ,
            2.4       , 21.        ,  2.66666667])
    """
    # k advances as i * n2 + j, so the write position is an affine function of
    # the loop indices and the whole Cartesian product lands in C order.
    amplitudes = np.outer(e1[0::2], e2[0::2])
    lifetimes = 1.0 / (1.0 / e1[1::2][:, None] + 1.0 / e2[1::2][None, :])

    r = np.empty(amplitudes.size * 2, dtype=np.float64)
    r[0::2] = amplitudes.ravel()
    r[1::2] = lifetimes.ravel()
    return r


def ere2(
        e1: np.ndarray,
        e2: np.ndarray
) -> np.array:
    """
    Combine two interleaved rate spectra into a new spectrum.

    For each pair of corresponding elements in the two spectra, the resulting amplitude is the product
    of the amplitudes, and the resulting rate is the sum of the rates.

    :param e1: array_like
        First interleaved rate spectrum in the format (a1, r1, a2, r2, ...).
    :param e2: array_like
        Second interleaved rate spectrum in the same format as e1.
    :return: numpy array
        A new interleaved rate spectrum of the form (a1*a1, r1+r1, ...).

    Examples
    --------
    >>> import numpy as np
    >>> e1 = np.array([0.5, 1, 0.5, 2])
    >>> e2 = np.array([0.5, 3, 0.5, 4])
    >>> ere2(e1, e2)
    array([0.25, 4.  , 0.25, 5.  , 0.25, 5.  , 0.25, 6.  ])
    """
    amplitudes = np.outer(e1[0::2], e2[0::2])
    rates = e1[1::2][:, None] + e2[1::2][None, :]

    r = np.empty(amplitudes.size * 2, dtype=np.float64)
    r[0::2] = amplitudes.ravel()
    r[1::2] = rates.ravel()
    return r


def invert_interleaved(
        interleaved_spectrum: np.ndarray
) -> np.ndarray:
    """Convert an interleaved lifetime spectrum to a rate spectrum and vice versa.

    For each pair in the interleaved spectrum, the amplitude remains unchanged while the second value
    (lifetime or rate) is inverted (i.e., replaced by its reciprocal).

    :param interleaved_spectrum: array_like
        Interleaved lifetime or rate spectrum.
    :return: numpy array
        The spectrum with each second component inverted.

    Examples
    --------
    >>> import numpy as np
    >>> e1 = np.array([1, 2, 3, 4])
    >>> invert_interleaved(e1)
    array([1.  , 0.5 , 3.  , 0.25])
    """
    n1 = interleaved_spectrum.shape[0] // 2
    r = np.empty(n1 * 2, dtype=np.float64)
    r[0::2] = interleaved_spectrum[0:n1 * 2:2]
    r[1::2] = 1.0 / interleaved_spectrum[1:n1 * 2:2]
    return r


def e1tn(
        e1: np.array,
        n: float
) -> np.array:
    """
    Multiply the amplitude components of an interleaved spectrum by a constant factor.

    Only the amplitude values (every other element starting from the first) are multiplied by the factor n.
    The rate or lifetime values remain unchanged.

    :param e1: array_like
        An interleaved spectrum in the format (amplitude, value, amplitude, value, ...).
    :param n: float
        The multiplication factor for the amplitude components.
    :return: numpy array
        The interleaved spectrum with scaled amplitude values.

    Examples
    --------
    >>> e1 = np.array([1, 2, 3, 4])
    >>> e1tn(e1, 2.0)
    array([2, 2, 6, 4])
    """
    # In place, and the caller relies on it: the array is returned as well as
    # modified.
    e1[0::2] *= n
    return e1


def e1ti2(
        e1: np.array,
        e2: np.array
) -> np.array:
    """
    Combine two interleaved spectra by multiplying corresponding amplitude and rate/lifetime components.

    This function takes two interleaved spectra (each formatted as alternating amplitude and rate/lifetime values)
    and computes a new interleaved spectrum. For each combination of a pair from the first spectrum and a pair from
    the second spectrum, the resulting amplitude is the product of the amplitude values, and the resulting rate/lifetime
    is the product of the corresponding second values.

    :param e1: array_like
        First interleaved spectrum.
    :param e2: array_like
        Second interleaved spectrum.
    :return: numpy array
        A new interleaved spectrum resulting from the element-wise multiplications.

    Examples
    --------
    >>> import numpy as np
    >>> e1 = np.array([1, 2, 3, 4])
    >>> e2 = np.array([5, 6, 7, 8])
    >>> e1ti2(e1, e2)
    array([ 5., 12.,  7., 16., 15., 24., 21., 32.])
    """
    amplitudes = np.outer(e1[0::2], e2[0::2])
    lifetimes = np.outer(e1[1::2], e2[1::2])

    r = np.empty(amplitudes.size * 2, dtype=np.float64)
    r[0::2] = amplitudes.ravel()
    r[1::2] = lifetimes.ravel()
    return r


def pairwise(iterable):
    """Generate successive overlapping pairs from an iterable.

    Example: s -> (s0, s1), (s1, s2), (s2, s3), ...

    :param iterable: iterable
        An iterable sequence.
    :return: iterator
        An iterator over pairs of consecutive elements.
    """
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)
