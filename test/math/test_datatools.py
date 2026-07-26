import pytest
import numpy as np
import chisurf.core.math.datatools as dt

@pytest.mark.parametrize("distances, separation, sigma, normalize, expected_sum", [
    (np.linspace(0, 10, 100), 5.0, 1.0, True, 1.0),
    (np.linspace(0, 10, 100), 5.0, 1.0, False, None), # Sum depends on spacing
    (np.array([5.0]), 5.0, 1.0, True, 1.0),
    (np.array([]), 5.0, 1.0, True, 0.0), # Empty input
    (np.array([np.nan, 5.0]), 5.0, 1.0, True, 1.0), # NaN handling
])
def test_distance_between_gaussian(distances, separation, sigma, normalize, expected_sum):
    result = dt.distance_between_gaussian(distances, separation, sigma, normalize=normalize)
    assert result.shape == distances.shape
    assert np.all(result[~np.isnan(result)] >= 0)
    if normalize and distances.size > 0:
        assert np.isclose(np.sum(result), expected_sum)

def test_histogram_rebin():
    counts = np.array([0, 2, 1])
    bin_edges = np.array([0, 5, 10, 15])
    new_bin_edges = np.array([-5, 2.5, 7.5, 12.5, 20])
    
    rebinded = dt.histogram_rebin(bin_edges, counts, new_bin_edges)
    # new_bin_edges: -5 (out -> 0), 2.5 (bin 0-5 -> counts[0]=0), 7.5 (bin 5-10 -> counts[1]=2), 
    #                12.5 (bin 10-15 -> counts[2]=1), 20 (out -> 0)
    expected = [0.0, 0, 2, 1, 0.0]
    assert rebinded == expected


def test_histogram_rebin_upper_edge():
    """The largest original edge is inside the histogram, not out of range."""
    counts = np.array([0, 2, 1])
    bin_edges = np.array([0, 5, 10, 15])

    # the upper edge closes the last bin (np.histogram convention)
    assert dt.histogram_rebin(bin_edges, counts, np.array([15.0])) == 1.0
    # the lower edge opens the first one, anything beyond either is zero
    assert dt.histogram_rebin(bin_edges, counts, np.array([0.0])) == 0.0
    assert dt.histogram_rebin(bin_edges, counts, np.array([15.001])) == 0.0
    assert dt.histogram_rebin(bin_edges, counts, np.array([-0.001])) == 0.0

    # every value is a plain float, whatever dtype the counts have
    rebinned = dt.histogram_rebin(bin_edges, counts, np.array([2.5, 7.5, 15.0]))
    assert rebinned == [0.0, 2.0, 1.0]
    assert all(type(v) is float for v in rebinned)


def test_bin_count():
    data = np.array([0, 10, 20, 30, 4000])
    bins, counts = dt.bin_count(data, bin_width=100, bin_min=0, bin_max=4000)
    assert bins.shape == counts.shape
    assert counts[0] == 4 # 0, 10, 20, 30 are in first bin [0, 100)
    assert counts[-1] == 0 # 4000 is bin_max, bin_index = 40. n_bins = 40. 40 < 40 is false.

def test_bin_count_empty():
    bins, counts = dt.bin_count(np.array([]), bin_width=100)
    assert counts.sum() == 0


def test_minmax():
    x = np.array([0, 1, 2, 3, 4, 5])
    assert dt.minmax(x) == (0, 5)
    assert dt.minmax(x, ignore_zero=True) == (1, 5)
    
    x_neg = np.array([-10, 0, 10])
    assert dt.minmax(x_neg) == (-10, 10)

def test_overlapping_region():
    x1 = np.linspace(0, 10, 11)
    y1 = x1 * 2
    x2 = np.linspace(5, 15, 11)
    y2 = x2 * 3
    
    (rx1, ry1), (rx2, ry2) = dt.overlapping_region((x1, y1), (x2, y2))
    # Overlap should be [5, 10]
    assert np.all(rx1 >= 5) and np.all(rx1 <= 10)
    assert np.all(rx2 >= 5) and np.all(rx2 <= 10)
    assert np.array_equal(ry1, rx1 * 2)
    assert np.array_equal(ry2, rx2 * 3)

def test_overlapping_region_no_overlap():
    x1 = np.linspace(0, 5, 6)
    y1 = x1
    x2 = np.linspace(10, 15, 6)
    y2 = x2
    (rx1, ry1), (rx2, ry2) = dt.overlapping_region((x1, y1), (x2, y2))
    assert rx1.size == 0
    assert rx2.size == 0


def test_interleaved_conversions():
    spectrum = np.array([0.1, 1.0, 0.2, 2.0]) # amp, lifetime, amp, lifetime
    amps, lifes = dt.interleaved_to_two_columns(spectrum)
    assert np.array_equal(amps, [0.1, 0.2])
    assert np.array_equal(lifes, [1.0, 2.0])
    
    interleaved = dt.two_column_to_interleaved(amps, lifes)
    assert np.array_equal(interleaved, spectrum)

def test_invert_interleaved():
    spectrum = np.array([0.1, 2.0, 0.2, 4.0])
    inverted = dt.invert_interleaved(spectrum)
    # Amps same, lifetimes inverted (converted to rates)
    expected = np.array([0.1, 0.5, 0.2, 0.25])
    assert np.allclose(inverted, expected)

def test_smooth_is_a_real_average():
    # A constant signal is a fixed point of a moving average, edges included.
    assert np.allclose(dt.smooth(np.ones(10), 3), 1.0)
    # A unit spike is spread evenly over the (2 * m + 1) wide window.
    x = np.zeros(7)
    x[3] = 1.0
    smoothed = dt.smooth(x, 1)
    assert np.allclose(smoothed, [0, 0, 1 / 3, 1 / 3, 1 / 3, 0, 0])
    # The window is centred, not shifted: the response mirrors about the spike.
    assert np.allclose(smoothed, smoothed[::-1])


def test_smooth_clips_the_window_at_the_edges():
    # The window is clipped, never wrapped: the first element must not see the
    # tail of the array.
    x = np.array([0.0, 0.0, 0.0, 0.0, 100.0])
    assert dt.smooth(x, 1)[0] == 0.0
    # A half-window wider than the array averages everything.
    assert np.allclose(dt.smooth(np.arange(5.0), 10), 2.0)


def test_smooth_edge_cases():
    x = np.arange(10.0)
    # m <= 0 is the identity, not a zero array.
    assert np.array_equal(dt.smooth(x, 0), x)
    assert np.array_equal(dt.smooth(x, -1), x)
    # Length is preserved and no element is left uninitialized.
    for m in range(0, 6):
        smoothed = dt.smooth(x, m)
        assert smoothed.shape == x.shape
        assert np.all(np.isfinite(smoothed))
        assert np.all(smoothed >= x.min()) and np.all(smoothed <= x.max())
    assert dt.smooth(np.array([]), 2).size == 0
    # The input is not modified in place.
    assert np.array_equal(x, np.arange(10.0))

