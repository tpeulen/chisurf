"""QuEst screenshots: the Forward model page (guide 80) and the Analysis page (guide 111).

The window is the plugin's emtk app (the QuEst card plus site picking, and the Analysis page),
driven headlessly with real presses on its buttons and written to ``figures/``. Settings live in a
scratch folder, so the demo cache and the site tables are written there and never into the user's
settings.

``python docs/guides/screenshots/quest.py`` takes the guide-80 figure;
``python docs/guides/screenshots/quest.py _grab_quest_analysis`` takes the six guide-111 figures.
That one builds the 46 MalE site tables from scratch (about 10 s each) and runs every stage at the
quick preset on every CPU (about 20 min on a desktop).
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


def _grab_quest_analysis():
    """The Analysis page on the MalE demo at 1280 x 820: loaded, running, and every result tab."""
    import time

    from emtk import testing

    from chisurf.plugins.quenching_estimator.gui.app import make_app
    from test.gui.emtk_port_parity import draw_app

    size = (1280, 820)
    app = make_app()
    page = app.analysis
    driver = testing.Driver(app, size)

    def press(name):
        driver.frame(1)
        found = page.form.rects.get(name) or page.item_rects.get(name) or app.item_rects.get(name)
        assert found, f"{name!r} not drawn"
        x, y, w, h = found
        driver.click((x + w / 2.0, y + h / 2.0))
        driver.frame(2)

    def shot(name):
        painter = draw_app(app, size)
        (FIG / name).write_bytes(testing.png_encode(painter.width, painter.height, painter.px))
        print("wrote", name, flush=True)

    driver.frame(3)
    press("tab_Analysis")
    press("load_example")
    page.model.wait(120)
    driver.frame(3)
    shot("111_quest_analysis_data.png")
    press("results.kq")
    press("run_analysis")
    start, running = time.time(), False
    while page.model.busy:
        driver.frame(1)
        time.sleep(0.5)
        if not running and time.time() - start > 20:
            shot("111_quest_analysis_running.png")
            running = True
    driver.frame(3)
    print(page.model.status, round(time.time() - start), "s", flush=True)
    press("results.sites")
    rows = page.model.tables.site_tables.rows()
    page.model.select_site_table(rows[6])  # APO 233 (AF488)
    driver.frame(2)
    shot("111_quest_analysis_sites.png")
    press("results.fit")
    page.model.view_stage = "B"
    page.model.stage_changed()
    page.model.view_block = page.model.block_options()[0]
    page.model.touch()
    driver.frame(2)
    shot("111_quest_analysis_fit.png")
    press("results.water")
    shot("111_quest_analysis_water.png")
    press("results.summary")
    shot("111_quest_analysis_summary.png")
    app.close()


if __name__ == "__main__":
    for name in sys.argv[1:] or ["_grab_quest_demo_result"]:
        globals()[name]()
