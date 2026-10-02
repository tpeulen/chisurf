"""Populated captures of the emtk app. Usage: capture_emtk.py <out_dir> <prefix: before_emtk | after>.

Builds the same state as the Qt capture (catalogue of 7 generated probes, default path, an APD on both detectors, simulated).
"""
import pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from test.gui import migration_parity as _mp  # noqa: F401
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import lp_env
from emtk import testing
from emtk.testing import PixelPainter

out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
from chisurf.plugins.core.lightpath_simulator.gui.app import create_app

app = create_app(client=lp_env.in_process_client())
ctrl = app.controller


def frame(size, painter_cls=PixelPainter):
    p = painter_cls(*size); app.draw(p, 0.0, 0.0, float(size[0]), float(size[1])); return p


def settle(size=(1200, 800), timeout=60):
    end = time.monotonic() + timeout
    frame(size)
    while (ctrl.running or ctrl.pending) and time.monotonic() < end:
        time.sleep(0.02); frame(size)
    return frame(size)


def shot(name, size):
    p = settle(size); p = frame(size)
    (out / f"{prefix}_{name}_{size[0]}x{size[1]}.png").write_bytes(testing.png_encode(p.width, p.height, p.px))


ctrl.auto_update = False
frame((1200, 800)); settle()
ctrl.reset(); settle()
for n in ctrl.document.nodes:
    if n.type == "detector":
        n.config["probe_id"] = lp_env.IDS["APD (flat QE)"]
ctrl.start(); settle()
print("probes", len(ctrl.probes), "signals", len(ctrl.result.get("detector_signals", [])), ctrl.status)
for size in ((1200, 800), (800, 600)):
    shot("populated", size)
app.close()
