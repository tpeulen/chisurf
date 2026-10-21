"""The LUT tools demonstration stream drives the real plugin layer with known answers.

The photons come from the shared generator (``chisurf.plugins.tttr.demo_lib``):
a deterministic µs-ALEX measurement — donor (routing 0) and acceptor (routing 1)
detectors, single-molecule bursts over a weak background, micro times from
per-channel exponential decays that begin at each channel's rise bin — so every assertion below
is a property the generator put there on purpose.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.tttr.tttr_lut_tools.core.tac_lut import (
    compute_lut_from_files,
    load_microtimes,
)
from chisurf.plugins.tttr.tttr_lut_tools.demo import make_demo


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    """Generate the demonstration stream once for this module."""
    path = make_demo(tmp_path_factory.mktemp("lut-demo"))
    micro = load_microtimes([str(path)])
    return micro, compute_lut_from_files([str(path)], n_bins=4096)


def test_the_lut_spans_all_bins_and_is_monotonic(example):
    """The fractional LUT rises to the full scale without going backwards."""
    micro, lut = example
    fract = np.asarray(lut["NTAC_fract"], dtype=float)
    assert lut["n_bins"] == 4096
    assert fract.size == 4096
    assert np.all(np.diff(fract) >= -1e-9)
    assert fract[-1] == pytest.approx(4096.0)


def test_the_linear_region_is_detected_inside_the_decay(example):
    """The auto-detected linear region sits inside the used micro-time range."""
    micro, lut = example
    assert len(micro) > 100_000
    assert 0 < int(lut["linear_start"]) < int(lut["linear_stop"]) <= 4096

