"""The FCS hub's own native test: the rail, the five tools, search and navigation, pressed on the drawn controls.

The correlator workflow inside the hub is covered by ``fcs_correlator/test/test_emtk_workflow.py``; here it is the hub
that is under test: whether every tool of its rail opens its plugin's own app, what the rail says about them and how
the user gets from one to the next.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from emtk import keys

from chisurf.plugins.fcs.fcs_correlator.test.test_emtk_workflow import Hub, hermetic  # noqa: F401
from chisurf.plugins.fcs.fcs_toolbox.gui.app import TOOLS, make_app

PLUGINS = Path(__file__).resolve().parents[2]
ROLES = ["flc_2d", "lfcs_sim", "burst_fcs", "diffusion_calc", "filter_calc"]


@pytest.fixture
def hub():
    window = Hub(make_app())
    yield window
    window.app.close()


def test_the_rail_lists_the_workflow_then_the_tools_with_their_captions(hub):
    assert hub.app.title == "FCS"
    assert [p["role"] for p in hub.app.tools] == ["channel_def", "files", "filter", "correlator", "merger", *ROLES]
    for caption in ("1. Channel Definitions", "2. Files & Steps", "3. Photon / Burst Filter", "4. Correlator",
                    "5. FCS Merger", "Tools", "Diffusion Calc", "Burst-wise FCS"):
        assert hub.shown(caption), caption
    assert hub.shown("2D-FLCS ⚠") and hub.shown("Filter Calc ⚠") and hub.shown("Lifetime-FCS Sim ⚠")
    assert not hub.shown("Diffusion Calc ⚠"), "only experimental tools carry the warning mark"


def test_every_tool_entry_names_a_real_plugin():
    for tool in TOOLS:
        manifest = PLUGINS.parent / tool["plugin"] / "manifest.json"
        assert manifest.is_file(), tool
        assert json.loads(manifest.read_text())["display_name"], tool
        assert tool["description"].strip() and tool["icon"]


@pytest.mark.parametrize("role", ROLES)
def test_pressing_a_tool_in_the_rail_opens_that_plugins_app(hub, role):
    hub.nav(role)
    assert hub.app.selected == role, hub.app.errors
    assert role not in hub.app.errors
    assert hub.child is not None
    painter = hub.draw(3)
    assert len(painter.texts) > 5, f"{role} drew nothing"
    # its controls are inside the hub's child window
    bx, by, bw, bh = hub.app.child_box
    assert bw > 200 and bh > 200
    # the tool stays alive when the user moves on and comes back
    hub.nav("files")
    assert hub.app.selected == "files"
    hub.nav(role)
    assert hub.app.selected == role


def test_a_tool_that_is_experimental_shows_its_banner_when_open(hub):
    hub.nav("filter_calc")
    assert hub.shown("experimental")
    hub.nav("diffusion_calc")
    assert not hub.shown("experimental")


def test_back_and_next_walk_the_workflow_and_stop_at_its_ends(hub):
    assert hub.app.selected == "files"
    hub.nav("channel_def")
    assert hub.app.selected == "channel_def"
    hub.click("back")
    assert hub.app.selected == "channel_def", "Back at the first step stays there"
    hub.click("next")
    assert hub.app.selected == "files"
    hub.nav("merger")
    hub.click("next")
    assert hub.app.selected == "flc_2d", "after the last step Next goes on to the first tool"
    hub.click("back")
    assert hub.app.selected == "merger"


def test_the_search_box_filters_the_rail(hub):
    hub.click("search", fx=0.3)
    for ch in "diffus":
        hub.app.key(ord(ch), ch)
        hub.draw(1)
    assert hub.app.filter == "diffus"
    assert hub.shown("Diffusion Calc")
    assert not hub.shown("Burst-wise FCS") and not hub.shown("4. Correlator")
    hub.press_text("Diffusion Calc")
    assert hub.app.selected == "diffusion_calc"
    # a query that matches nothing says so
    hub.click("search", fx=0.3)
    hub.app.key(keys.KEY_END, "")
    hub.draw(1)
    for ch in "zzz":
        hub.app.key(ord(ch), ch)
        hub.draw(1)
    assert hub.shown("No matching tools.")
