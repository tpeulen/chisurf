"""Populated Qt baseline: stack loaded from a TIFF, beads detected, one fitted. Usage: <out_dir>. Temp HOME/settings/QSettings."""
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from make_data import write_stack
import numpy as np
from qtpy import QtCore, QtWidgets
tmp = pathlib.Path(tempfile.mkdtemp())
QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, str(tmp / "qt"))
out = pathlib.Path(sys.argv[1]); path = write_stack(tmp / "data")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.microscopy.psf_determination.gui.tool import PsfDeterminationTool
w = PsfDeterminationTool(); w.resize(1200, 800); w.show()
def shot(name):
    for _ in range(40): app.processEvents()
    w.grab().save(str(out / f"before_populated_{name}.png"))
shot("0_empty")
m = w.model; m.pixel_size_nm = 100.0; m.z_step_nm = 300.0
m.load_stack(path); shot("1_stack_loaded")
n = m.detect_beads(); shot("2_beads_detected")
m.selected_bead = (10, 20, 20); r = m.fit_selected(); shot("3_bead_fitted")
rows = m.fit_all(); shot("4_fit_all")
bars = w.findChildren(QtWidgets.QTabBar)
if bars:
    bar = max(bars, key=lambda b: b.count())
    for i in range(bar.count()):
        bar.setCurrentIndex(i); shot("5_tab_%d_%s" % (i, bar.tabText(i).replace(" ", "_")))
res = {"detected": n, "beads": [list(map(int, b)) for b in m.detected_beads], "fit": {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in (r or {}).items() if not isinstance(v, (list, dict, np.ndarray))},
       "fit_all": [{k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in row.items() if not isinstance(v, (list, dict, np.ndarray))} for row in rows], "results_text": m.results_text}
pathlib.Path(out / "qt_values.json").write_text(json.dumps(res, indent=1, default=str)); print(n, res["fit"]); 
m.export_csv(str(tmp / "batch.csv")); (out / "qt_batch.csv").write_text((tmp / "batch.csv").read_text())
