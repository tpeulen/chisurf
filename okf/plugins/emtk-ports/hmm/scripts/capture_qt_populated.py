"""Populated Qt baseline: the AutoForm tool with a loaded trace, a fit and a state scan. Usage: <out_dir>. Temp HOME/settings/QSettings."""
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from make_data import write_trace
import numpy as np
from qtpy import QtCore, QtWidgets
tmp = pathlib.Path(tempfile.mkdtemp())
QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, str(tmp / "qt"))
out = pathlib.Path(sys.argv[1]); trace = write_trace(tmp / "data")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.core.hmm.gui.tool import HmmTool
w = HmmTool(); w.resize(1200, 800); w.show()
def shot(name):
    for _ in range(40): app.processEvents()
    w.grab().save(str(out / f"before_populated_{name}.png"))
shot("0_empty")
m = w.model; m.files = [trace]; m.n_states = 3; m.time_step = 0.001; m.max_states = 5
m.run(); w._refresh(); shot("1_fit_3_states")
m.run_scan(); w._refresh(); shot("2_state_scan")
f = m.fit
res = {"n_states": f.n_states, "log_likelihood": f.log_likelihood, "bic": f.bic, "n_iterations": f.n_iterations, "converged": bool(f.converged),
       "means": np.asarray(f.means).tolist(), "transmat": np.asarray(f.transmat).tolist(), "rates": np.asarray(f.transition_rates).tolist(),
       "occupancy": [s.occupancy for s in f.summaries], "dwell": [s.mean_dwell for s in f.summaries], "visits": [s.n_dwells for s in f.summaries],
       "scan_n": list(m._scan.n_states), "scan_bic": list(map(float, m._scan.bic)), "scan_aic": list(map(float, m._scan.aic)), "best_bic": m._scan.best_bic, "best_aic": m._scan.best_aic,
       "status": m._status}
json.dump(res, open(out / "qt_values.json", "w"), indent=1); print(res["status"], res["best_bic"])
