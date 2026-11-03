"""Data Selection takes workspace photons by a drag down into the step or by its context menu.

A row of the Input table dragged out and let go below it (on the step's own file list) is handed
over, like *Use selected*; let go back on the table it is not. A right click offers *Add to this
tool*.
"""

from __future__ import annotations

from emtk.events import LEFT_BUTTON, RIGHT_BUTTON
from emtk.testing import Driver

from chisurf.core.plugin.workspace_input import register_result

from .test_emtk_native_hub import files, hub  # noqa: F401 - fixtures


def _row(drv, name):
    hits = [t for t in drv.frame().texts if t[5] == name]
    assert hits, f"{name} is not in the Input table"
    x, y, w, h = hits[0][:4]
    return x + 4.0, y + h / 2.0


def _drag(drv, start, end):
    drv.hover(start)
    drv.surface.on_pointer_press(*start, LEFT_BUTTON, 0)
    drv.frame()
    for k in range(1, 9):
        point = (start[0] + (end[0] - start[0]) * k / 8, start[1] + (end[1] - start[1]) * k / 8)
        drv.surface.on_pointer_move(*point, LEFT_BUTTON, 0)
        drv.frame()
    drv.surface.on_pointer_release(*end, LEFT_BUTTON, 0)
    drv.frame(3)


def test_a_workspace_row_dragged_down_or_added_from_its_menu_is_taken(hub, files):  # noqa: F811
    drv = Driver(hub, size=(1200, 760))
    hub.select("data")
    drv.draw(4)
    data = hub.children["data"]
    register_result(str(files[0]), kind="photons")
    register_result(str(files[1]), kind="photons")
    drv.draw(3)
    taken = lambda: [str(p) for p in data.model.paths()]  # noqa: E731
    assert taken() == []
    first = _row(drv, files[0].name)
    _drag(drv, first, (first[0] + 2.0, first[1] + 6.0))  # let go on the table: nothing
    assert taken() == []
    _drag(drv, first, (first[0], first[1] + 300.0))  # down into the step's file list
    assert [p.endswith(files[0].name) for p in taken()] == [True]
    second = _row(drv, files[1].name)
    drv.hover(second)
    drv.surface.on_pointer_press(*second, RIGHT_BUTTON, 0)
    drv.surface.on_pointer_release(*second, RIGHT_BUTTON, 0)
    drv.frame(2)
    drv.click("Add to this tool")
    drv.frame(3)
    assert sorted(p.rsplit("/", 1)[-1] for p in taken()) == sorted(f.name for f in files)
