"""Headless emtk renders for the guide figures (no Qt).

``render(app, name, size)`` drives the native app through :class:`emtk.testing.Driver`,
waits for its worker, and writes ``docs/guides/figures/<name>``. Read the PNG afterwards.
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[3]
FIG = REPO / "docs" / "guides" / "figures"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def wait(driver, done, timeout: float = 120.0) -> None:
    """Draw frames until ``done()`` is true (a worker finished), or raise ``TimeoutError``."""
    end = time.monotonic() + timeout
    while not done():
        if time.monotonic() > end:
            raise TimeoutError("worker did not finish")
        time.sleep(0.02)
        driver.frame()
    driver.frame(3)


def render(app, name: str, size=(1400, 860), driver=None):
    """Write the app's settled frame to ``FIG / name`` and return the driver."""
    from emtk.testing import Driver

    driver = driver or Driver(app, size)
    driver.settle()
    driver.frame(2)
    driver.screenshot(FIG / name)
    print("wrote", name, flush=True)
    return driver


def app_from(plugin_id: str):
    """Build the plugin's emtk app as the launcher does (settings in a scratch dir)."""
    from chisurf.emtk.plugins import load_plugin

    return load_plugin(plugin_id, persist=False)
