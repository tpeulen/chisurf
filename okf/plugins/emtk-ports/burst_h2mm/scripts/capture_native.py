"""Populated screenshots of the standalone emtk H2MM app on the in-repo BH SPC-132 sample (real photons, real fit).

    python okf/plugins/emtk-ports/burst_h2mm/scripts/capture_native.py <out_dir>   (temp HOME / settings set by the caller)
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))
SAMPLE = REPO / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("emtk_port_parity", REPO / "test/gui/emtk_port_parity.py")
    parity = importlib.util.module_from_spec(spec)
    sys.modules["emtk_port_parity"] = parity
    spec.loader.exec_module(parity)

    from chisurf.plugins.burst.burst_h2mm.gui.native import create_app
    from chisurf.plugins.emtk_test_input import Driver

    work = Path(tempfile.mkdtemp(prefix="h2mm_capture_")) / "data"
    shutil.copytree(SAMPLE, work, ignore=shutil.ignore_patterns(".DS_Store"))
    app = create_app()
    drv = Driver(app)
    drv.draw()
    parity.emtk_screenshot(app, out / "after_empty_1200x800.png", (1200, 800))
    import copy

    setup = {
        "detectors": {
            "green": {"chs": [0, 1], "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
            "red": {"chs": [8, 9], "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        },
        "windows": {},
        "tttr_reading": {"file_type": "SPC-130", "macro_time_resolution": 0.0, "micro_time_resolution": 0.0, "micro_time_binning": 1},
    }
    app.editor.model.data = copy.deepcopy(setup)
    app.model.set_setup(setup)
    drv.type_into_name("data_folder", str(work / "burstwise_All 0.1000#15"))
    drv.type_into_name("min_states", "2")
    drv.type_into_name("patience", "-1")
    drv.type_into_name("max_states", "3")
    drv.type_into_name("restarts", "1")

    def wait():
        while app.job.busy:
            time.sleep(0.1)
            drv.draw(1)
        drv.draw(2)

    drv.click_name("toolAction_run")
    wait()
    drv.click_name("bootstrap")
    wait()
    drv.click_name("ll_scan")
    wait()
    for size in ((1200, 800), (800, 600)):
        drv.size = size
        for tab, name in (("Dwell FRET", None), ("TDP", None)):
            drv.click_text(tab)
        parity.emtk_screenshot(app, out / f"after_populated_{size[0]}x{size[1]}.png", size)
    drv.size = (1200, 800)
    for tab, name in (("Selection", "selection"), ("LL scan", "scan"), ("Dwell times", "dwells"), ("State path", "path"), ("Decays", "decays")):
        drv.click_text(tab)
        parity.emtk_screenshot(app, out / f"after_tab_{name}_1200x800.png", (1200, 800))
    drv.click_text("Detector setup")
    parity.emtk_screenshot(app, out / "after_detector_setup_1200x800.png", (1200, 800))
    drv.size = (800, 600)
    parity.emtk_screenshot(app, out / "after_detector_setup_800x600.png", (800, 600))


if __name__ == "__main__":
    main()
