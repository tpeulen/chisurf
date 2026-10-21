"""The photon table demonstration stream drives the real plugin layer with known answers.

The photons come from the shared generator (``chisurf.plugins.tttr.demo_lib``):
a deterministic µs-ALEX measurement — donor (routing 0) and acceptor (routing 1)
detectors, single-molecule bursts over a weak background, micro times from
per-channel exponential decays that begin at each channel's rise bin — so every assertion below
is a property the generator put there on purpose.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.tttr.photon_table.core.model import PhotonTableModel
from chisurf.plugins.tttr.photon_table.demo import make_demo


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    """Generate the demonstration stream once for this module."""
    model = PhotonTableModel()
    model.load_file(make_demo(tmp_path_factory.mktemp("photon-table-demo")))
    return model


def test_the_table_classifies_every_record_and_channel(example):
    """All records classify, both detectors appear, and no record is lost."""
    assert set(example.used_channels) == {0, 1}
    assert sum(example.kind_counts().values()) == example.n_records
    assert example.n_photons > 250_000
    assert example.kind_counts()["photon"] == example.n_photons


def test_filtering_by_channel_partitions_the_photons(example):
    """Donor + acceptor photons add up to the total."""
    donor = example.filtered_count(channel=0)
    acceptor = example.filtered_count(channel=1)
    assert donor + acceptor == example.n_photons
    assert donor > 50_000 and acceptor > 50_000

