"""Populated Qt baseline: a stub live fit (two-lifetime decay 1.1/3.6 ns + IRF) feeds the Qt tool; Run MEM, L-curve. Usage: <out_dir>.
Temp HOME / settings / QSettings only."""
import json, pathlib, sys, tempfile
from types import SimpleNamespace
import numpy as np
from qtpy import QtCore, QtWidgets
tmp = pathlib.Path(tempfile.mkdtemp())
QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, str(tmp / "qt"))
out = pathlib.Path(sys.argv[1])
from chisurf.plugins.fluorescence_decay.maxent_decay.test.test_solver_contract import _problem
from chisurf.plugins.fluorescence_decay.maxent_decay.gui.gui import MaxentDecayWidget
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
y, lamp, dt, t = _problem(n=256)
data = SimpleNamespace(x=t, y=y, name="two_lifetimes.dat", dx=np.array([dt]))
irf = SimpleNamespace(x=t, y=lamp, name="IRF.dat")
fit = SimpleNamespace(data=data, xmin=20, xmax=255, model=SimpleNamespace(
    convolve=SimpleNamespace(irf=irf, unnormalized_irf=irf, timeshift=0.0, lamp_background=0.0),
    generic=SimpleNamespace(background=5.0, scatter=0.0)))
w = MaxentDecayWidget(); w.resize(1200, 800); w._current_fit = lambda: fit; w.show()
def shot(name, widget=None):
    for _ in range(30): app.processEvents()
    (widget or w).grab().save(str(out / f"before_populated_{name}.png"))
res = {}
shot("0_empty_settings")
w._on_refresh_data(); w.spin_tau_bins.setValue(64); w.spin_tau_max.setValue(8.0); shot("1_data_loaded_settings")
shot("1b_decay_plot", w.plot_decay)
w._run_mem(); shot("2_after_run_settings"); shot("2b_decay_plot", w.plot_decay); shot("2c_residuals", w.plot_wres); shot("2d_distribution", w.plot_dist)
r = w._last_result
res["run"] = {k: (np.asarray(r[k]).tolist() if k in ("p", "tau") else float(np.asarray(r[k]).ravel()[0]) if np.ndim(r[k]) == 0 or np.size(r[k]) == 1 else None) for k in ("p", "tau", "chisq", "timeshift", "background", "sigma") if k in r}
res["settings"] = {n: getattr(w, n).value() for n in ("spin_nu", "spin_tau_min", "spin_tau_max", "spin_tau_bins", "spin_timeshift", "spin_background", "spin_irf_bg", "spin_lamp_scatter", "spin_period") if hasattr(w, n)}
try:
    w._run_lcurve(); shot("3_lcurve", w.plot_lcurve)
    res["lcurve_points"] = len(w._lcurve_curve.getData()[0]) if hasattr(w._lcurve_curve, "getData") else None
except Exception as exc:
    res["lcurve_error"] = repr(exc)
json.dump(res, open(out / "qt_values.json", "w"), indent=1, default=str)
print(json.dumps(res, default=str)[:900])
