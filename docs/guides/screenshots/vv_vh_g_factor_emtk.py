"""The VV/VH G-Factor Calculator figures of docs/guides/91_vv_vh_g_factor.md, rendered headlessly by emtk.

Run from the repository root::

    IMP_BFF_GPU=off python docs/guides/screenshots/vv_vh_g_factor_emtk.py

It presses **Load example** (the plugin's simulated references, known G = 1.2), waits for the
calculation, grabs the G-factor tab, then runs the batch and grabs the Batch anisotropy tab.
"""

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="vv_vh_g_factor_shot_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from docs.guides.screenshots.emtk_shot import app_from, render, wait  # noqa: E402


def main():
    """Render vv_vh_g_factor_native_reference.png and vv_vh_g_factor_native_batch.png."""
    from emtk.testing import Driver

    app = app_from("vv_vh_g_factor")
    driver = Driver(app, (1600, 1000))
    driver.settle()
    app.load_example()
    wait(driver, lambda: not app.job.running)
    render(app, "vv_vh_g_factor_native_reference.png", driver=driver)
    app.run(lambda model: model.compute_batch(app.job.cancelled.is_set))
    wait(driver, lambda: not app.job.running)
    app.docks.focus("batch")
    driver.frame(4)
    render(app, "vv_vh_g_factor_native_batch.png", driver=driver)


if __name__ == "__main__":
    main()
