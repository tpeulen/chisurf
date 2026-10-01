"""Qt baseline of RICS precision (the AutoForm tool as committed, HEAD gui/tool.py), populated.

Run: python okf/plugins/emtk-ports/rics_precision/scripts/capture_qt.py <out-dir> <prefix>
Settings: the default acquisition with a small estimator (n_repeats 10, n_images 20) so the sweep takes seconds.
"""
import os, sys, pathlib, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from qt_head import load_head_tool
from qtpy import QtWidgets, QtCore
out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
klass, _ = load_head_tool("rics_precision")
tool = klass(); tool.resize(1200, 800); tool.show()
def pump(n=20):
    for _ in range(n): app.processEvents()
pump(); tool.grab().save(str(out / f"{prefix}_empty.png"))
m = tool.model
m.n_repeats, m.n_images = 10, 20
tool.auto_form.sync_fields(); pump()
tool.run_with_progress()
t0 = time.time()
while m.sweep is None and time.time() - t0 < 120:
    pump(5); time.sleep(0.1)
pump(30)
print("status:", m.status)
tool.grab().save(str(out / f"{prefix}_populated.png"))
rows = m.sweep_rows(); print("rows:", len(rows)); [print(r) for r in rows]
# CSV export through a patched dialog
target = pathlib.Path(tempfile.mkdtemp()) / "rics_precision.csv"
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target), ""))
tool._export_csv(); print("csv:", repr(target.read_text()[:400]))
# the error state: a lag count no 8x8 image can support
m.nx, m.ny, m.n_lags = 8, 8, 15
tool.run_with_progress(); t0 = time.time()
while "failed" not in m.status.lower() and time.time() - t0 < 60:
    pump(5); time.sleep(0.1)
pump(30); print("error status:", m.status)
tool.grab().save(str(out / f"{prefix}_error.png"))
# export with nothing predicted (the sweep was reset by the failure)
target2 = target.with_name("none.csv")
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target2), ""))
tool._export_csv(); print("export without sweep wrote:", target2.exists())
tool.close()
