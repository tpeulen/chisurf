"""FRET live-view colour and histogram dynamic-range contracts."""
import numpy as np


def test_histogram_log_mapping_preserves_zeros_and_makes_low_peaks_visible():
    from chisurf.plugins.core.acq.gui.record_app import _histogram_display_grid
    data = np.array([[0., 1.], [10., 10000.]])
    scaled, upper = _histogram_display_grid(data, 'log', 0)
    assert scaled[0, 0] == 0
    assert 0 < scaled[0, 1] < scaled[1, 0] < scaled[1, 1] == upper
    assert scaled[1, 0] / upper > data[1, 0] / data[1, 1]
    assert data[1, 1] == 10000


def test_histogram_cap_only_changes_display_not_raw_counts():
    from chisurf.plugins.core.acq.gui.record_app import _histogram_display_grid
    data = np.array([[0., 1.], [10., 100.]])
    scaled, upper = _histogram_display_grid(data, 'linear', 10)
    assert upper == 10 and scaled[-1, -1] == 10 and data[-1, -1] == 100


def test_overlap_white_represents_donor_and_acceptor_same_bin():
    from chisurf.plugins.core.acq.gui.record_app import _trace_overlap
    donor = np.array([0, 2, 8, 3])
    acceptor = np.array([4, 0, 3, 7])
    assert np.array_equal(_trace_overlap(donor, acceptor), [0, 0, 3, 3])
