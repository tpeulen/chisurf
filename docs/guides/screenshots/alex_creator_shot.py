"""Guide 100: the ALEX Creator on a real two-colour µs-ALEX calibration (headless emtk, no Qt).

Loads ``tttr-data/sm/cal1/001_60g_25r_cal1_cy3b_8_18_33bp_atto647n.sm`` (a sibling checkout of
the repository, or ``$CHISURF_TTTR_DATA``), presses **Detect period**, lets the excitation regions
be inferred, and writes ``docs/guides/figures/alex_creator.png``. Read the PNG afterwards.

Run from the repository root::

    IMP_BFF_GPU=off CHISURF_SETTINGS_DIR=$(mktemp -d) python docs/guides/screenshots/alex_creator_shot.py
"""

from __future__ import annotations

import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG, REPO, wait  # noqa: E402

DATA = pathlib.Path(os.environ.get("CHISURF_TTTR_DATA", REPO.parent / "tttr-data"))
CAL = DATA / "sm" / "cal1" / "001_60g_25r_cal1_cy3b_8_18_33bp_atto647n.sm"


def main() -> None:
    """Load the calibration, measure the period, and save the settled window."""
    import tempfile

    from emtk.testing import Driver

    from chisurf.plugins.tttr.ptu_alex_creator.gui.app import AlexApp

    state = pathlib.Path(tempfile.mkdtemp()) / "alex.json"
    app = AlexApp(state_path=state)
    app.model.alex_period = 4000  # a wrong guess, so Detect period has something to correct
    app.model.period_shift = 0
    driver = Driver(app, (1400, 860))
    driver.frame(2)
    app.load(CAL)
    wait(driver, lambda: not app.job.running and not app.preview_job.running, timeout=300)
    app.detect_period()
    wait(driver, lambda: not app.job.running, timeout=300)
    driver.frame(4)
    wait(driver, lambda: not app.preview_job.running, timeout=300)
    driver.frame(6)
    print("period", app.model.alex_period, "|", app.message, flush=True)
    driver.screenshot(FIG / "alex_creator.png")
    print("wrote alex_creator.png", flush=True)
    app.close()


if __name__ == "__main__":
    main()
