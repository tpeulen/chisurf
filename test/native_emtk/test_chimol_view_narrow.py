"""An embedded chimol view narrower than a desktop canvas keeps its interface at full size.

The view used to render below 760 x 420 at a larger size and scale the picture down, so the menus and panels of
every embedded view narrower than that (the FPS editor's 3D View at the default hub width) were illegible. chimol
keeps its chrome at size now and folds panels, so the picture is drawn at the region's own size.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

pytest.importorskip("wgpu")
chimol = pytest.importorskip("chimol")

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
PDB = Path(chimol.__file__).parent / "data" / "demos" / "148l.pdb"


@pytest.mark.parametrize("size", [(420, 300), (600, 360)], ids=lambda s: f"{s[0]}x{s[1]}")
def test_the_view_is_drawn_at_the_size_of_its_region(size):
    from emtk import im
    from emtk.app import ImApp
    from emtk.testing import Driver

    from chisurf.emtk.chimol_view import ChimolView

    view = ChimolView()

    class Host(ImApp):
        def __init__(self):
            super().__init__(self.render, continuous=True)

        def render(self):
            im.begin("view", (0, 0, *size))
            view.draw()
            im.end()

    driver = Driver(Host(), size)
    try:
        end = time.monotonic() + 120
        while not view.ready() and time.monotonic() < end:
            driver.frame(1)
            time.sleep(0.05)
        assert view.ready(), view.error
        view.app.load(str(PDB))
        driver.frame(4)
        assert view._render_size == size, "the picture was rendered larger and scaled down"
        gui = view.app.renderer._internal_gui
        assert gui.window("mouse").collapsed  # a small region folds the mouse block
        SHOTS.mkdir(parents=True, exist_ok=True)
        driver.screenshot(SHOTS / f"chimol_view_{size[0]}x{size[1]}.png")
    finally:
        view.close()
