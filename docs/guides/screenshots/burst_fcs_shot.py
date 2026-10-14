"""Guide 16: Burst-wise FCS on its built-in example (headless emtk, no Qt).

Presses **Load example** (eight simulated bursts on two detectors, pairs ACF_0, ACF_1 and cross_01),
then **Run FCS**, waits for the 24 curves, and writes the Inputs tab to
``docs/guides/figures/burst_fcs_native_primary_window.png`` and the Settings tab of the same run to
``docs/guides/figures/burst_fcs_settings.png``. Read the PNGs afterwards.

Run from the repository root::

    IMP_BFF_GPU=off CHISURF_SETTINGS_DIR=$(mktemp -d) python docs/guides/screenshots/burst_fcs_shot.py
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG, wait  # noqa: E402


def main() -> None:
    """Run the example and save the Inputs and Settings tabs."""
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app

    app = create_app()
    driver = Driver(app, (1200, 800))
    driver.frame(2)
    app.select_tab("Inputs")
    app.load_example()
    driver.frame(2)
    controller = app.controller
    controller._on_run()
    wait(driver, lambda: (controller.poll(), not controller.running)[1], timeout=300)
    driver.frame(4)
    print(controller.status, flush=True)
    driver.screenshot(FIG / "burst_fcs_native_primary_window.png")
    app.select_tab("Settings")
    driver.frame(4)
    driver.screenshot(FIG / "burst_fcs_settings.png")
    print("wrote burst_fcs_native_primary_window.png, burst_fcs_settings.png", flush=True)
    app.close()


if __name__ == "__main__":
    main()
