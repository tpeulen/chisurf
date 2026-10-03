"""Populated Qt baseline of CLSM Pixel Select: Leica SP5 PTU, Build CLSM, an intensity and a micro-time representation, a painted selection and its decay.
usage: capture_qt.py <out_dir> (repo root, offscreen, temporary HOME/settings)"""
import pathlib, sys, time
import numpy as np
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.microscopy.clsm.gui.tool import CLSMPixelSelect
out = pathlib.Path(sys.argv[1])
def pump(n=30):
    for _ in range(n): app.processEvents(); time.sleep(0.02)
w = CLSMPixelSelect(); w.resize(1200, 800); w.show(); pump()
w.grab().save(str(out / "before_populated_empty.png"))
m = w.model
m.load_file(str(pathlib.Path("test/data/clsm/Leica_SP5.ptu").resolve()))
m.add_clsm(); m.add_representation(); pump(40)
img = m.current_image
mask = m.selection_mask
if mask is not None:
    ny, nx = mask.shape
    mask[ny // 3: ny // 2, nx // 3: nx // 2] = 1
    m.recompute_decay(); m.notify("decay"); m.notify("selection")
w.auto_form.sync_fields(); w.auto_form.refresh_plots(); pump(40)
tabs = max(w.findChildren(QtWidgets.QTabBar), key=lambda t: t.count())
for i in range(tabs.count()):
    tabs.setCurrentIndex(i); pump(15)
    w.grab().save(str(out / f"before_populated_{tabs.tabText(i).lower().replace(' ', '_')}.png"))
print("image", getattr(img, "shape", None), "decay", None if m.current_decay is None else {k: getattr(v, "shape", v) for k, v in m.current_decay.items()} if isinstance(m.current_decay, dict) else type(m.current_decay))
