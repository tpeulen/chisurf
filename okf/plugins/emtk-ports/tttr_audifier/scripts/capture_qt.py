"""Populated Qt baseline of the TTTR Audifier: BH SPC-132 test file, two detectors, micro-time and lifetime waterfalls.
usage: capture_qt.py <out_dir>  (repo root, offscreen, temporary HOME/settings; nothing is played)"""
import pathlib, sys, time
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.tttr.audifier.gui.tool import TTTRAudifierWidget
out = pathlib.Path(sys.argv[1])
def pump(n=30):
    for _ in range(n): app.processEvents(); time.sleep(0.02)
w = TTTRAudifierWidget(); w.resize(1200, 800); w.show(); pump()
w.grab().save(str(out / "before_populated_empty.png"))
m = w.model
m.load(str(pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc").resolve()))
m.set_detectors_from_settings({"detectors": {"Green": {"chs": [0, 8]}, "Red": {"chs": [1, 9]}}})
m.compute_waterfall(); m.notify("loaded"); m.notify("channels"); pump(40)
tabs = w.findChildren(QtWidgets.QTabBar)
bar = max(tabs, key=lambda t: t.count())
names = [bar.tabText(i) for i in range(bar.count())]
print("tabs", names)
def shoot(tag):
    for i, n in enumerate(names):
        bar.setCurrentIndex(i); pump(15)
        w.grab().save(str(out / f"before_populated_{tag}_{n.lower().replace(' ', '_')}.png"))
shoot("microtime")
m.waterfall_mode = "lifetime"; m.compute_waterfall(); m.notify("waterfall"); w.auto_form.refresh_plots(); pump(40)
shoot("lifetime")
print("events", len(m.data.macro_ticks), "channels", m.channels, "payload", {k: getattr(v, "shape", v) for k, v in (m._waterfall_payload or {}).items() if k in ("rgb_data", "info")})
