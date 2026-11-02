"""A detector without micro-time gates may come without the ``micro_time_ranges`` key.

A setup proposed from a file (detectors ch0..ch3, no gates) carried into the data's channels writes
the key only for gated detectors; the burst summary read it unconditionally and the Burst
Selection preview failed with ``Diagnostics unavailable: 'micro_time_ranges'``.
"""

from pathlib import Path

import numpy as np

from chisurf.core.datastore import numeric_column
from chisurf.plugins.burst.burst_selection.api.selection import summarize_bursts
from chisurf.plugins.burst.burst_selection.api.io import load_tttr

DATA = Path(__file__).resolve().parents[2] / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000.spc"


def test_a_detector_without_the_gate_key_is_ungated():
    tttr = load_tttr(DATA)
    start_stop = np.array([[0, 99], [200, 399]])
    without = summarize_bursts(start_stop, DATA, tttr, windows={}, detectors={"ch0": {"chs": [0]}})
    empty = summarize_bursts(start_stop, DATA, tttr, windows={},
                             detectors={"ch0": {"chs": [0], "micro_time_ranges": []}})
    a = numeric_column(without, "Number of Photons (ch0)")
    b = numeric_column(empty, "Number of Photons (ch0)")
    assert np.array_equal(a, b, equal_nan=True) and np.nansum(a) > 0
