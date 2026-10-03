"""Populated emtk captures of the CLSM Generator (usage: capture_emtk.py <out> <prefix> [WxH...])."""
import pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fixtures
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.microscopy.clsm_generator.gui.app import make_app
out, prefix = pathlib.Path(sys.argv[1]), sys.argv[2]
sizes = [tuple(map(int, a.split("x"))) for a in sys.argv[3:]] or [(1200, 800), (800, 600)]
def settle(app, size):
    end = time.time() + 120
    while app.job.busy and time.time() < end:
        app.draw(RecordingPainter(), 0, 0, *size); time.sleep(0.02)
    for _ in range(3): app.draw(RecordingPainter(), 0, 0, *size)
for size in sizes:
    app = make_app(); settle(app, size)
    emtk_screenshot(app, out / f"{prefix}_empty_{size[0]}x{size[1]}.png", size)
    i, l0, l1 = fixtures.make(tempfile.mkdtemp())
    app.load_maps([i]); app.load_maps([l0, l1], lifetime=True)
    app.model.n_lifetime_levels = 4; app.model.n_intensity_levels = 4
    app.generate(); settle(app, size)
    emtk_screenshot(app, out / f"{prefix}_generated_{size[0]}x{size[1]}.png", size)
    print(app.model.status_text, app.error)
