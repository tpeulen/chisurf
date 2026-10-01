"""The order a user meets it: the window drawn empty first, then Demo and Estimate pressed (frames throughout).

usage: capture_live.py <out_dir>   -- the fragments axis must hold every bar on a plot that existed before the data.
"""
import pathlib, sys, time
from test.gui.emtk_port_parity import emtk_screenshot
from emtk.testing import RecordingPainter
from chisurf.plugins.burst.burst_fusion.gui.app import create_app

out = pathlib.Path(sys.argv[1])
a = create_app()
for _ in range(2):
    a.draw(RecordingPainter(), 0, 0, 1200, 800)
for action in (a.controller.demo, a.controller.estimate):
    action()
    while a.controller.running:
        time.sleep(0.05); a.draw(RecordingPainter(), 0, 0, 1200, 800)
emtk_screenshot(a, out / "after_live_1200x800.png", (1200, 800))
a.close()
