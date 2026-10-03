"""Populated screenshots of the standalone emtk burst-MLE app on the in-repo BH SPC-132 sample.

    python scripts/capture_native.py <out_dir>   (temp HOME / settings set by the caller)
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
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
    spec = importlib.util.spec_from_file_location("emtk_port_parity", REPO / "test/gui/emtk_port_parity.py")
    parity = importlib.util.module_from_spec(spec)
    sys.modules["emtk_port_parity"] = parity
    spec.loader.exec_module(parity)
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app
    from chisurf.plugins.emtk_test_input import Driver

    work = Path(tempfile.mkdtemp(prefix="mle_native_")) / "data"
    shutil.copytree(SAMPLE, work, ignore=shutil.ignore_patterns(".DS_Store"))
    app = create_app()
    drv = Driver(app)
    drv.draw()
    parity.emtk_screenshot(app, out / "after_empty_1200x800.png", (1200, 800))

    def wait():
        while app.job.busy:
            time.sleep(0.1)
            drv.draw(1)
        drv.draw(2)

    app.model.set_setup({"detectors": CHANNELS["detectors"], "windows": {}, "tttr_reading": {"file_type": "SPC-130"}})
    app.editor.model.data["detectors"] = CHANNELS["detectors"]
    drv.drop(work / BURSTS)
    drv.click_name("auto")
    wait()
    app.model.current_detector = "red"
    app.model.auto_extract()
    app.model.current_detector = "green"
    drv.draw(2)
    drv.click_name("toolAction_run")
    wait()
    for size in ((1200, 800), (800, 600)):
        drv.size = size
        drv.click_text("Decay and fit")
        drv.click_text("Burst lifetimes")
        parity.emtk_screenshot(app, out / f"after_populated_{size[0]}x{size[1]}.png", size)
    drv.size = (1200, 800)
    for tab, name in (("Inspected burst", "inspected"), ("Lifetime table", "table")):
        drv.click_text(tab)
        parity.emtk_screenshot(app, out / f"after_tab_{name}_1200x800.png", (1200, 800))
    for tab, name in (("IRF", "irf"), ("Detector setup", "detectors")):
        drv.click_text(tab)
        parity.emtk_screenshot(app, out / f"after_{name}_1200x800.png", (1200, 800))


if __name__ == "__main__":
    main()
