"""The map panel edits the map that is on screen, not the first one ever loaded.

Reported as *"load demo emdb, load other demo, map still in map level adj
tool"*. The panel prefers the active object's map and otherwise searched
``_objects`` — which is **insertion-ordered** — forwards, so with two maps
loaded and anything else active it kept editing the first. The levels and the
histogram then described a map that was not the one being drawn, which is worse
than showing nothing: both are pictures of a map and neither says which.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("qtpy")


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(qapp):
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )

    win = MolViewPluginWindow()
    win.resize(800, 600)
    win.show()
    for _ in range(4):
        qapp.processEvents()
    yield win, qapp
    win.close()


def _grid(name: str, width: float):
    from chisurf.plugins.chimol.chimol.volume import VolumeGrid

    z, y, x = np.mgrid[-6:6, -6:6, -6:6]
    values = np.exp(-(x * x + y * y + z * z) / width).astype(np.float32)
    return VolumeGrid(values=values, name=name)


def _showing(win) -> str:
    return win.volume_panel.model.summary().split(" — ")[0]


def test_the_panel_follows_the_newest_map(window):
    win, qapp = window
    viewer = win.viewer

    first = viewer.add_volume(_grid("map_ONE", 12.0), name="map_ONE")
    qapp.processEvents()
    assert _showing(win) == "map_ONE"

    second = viewer.add_volume(_grid("map_TWO", 40.0), name="map_TWO")
    qapp.processEvents()
    assert _showing(win) == "map_TWO"

    # The reported case: nothing map-like is active any more.
    viewer._active_object_id = None
    assert _showing(win) == "map_TWO", "the panel fell back to the first map"

    # And choosing one explicitly still wins over "newest".
    viewer.set_active_object(first)
    assert _showing(win) == "map_ONE"
    viewer.set_active_object(second)
    assert _showing(win) == "map_TWO"


def test_deleting_a_map_falls_back_to_one_that_is_still_there(window):
    win, qapp = window
    viewer = win.viewer
    first = viewer.add_volume(_grid("map_ONE", 12.0), name="map_ONE")
    second = viewer.add_volume(_grid("map_TWO", 40.0), name="map_TWO")
    qapp.processEvents()

    viewer.remove_object(second)
    qapp.processEvents()
    assert _showing(win) == "map_ONE"

    viewer.remove_object(first)
    qapp.processEvents()
    assert "No map loaded" in win.volume_panel.model.summary(), (
        "the panel still describes a map that has been unloaded"
    )
