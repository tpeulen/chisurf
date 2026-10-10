"""Figure of the Light Path Simulator guide: the default two-colour graph and its results.

    python docs/guides/screenshots/lightpath_simulator_emtk.py

Needs the shipped spectra catalogue (``~/.chisurf/flr/sample_management.db``).
Writes ``docs/guides/figures/104_lightpath_simulator.png``. Run from the repository root.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from emtk_shot import FIG  # noqa: E402


def main() -> None:
    """Open the simulator on the default graph, calculate, and write the frame."""
    from chisurf.plugins.core.lightpath_simulator.gui.app import create_app

    state = pathlib.Path(tempfile.mkdtemp()) / "lightpath_state.json"
    app = create_app(state_path=state)
    from emtk.testing import Driver

    driver = Driver(app, (1400, 860))
    driver.frame(3)
    import time

    for _ in range(100):  # the spectra catalogue arrives asynchronously
        time.sleep(0.05)
        driver.frame()
    graph = app.controller.graph()
    for node in graph["nodes"]:
        if node["id"] == "light_source":
            node["config"]["manual_lines"] = "488:1.0, 640:1.0"
        elif node["id"] == "sample":  # Alexa488 donor, Alexa594 acceptor
            node["config"]["probe_ids"] = [1, 2]
    app.controller.load_document(graph)
    app.controller.start()

    end = time.monotonic() + 60
    while (app.controller.running or app.controller.pending) and time.monotonic() < end:
        time.sleep(0.02)
        driver.frame()
    driver.frame(4)
    driver.click((354, 602))  # the "Förster radius" result tab
    driver.frame(4)
    driver.frame(3)
    driver.screenshot(FIG / "104_lightpath_simulator.png")
    print("wrote 104_lightpath_simulator.png")
    app.close()


if __name__ == "__main__":
    main()
