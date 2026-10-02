"""Render native calibration with the same populated photon histograms as Qt."""

from pathlib import Path

import numpy as np
from emtk.pil_painter import PilPainter

from chisurf.plugins.microscopy.img_calibration.gui.app import make_app

app = make_app()
model = app.model
app.apply_setup_settings(
    {"detectors": {"green": {"chs": [0, 1], "ch_p": [0], "ch_s": [1]}, "red": {"chs": [2, 3]}}}
)
model.filename = "Reference FLIM source.ptu"
model.sel_irf_files = ["Reference IRF.ptu"]
x = np.arange(256)
vv = 3 + 900 * np.exp(-np.maximum(x - 35, 0) / 42) * (x >= 35)
vh = 2 + 450 * np.exp(-np.maximum(x - 35, 0) / 32) * (x >= 35)
model._hist_cache[model._hist_key()] = {
    "n": 256,
    "data": vv + vh,
    "data_vv": vv,
    "data_vh": vh,
    "irf_vv_raw": 3 + 300 * np.exp(-(((x - 35) / 5) ** 2)),
    "irf_vh_raw": 2 + 200 * np.exp(-(((x - 38) / 6) ** 2)),
}
model.set_conv_range(32, 220)
model.set_irf_range(20, 65)
model.set_bg_range(0, 20)
output = Path(__file__).resolve().parents[5] / "okf/plugins/emtk-native/calibration-populated"
output.mkdir(parents=True, exist_ok=True)
for width, height in ((1200, 800), (800, 600)):
    for _ in range(3):
        painter = PilPainter(width, height)
        app.draw(painter, 0, 0, width, height)
    painter.frame.save(output / f"{width}x{height}.png")
