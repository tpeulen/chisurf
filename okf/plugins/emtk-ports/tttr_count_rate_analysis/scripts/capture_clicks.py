"""The real flow with simulated clicks and typing, a screenshot after each step (Leica_SP5.ptu, real reader).

Run from the repo root: python okf/plugins/emtk-ports/tttr_count_rate_analysis/scripts/capture_clicks.py <out-dir>
"""
import os, sys, pathlib, tempfile, time
import tttrlib
from emtk.testing import PixelPainter, png_encode
from chisurf.plugins.tttr.tttr_count_rate_analysis.tests.pointer import Pointer
from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller import create_app

out = pathlib.Path(sys.argv[1]).resolve(); SIZE = (1200, 800)
ptu = pathlib.Path("test/data/clsm/Leica_SP5.ptu").resolve()
tmp = pathlib.Path(tempfile.mkdtemp()); os.chdir(tmp)
(tmp / "leica.ptu").symlink_to(ptu)
routing = [int(c) for c in tttrlib.TTTR(str(ptu)).get_used_routing_channels()]
channels = {"all": [{"detector_chs": routing, "micro_time_range": None, "window_range": None}]}
app = create_app(); app.tool.channels = lambda: channels
ui = Pointer(app, SIZE)

def shot(name):
    painter = PixelPainter(*SIZE)
    app.draw(painter, 0.0, 0.0, float(SIZE[0]), float(SIZE[1]))
    (out / f"click_{name}_{SIZE[0]}x{SIZE[1]}.png").write_bytes(png_encode(painter.width, painter.height, painter.px))
    ui.frame(2)

def settle():
    t0 = time.time()
    while app.tool.job.running and time.time() - t0 < 120:
        if app.tool.job.future is not None:
            try: app.tool.job.future.result(timeout=0.5)
            except Exception: pass
        ui.frame()
    ui.frame(3)

shot("1_before_add_files")
ui.click("Calculate"); shot("2_after_click_calculate_without_files")
ui.click("Add files"); shot("3_after_click_add_files_dialog")
ui.click("leica.ptu"); ui.click("Open"); shot("4_after_picking_the_file_and_open")
ui.click("Calculate"); settle(); shot("5_after_click_calculate")
ui.click("Leica_SP5.ptu"); shot("6_after_click_the_row_remove_enabled")
ui.right_click("Leica_SP5.ptu"); shot("7_after_right_click_the_row")
ui.click("Remove from queue"); shot("8_after_click_remove_from_queue")
ui.click("Save"); shot("9_after_click_save_with_nothing_new")
print("files", app.tool._model.files, "| message:", app.tool.message, "| rows:", app.tool._model.results_rows())
