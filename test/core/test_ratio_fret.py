"""Ratiometric FRET: the acceptor/donor trace and map.

The cheapest FRET readout there is, and the easiest to misuse. These tests pin
the two things that matter: that the ratio reports *change* correctly when
normalised to a baseline, and that the median filtering which makes a ratio map
usable also costs real spatial resolution — a feature smaller than the kernel
disappears entirely.
"""
from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.imaging.ratio_fret import (
    RatioTrace,
    ratio_image,
    ratio_trace,
)
from chisurf.core.roi.roi import RectangleROI


# --- the trace -------------------------------------------------------------
def test_trace_reports_fold_change_from_the_baseline():
    """Normalised to rest, the trace reads 1.0 before and the fold-change after."""
    d = np.ones((6, 4, 4))
    a = np.ones((6, 4, 4))
    a[3:] = 2.0

    t = ratio_trace(d, a, baseline=(0, 3), frame_time=0.5)
    np.testing.assert_allclose(t.ratio, [1, 1, 1, 2, 2, 2])
    np.testing.assert_allclose(t.time, [0.0, 0.5, 1.0, 1.5, 2.0, 2.5])
    assert t.normalisation == pytest.approx(1.0)


def test_an_unnormalised_trace_reports_the_raw_ratio():
    """Without a baseline the absolute ratio is kept, whatever it means."""
    d = np.full((4, 4, 4), 100.0)
    a = np.full((4, 4, 4), 25.0)
    t = ratio_trace(d, a)
    np.testing.assert_allclose(t.ratio, 0.25)
    assert t.normalisation == 1.0


def test_normalisation_divides_out_an_arbitrary_resting_ratio():
    """Two sensors with different resting ratios give the same fold-change.

    This is why the trace is normalised: the absolute A/D depends on expression
    level, filters and detector gain, none of which are the biology.
    """
    d = np.ones((6, 4, 4))
    bright = np.ones((6, 4, 4)) * 3.0
    dim = np.ones((6, 4, 4)) * 0.2
    bright[3:] *= 1.5
    dim[3:] *= 1.5

    t_bright = ratio_trace(d, bright, baseline=(0, 3))
    t_dim = ratio_trace(d, dim, baseline=(0, 3))
    np.testing.assert_allclose(t_bright.ratio, t_dim.ratio)
    assert t_bright.normalisation != t_dim.normalisation


def test_both_channels_are_kept_so_a_move_can_be_attributed():
    """A ratio that changes is ambiguous until you see which channel moved."""
    d = np.ones((4, 4, 4))
    a = np.ones((4, 4, 4))
    d[2:] = 0.5                       # the donor fell; the acceptor did not

    t = ratio_trace(d, a)
    np.testing.assert_allclose(t.ratio, [1, 1, 2, 2])
    np.testing.assert_allclose(t.donor, [1, 1, 0.5, 0.5])
    np.testing.assert_allclose(t.acceptor, 1.0)


def test_a_region_restricts_the_trace():
    """Averaging over a region ignores everything outside it."""
    d = np.ones((3, 8, 8))
    a = np.ones((3, 8, 8))
    a[:, :4, :] = 5.0                 # only the top half responds

    whole = ratio_trace(d, a).ratio
    top = ratio_trace(d, a, roi=RectangleROI(-0.5, -0.5, 7.5, 3.5)).ratio
    np.testing.assert_allclose(top, 5.0)
    assert whole[0] == pytest.approx(3.0)      # averaged with the quiet half


def test_response_summarises_the_excursion():
    """The single number a sensor experiment reports."""
    d = np.ones((5, 4, 4))
    a = np.ones((5, 4, 4))
    a[2] = 1.4
    t = ratio_trace(d, a, baseline=(0, 2))
    assert t.response == pytest.approx(0.4, abs=1e-9)


def test_mismatched_or_wrong_shaped_channels_are_rejected():
    """Two channels of different shape cannot be divided."""
    with pytest.raises(ValueError):
        ratio_trace(np.ones((4, 4, 4)), np.ones((4, 8, 8)))
    with pytest.raises(ValueError):
        ratio_trace(np.ones((4, 4)), np.ones((4, 4)))


def test_an_empty_baseline_is_rejected():
    """A baseline outside the stack cannot normalise anything."""
    d = np.ones((3, 4, 4))
    with pytest.raises(ValueError):
        ratio_trace(d, d, baseline=[10, 11])


