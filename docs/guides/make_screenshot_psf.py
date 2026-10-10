#!/usr/bin/env python
"""Render the PSF calculator (the native emtk window) for docs/guides/72_psf_calculator.md.

Headless through ``emtk.testing.Driver``; no Qt. Run from the repository root::

    CHISURF_SETTINGS_DIR=$(mktemp -d) python docs/guides/make_screenshot_psf.py
"""
from __future__ import annotations

import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "screenshots"))
from emtk_shot import FIG, app_from, render, wait  # noqa: E402,F401


def _grab_psf_calculator():
    """Grab the PSF calculator (guide 72).

    Not the default state: linear x polarization at NA 1.4 on the full aperture
    quadrature, so the figure shows what the vectorial model exists for -- a focus
    longer along the polarization axis than across it -- and the measured widths in
    the Result panel.
    """
    app = app_from("psf_calculator")
    m = app.model
    m.model, m.polarization, m.na, m.n_immersion = "vectorial", "x", 1.4, 1.518
    m.quality = "full"
    m.show_polarization = False
    m.nxy, m.nz, m.pixel_size_nm, m.z_step_nm = 64, 31, 25.0, 50.0
    app.schedule()
    app.deadline = 0.0
    from emtk.testing import Driver

    driver = Driver(app, (1400, 860))
    driver.frame(2)
    wait(driver, lambda: not app.busy and m.volume is not None)
    render(app, "psf_calculator.png", driver=driver)
    return app


if __name__ == "__main__":
    t = _grab_psf_calculator()
    print(t.model.summary_text())
