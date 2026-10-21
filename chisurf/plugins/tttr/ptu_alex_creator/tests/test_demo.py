"""The ALEX creator demonstration stream drives the real plugin layer with known answers.

The photons come from the shared generator (``chisurf.plugins.tttr.demo_lib``):
a deterministic µs-ALEX measurement — donor (routing 0) and acceptor (routing 1)
detectors, single-molecule bursts over a weak background, micro times from
per-channel exponential decays that begin at each channel's rise bin — so every assertion below
is a property the generator put there on purpose.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.tttr.demo_lib import DONOR_GATE, ACCEPTOR_GATE
from chisurf.plugins.tttr.ptu_alex_creator import core
from chisurf.plugins.tttr.ptu_alex_creator.demo import make_demo


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    """Generate the demonstration stream once for this module."""
    path = make_demo(tmp_path_factory.mktemp("alex-creator-demo"))
    tttr = core.load(str(path))
    folded = core.apply_alex(tttr, alex_period=8000, period_shift=0)
    regions = core.auto_excitation_regions(
        np.asarray(folded.micro_times),
        np.asarray(folded.routing_channels),
        alex_period=8000,
    )
    return path, tttr, folded, regions


def test_conversion_preserves_every_photon_and_folds_the_phase(example):
    """ALEX conversion is a re-labelling: the event count never changes."""
    _, tttr, folded, _ = example
    assert len(folded) == len(tttr)
    assert np.all(np.diff(np.asarray(folded.macro_times)) > 0)


def test_the_two_excitation_gates_are_recovered(example):
    """Phase detection finds the donor and acceptor gates the generator wrote."""
    _, _, _, regions = example
    found = regions["regions"]
    assert 2 <= len(found) <= 3
    starts = [region["start"] for region in found]
    donor_centered = any(abs(s - DONOR_GATE[0]) < 500 for s in starts)
    acceptor_centered = any(abs(s - ACCEPTOR_GATE[0]) < 500 for s in starts)
    assert donor_centered and acceptor_centered

