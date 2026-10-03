"""Capture populated screenshots of burst_ebfret.

Usage:
    python okf/plugins/emtk-ports/burst_ebfret/scripts/capture_emtk.py <out_dir>
"""

from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, ".")
import test.gui.emtk_port_parity as parity

from chisurf.plugins.burst.burst_ebfret import demo
from chisurf.plugins.burst.burst_ebfret.gui.app import make_app
from chisurf.plugins.emtk_test_input import Driver


def main():
    out = pathlib.Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)

    demo_file = demo.write_demo()

    # 1. Empty state at 1200x800 and 800x600
    for size in ((1200, 800), (800, 600)):
        tag = f"{size[0]}x{size[1]}"
        app = make_app()
        drv = Driver(app, size)
        drv.draw(2)
        parity.emtk_screenshot(app, out / f"after_empty_{tag}.png", size)

    # 2. Populated state at 1200x800 and 800x600
    for size in ((1200, 800), (800, 600)):
        tag = f"{size[0]}x{size[1]}"
        app = make_app()
        drv = Driver(app, size)
        drv.draw(2)
        app.gui.client.load([str(demo_file)], 2)
        app.gui.client.set("min_states", 2)
        app.gui.client.set("max_states", 2)
        app.gui.client.set("restarts", 1)
        app.gui.client.run()
        for _ in range(100):
            time.sleep(0.05)
            drv.draw(1)
            status = app.gui.client.status()
            if not status.get("running"):
                break
        drv.draw(3)
        parity.emtk_screenshot(app, out / f"after_populated_{tag}.png", size)

    print("burst_ebfret screenshots captured successfully.")


if __name__ == "__main__":
    main()
