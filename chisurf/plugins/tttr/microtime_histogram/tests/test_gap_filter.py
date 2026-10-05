"""The inter-photon filter: burst photons, or with Invert the background between bursts, from one file.

This was the one thing the retired *TTTR: Generate Decay* tool could do that the
micro-time histogram could not. The real-file test reproduces that tool's own
algorithm (the retired ``tttr_histogram/gui.py: make_histogram``): select the detector's
photons, drop the last one, keep a photon when the gap to the next selected
photon is at most ``dMTmin`` ticks — or, inverted, at least ``dMTmin`` ticks.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.tttr.microtime_histogram.gui.model import HistogramModel, gap_selection

FIXTURE = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"


def test_gap_selection_keeps_close_photons_and_drops_the_last():
    selected = np.array([True, True, False, True, True, True])
    macro = np.array([0, 5, 6, 100, 104, 300])
    # selected photons at 0, 5, 100, 104, 300: gaps 5, 95, 4, 196
    np.testing.assert_array_equal(
        gap_selection(selected, macro, 10), [True, False, False, True, False, False]
    )
    np.testing.assert_array_equal(
        gap_selection(selected, macro, 10, invert=True), [False, True, False, False, True, False]
    )


def test_gap_selection_of_fewer_than_two_photons_is_empty():
    assert not gap_selection(np.array([False, True]), np.array([0, 1]), 5).any()


@pytest.mark.parametrize("invert", [False, True])
def test_the_filtered_decay_equals_the_retired_generate_decay_tool(invert):
    from chisurf.core.fio.staging import open_tttr

    if not FIXTURE.is_file():
        pytest.skip("Real PTU fixture unavailable.")
    stream = open_tttr(FIXTURE, apply_lut=False, channel_shifts={})
    micro = np.asarray(stream.micro_times, dtype=np.int64)
    macro = np.asarray(stream.macro_times, dtype=np.int64)
    routing = np.asarray(stream.routing_channels)
    gap = int(np.median(np.diff(macro[routing == 0])))  # splits the photons roughly in half

    # The retired tool, verbatim in effect.
    selected = routing == 0
    tac = np.ma.array(micro[selected][:-1])
    gaps = np.diff(macro[selected])
    tac.mask = (gaps < gap) if invert else (gaps > gap)
    n = int(stream.header.get_effective_number_of_micro_time_channels())
    expected = np.bincount(tac.compressed(), minlength=n)

    model = HistogramModel()
    model.auto_save = False
    model.polarized = False
    model.parallel, model.perpendicular = [0], []
    model.gap_filter, model.gap_ticks, model.gap_invert = True, gap, invert
    model.add_paths([FIXTURE])
    model.compute()
    got = np.asarray(model.cumulative_parallel)
    size = max(len(got), len(expected))
    np.testing.assert_array_equal(np.pad(got, (0, size - len(got))), np.pad(expected, (0, size - len(expected))))
    assert 0 < got.sum() < selected.sum()


def test_the_filter_settings_round_trip():
    model = HistogramModel()
    model.gap_filter, model.gap_ticks, model.gap_invert = True, 1234, True
    other = HistogramModel()
    other.restore_settings(model.export_settings())
    assert (other.gap_filter, other.gap_ticks, other.gap_invert) == (True, 1234, True)
