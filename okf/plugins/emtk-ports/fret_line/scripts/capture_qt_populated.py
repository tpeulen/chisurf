"""Populated captures of the Qt FRET line tool (temp HOME/settings). Usage: <out_dir>. Writes before_populated_*.png and qt_values.json."""
import json, pathlib, sys
import numpy as np
from qtpy import QtWidgets
out = pathlib.Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.fret_line.gui.tool import FRETLineTool
w = FRETLineTool(); w.resize(1200, 800); w.show()
def settle():
    for _ in range(30): app.processEvents()
def grab(name): settle(); w.grab().save(str(out / f"before_populated_{name}.png"))
vals = {}
grab("start")
# default: one Gaussian component, sweep list
vals["targets"] = [t["label"] for t in [w._sweep_combo.itemData(i) for i in range(w._sweep_combo.count())]]
idx = next(i for i in range(w._sweep_combo.count()) if "distance.mean" in (w._sweep_combo.itemData(i) or {}).get("name", ""))
w._sweep_combo.setCurrentIndex(idx); w._min_spin.setValue(20); w._max_spin.setValue(120)
w._do_compute(); grab("static_line")
def line(ln): r = ln["result"]; return {k: [float(r[k][0]), float(r[k][len(r[k])//2]), float(r[k][-1])] for k in ("tau_f", "tau_x", "e_fret")} | {"n": len(r["tau_f"]), "sweep": ln["sweep_label"]}
vals["static"] = line(w._lines[-1])
w._add_component(); settle()
vals["targets_two"] = [(w._sweep_combo.itemData(i) or {}).get("label") for i in range(w._sweep_combo.count())]
fr = next(i for i in range(w._sweep_combo.count()) if (w._sweep_combo.itemData(i) or {}).get("kind") == "fraction")
w._sweep_combo.setCurrentIndex(fr); w._min_spin.setValue(0); w._max_spin.setValue(1); w._do_compute()
vals["fraction"] = line(w._lines[-1])
w._dock  # layout
grab("two_lines"); json.dump(vals, open(out / "qt_values.json", "w"), indent=1)
w.resize(800, 600); grab("800x600")
