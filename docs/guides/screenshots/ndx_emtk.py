"""Drive ndX -- the emtk app -- for guide screenshots, without a window.

ndX's GUI is the emtk app (:class:`ndxplorer.app.frame.NdxApp`); its Qt window
was deleted. A grab builds the app through ndX's own capture driver
(:class:`ndxplorer.app.capture.Replay`), which draws every frame with emtk's
PIL painter, replays the parity-scenario steps (``axis``, ``trigger``,
``canvas_click``, ``click``, ``capture`` ...) and photographs the window, a
dock or a menu. Nothing here imports Qt, and nothing is written into the data a
grab opens.
"""

from __future__ import annotations

import pathlib
import sys

#: ndX's checkout, put on the path when ndX is not installed.
NDX = pathlib.Path(__file__).resolve().parents[3] / "modules" / "ndxplorer"


def replay(size=(1400, 900), chisurf: bool = False):
    """A fresh ndX app behind a :class:`~ndxplorer.app.capture.Replay`.

    Parameters
    ----------
    size : tuple of int
        The window's logical size.
    chisurf : bool
        Give the app ChiSurf's in-process RPC client, as ChiSurf's
        ``Main → Tools → ndX`` does (the "Send selection to" menu needs it).
    """
    if str(NDX) not in sys.path:
        sys.path.insert(0, str(NDX))
    from ndxplorer.app.capture import Replay

    driver = Replay({"id": "guide", "steps": []}, {}, size=size)
    if chisurf:
        from chisurf.plugins.ndxplorer.rpc_bridge import make_inprocess_chisurf_client

        driver.app.chisurf_rpc = make_inprocess_chisurf_client()
    driver.settle()
    return driver


def feature(driver, name: str):
    """The app feature called *name* (``"analysis"``, ``"selection"`` ...)."""
    return next(f for f in driver.app.features if f.name == name)


def open_table(driver, path) -> None:
    """Open *path* (a table or a burst-analysis folder) in the app."""
    if not driver.app.open_path(str(path)):
        raise RuntimeError(f"ndX could not open {path}: {driver.app.model.error}")
    driver.settle(3)


def axes(driver, x: str, y: str, z: str = None) -> None:
    """Show parameters *x*, *y* (and *z*) on the plots."""
    for axis, name in (("x", x), ("y", y), ("z", z)):
        if name is not None:
            driver.step({"op": "axis", "axis": axis, "name": name})


def save(image, fig: pathlib.Path, name: str) -> None:
    """Write a PIL *image* into the guide figures."""
    image.save(str(fig / name))
    print("wrote", name)


def grab_view_menu_rank(fig: pathlib.Path) -> None:
    """Guide 46's ``ndxplorer_view_menu_rank.png``: ndX's View menu with a table loaded.

    The ranking entries are greyed out until a table is loaded, so a small
    two-population table is written first; the window is the emtk app ChiSurf
    hosts (``Tools › Views › ndX``), clicked open as a person does, and the
    menu's corner of the frame is kept.
    """
    import tempfile

    import numpy as np
    from emtk.testing import Driver

    from chisurf.emtk.plugins import load_plugin

    rng = np.random.default_rng(3)
    efficiency = np.r_[rng.normal(0.02, 0.02, 400), rng.normal(0.5, 0.05, 600)]
    table = pathlib.Path(tempfile.mkdtemp(prefix="ndx-menu-")) / "bursts.csv"
    np.savetxt(table, np.column_stack([4.0 * (1 - efficiency), efficiency]), delimiter=",",
               header="Tau (green),FRET efficiency", comments="")
    app = load_plugin("ndxplorer", persist=False)
    driver = Driver(app, (900, 520))
    driver.frame(3)
    if not app.open_path(str(table)):
        raise RuntimeError(f"ndX could not open {table}")
    driver.frame(10)
    driver.click("View")
    driver.frame(2)
    shot = fig / "ndxplorer_view_menu_rank.png"
    driver.screenshot(shot)
    from PIL import Image

    Image.open(shot).crop((0, 0, 560, 260)).save(shot)
    print("wrote", shot.name)


if __name__ == "__main__":
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    grab_view_menu_rank(pathlib.Path(__file__).resolve().parents[1] / "figures")
    os._exit(0)
