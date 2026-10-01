"""Gated (high FRET, donor-only dropped) and the folder dialog, on the demo folder. usage: capture_states.py <out_dir>"""
import pathlib, sys, tempfile, time
from test.gui.emtk_port_parity import emtk_screenshot
from emtk.testing import RecordingPainter
from chisurf.plugins.burst.burst_browser.gui.app import create_app
from chisurf.plugins.burst.burst_browser.test.demo_folder import build

out = pathlib.Path(sys.argv[1])
root = build(pathlib.Path(tempfile.mkdtemp()) / "measurement")
a = create_app()
a.load_folder(root)
while a.controller.running or a.table is None:
    time.sleep(0.05); a.draw(RecordingPainter(), 0, 0, 1200, 800)
a.model.hist_column = "S"
a.model.e_min, a.model.e_max, a.model.s_min, a.model.s_max = 0.5, 0.9, 0.3, 0.7
a.model.refresh()
for _ in range(3):
    a.draw(RecordingPainter(), 0, 0, 1200, 800)
emtk_screenshot(a, out / "after_gated_1200x800.png", (1200, 800))
a.close()
b = create_app()
b.controller.browse("file")
for _ in range(2):
    b.draw(RecordingPainter(), 0, 0, 1200, 800)
emtk_screenshot(b, out / "after_file_dialog_1200x800.png", (1200, 800))
b.close()
