"""A long status line in any native hub stays left of Back / >> / Next, and Next still works.

Fixed globally rather than per hub: emtk no longer lets an id-less text claim the pointer
(emtk ``item_add``), and ``ToolHubApp`` cuts the status to its room with ``im.text_ellipsis``.
"""

from __future__ import annotations

from emtk.app import ImApp

from chisurf.emtk.tool_hub import ToolHubApp
from chisurf.plugins.emtk_test_input import Driver


class _Child(ImApp):
    def __init__(self):
        super().__init__(lambda: None)


def _hub():
    panels = [{"name": f"Step {i}", "role": f"s{i}", "factory": _Child} for i in range(3)]
    return ToolHubApp("Demo", panels)


def test_a_long_status_is_cut_before_the_buttons_and_next_takes_the_click():
    hub = _hub()
    drv = Driver(hub, (1200, 800))
    drv.draw(2)
    hub.status = "Bursts for the later steps: " + "/a/very/long/folder" * 40
    drv.draw(2)
    status, next_box = hub.item_rects["status"], hub.item_rects["next"]
    assert status[0] + status[2] <= next_box[0]
    assert hub.selected == "s0"
    drv.click_name("next")
    assert hub.selected == "s1"
