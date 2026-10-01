"""Qt baseline in populated states (the genuine Qt tool: HEAD __init__.py == qt_tool.py).

Run: python okf/plugins/emtk-ports/vv_vh_anisotropy/scripts/capture_qt.py <out-dir> <prefix>
"""
import os, sys, tempfile, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("CHISURF_PLOT_BACKEND", "pyqtgraph")
import numpy as np
from qtpy import QtWidgets
from data import make
from chisurf.gui import chiplot
from chisurf.plugins.vv_vh_anisotropy.qt_tool import VvVhAnisotropyCalculator, VvVhAnisotropyBatchWindow

out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
chiplot.set_backend("pyqtgraph")
tmp = pathlib.Path(tempfile.mkdtemp())
a = make(tmp / "a.dat", seed=1); b = make(tmp / "b.dat", seed=2, rinf=0.08)
bad = tmp / "bad.dat"; bad.write_text("not numbers\n")

def pump(n=20):
    for _ in range(n): app.processEvents()

w = VvVhAnisotropyCalculator(); w.resize(1200, 800); w.show(); pump()
w.grab().save(str(out / f"{prefix}_empty.png"))
w.load_vv_vh_file(a); pump()
w.g_spin.setValue(1.05); w.bg_vv_spin.setValue(12.0); w.bg_vh_spin.setValue(9.0); w.shift_spin.setValue(1.5); pump()
w.grab().save(str(out / f"{prefix}_populated.png"))
print("r_inf:", w.rinf_line.text(), "region:", w.region_bounds, "label:", w.file_label.text())
try:
    w.load_vv_vh_file(bad)
except Exception as exc:                      # the Qt slot raises on a file without numbers
    print("QT RAISES on bad file:", type(exc).__name__, exc)
pump()
w.grab().save(str(out / f"{prefix}_load_error.png"))
print("after bad load label:", w.file_label.text(), "| data kept:", w.vv is not None)
w.load_vv_vh_file(a); pump()
# save outputs through a patched dialog, to see which files the Qt tool really writes
target = tmp / "result.txt"
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target), ""))
w.save_outputs()
print("saved:", sorted(p.name for p in tmp.glob("result*")))
for p in sorted(tmp.glob("result*")):
    print("---", p.name); print(p.read_text()[:300])
# batch window
w.open_batch(); bw = w._batch_window; bw.resize(900, 600); pump()
bw.file_list.add_paths([str(a), str(b)])
pump(); print("batch paths:", bw.file_list.paths())
bw.grab().save(str(out / f"{prefix}_batch_empty.png"))
import chisurf.gui.dialogs as d
d.information = lambda *a, **k: print("INFO:", a[1:])
bw._on_run(); pump()
bw.grab().save(str(out / f"{prefix}_batch_results.png"))
for r in bw.results: print("row", r)
bw.file_list.add_paths([str(bad)]); n = len(bw.results)
try:
    bw._on_run()
except Exception as exc:
    print("QT BATCH RAISES with a bad file in the list:", type(exc).__name__, exc, "| rows before:", n, "after:", len(bw.results))
pump(); bw.grab().save(str(out / f"{prefix}_batch_bad_file.png"))
csv = tmp / "batch.csv"
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(csv), ""))
bw._on_save(); print(csv.read_text())
