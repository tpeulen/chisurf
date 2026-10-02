"""The Qt QuEst tool (QuEstTool -> TransientDecayGenerator), populated, on a real 148L simulation. Usage: <out_dir>.

Writes before_populated_*.png, before.png/before.json (the tool tool) and qt_values.json (the project, the numbers of the run, the
tables). Hermetic: temporary HOME / CHISURF_SETTINGS_DIR / MMFDB_*; QFileDialog answers from this script; no network (the PDB is
the local quest test file); nothing is written outside the temporary folder and the output directory.
"""
import json, os, pathlib, sys, tempfile

PDB = "/Users/tpeulen/dev/quest/tests/148l.pdb"
tmp = pathlib.Path(tempfile.mkdtemp(prefix="quest_qt_"))
os.environ.update(CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"),
                  HOME=str(tmp / "home"), QT_QPA_PLATFORM="offscreen")
(tmp / "s").mkdir(); (tmp / "home").mkdir()
from test.gui import migration_parity as mpar
from test.gui.emtk_port_parity import SIZES, normalize
import numpy as np
from qtpy import QtTest, QtWidgets

out = pathlib.Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.quenching_estimator.gui.tool import QuEstTool

picked = {"pdb": PDB, "save": str(tmp / "saved_project.json"), "load": ""}
QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (picked["pdb"] if "tructure" in str(a[1:2]) or not picked["load"] else picked["load"], ""))
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (picked["save"], ""))

tool = QuEstTool()
tool.resize(*SIZES[0]); tool.show(); QtTest.QTest.qWait(600)
dg = tool.dg


def grab(name):
    QtTest.QTest.qWait(300)
    tool.grab().save(str(out / f"before_populated_{name}.png"))


tool.grab().save(str(out / "before.png"))
inv = mpar.control_inventory(tool)
inv["controls"] = sorted({normalize(c) for c in inv["controls"]} - {""})
inv["entrypoint"] = "chisurf.plugins.quenching_estimator.gui.tool:QuEstTool"; inv["size"] = list(SIZES[0])
(out / "before.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False))
grab("empty")
values = {"empty_status": dg.model.status, "empty_project_pdb": dg.model.pdb, "tabs": [dg.tabs.tabText(i) for i in range(dg.tabs.count())]}
dg.onLoadPDB(); grab("structure_loaded")
m = dg.model
m.attachment_chain, m.attachment_residue, m.attachment_atom = "E", 117, "CB"
m.t_max, m.t_step, m.n_photons, m.n_bins = 200.0, 0.02, 10000, 512
m.critical_distance, m.random_seed, m.parallel_trajectories, m.skip_frame = 6.5, 3, 1, 10
m.fret_enabled = False
dg.refresh()
values["loaded"] = dict(status=m.status, attach=[m.attachment_chain, m.attachment_residue, m.attachment_atom], structure_label=m.structure_label, problems=m.validate())
values["quencher_rows_default"] = m.quencher_rows()
dg.update_all(); grab("simulated")
r = m.results
if r is None:
    # The simulation cannot run in this environment (IMP.bff no longer has the Python modules QuEst's core imports): the
    # failure IS the baseline, recorded as it is shown to the user.
    values["run"] = dict(status=m.status, results=None)
else:
    values["run"] = dict(status=m.status, qy=float(r.quantum_yield_donor), lifetime=float(r.lifetime_donor), counts_sum=float(np.sum(r.donor_counts)),
                         counts_head=[float(v) for v in np.asarray(r.donor_counts)[:8]], n_time=int(len(r.time)))
for i in range(dg.tabs.count()):
    dg.tabs.setCurrentIndex(i); grab("tab_" + dg.tabs.tabText(i).replace(" ", "_").replace("&", "and").replace("(", "").replace(")", ""))
m.update_quencher_cell(m.quencher_rows().index(next(r for r in m.quencher_rows() if r["residue"] == "TYR")), "kQ", "2.5")
dg.refresh()
values["after_edit"] = dict(tyr=next(r for r in m.quencher_rows() if r["residue"] == "TYR"))
dg.onSaveProject()
saved = json.loads(pathlib.Path(picked["save"]).read_text())
values["saved_project_keys"] = sorted(saved)
values["saved_pdb"] = saved["pdb"]; values["saved_tyr_kq"] = saved["amino_acid_interactions"]["TYR"]["kQ"] if "amino_acid_interactions" in saved else saved["fret"]["dyes"][0]["amino_acid_interactions"]["TYR"]["kQ"]
values["project_json_text"] = dg.json_edit.toPlainText()[:200]
(out / "qt_values.json").write_text(json.dumps(values, indent=2, default=str))
print(json.dumps(values["run"], indent=1))
tool.close()
