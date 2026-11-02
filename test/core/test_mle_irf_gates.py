"""The auto IRF of a gated detector is taken inside its gate: a PIE acceptor's channels carry the
other laser's pulse too, and taking that as its IRF drove every lifetime fit to the period."""

from __future__ import annotations

import numpy as np
import tttrlib

from chisurf.core.fluorescence.burst import extract_mle_irf_background


def _tttr():
    rng = np.random.default_rng(0)
    n_prompt, n_delayed = 2000, 8000  # the delayed (direct-excitation) pulse is the stronger one
    micro = np.concatenate([rng.normal(150, 3, n_prompt), rng.normal(2150, 3, n_delayed)])
    micro = np.clip(micro, 0, 3999).astype(np.uint16)
    order = rng.permutation(micro.size)
    t = tttrlib.TTTR()
    t.append_events(
        np.arange(micro.size, dtype=np.uint64) * 100,
        micro[order],
        np.ones(micro.size, dtype=np.int8),
        np.zeros(micro.size, dtype=np.int8),
    )
    t.header.set_tag("MeasDesc_NumberMicrotimes", 4000, 268435464)
    return t


def test_a_gated_detector_takes_its_own_pulse_as_irf():
    t = _tttr()
    detectors = {
        "red": {"chs": [1], "micro_time_ranges": [[0, 2000]]},
        "yellow": {"chs": [1], "micro_time_ranges": [[2000, 4000]]},
        "ungated": {"chs": [1], "micro_time_ranges": []},
    }
    patterns = extract_mle_irf_background(
        t, detectors, micro_time_binning=1, mask=np.ones(len(t), dtype=bool), irf_model="raw"
    )

    def peak(name):
        irf = np.asarray(patterns[name]["irf"])
        return int(np.argmax(irf[: irf.size // 2]))

    assert abs(peak("red") - 150) < 15
    assert abs(peak("yellow") - 2150) < 15
    assert abs(peak("ungated") - 2150) < 15  # without a gate: the stronger pulse, as before
