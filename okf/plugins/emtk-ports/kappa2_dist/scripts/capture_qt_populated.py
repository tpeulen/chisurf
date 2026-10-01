"""Populated captures of the committed Qt tool (a59fde86d~1, the AutoForm Kappa2Dist). Usage: <out_dir>.

Writes before_populated_*.png, qt_values.json (every result of every scenario, seed 7) and
qt_saved.csv (what the Qt Save wrote). The Qt source is read from git; resources resolve to the real folder.
"""
import importlib.util, json, pathlib, subprocess, sys, tempfile
import numpy as np
from qtpy import QtWidgets

PLUGIN = pathlib.Path("chisurf/plugins/calculator/kappa2_dist").resolve()
out = pathlib.Path(sys.argv[1])
src = subprocess.run(["git", "show", f"a59fde86d~1:chisurf/plugins/calculator/kappa2_dist/gui/tool.py"],
                     capture_output=True, text=True, check=True).stdout
src = src.replace("pathlib.Path(__file__).parent\n", f"pathlib.Path({str(PLUGIN / 'gui')!r})\n")
tmp = pathlib.Path(tempfile.mkdtemp()) / "qt_tool.py"; tmp.write_text(src)
spec = importlib.util.spec_from_file_location("chisurf.plugins.calculator.kappa2_dist.gui.qt_original", tmp)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
np.random.seed(7)
w = mod.Kappa2Dist(); w.resize(1200, 800); w.show()
from chisurf.gui.autoform.sections.builtin import ChoiceWidget, ToggleWidget, ValueWidget
editors = {vw._section.attr: vw.editor for vw in w._form.findChildren(ValueWidget) if getattr(vw, "_section", None)}
toggle = {tw._section.attr: tw.checkbox for tw in w._form.findChildren(ToggleWidget)}
_by_text = {b.text(): b for b in w._form.findChildren(QtWidgets.QRadioButton)}
radios = {"cone": _by_text["WIC (Cone)"], "diffusion": _by_text["DWT (Diffusion)"], "isotropic": _by_text["Isotropic"]}


def settle():
    for _ in range(30): app.processEvents()


def values():
    m = w._model
    d = {k: getattr(m, k) for k in ("model_type", "r_0", "r_Dinf", "r_Ainf", "r_ADinf", "kappa2_true", "fret_efficiency",
                                    "step", "n_bins", "rAD_known", "k2_mean", "k2_sd", "Rapp_mean", "RappSD", "delta_deg")}
    d["SD2"], d["SA2"] = float(m.SD2), float(m.SA2)
    d["hist_sum"] = float(np.sum(m._k2hist)); d["hist_len"] = int(len(m._k2hist))
    d["hist_head"] = [float(x) for x in m._k2hist[:5]]
    d["save_enabled"] = w.saveButton.isEnabled()
    return d


def edit(attr, v):
    if attr == "model_type":
        radios[v].click()
    elif attr == "rAD_known":
        toggle[attr].setChecked(bool(v))
    else:
        editors[attr].setValue(v); editors[attr].editingFinished.emit()
    np.random.seed(7)          # the debounce timer computes: same seed for every scenario
    w._compute_timer.stop(); w._do_compute(); settle()


def grab(name):
    settle(); w.grab().save(str(out / f"before_populated_{name}.png"))


vals = {}
np.random.seed(7); w._do_compute(); settle(); vals["default"] = values(); grab("default")
edit("model_type", "isotropic"); vals["isotropic"] = values(); grab("isotropic")
edit("model_type", "diffusion"); edit("fret_efficiency", 0.4); vals["diffusion_E04"] = values(); grab("diffusion")
edit("model_type", "cone"); edit("r_Dinf", 0.15); edit("n_bins", 60); edit("step", 3.0); vals["cone_rDinf015_bins60_step3"] = values()
edit("rAD_known", True); vals["cone_rAD_known"] = values(); grab("cone_rAD_known")
edit("kappa2_true", 1.0); vals["kappa2_true_1"] = values()
edit("r_ADinf", 0.4); vals["rAD_known_big_rADinf"] = values(); grab("nan_results")

# Save: the file dialog and the message boxes stubbed
saved = {}
mod.QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out / "qt_saved_target"), ""))
mod.dialogs.information = lambda parent, title, text: saved.update(info=(title, text))
mod.dialogs.error = lambda parent, title, text: saved.update(error=(title, text))
mod.dialogs.warning = lambda parent, title, text: saved.update(warning=(title, text))
edit("rAD_known", False); edit("r_ADinf", 0.005); edit("r_Dinf", 0.05); edit("n_bins", 131); edit("step", 1.5)
np.random.seed(7); w._do_compute()
w._on_save()
vals["save_messages"] = {k: list(v) for k, v in saved.items()}
(out / "qt_saved.csv").write_text((out / "qt_saved_target.csv").read_text()); (out / "qt_saved_target.csv").unlink()
(out / "qt_values.json").write_text(json.dumps(vals, indent=1))
print(json.dumps({k: (v if k == "save_messages" else {a: (round(b, 5) if isinstance(b, float) else b) for a, b in v.items() if a.startswith(("k2", "Rapp", "delta", "save"))}) for k, v in vals.items()}, indent=0))
