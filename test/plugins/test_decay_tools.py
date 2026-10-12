"""The decay tools are ordinary Spectroscopy > Decay tools, not panels of a hub."""

from __future__ import annotations

import pathlib

import pytest

import chisurf.plugins
from chisurf.core.plugin.manifest import load_manifest

ROOT = pathlib.Path(chisurf.plugins.__file__).parent

#: plugin dir -> ribbon title
TOOLS = {
    "fluorescence_decay/irf_estimator": "IRF Estimation",
    "fluorescence_decay/maxent_decay": "MaxEnt MEM",
    "fluorescence_decay/lltf": "Lazy Lifetime Analysis",
    "tttr/microtime_histogram": "Histogram-Microtime",
    "vv_vh_g_factor": "VV/VH G-Factor Calculator",
    "vv_vh_anisotropy": "VV/VH Anisotropy Decay",
    "fluorescence_decay/synthetic_decay": "Synthetic Decay Generator",
}


@pytest.mark.parametrize("rel, title", TOOLS.items())
def test_each_decay_tool_is_a_visible_decay_group_tool(rel, title):
    manifest = load_manifest(ROOT / rel / "manifest.json")
    assert manifest is not None
    assert manifest.display_name == f"Spectroscopy:Decay:{title}"
    assert manifest.menu_hidden is False
    assert manifest.entrypoints.emtk
    gui = ROOT / rel / "gui"
    assert (gui.exists() and any(gui.glob("*guide*.json"))) or (ROOT / rel / "guide.json").exists()


def test_only_unvalidated_tools_are_experimental():
    flagged = {
        rel
        for rel in TOOLS
        if load_manifest(ROOT / rel / "manifest.json").experimental
    }
    assert flagged == {"fluorescence_decay/lltf"}


def test_the_decay_hub_is_gone():
    assert not (ROOT / "fluorescence_decay" / "lifetime_analysis").exists()
