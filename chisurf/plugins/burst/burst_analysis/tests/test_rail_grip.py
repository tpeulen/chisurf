"""The steps rail resizes by its right edge and folds to its icons when narrow, as a dock folds.

The grip is centred on the edge and drawn over the tool: grabbed on either side of the line it
drags (the half over the tool once belonged to the tool's window and could not be hit).
"""

from __future__ import annotations

from emtk.events import LEFT_BUTTON
from emtk.testing import Driver

from chisurf.emtk.tool_hub import RAIL_FOLD, RAIL_FOLDED, RAIL_GRIP

from .test_emtk_native_hub import files, hub  # noqa: F401 - fixtures


def _drag(drv, x0, dx, y=400.0):
    drv.hover((x0, y))
    drv.surface.on_pointer_press(x0, y, LEFT_BUTTON, 0)
    drv.frame()
    for k in range(1, 9):
        drv.surface.on_pointer_move(x0 + dx * k / 8, y, LEFT_BUTTON, 0)
        drv.frame()
    drv.surface.on_pointer_release(x0 + dx, y, LEFT_BUTTON, 0)
    drv.frame(3)


def test_the_rail_edge_drags_from_either_side_folds_and_is_saved(hub):  # noqa: F811
    drv = Driver(hub, size=(1200, 700))
    drv.draw(4)
    left = hub.rail_width_now(1200)
    _drag(drv, left + RAIL_GRIP / 2, 100)  # grabbed over the tool
    assert hub.rail_width == left + 100 and not hub.rail_folded
    _drag(drv, left + 100 - RAIL_GRIP / 2, -60)  # grabbed over the rail
    assert hub.rail_width == left + 40
    assert hub.export_settings()["rail_width"] == left + 40
    _drag(drv, left + 40, -(left + 40 - RAIL_FOLD) - 40)
    assert hub.rail_folded and hub.rail_width_now(1200) == RAIL_FOLDED
    shown = [t[5] for t in drv.frame().texts]
    assert "Search…" not in shown  # folded: the icons only
    _drag(drv, RAIL_FOLDED, 200)
    assert not hub.rail_folded
