"""The real flow with simulated clicks and typing, a screenshot after each step (Leica_SP5.ptu, real client).

Run from the repo root: python okf/plugins/emtk-ports/tttr_time_windows/scripts/capture_clicks.py <out-dir>
"""
import os, sys, pathlib, tempfile, time
from emtk.events import CONTROL_MODIFIER
from emtk.testing import PixelPainter, png_encode
from chisurf.plugins.tttr.tttr_time_windows.tests.pointer import Pointer
from chisurf.plugins.tttr.tttr_time_windows.gui.controller import create_app

out = pathlib.Path(sys.argv[1]).resolve(); SIZE = (1200, 800)
ptu = pathlib.Path("test/data/clsm/Leica_SP5.ptu").resolve()
tmp = pathlib.Path(tempfile.mkdtemp()); os.chdir(tmp)
(tmp / "leica.ptu").symlink_to(ptu)
app = create_app(); ui = Pointer(app, SIZE)

def shot(name):
    painter = PixelPainter(*SIZE)
    app.draw(painter, 0.0, 0.0, float(SIZE[0]), float(SIZE[1]))
    (out / f"click_{name}_{SIZE[0]}x{SIZE[1]}.png").write_bytes(png_encode(painter.width, painter.height, painter.px))
    ui.frame(2)

def settle():
    t0 = time.time()
    tool = app.tool
    while (tool.job.running or tool.job.future is not None or tool.process_pending) and time.time() - t0 < 300:
        if tool.job.future is not None:
            try: tool.job.future.result(timeout=0.5)
            except Exception: pass
        ui.frame()
    ui.frame(3)

def field(text):
    x, y, w, h = app.item_rects["time_window"]
    ui.click((x + w / 2, y + h / 2)); ui.key(ord("A"), "a", CONTROL_MODIFIER); ui.type(text); ui.enter()

shot("1_before_files")
ui.click("Files"); shot("2_after_click_files_dialog")
ui.click("leica.ptu"); ui.click("Open"); settle(); shot("3_after_picking_the_file_preview_loaded")
field("10000"); settle(); shot("4_after_typing_the_window_10000_ms")
ui.click("Auto (derived from first file)"); ui.type(str(tmp / "out")); ui.enter(); shot("5_after_typing_the_output_folder")
ui.click("Process"); settle(); shot("6_after_click_process")
ui.click("Clear"); shot("7_after_click_clear")
print("window", app.tool.time_window_ms, "| output", sorted(p.name for p in (tmp / "out").rglob("*") if p.is_file()), "| log", app.tool._log_lines[-3:])
