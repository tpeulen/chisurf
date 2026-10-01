"""The upgraded emtk app in the scenarios of capture_qt_populated.py (seed 7). Usage: <out_dir>."""
import pathlib, sys, time
import numpy as np
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.calculator.kappa2_dist.gui.app import make_app

out = pathlib.Path(sys.argv[1])
size = (1200, 800)


def settle(app, size):
    app.draw(RecordingPainter(), 0, 0, *size)
    while app.tool.busy or app.tool.dirty:
        time.sleep(0.005); app.draw(RecordingPainter(), 0, 0, *size)
    for _ in range(2): app.draw(RecordingPainter(), 0, 0, *size)


def run(app, size, **inputs):
    for k, v in inputs.items(): setattr(app.tool._model, k, v)
    np.random.seed(7); app.kappa2_gui.on_compute(); settle(app, size)


def shot(app, name, size=size):
    settle(app, size)
    emtk_screenshot(app, out / f"after_populated_{name}_{size[0]}x{size[1]}.png", size)


for sz in [(1200, 800), (800, 600)]:
    np.random.seed(7); app = make_app(); shot(app, "default", sz)
    run(app, sz, model_type="isotropic"); shot(app, "isotropic", sz)
    run(app, sz, model_type="diffusion", fret_efficiency=0.4); shot(app, "diffusion", sz)
    run(app, sz, model_type="cone", r_Dinf=0.15, n_bins=60, step=3.0, rAD_known=True); shot(app, "cone_rAD_known", sz)
    run(app, sz, kappa2_true=1.0, r_ADinf=0.4, r_0=0.38, r_Ainf=0.1); shot(app, "nan_results", sz)
    if sz == size:
        app = make_app(); run(app, sz)
        app.kappa2_gui.on_save(); shot(app, "save_dialog")
        app = make_app(); app.kappa2_gui.show_help(); shot(app, "help")
        app = make_app(); app.kappa2_gui.tour.start(2); shot(app, "guide_compute_step")
        app = make_app(); shot(app, "narrow", (500, 500))
