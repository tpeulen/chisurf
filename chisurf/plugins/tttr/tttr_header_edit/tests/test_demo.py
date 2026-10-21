"""The header editor demonstration stream drives the real plugin layer with known answers.

The photons come from the shared generator (``chisurf.plugins.tttr.demo_lib``):
a deterministic µs-ALEX measurement — donor (routing 0) and acceptor (routing 1)
detectors, single-molecule bursts over a weak background, micro times from
per-channel exponential decays that begin at each channel's rise bin — so every assertion below
is a property the generator put there on purpose.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.tttr.tttr_header_edit.demo import make_demo
from chisurf.plugins.tttr.tttr_header_edit.gui.view_model import HeaderEditorViewModel


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    """Generate the demonstration stream once for this module."""
    return make_demo(tmp_path_factory.mktemp("header-edit-demo"))


def test_the_header_opens_with_the_written_resolution_tags(example):
    """The PTU tag table carries the resolutions the generator recorded."""
    vm = HeaderEditorViewModel()
    vm.load_file(str(example))
    tags = {tag.get("name") or tag.get("key", "") for tag in vm.tags}
    assert len(vm.tags) >= 5
    assert any("Micro" in name or "micro" in name for name in tags)
    assert any("Resolution" in name for name in tags)


def test_a_saved_copy_reopens_with_the_same_tags(example, tmp_path):
    """Round-tripping the header keeps the tag table intact."""
    vm = HeaderEditorViewModel()
    vm.load_file(str(example))
    copy = tmp_path / "copy.ptu"
    vm.save(str(copy))
    vm2 = HeaderEditorViewModel()
    vm2.load_file(str(copy))
    assert len(vm2.tags) == len(vm.tags)

