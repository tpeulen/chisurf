"""The micro-time shifter demonstration stream drives the real plugin layer with known answers.

The photons come from the shared generator (``chisurf.plugins.tttr.demo_lib``):
a deterministic µs-ALEX measurement — donor (routing 0) and acceptor (routing 1)
detectors, single-molecule bursts over a weak background, micro times from
per-channel exponential decays that begin 500 bins apart on the two channels (donor 400, acceptor 900) — so every assertion below
is a property the generator put there on purpose.
"""

from __future__ import annotations

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.tttr.tttr_microtime_shifter.api.shift import shift_file
from chisurf.plugins.tttr.tttr_microtime_shifter.demo import make_demo


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    """Generate the demonstration stream once for this module."""
    path = make_demo(tmp_path_factory.mktemp("shifter-demo"))
    src = tttrlib.TTTR(str(path), "SPC-130")
    micro = np.asarray(src.micro_times)
    routing = np.asarray(src.routing_channels)
    offset = int(micro[routing == 1].min()) - int(micro[routing == 0].min())
    out, applied = shift_file(
        str(path),
        channel_shifts={1: -offset},
        filetype="SPC-130",
        output_dir=str(path.parent / "shifted"),
    )
    n_source = len(src)
    return offset, applied, out, n_source


def test_the_channel_offset_is_the_generator_rise_difference(example):
    """The acceptor decay starts exactly 500 bins after the donor's."""
    offset, _, _, _ = example
    assert offset == 500


def test_shifting_aligns_the_channels_without_losing_photons(example):
    """After the shift both channels' decays begin at the same bin."""
    offset, applied, out, n_source = example
    fixed = tttrlib.TTTR(str(out), "SPC-130")
    micro = np.asarray(fixed.micro_times)
    routing = np.asarray(fixed.routing_channels)
    assert applied[1] % 4096 == (4096 - offset) % 4096
    assert len(fixed) == n_source
    assert int(micro[routing == 1].min()) - int(micro[routing == 0].min()) <= 1

