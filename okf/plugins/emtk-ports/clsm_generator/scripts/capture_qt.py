"""Populated Qt baseline of the CLSM Generator: input maps loaded, a photon image generated, viewer on each map.
usage: capture_qt.py <out_dir> (repo root, offscreen, temporary HOME/settings)"""
import pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fixtures
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.microscopy.clsm_generator.gui.tool import ClsmGeneratorTool
out = pathlib.Path(sys.argv[1])
def pump(n=30):
    for _ in range(n): app.processEvents(); time.sleep(0.02)
w = ClsmGeneratorTool(); w.resize(1200, 800); w.show(); pump()
w.grab().save(str(out / "before_populated_empty.png"))
m = w.model
i, l0, l1 = fixtures.make(tempfile.mkdtemp())
m.sel_intensity = i; m.sel_lifetime_files = [l0, l1]
m.n_lifetime_levels = 4; m.n_intensity_levels = 4
m.notify("settings"); w.auto_form.sync_fields(); pump(30)
w.grab().save(str(out / "before_populated_maps_loaded.png"))
m.generate(); w.auto_form.sync_fields(); w.auto_form.refresh_plots(); pump(40)
w.grab().save(str(out / "before_populated_generated.png"))
bar = max(w.findChildren(QtWidgets.QTabBar), key=lambda t: t.count())
bar.setCurrentIndex(1); pump(20)
w.grab().save(str(out / "before_populated_maps_tab.png"))
print(m.status_text, [e["label"] for e in m.view_entries()])
