"""The upgraded emtk app driven with simulated pointer and keys on the REAL plugin list and a REAL safe sweep
(ten child processes on throw-away settings and HOME). Usage: <out_dir>. Writes after_populated_*.png and click_*.png."""
import pathlib, sys, time
from test.gui.emtk_port_parity import emtk_screenshot
from emtk import keys
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.core.plugin_check.gui.app import make_app

out = pathlib.Path(sys.argv[1])
n = [0]


def shot(drv, name, size):
    n[0] += 1
    drv.draw(3, size=size)
    emtk_screenshot(drv.app, out / f"click_{n[0]}_{name}.png", size)


for size in ((1200, 800), (800, 600)):
    app = make_app(); app.model.delay = 0.0
    d = Driver(app, size); d.draw(3)
    if size == (1200, 800):
        shot(d, "start_real_plugin_list_pending", size)
    d.click("test_safe")
    if size == (1200, 800):
        time.sleep(4); shot(d, "safe_sweep_done_first_row_selected", size)
    end = time.monotonic() + 240
    while app.model.running and time.monotonic() < end:
        time.sleep(0.2); d.draw(1)
    d.draw(3)
    emtk_screenshot(app, out / f"after_populated_{size[0]}x{size[1]}.png", size)
    if size == (1200, 800):
        failed = [k for k, r in app.model.results.items() if r["status"] == "fail"]
        key = failed[0] if failed else next(iter(app.model.results))
        x, y, w, h = app.form.rects["check_rows"]
        name = app.model.name_of(key)
        d.click_text(name if name in d.strings() else [s for s in d.strings() if name.startswith(s.rstrip("."))][0])
        shot(d, f"selected_{app.model.status_of(key)}_row_details", size)
        d.click_text("Plugin"); shot(d, "sorted_by_plugin", size)
        d.click_text("filter"); d.type_text("fcs"); shot(d, "filter_fcs_typed", size)
        for _ in range(3): d.key(keys.KEY_BACKSPACE)
        d.click_text("Help"); shot(d, "help_window", size)
        d.click_text("Close Help", last=True)
        d.click_text("Guide"); shot(d, "guide_first_step", size)
        app.tour.stop()
        d.type_into("delay", "1.5"); shot(d, "delay_typed_1.5_enter", size)
    app.close()
