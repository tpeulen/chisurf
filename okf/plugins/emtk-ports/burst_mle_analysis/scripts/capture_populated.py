"""Populated screenshots of the emtk burst-MLE app on the in-repo BH SPC-132 sample (real photons, real fit).

Run on temporary settings (the caller sets HOME, CHISURF_SETTINGS_DIR, MMFDB_*):

    python okf/plugins/emtk-ports/burst_mle_analysis/scripts/capture_populated.py <out_dir> [qt]

The ``qt`` argument grabs the Qt wizard in the same state instead (the baseline).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))

SAMPLE = REPO / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
BURSTS = Path("burstwise_All 0.1000#15/bi4_bur/m000.bur")
CHANNELS = {
    "detectors": {
        "green": {"chs": [0, 1], "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0308, "l2": 0.0368},
        "red": {"chs": [8, 9], "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0308, "l2": 0.0368},
    },
    "windows": {},
    "file_type": "SPC-130",
}


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    qt = len(sys.argv) > 2 and sys.argv[2] == "qt"
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    work = Path(tempfile.mkdtemp(prefix="mle_capture_")) / "data"
    shutil.copytree(SAMPLE, work, ignore=shutil.ignore_patterns(".DS_Store"))
    w = MLELifetimeAnalysisWizard()
    app.processEvents()
    w.channel_definer.load_data_into_tables(CHANNELS)
    w.channel_definer.file_type_combo.setCurrentText("SPC-130")
    w._init_channels_from_wizard()
    w.burst_files_list.add_file(str(work / BURSTS))
    w.load_burst_data()
    w.update_burst_files()
    w.comboBox_window.setCurrentText("green")
    app.processEvents()
    w.auto_extract_irf_bg()
    app.processEvents()

    if qt:
        w.resize(1200, 800)
        w.show()
        app.processEvents()
        w.grab().save(str(out / "before_populated.png"))
        w.process_bursts(force=True)
        app.processEvents()
        w.grab().save(str(out / "before_populated_batch.png"))
        return

    from test.gui.emtk_port_parity import emtk_screenshot

    from chisurf.plugins.burst.burst_mle_analysis.gui.app import BurstMleApp
    from chisurf.plugins.emtk_test_input import Driver

    emtk = BurstMleApp(w)
    drv = Driver(emtk)
    drv.draw()
    drv.click_name("toolAction_run")  # the real batch, started with a pointer press
    for size in ((1200, 800), (800, 600)):
        emtk_screenshot(emtk, out / f"after_populated_{size[0]}x{size[1]}.png", size)


if __name__ == "__main__":
    main()
