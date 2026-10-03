"""Populated emtk captures of CLSM Pixel Select (usage: capture_emtk.py <out> <prefix> [WxH...]): Leica SP5 built, representation, painted selection."""
import pathlib, sys, time
import numpy as np
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.microscopy.clsm.gui.app import ClsmApp
out, prefix = pathlib.Path(sys.argv[1]), sys.argv[2]
sizes = [tuple(map(int, a.split("x"))) for a in sys.argv[3:]] or [(1200, 800), (800, 600)]
def settle(app, size):
    end = time.time() + 180
    while app.job.busy and time.time() < end:
        app.draw(RecordingPainter(), 0, 0, *size); time.sleep(0.02)
    for _ in range(3): app.draw(RecordingPainter(), 0, 0, *size)
for size in sizes:
    app = ClsmApp(); settle(app, size)
    emtk_screenshot(app, out / f"{prefix}_empty_{size[0]}x{size[1]}.png", size)
    app.start("load_file", str(pathlib.Path("test/data/clsm/Leica_SP5.ptu").resolve())); settle(app, size)
    app.start("add_clsm"); settle(app, size)
    app.start("add_representation"); settle(app, size)
    m = app.model
    ny, nx = m.selection_mask.shape
    m.selection_mask[ny // 3: ny // 2, nx // 3: nx // 2] = 1
    app.selection_changed(); app.request_decay(); settle(app, size); time.sleep(0.5); settle(app, size)
    emtk_screenshot(app, out / f"{prefix}_selected_{size[0]}x{size[1]}.png", size)
    print(app.status, app.error)
