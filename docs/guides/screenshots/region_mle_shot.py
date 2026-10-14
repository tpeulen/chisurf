"""Region MLE on its known-field demo, fitted (guide 48).

Run from the repository root with the project environment:
``IMP_BFF_GPU=off python docs/guides/screenshots/region_mle_shot.py``.
Presses **Load example** (simulate the four-region field, detect it with the
standard Spot Finder workflow), then **Run**, waits for each worker, and writes
``docs/guides/figures/region_mle_native_wide_counts.png``.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from emtk_shot import FIG, app_from, wait  # noqa: E402


def main() -> None:
    """Load the demo, fit it, and grab the window at its declared size."""
    from emtk.testing import Driver

    app = app_from("region_mle")
    driver = Driver(app, (1100, 720))
    driver.frame(3)
    for method in ("load_demo", "run"):
        assert app.start_job(method), method
        wait(driver, lambda: not app.job.busy, timeout=600)
        if app.model.error_text:
            raise RuntimeError(app.model.error_text)
    driver.frame(4)
    driver.screenshot(FIG / "region_mle_native_wide_counts.png")
    print("wrote region_mle_native_wide_counts.png", flush=True)
    app.close()


if __name__ == "__main__":
    main()
