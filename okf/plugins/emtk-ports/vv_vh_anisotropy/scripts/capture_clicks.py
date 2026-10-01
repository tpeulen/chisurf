"""The real flow with simulated clicks and typing, a screenshot before and after each step.

Run from the repo root: python okf/plugins/emtk-ports/vv_vh_anisotropy/scripts/capture_clicks.py <out-dir>
"""
import os, sys, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from data import make
from emtk.events import CONTROL_MODIFIER
from emtk.testing import PixelPainter, png_encode
from chisurf.plugins.vv_vh_anisotropy.test.pointer import Pointer
from chisurf.plugins.vv_vh_anisotropy.gui.app import create_app

out = pathlib.Path(sys.argv[1]).resolve(); SIZE = (1200, 800)
tmp = pathlib.Path(tempfile.mkdtemp()); os.chdir(tmp)
make(tmp / "a.dat", seed=1); make(tmp / "b.dat", seed=2, rinf=0.08)
app = create_app(); ui = Pointer(app, SIZE)

def shot(name):
    """One more frame, drawn to pixels: the state the events left, not a re-settled one."""
    painter = PixelPainter(*SIZE)
    app.draw(painter, 0.0, 0.0, float(SIZE[0]), float(SIZE[1]))
    (out / f"click_{name}_{SIZE[0]}x{SIZE[1]}.png").write_bytes(png_encode(painter.width, painter.height, painter.px))
    ui.frame(2)          # the pixel painter measures text differently: re-lay-out before the next event

def field(name, text):
    x, y, w, h = app.form.rects[name]
    ui.click((x + w / 2, y + h / 2)); ui.key(ord("A"), "a", CONTROL_MODIFIER); ui.type(text); ui.enter()

shot("1_before_load")
ui.click("Load VV/VH file…"); shot("2_after_click_load_dialog")
ui.click("a.dat"); ui.click("Open"); shot("3_after_click_open_populated")
field("g_factor", "1.2"); shot("4_after_typing_g_factor_1_2")
x0, y0, w0, h0 = app.item_rects["region_line_0"]
ui.drag((x0 + w0 / 2, y0 + h0 / 2), (x0 + w0 / 2 - 120.0, y0 + h0 / 2)); shot("5_after_dragging_the_start_line")
ui.click("Batch files…"); shot("6_after_click_batch")
ui.click("Files"); ui.click("a.dat"); ui.click("b.dat"); ui.click("Open"); shot("7_after_queueing_two_files")
ui.click("Run Batch"); shot("8_after_click_run_batch")
print("g", app.model.g_factor, "region", app.model.region_bounds, "r_inf", app.model.r_infty_text, "batch", [(r[0], round(r[1], 5)) for r in app.model.batch_results])
