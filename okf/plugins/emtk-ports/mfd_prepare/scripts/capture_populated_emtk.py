"""Populated emtk screenshots of mfd_prepare on the in-repo measured fixture (run from the repo root, temporary HOME/settings).

usage: capture_populated_emtk.py <out_dir> [<guide_figure.png>]
"""
import sys, time, pathlib, os, tempfile
sys.path.insert(0, ".")
import test.gui.emtk_port_parity  # noqa: F401  (before anything shadows the stdlib `test`)
from chisurf.plugins.burst.mfd_prepare.gui.app import make_app
from chisurf.plugins.emtk_test_input import Driver

out = pathlib.Path(sys.argv[1])
FOLDER = pathlib.Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burst_analysis_handoff").resolve()


def settle(d):
    while d.app.job.busy:
        d.draw(1)
        time.sleep(0.05)
    d.draw(3)


for size in ((1200, 800), (800, 600)):
    tag = f"{size[0]}x{size[1]}"
    app = make_app()
    d = Driver(app, size)
    d.screenshot(out / f"after_empty_{tag}.png")
    app.files_dropped([str(FOLDER)])
    d.click_name("prepare")
    settle(d)
    d.screenshot(out / f"after_populated_{tag}.png")
    if size[0] == 1200:
        if len(sys.argv) > 2:
            d.screenshot(sys.argv[2])
        d.click_name("browse")
        d.screenshot(out / f"after_dialog_{tag}.png")
        d.click_text("Cancel")
        d.click_name("help")
        d.screenshot(out / f"after_help_{tag}.png")
        app.help_window.hide(); d.draw(2)
        d.click_name("guide")
        d.screenshot(out / f"after_tour_{tag}.png")
        app.tour.active = False; d.draw(2)
        app.files_dropped([tempfile.mkdtemp()])
        d.click_name("prepare")
        settle(d)
        d.screenshot(out / f"after_error_{tag}.png")
    else:
        d.wheel(400, 560, steps=-8)
        d.screenshot(out / f"after_populated_scrolled_{tag}.png")
print("ok")
