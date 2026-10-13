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
from native_window import process_events




@pytest.fixture
def window():
    from native_window import NativeWindow
    win = NativeWindow()
    win.resize(800, 600)
    for _ in range(4):
        process_events()
    yield win, None
    win.close()


def _grid(name: str, width: float):
    from chimol.core.model.volume import VolumeGrid

    z, y, x = np.mgrid[-6:6, -6:6, -6:6]
    values = np.exp(-(x * x + y * y + z * z) / width).astype(np.float32)
    return VolumeGrid(values=values, name=name)


def _showing(win) -> str:
    return win.open_panel("density").model.summary().split(" — ")[0]


def test_the_panel_follows_the_newest_map(window):
    win, qapp = window
    viewer = win.viewer

    first = viewer.add_volume(_grid("map_ONE", 12.0), name="map_ONE")
    process_events()
    assert _showing(win) == "map_ONE"

    second = viewer.add_volume(_grid("map_TWO", 40.0), name="map_TWO")
    process_events()
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
    process_events()

    viewer.remove_object(second)
    process_events()
    assert _showing(win) == "map_ONE"

    viewer.remove_object(first)
    process_events()
    assert "No map loaded" in win.open_panel("density").model.summary(), (
        "the panel still describes a map that has been unloaded"
    )
