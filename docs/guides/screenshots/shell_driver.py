"""Helpers that drive the emtk shell (the default ChiSurf window) for the manual's screenshots.

``shell()`` starts the shell on a private session and returns an :class:`emtk.testing.Driver` and a
``wait(predicate)`` that draws frames until a worker call has landed. Run the generators with
``IMP_BFF_GPU=off pixi run -e test python <script>`` and ``CHISURF_SETTINGS_DIR`` pointing at a scratch
folder, so no user preference is read or written.
"""

from __future__ import annotations

import io
import pathlib
import time

#: Where the manual's figures live.
OUT = pathlib.Path(__file__).resolve().parents[2] / "manual" / "figures"


def shell(size=(1900, 1100)):
    """The emtk shell (the default ChiSurf window) on a private session; returns ``(driver, wait)``.

    ``wait(predicate)`` draws frames until the predicate holds (a worker call landed).
    """
    import time

    from emtk.testing import Driver

    from chisurf.emtk.main_app import make_app

    app = make_app(persist=False)
    driver = Driver(app, size)

    def wait(predicate, timeout: float = 300.0) -> None:
        end = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > end:
                raise TimeoutError(app.data.status)
            driver.frame(1)
            time.sleep(0.03)
        driver.frame(3)

    wait(lambda: app.data.session is not None)
    return driver, wait


def tile(app, first: str | None = None) -> None:
    """*Tile Windows* (Main tab): the fit windows side by side, the Start page closed first.

    The window in the centre is the one the Analysis dock follows, so *first* (a fit uid) is
    tiled there.
    """
    app.docks.hide("start")
    if first in app.data.windows:
        windows = app.data.windows
        app.data.windows = {first: windows[first]} | {k: v for k, v in windows.items() if k != first}
    app.tile_windows()


def idle(app) -> bool:
    return not app.data.busy and not app.data._dirty


def shot_shell(driver, name: str) -> None:
    """Grab the whole shell window into ``OUT/name``.

    The pointer is parked over the console first: left where the last click landed, it hovers a
    table row (a second highlighted row) or raises that control's tooltip over the figure.
    """
    driver.hover((float(driver.size[0]) - 300.0, float(driver.size[1]) - 60.0))
    driver.frame(3)
    driver.screenshot(OUT / name)
    print("wrote", name, flush=True)


def shot_region(driver, name: str, region: str = "left_lower", size=(1900, 2400)) -> None:
    """Grab one dock region of the shell (tall enough for a long editor) into ``OUT/name``."""
    import io

    from PIL import Image

    original = driver.size
    driver.draw(3, size=size)
    box = driver.app.docks.region_boxes[region]
    image = Image.open(io.BytesIO(driver.screenshot()))
    x, y, w, h = (int(v) for v in box)
    image.crop((x, y, x + w, min(y + h, image.height))).save(OUT / name)
    driver.draw(3, size=original)
    print("wrote", name, flush=True)


def show(driver, wait, uid: str) -> None:
    """Make fit *uid* current (its window forward, the Analysis dock follows)."""
    from chisurf.emtk.fit_docks import ANALYSIS_KEY

    app = driver.app
    app.data.show_fit(uid)
    wait(lambda: idle(app) and app.data.analysis.info)
    app.docks.focus(ANALYSIS_KEY)
    driver.frame(3)


def run(driver, wait) -> None:
    """Press *Fit* of the Analysis dock and wait until the worker is done."""
    app = driver.app
    app.data.run_fit()
    driver.frame(2)
    wait(lambda: idle(app))


