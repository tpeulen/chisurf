"""The IRF tool's background rate is fitted in a seeded window, not the far-tail fraction rule.

On a measurement whose non-burst stream is the same on both detectors, the fraction rule
(80 % of the longest gap) left a few one-count bins and reported 0.69 / 0.15 kHz where an
exact tail estimate of the same photons is ~1.9 kHz on both.
"""

from __future__ import annotations

import numpy as np
import tttrlib

from chisurf.core.fluorescence.burst import extract_irf_background, non_burst_mask
from chisurf.plugins.burst.burst_irf_bg.test.demo_data import IRF_PEAK_NS, build

DETECTORS = {"green": {"chs": [0], "micro_time_ranges": [[0, 4096]]},
             "red": {"chs": [1], "micro_time_ranges": [[0, 4096]]}}


def test_background_rates_agree_with_the_exact_tail_estimate(tmp_path):
    path = build(tmp_path / "measurement")
    tttr = tttrlib.TTTR(str(path), "SPC-130")
    keep = non_burst_mask(tttr, min_photons=60, photon_window=10, time_window=1e-3)
    result = extract_irf_background(tttr, DETECTORS, mask=keep)
    rout = np.asarray(tttr.routing_channel)
    macro = np.asarray(tttr.macro_times, dtype=np.int64)
    scale_ms = tttr.header.macro_time_resolution * 1e3
    for name, det in DETECTORS.items():
        dt = np.diff(macro[np.isin(rout, det["chs"]) & keep].astype(float)) * scale_ms
        exact = 1.0 / np.mean(dt[dt > 1.0] - 1.0)               # MLE of an exponential tail past 1 ms
        assert abs(result[name].background_khz - exact) / exact < 0.15, (name, result[name].background_khz, exact)
        assert abs(result[name].prompt_ns - IRF_PEAK_NS) < 0.15
    rates = [result[n].background_khz for n in DETECTORS]
    assert abs(rates[0] - rates[1]) / max(rates) < 0.05          # the same stream on both detectors
