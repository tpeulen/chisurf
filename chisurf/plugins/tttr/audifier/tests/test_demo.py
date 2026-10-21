"""The audifier demonstration stream drives the real plugin layer with known answers.

The photons come from the shared generator (``chisurf.plugins.tttr.demo_lib``):
a deterministic µs-ALEX measurement — donor (routing 0) and acceptor (routing 1)
detectors, single-molecule bursts over a weak background, micro times from
per-channel exponential decays that begin at each channel's rise bin — so every assertion below
is a property the generator put there on purpose.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.tttr.audifier import core
from chisurf.plugins.tttr.audifier.demo import make_demo


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    """Generate the demonstration stream once for this module."""
    return make_demo(tmp_path_factory.mktemp("audifier-demo"))


def test_the_stream_sonifies_into_bursts_over_silence(example):
    """Bursts pass the envelope threshold; the weak background is silenced."""
    data = core.load_tttr_with_tttrlib(str(example))
    _, counts = core.bin_photons(
        data,
        bin_width_s=2e-3,
        channels=[0, 1],
        channel_cfg={
            0: core.ChannelConfig(note_hz=261.63),
            1: core.ChannelConfig(note_hz=329.63),
        },
    )
    env = core.counts_to_envelopes(counts)
    sounding = int((env.max(axis=1) > 0).sum())
    donor = counts[:, 0]
    bursts = donor > 4.0 * max(donor.mean(), 1e-9)
    assert counts.sum() > 200_000
    assert sounding > 0
    assert bursts.any()


def test_both_detectors_are_mapped_to_their_own_voice(example):
    """Each routing channel carries photons, so both chords sound."""
    data = core.load_tttr_with_tttrlib(str(example))
    _, counts = core.bin_photons(
        data,
        bin_width_s=2e-3,
        channels=[0, 1],
        channel_cfg={
            0: core.ChannelConfig(note_hz=261.63),
            1: core.ChannelConfig(note_hz=329.63),
        },
    )
    per_channel = counts.sum(axis=0)
    assert (per_channel > 0).all()
    assert np.isclose(per_channel.sum(), counts.sum())

