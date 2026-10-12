"""QuEst screenshot: the native window after Load example and Simulate (guide 80).

The window is the plugin's emtk app (the QuEst card plus site picking), driven headlessly with
real presses on its buttons and written to ``figures/``. Settings live in a scratch folder, so the
demo cache is written there and never into the user's settings.
"""
import os
import pathlib
import sys
import tempfile

_SCRATCH = pathlib.Path(tempfile.mkdtemp(prefix="quest_shot_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(_SCRATCH / "settings")
os.environ["QUEST_RUNS_DIR"] = str(_SCRATCH / "jobs")

REPO = pathlib.Path(__file__).resolve().parents[3]
for entry in (REPO, REPO / "docs" / "guides"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from emtk.testing import Driver  # noqa: E402
from screenshots.emtk_shot import FIG, wait  # noqa: E402


def _grab_quest_demo_result():
    """Load example, then Simulate, at 800 x 600; the state line shows QY and the mean lifetime."""
    from chisurf.plugins.quenching_estimator.gui.app import make_app

    app = make_app()
    driver = Driver(app, (800, 600))
    driver.frame(3)
    driver.click("load_example")
    driver.frame(2)
    driver.click("simulate")
    wait(driver, lambda: not app.session.running, timeout=300.0)
    print(app.session.model.status, flush=True)
    driver.hover((12.0, 588.0))
    driver.frame(3)
    driver.screenshot(FIG / "quest_demo_result.png")
    print("wrote quest_demo_result.png", flush=True)
    app.close()


if __name__ == "__main__":
    for name in sys.argv[1:] or ["_grab_quest_demo_result"]:
        globals()[name]()