def test_trace_serialises():
    """JSON-friendly for the CLI and RPC paths."""
    import json

    d = np.ones((4, 4, 4))
    a = np.ones((4, 4, 4)) * 2
    restored = json.loads(json.dumps(ratio_trace(d, a, frame_time=0.25).to_dict()))
    assert restored["time"][-1] == pytest.approx(0.75)
    assert restored["ratio"][0] == pytest.approx(2.0)


# --- the map ---------------------------------------------------------------
def test_map_gives_the_expected_ratio_per_region():
    """A patch with twice the acceptor reads twice the ratio."""
    d = np.full((10, 32, 32), 100.0)
    a = np.full((10, 32, 32), 50.0)
    a[:, 8:24, 8:24] = 200.0

    m = ratio_image(d, a)
    assert float(np.nanmedian(m[28:, 28:])) == pytest.approx(0.5, abs=1e-9)
    assert float(np.nanmedian(m[12:20, 12:20])) == pytest.approx(2.0, abs=1e-9)


def test_the_median_filter_erases_features_smaller_than_its_kernel():
    """Denoising a ratio map is not free: it costs spatial resolution.

    A 4x4 feature vanishes under the default 5x5 ratio filter. Worth knowing
    before concluding that a small structure has no FRET signal.
    """
    d = np.full((10, 16, 16), 100.0)
    a = np.full((10, 16, 16), 50.0)
    a[:, 4:8, 4:8] = 200.0            # 4x4, smaller than the 5x5 kernel

    filtered = ratio_image(d, a)
    raw = ratio_image(d, a, channel_median=0, ratio_median=0)

    assert float(np.nanmedian(raw[5:7, 5:7])) == pytest.approx(2.0, abs=1e-9)
    assert float(np.nanmedian(filtered[5:7, 5:7])) == pytest.approx(0.5, abs=1e-9)


def test_dim_donor_pixels_are_excluded_not_divided():
    """Where the donor is dark the ratio is undefined, and says so."""
    d = np.full((5, 16, 16), 100.0)
    d[:, 0:2, :] = 0.0
    a = np.full((5, 16, 16), 50.0)

    m = ratio_image(d, a, minimum_donor=1.0)
    assert np.all(np.isnan(m[0:2, :]))
    assert np.isfinite(m[8:, :]).all()


def test_negative_intensities_do_not_flip_the_ratio():
    """Background subtraction can push pixels negative; that is not a signal."""
    d = np.full((4, 12, 12), 50.0)
    a = np.full((4, 12, 12), 25.0)
    a[:, :3, :3] = -30.0              # over-subtracted corner

    m = ratio_image(d, a, ratio_median=0, channel_median=0)
    finite = m[np.isfinite(m)]
    assert (finite >= 0).all(), "a clipped channel must not produce a negative ratio"


def test_regions_restrict_the_map():
    """Pixels outside either channel's region are not part of the map."""
    d = np.full((4, 16, 16), 100.0)
    a = np.full((4, 16, 16), 50.0)
    roi = RectangleROI(3.5, 3.5, 11.5, 11.5)

    m = ratio_image(d, a, donor_roi=roi, ratio_median=0, channel_median=0)
    assert np.isnan(m[0, 0])
    assert np.isfinite(m[8, 8])


def test_frame_selection_picks_the_window():
    """Only the requested frames are averaged into the map."""
    d = np.ones((10, 8, 8))
    a = np.ones((10, 8, 8))
    a[5:] = 4.0

    early = ratio_image(d, a, frames=(0, 5), ratio_median=0, channel_median=0)
    late = ratio_image(d, a, frames=(5, 10), ratio_median=0, channel_median=0)
    assert float(np.nanmedian(early)) == pytest.approx(1.0)
    assert float(np.nanmedian(late)) == pytest.approx(4.0)


def test_map_and_trace_share_a_normalisation():
    """Passing the trace's normalisation puts the map on the fold-change scale."""
    d = np.ones((8, 12, 12))
    a = np.ones((8, 12, 12)) * 4.0
    a[4:] = 8.0

    trace = ratio_trace(d, a, baseline=(0, 4))
    m = ratio_image(d, a, frames=(4, 8), normalisation=trace.normalisation,
                    ratio_median=0, channel_median=0)
    assert trace.normalisation == pytest.approx(4.0)
    assert float(np.nanmedian(m)) == pytest.approx(2.0)
    assert trace.ratio[-1] == pytest.approx(2.0)


def test_no_valid_frame_is_rejected():
    """A frame selection outside the stack fails loudly."""
    d = np.ones((3, 4, 4))
    with pytest.raises(ValueError, match="no valid frame"):
        ratio_image(d, d, frames=[7, 8])
