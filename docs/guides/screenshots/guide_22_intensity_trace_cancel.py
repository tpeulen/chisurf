"""Guide 22 figure: the Intensity Trace emtk app after Cancel during an HMM fit.

Run from the repository root, headless, with a scratch settings dir::

    CHISURF_SETTINGS_DIR=$(mktemp -d) python docs/guides/screenshots/guide_22_intensity_trace_cancel.py

Loads the plugin's switching-molecule demo at 2 ms bins, opens the HMM tab, presses
**Compute HMM**, holds the fit inside its first E-step, presses **Cancel** and writes
``docs/guides/figures/intensity_trace_cancelled.png``. Read the PNG afterwards.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
from threading import Event

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))


def main() -> None:
    from emtk.testing import Driver
    from emtk_shot import FIG

    from chisurf.core.math.hmm import GaussianHMM
    from chisurf.plugins.tttr.intensity_trace.demo import make_demo
    from chisurf.plugins.tttr.intensity_trace.gui.app import make_app

    app = make_app()
    app.model.window_ms = 2.0
    assert app.model.load(make_demo(pathlib.Path(tempfile.mkdtemp()) / "data"))
    app.tab = "HMM"

    original = GaussianHMM._do_estep
    entered, released = Event(), Event()

    def step(self, *args):
        result = original(self, *args)
        entered.set()
        released.wait(30)
        return result

    GaussianHMM._do_estep = step
    driver = Driver(app, (1100, 720))
    driver.frame(2)
    driver.click("request_hmm")
    assert entered.wait(30), "the HMM worker never started"
    driver.click("request_cancel")
    released.set()
    app.wait(30)
    GaussianHMM._do_estep = original
    driver.frame(3)
    print("status:", app.status, flush=True)
    driver.screenshot(FIG / "intensity_trace_cancelled.png")
    print("wrote intensity_trace_cancelled.png", flush=True)
    app.close()


if __name__ == "__main__":
    main()
