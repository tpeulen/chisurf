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


def simulated_alex_table(path, *, gamma, alpha, beta, delta, efficiencies=(0.28, 0.72), seed=7,
                         tau_d0=4.0, r0=52.0):
    """Write an ALEX burst table with known correction factors (two FRET populations, D-only, A-only).

    ``Green Count Rate (KHz)``/``Red Count Rate (KHz)``/``S delayed yellow (kHz)``/``Tau (green)`` -- the
    ``.bur`` spellings the Accurate FRET channel guess recognises. Returns *path*.
    """
    import numpy as np

    from chisurf.core.fluorescence.fret.lines import static_fret_line

    line = static_fret_line(tau_d0, r0=r0, sigma=6.0)
    rng = np.random.default_rng(seed)
    dd, da, aa, tau = [], [], [], []
    for efficiency in efficiencies:
        photons = rng.poisson(400, 1500).astype(float)
        dd.append(rng.poisson((1 - efficiency) * photons))
        aa.append(rng.poisson(beta * gamma * photons))
        da.append(rng.poisson(gamma * efficiency * photons + alpha * (1 - efficiency) * photons
                              + delta * beta * gamma * photons))
        tau.append(rng.normal(float(line.lifetime_at(efficiency)), 0.15, 1500))
    photons = rng.poisson(400, 500).astype(float)  # donor-only
    dd.append(rng.poisson(photons))
    da.append(rng.poisson(alpha * photons))
    aa.append(rng.poisson(2.0, 500))
    tau.append(rng.normal(tau_d0, 0.15, 500))
    photons = rng.poisson(400, 500).astype(float)  # acceptor-only
    dd.append(rng.poisson(2.0, 500))
    aa.append(rng.poisson(beta * gamma * photons))
    da.append(rng.poisson(delta * beta * gamma * photons))
    tau.append(np.full(500, np.nan))
    np.savetxt(
        path,
        np.column_stack([np.concatenate(c).astype(float) for c in (dd, da, aa, tau)]),
        delimiter=",", comments="",
        header="Green Count Rate (KHz),Red Count Rate (KHz),S delayed yellow (kHz),Tau (green)",
    )
    return path


def accurate_fret_calibrated(table, size=(1400, 860), n_bootstrap=20, tau_d0=4.0, r0=52.0):
    """The native Accurate FRET app with *table* loaded and calibrated; returns ``(app, driver)``."""
    from emtk.testing import Driver

    app = app_from("accurate_fret")
    driver = Driver(app, size)
    driver.frame(3)
    app.model.donor_lifetime, app.model.forster_radius = tau_d0, r0
    app.model.n_bootstrap = n_bootstrap
    app.on_paths_dropped([str(table)])
    driver.frame(3)
    app.controller.run()
    wait(driver, lambda: (app.controller.poll(), not app.controller.running)[1], timeout=600)
    driver.frame(4)
    return app, driver


def show_tabs(driver, *captions):
    """Click each tab caption (as a person does) and draw the frames that bring it forward."""
    for caption in captions:
        driver.click(caption)
        driver.frame(3)
