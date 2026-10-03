"""Populated Qt baseline of the Spot Finder: the tool's own known-field demo (four objects, simulated PTU), Preview, Detect, a pick.
usage: capture_qt.py <out_dir> (repo root, offscreen, temporary HOME/settings)"""
import pathlib, sys, time
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.microscopy.spot_finder.gui.tool import SpotFinderTool
out = pathlib.Path(sys.argv[1])
def pump(n=30):
    for _ in range(n): app.processEvents(); time.sleep(0.02)
w = SpotFinderTool(); w.resize(1200, 800); w.show(); pump()
w.grab().save(str(out / "before_populated_empty.png"))
m = w.model
m.load_demo(); pump(30)
w.grab().save(str(out / "before_populated_demo_loaded.png"))
m.preview(); w._refresh_region_overlays(); pump(30)
w.grab().save(str(out / "before_populated_preview.png"))
m.run(); w._refresh_region_overlays(); pump(30)
w.grab().save(str(out / "before_populated_detected.png"))
print(m.summary()); print([ (e["label"], e["badge"]) for e in m.region_entries()][:6]); print(m.run_entries()[:2])
print("settings", m.settings)
