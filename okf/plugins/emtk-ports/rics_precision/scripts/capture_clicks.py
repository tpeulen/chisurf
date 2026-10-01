"""The real flow with simulated clicks and typing, a screenshot before and after each step.

Run from the repo root: python okf/plugins/emtk-ports/rics_precision/scripts/capture_clicks.py <out-dir>
"""
import os, sys, pathlib, tempfile, time
from emtk.events import CONTROL_MODIFIER
from emtk.testing import PixelPainter, png_encode
from chisurf.plugins.calculator.rics_precision.test.pointer import Pointer
from chisurf.plugins.calculator.rics_precision.gui.app import RicsPrecisionApp

out = pathlib.Path(sys.argv[1]).resolve(); SIZE = (1200, 800)
tmp = pathlib.Path(tempfile.mkdtemp()); os.chdir(tmp)
app = RicsPrecisionApp(); app.model.n_repeats, app.model.n_images = 10, 20
ui = Pointer(app, SIZE)

def shot(name):
    """One more frame, drawn to pixels: the state the events left, not a re-settled one."""
    painter = PixelPainter(*SIZE)
    app.draw(painter, 0.0, 0.0, float(SIZE[0]), float(SIZE[1]))
    (out / f"click_{name}_{SIZE[0]}x{SIZE[1]}.png").write_bytes(png_encode(painter.width, painter.height, painter.px))
    ui.frame(2)          # the pixel painter measures text differently: re-lay-out before the next event

def field(name, text):
    x, y, w, h = app.form.rects[name]
    ui.click((x + w / 2, y + h / 2)); ui.key(ord("A"), "a", CONTROL_MODIFIER); ui.type(text); ui.enter()

def finish():
    t0 = time.time()
    while app.job.busy and time.time() - t0 < 120:
        if app.job.thread is not None: app.job.thread.join(timeout=0.2)
        ui.frame()
    ui.frame(2)

shot("1_before_predict")
ui.click("Predict"); finish(); shot("2_after_click_predict")
field("pixel_time_us", "15.8"); ui.click("Predict"); finish(); shot("3_after_typing_dwell_15_8_and_predict")
ui.click("▴ Error [%]") if False else ui.click("Error [%]"); shot("4_after_click_error_header_sort")
ui.click("Estimator"); shot("5_after_click_estimator_unfolded")
field("n_lags", "15"); field("nx", "8"); field("ny", "8"); ui.click("Predict"); finish(); shot("6_after_bad_setting_predict")
ui.click("Export CSV"); shot("7_after_click_export_csv_nothing_to_write")
print("status:", app.model.status, "| notice:", app.notice)
