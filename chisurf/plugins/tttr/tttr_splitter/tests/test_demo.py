"""The splitter demonstration stream drives the real plugin layer with known answers.

The photons come from the shared generator (``chisurf.plugins.tttr.demo_lib``):
a deterministic µs-ALEX measurement — donor (routing 0) and acceptor (routing 1)
detectors, single-molecule bursts over a weak background, micro times from
per-channel exponential decays that begin at each channel's rise bin — so every assertion below
is a property the generator put there on purpose.
"""

from __future__ import annotations

import tttrlib
import pytest

from chisurf.plugins.tttr.tttr_splitter.demo import make_demo
from chisurf.plugins.tttr.tttr_splitter.gui.view_model import SplitterViewModel


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    """Generate the demonstration stream once for this module."""
    path = make_demo(tmp_path_factory.mktemp("splitter-demo"))
    vm = SplitterViewModel()
    vm.set_tttr(tttrlib.TTTR(str(path)), str(path))
    vm.output_folder = str(path.parent / "out")
    vm.output_format = "PTU"
    vm.photons_per_file_k = 300
    vm.split_files = True
    total = len(vm.tttr)
    sub = vm.do_split()
    return total, sub, sorted(sub.glob("*.ptu"))


def test_splitting_preserves_every_photon_across_chunks(example):
    """Two chunks reassemble to exactly the source event count."""
    total, _, outs = example
    assert len(outs) > 1
    assert sum(len(tttrlib.TTTR(str(out), "PTU")) for out in outs) == total


def test_can_split_demands_a_loaded_file():
    """The guard still refuses to run without a source."""
    assert SplitterViewModel().can_split() is not None

