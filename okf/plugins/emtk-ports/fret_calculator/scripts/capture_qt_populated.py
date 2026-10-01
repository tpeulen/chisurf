"""Populated captures of the committed Qt tool (HEAD tool.py via qt_head.py). Usage: <out_dir>.

Writes before_populated_*.png and qt_values.json (the numbers the Qt tool shows for each scenario).
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from qtpy import QtWidgets
from qt_head import load_head_tool

out = pathlib.Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
klass, _ = load_head_tool("fret_calculator")
w = klass(); w.resize(1200, 800); w.show()
het, homo = w.tabs.widget(0), w.tabs.widget(1)


def spin_set(spin, v):
    spin.setValue(v); spin.editingFinished.emit(); app.processEvents()


def settle():
    for _ in range(20):
        app.processEvents()


def het_values():
    return {k: getattr(het, f"spin_{k}").value() for k in ("tau0", "R0", "tau", "R", "sigma", "E", "kFRET")} | {"chi": het.check_chi.isChecked()}


def homo_values():
    return {"tau0": homo.spin_tau0.value(), "R0": homo.spin_R0.value(), "t_RM": homo.spin_tRM.value(), "rho": homo.spin_rho.value(),
            "sigma": homo.spin_sigma.value(), "k_homo": homo.spin_kHomo.value(), "R_DA": homo.spin_Rhomo.value(), "chi": homo.check_chi.isChecked()}


def grab(name):
    settle(); w.grab().save(str(out / f"before_populated_{name}.png"))


vals = {"hetero_default": het_values(), "homo_default": homo_values()}
w.tabs.setCurrentIndex(0)
spin_set(het.spin_tau0, 3.5); spin_set(het.spin_R0, 60.0); spin_set(het.spin_R, 55.0); spin_set(het.spin_sigma, 8.0)
het.check_chi.setChecked(True); settle()
vals["hetero_forward_chi"] = het_values(); grab("hetero_forward_chi")
spin_set(het.spin_E, 0.8); vals["hetero_from_E"] = het_values(); grab("hetero_inverse")
spin_set(het.spin_tau, 2.0); vals["hetero_from_tau"] = het_values()
spin_set(het.spin_kFRET, 0.5); vals["hetero_from_k"] = het_values()
het.check_chi.setChecked(False); settle(); vals["hetero_gaussian_again"] = het_values()
spin_set(het.spin_E, 0.0); vals["hetero_E0"] = het_values()
spin_set(het.spin_E, 1.0); vals["hetero_E1"] = het_values()

w.tabs.setCurrentIndex(1); settle()
spin_set(homo.spin_tau0, 2.5); spin_set(homo.spin_R0, 55.0); spin_set(homo.spin_rho, 20.0); spin_set(homo.spin_tRM, 1.5)
vals["homo_forward"] = homo_values(); grab("homo_forward")
spin_set(homo.spin_Rhomo, 45.0); vals["homo_backmap"] = homo_values()
homo.check_chi.setChecked(True); spin_set(homo.spin_sigma, 10.0); vals["homo_chi"] = homo_values(); grab("homo_chi_backmap")
(out / "qt_values.json").write_text(json.dumps(vals, indent=1))
print(json.dumps(vals, indent=1))
