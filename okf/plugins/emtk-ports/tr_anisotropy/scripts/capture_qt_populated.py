"""Populated Qt baseline of the AutoForm wizard: every step, with data loaded. Usage: <out_dir>. Temp settings only."""
import json, pathlib, sys, tempfile, types
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from make_data import make_data
from qtpy import QtWidgets
import numpy as np
out = pathlib.Path(sys.argv[1])
tmp = pathlib.Path(tempfile.mkdtemp())
files = make_data(tmp / "data")
import chisurf
from chisurf.core.experiments.tcspc.reader import TCSPCReader
reader = TCSPCReader(dt=1.0, rep_rate=10.0, skiprows=0)       # the reader configuration the native model uses for a time column
chisurf.cs = types.SimpleNamespace(current_setup=None, current_experiment_reader=reader, current_experiment=None, dataset_selector=None)
from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.tool import AnisotropyWizard
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
w = AnisotropyWizard(); w.resize(1200, 800); w.show()
m = w.model
for k, p in files.items():
    setattr(m, k + "_path", p)
m.notify("refresh")
from chisurf.gui.autoform.sections.wizard_section import WizardWidget
wiz = w.findChild(WizardWidget)
def shot(name):
    for _ in range(20): app.processEvents()
    w.grab().save(str(out / f"before_populated_{name}.png"))
res = {}
wiz.nav_list.setCurrentRow(1)
for e, p in zip(w.findChildren(QtWidgets.QLineEdit), [files["irf_vv"], files["irf_vh"], files["data_vv"], files["data_vh"]]):
    e.setText(p); e.editingFinished.emit()
shot("1_data")
wiz.nav_list.setCurrentRow(2)
btn = [b for b in w.findChildren(QtWidgets.QToolButton) if "Load / reload" in b.text()][0]
btn.click(); res["load_ok"] = m.data["irf_vv"] is not None; shot("2_normalize")
res["region"] = [m.region_lb, m.region_ub]
for key in ("irf_vv_bg_norm", "irf_vh_bg_norm"):
    res[key + "_sum"] = float(np.sum(m.data[key].y)); res[key + "_head"] = [float(v) for v in m.data[key].y[:5]]
res["irf_vv_raw_sum"] = float(np.sum(m.data["irf_vv"].y)); res["n"] = len(m.data["irf_vv"].y)
m.g_factor, m.l1, m.l2 = 1.1, 0.02, 0.01
wiz.nav_list.setCurrentRow(3); shot("3_corrections")
wiz.nav_list.setCurrentRow(4); shot("4_components")
res["lifetime_spectrum"] = m.lifetime_spectrum; res["rotation_spectrum"] = m.rotation_spectrum
res["link_plan_len"] = len(__import__("chisurf.plugins.fluorescence_decay.tr_anisotropy.core.fits", fromlist=["x"]).build_link_plan(len(m.lifetime_spectrum), len(m.rotation_spectrum), m._corrections))
wiz.nav_list.setCurrentRow(5); shot("5_finish")
(out / "qt_values.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res)[:600])
