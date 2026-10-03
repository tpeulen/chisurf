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
    drv.type_into_name("data_folder", str(work / "burstwise_All 0.1000#15"))
    drv.type_into_name("donor_channels", "0, 1")
    drv.type_into_name("acceptor_channels", "8, 9")
    drv.type_into_name("min_states", "2")
    drv.type_into_name("max_states", "2")
    drv.type_into_name("restarts", "1")
    drv.click_name("toolAction_run")
    while app.job.busy:
        time.sleep(0.1)
        drv.draw(1)
    drv.draw(2)
    for size in ((1200, 800), (800, 600)):
        parity.emtk_screenshot(app, out / f"after_populated_{size[0]}x{size[1]}.png", size)


if __name__ == "__main__":
    main()
