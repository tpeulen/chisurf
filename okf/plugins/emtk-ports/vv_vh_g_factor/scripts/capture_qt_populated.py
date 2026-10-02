"""Populated Qt baseline: fast + slow loaded, background on, batch window. Usage: <out_dir>. Temp settings only."""
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from make_data import make_data
from qtpy import QtWidgets
out = pathlib.Path(sys.argv[1]); files = make_data(tempfile.mkdtemp())
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.vv_vh_g_factor.gui.tool import VvVhGFactorCalculator
w = VvVhGFactorCalculator(); w.resize(1200, 800); w.show()
def shot(n):
    for _ in range(30): app.processEvents()
    w.grab().save(str(out / f"before_populated_{n}.png"))
shot("0_empty")
w.load_vv_vh_file(files["fast"]); shot("1_fast_loaded")
w.fp_dt_spinbox.setValue(0.05); w.load_fp_vv_vh_file(files["slow"]); shot("2_slow_loaded")
w.bg_correction_checkbox.setChecked(True); w._calc_timer.stop(); w.calculate_g_factor(); shot("3_background_on")
res = {k: getattr(w, k) for k in ("g_factor","g_factor_uncorrected","g_factor_stddev","g_factor_corrected","l1_estimate","l2_estimate","fp_tau_estimate_ns","fp_rs_expected","region_bounds","bg_region_bounds")}
res = {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in res.items()}
res["fields"] = {n: getattr(w, n).text() for n in ("g_factor_value","g_factor_stddev_value","corrected_g_factor_value","bg_parallel_value","bg_perpendicular_value")}
res["fp"] = {n: getattr(w, n).value() for n in ("fp_tau_value","fp_rs_value","fp_l1_value","fp_rho_spinbox","fp_r0_spinbox","fp_dt_spinbox")}
json.dump(res, open(out / "qt_values.json", "w"), indent=1, default=str); print(res)
