"""Guide 101: the Tools › Photon data ribbon group and Count Rate Analysis on its own (headless emtk).

``main`` writes two figures into ``docs/guides/figures``:

* ``photon_data_ribbon.png`` -- the emtk shell with the **Tools** ribbon tab open, showing the five
  photon-data tools as ordinary buttons;
* ``photon_data_count_rate.png`` -- **Count Rate Analysis** opened on its own, its own detector
  editor holding detector ``green`` (routing channels 0 and 1, SPC-130 reading), after **Calculate** on
  ``m000.spc``–``m002.spc`` from ``chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna``.

Read both PNGs afterwards. Run from the repository root::

    IMP_BFF_GPU=off CHISURF_SETTINGS_DIR=$(mktemp -d) MMFDB_SETTINGS_DIR=$(mktemp -d) \
        python docs/guides/screenshots/photon_data_tools_shot.py
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


def ribbon() -> None:
    """The shell with its Tools tab selected: the Photon data group is five plain buttons."""
    from emtk.testing_realistic import RealisticDriver

    from chisurf.emtk.main_app import EmtkShellApp

    shell = EmtkShellApp(loader=lambda plugin_id: None, console_history=False, console_session_file=False)
    driver = RealisticDriver(shell, (1440, 900), real_painter=True)
    driver.frame(3)
    driver.click("ribbon.tab.Tools")
    driver.frame(4)
    driver.screenshot(FIG / "photon_data_ribbon.png")
    print("wrote photon_data_ribbon.png", flush=True)
    shell.close()


def count_rate() -> None:
    """Count Rate Analysis standalone: its own detector editor, three files, Calculate."""
    from emtk.testing import Driver

    from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller import create_app

    app = create_app()
    tool = app.tool
    driver = Driver(app, (1280, 860))
    driver.frame(2)
    tool.channel_editor.load_definition(SETUP)
    driver.frame(2)
    tool.add_paths([str(DATA / f"m00{i}.spc") for i in range(3)])
    driver.frame(2)
    tool.calculate()
    wait(driver, lambda: not tool.job.running, timeout=300)
    driver.frame(6)
    print("count rate:", getattr(tool, "message", ""), flush=True)
    driver.screenshot(FIG / "photon_data_count_rate.png")
    print("wrote photon_data_count_rate.png", flush=True)
    app.close()


def main() -> None:
    """Draw both figures."""
    ribbon()
    count_rate()


if __name__ == "__main__":
    main()
