"""The count-rate analysis demonstration stream drives the real plugin layer with known answers.

The photons come from the shared generator (``chisurf.plugins.tttr.demo_lib``):
a deterministic µs-ALEX measurement — donor (routing 0) and acceptor (routing 1)
detectors, single-molecule bursts over a weak background, micro times from
per-channel exponential decays that begin at each channel's rise bin — so every assertion below
is a property the generator put there on purpose.
"""

from __future__ import annotations

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.tttr.tttr_count_rate_analysis.cli import (
    calculate_count_rates,
    get_channels_from_setup,
)
from chisurf.plugins.tttr.tttr_count_rate_analysis.demo import make_demo


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    """Generate the demonstration stream once for this module."""
    path = make_demo(tmp_path_factory.mktemp("count-rate-demo"))
    setup = {
        "windows": {"": None},
        "detectors": {
            "donor": {"chs": [0], "micro_time_ranges": [[0, 4095]]},
            "acceptor": {"chs": [1], "micro_time_ranges": [[0, 4095]]},
        },
    }
    rates, counts, times = calculate_count_rates([str(path)], get_channels_from_setup(setup))
    return path, rates[str(path)], counts[str(path)], times[str(path)]


def test_the_reported_rates_match_the_stream(example):
    """Donor rate = donor photons / duration, to better than one percent."""
    path, rates, _, times = example
    tttr = tttrlib.TTTR(str(path))
    macro = np.asarray(tttr.macro_times)
    duration = float(macro[-1] - macro[0]) * tttr.header.macro_time_resolution
    donor_key = next(key for key in rates if key.endswith("donor"))
    n_donor = int((np.asarray(tttr.routing_channels) == 0).sum())
    assert rates[donor_key] == pytest.approx(n_donor / duration, rel=0.01)


def test_both_detectors_are_reported(example):
    """One rate per detector channel."""
    _, rates, _, _ = example
    assert len(rates) == 2
    assert all(rate > 0 for rate in rates.values())

