"""emtk RICS precision in the same populated states as capture_qt.py (make_app: the standalone app).

Run: python okf/plugins/emtk-ports/rics_precision/scripts/capture_emtk.py <out-dir> <prefix> [WxH]
"""
import sys, pathlib, time
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.calculator.rics_precision.gui.app import make_app

out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
size = tuple(int(v) for v in (sys.argv[3] if len(sys.argv) > 3 else "1200x800").split("x"))
app = make_app()
model = app.precision_gui.model if hasattr(app, "precision_gui") else app.model

def draw(n=2):
    for _ in range(n):
        app.draw(RecordingPainter(), 0, 0, *size)

def shot(name):
    draw(1)
    emtk_screenshot(app, out / f"{prefix}_{name}_{size[0]}x{size[1]}.png", size)

def wait(cond, limit=120):
    t0 = time.time()
    while not cond() and time.time() - t0 < limit:
        draw(1); time.sleep(0.1)

shot("empty")
model.n_repeats, model.n_images = 10, 20
if hasattr(app, "predict"):
    app.predict()
else:
    app.precision_gui.on_predict()
wait(lambda: model.sweep is not None)
draw(3)
print("status:", model.status)
for r in model.sweep_rows(): print(r)
shot("populated")
model.nx, model.ny, model.n_lags = 8, 8, 15
if hasattr(app, "predict"):
    app.predict()
else:
    app.precision_gui.on_predict()
wait(lambda: "failed" in model.status.lower())
draw(3); print("error status:", model.status); shot("error")
