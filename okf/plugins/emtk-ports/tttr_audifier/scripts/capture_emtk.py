"""Populated emtk captures of the audifier: BH SPC-132 file loaded, waterfall computed (usage: capture_emtk.py <out> <prefix> [WxH...])"""
import pathlib, sys, time
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.tttr.audifier.gui.app import create_app
out, prefix = pathlib.Path(sys.argv[1]), sys.argv[2]
sizes = [tuple(map(int, a.split("x"))) for a in sys.argv[3:]] or [(1200, 800), (800, 600)]
def settle(app, size):
    end = time.time() + 120
    while (app.job.running or app.editor._future is not None) and time.time() < end:
        app.draw(RecordingPainter(), 0, 0, *size); time.sleep(0.02)
    for _ in range(3): app.draw(RecordingPainter(), 0, 0, *size)
for size in sizes:
    app = create_app()
    app.draw(RecordingPainter(), 0, 0, *size)
    app.editor.model.data.setdefault("tttr_reading", {})["file_type"] = "SPC-130"   # an .spc needs its subtype chosen
    app.load("test/data/tttr/BH/132/BH_SPC132.spc"); settle(app, size)
    app.compute_waterfall(); settle(app, size)
    for panel in ("setup", "audio", "waterfall_parameters", "waterfall", "mixer", "notes"):
        app.docks.focus(panel)
        for _ in range(3): app.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(app, out / f"{prefix}_{panel}_{size[0]}x{size[1]}.png", size)
    print(app.message)
    app.close()
