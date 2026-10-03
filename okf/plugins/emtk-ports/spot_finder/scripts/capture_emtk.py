"""Populated emtk captures of the Spot Finder (usage: capture_emtk.py <out> <prefix> [WxH...]): demo loaded, Detect run."""
import pathlib, sys, time
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.microscopy.spot_finder.gui.app import make_app
out, prefix = pathlib.Path(sys.argv[1]), sys.argv[2]
sizes = [tuple(map(int, a.split("x"))) for a in sys.argv[3:]] or [(1200, 800), (800, 600)]
def settle(app, size):
    end = time.time() + 180
    while app.job.busy and time.time() < end:
        app.draw(RecordingPainter(), 0, 0, *size); time.sleep(0.02)
    for _ in range(3): app.draw(RecordingPainter(), 0, 0, *size)
for size in sizes:
    app = make_app(); settle(app, size)
    emtk_screenshot(app, out / f"{prefix}_empty_{size[0]}x{size[1]}.png", size)
    app.start("load_demo"); settle(app, size)
    app.start("run"); settle(app, size)
    emtk_screenshot(app, out / f"{prefix}_detected_{size[0]}x{size[1]}.png", size)
    print(app.model.summary(), app.error)
