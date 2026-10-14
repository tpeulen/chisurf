"""Guide 101: TTTR Tools with Count Rate Analysis computed on the bundled SPC-132 dsDNA files (headless emtk).

Defines one shared detector (``green``, routing channels 0 and 1, SPC-130 reading) at **0. Setup**,
selects **Count Rate Analysis**, queues ``m000.spc``–``m002.spc`` from
``chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna``, presses **Calculate** and writes
``docs/guides/figures/tttr_toolbox.png``. Read the PNG afterwards.

Run from the repository root::

    IMP_BFF_GPU=off CHISURF_SETTINGS_DIR=$(mktemp -d) MMFDB_SETTINGS_DIR=$(mktemp -d) \
        python docs/guides/screenshots/tttr_toolbox_shot.py
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG, REPO, wait  # noqa: E402

DATA = REPO / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
SETUP = {
    "detectors": {"green": {"chs": [0, 1], "micro_time_ranges": [], "g_factor": 1.0}},
    "windows": {},
    "tttr_reading": {"file_type": "SPC-130"},
}


def main() -> None:
    """Drive the hub into a computed Count Rate Analysis and save the frame."""
    from emtk.testing import Driver

    from chisurf.plugins.tttr.tttr_toolbox.gui.app import make_app

    hub = make_app()
    driver = Driver(hub, (1280, 860))
    driver.frame(2)
    hub.ensure_child("setup").page.load_definition(SETUP)
    driver.frame(2)
    child = hub.select("count_rate")
    driver.frame(2)
    child.tool.add_paths([str(DATA / f"m00{i}.spc") for i in range(3)])
    driver.frame(2)
    child.tool.calculate()
    wait(driver, lambda: not child.tool.job.running, timeout=300)
    driver.frame(6)
    print("count rate:", getattr(child.tool, "message", ""), flush=True)
    driver.screenshot(FIG / "tttr_toolbox.png")
    print("wrote tttr_toolbox.png", flush=True)
    hub.close()


if __name__ == "__main__":
    main()
