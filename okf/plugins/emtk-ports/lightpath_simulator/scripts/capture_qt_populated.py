"""Populated captures of the Qt light-path tool (HEAD's gui/tool.py, kept in pre-upgrade/qt_original_tool.py.txt).

Usage: python capture_qt_populated.py <out_dir>. Writes before_populated_*.png and qt_values.json. Hermetic (lp_env).
"""
import importlib.util, json, pathlib, sys, faulthandler
faulthandler.dump_traceback_later(100, exit=True)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from test.gui import migration_parity as _mp  # noqa: F401 (before the scripts folder can shadow `test`)
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import lp_env
lp_env.patch_client()
from qtpy import QtCore, QtWidgets

REPO = pathlib.Path(__file__).resolve().parents[4]
out = pathlib.Path(sys.argv[1])
src = (out / "pre-upgrade/qt_original_tool.py.txt").read_text()
spec = importlib.util.spec_from_file_location("chisurf.plugins.core.lightpath_simulator.gui.qt_original", out / "pre-upgrade/qt_original_tool.py.txt",
                                              loader=importlib.machinery.SourceFileLoader("chisurf.plugins.core.lightpath_simulator.gui.qt_original", str(out / "pre-upgrade/qt_original_tool.py.txt")))
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

# dialogs and file choosers answer from a script (a real one would block)
answers = {"save": str(lp_env.TMP / "qt_graph.json"), "open": str(lp_env.TMP / "qt_graph.json")}
shown = []
mod.dialogs.error = lambda parent, title, msg: shown.append(("error", title, msg))
mod.dialogs.information = lambda parent, title, msg: shown.append(("information", title, msg))
mod.dialogs.warning = lambda parent, title, msg: shown.append(("warning", title, msg))
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (answers["save"], ""))
QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (answers["open"], ""))
QtWidgets.QInputDialog.getText = staticmethod(lambda *a, **k: ("My preset", True))
items_seen = []
QtWidgets.QInputDialog.getItem = staticmethod(lambda parent, title, label, items, *a, **k: (items_seen.append(list(items)) or items[0], True))


def settle(n=40):
    for _ in range(n):
        app.processEvents()
    QtCore.QThread.msleep(30)
    for _ in range(n):
        app.processEvents()


def grab(w, name):
    settle(); w.grab().save(str(out / f"before_populated_{name}.png"))


w = mod.LightPathSimulatorWidget()
w.show(); w.resize(1200, 800)
for _ in range(200):
    if w.probes: break
    settle(5)
settle(80)
vals = {"probes": len(w.probes), "nodes": [n.type for n in w.graph_widget.document.nodes]}
grab(w, "default_1200x800")
# before.json / before.png of the HEAD Qt tool (what `emtk_port_parity before` records for a Qt-only plugin)
from test.gui import migration_parity as mp
from test.gui.emtk_port_parity import normalize
inv = mp.control_inventory(w)
inv["entrypoint"] = "HEAD gui/tool.py (pre-upgrade/qt_original_tool.py.txt)"; inv["size"] = [1200, 800]
inv["controls"] = sorted({normalize(c) for c in inv["controls"]} - {""})
(out / "before.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False))
w.grab().save(str(out / "before.png"))
w.calculate_crosstalk(); settle(80)
# the default path has no detector assigned (as in the tool): assign the catalogue's APD to both detectors
for n in w.graph_widget.document.nodes:
    if n.type == "detector":
        n.config["probe_id"] = lp_env.IDS["APD (flat QE)"]
w.calculate_crosstalk(); settle(80)
vals["signals"] = w._last_detector_signals
vals["matrices"] = {k: {"rows": v.get("rows"), "columns": v.get("columns")} for k, v in w._last_crosstalk_matrices.items()}
vals["table_rows"] = {name: [w.results_table.rowCount(), w.results_table.columnCount()]}if False else {}
for i, name in enumerate(("Signals", "Excitation", "Emission", "Detected")):
    w.results_tabs.setCurrentIndex(i); grab(w, f"results_{name}_1200x800")
    t = w.results_tabs.currentWidget()
    vals.setdefault("tables", {})[name] = {"rows": t.rowCount(), "cols": t.columnCount(),
        "header": [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())],
        "cells": [[t.item(r, c).text() if t.item(r, c) else "" for c in range(t.columnCount())] for r in range(t.rowCount())]}
w.resize(800, 600); grab(w, "default_800x600"); w.resize(1200, 800)
# Easy Mode tab
ea = w.easy_mode_widget
for i in range(w.dock_area.count()):
    if "Easy" in w.dock_area.tabText(i): w.dock_area.setCurrentIndex(i)
grab(w, "easy_mode_tab_1200x800")
# palette: activate a node type
n0 = len(w.graph_widget.document.nodes)
w._on_palette_node_type_activated("detector"); settle()
vals["palette_added"] = len(w.graph_widget.document.nodes) - n0
grab(w, "palette_added_detector")
# Reset to default
w.btn_reset.click(); settle(80)
vals["after_reset_nodes"] = len(w.graph_widget.document.nodes)
# file actions
w._on_save_graph(); vals["graph_saved"] = pathlib.Path(answers["save"]).exists()
vals["graph_saved_nodes"] = len(json.loads(pathlib.Path(answers["save"]).read_text())["nodes"])
w._on_load_graph(); settle(80)
answers["save"] = str(lp_env.TMP / "qt_instrument.json"); w._on_export_json(); vals["instrument_saved"] = pathlib.Path(answers["save"]).exists()
w._on_save_to_mmfdb(); vals["mmfdb_save_dialog"] = list(shown[-1]) if shown else None
shown.clear(); w._on_load_from_mmfdb(); vals["mmfdb_load_dialogs"] = [list(s) for s in shown]; vals["mmfdb_items"] = items_seen
# load a missing graph: error dialog
shown.clear(); answers["open"] = str(lp_env.TMP / "missing.json"); w._on_load_graph(); vals["load_missing"] = [list(s) for s in shown]
vals["preset_saved"] = (mod.OPTICAL_PRESETS_DIR / "My preset.json").exists()
# easy mode dialog
dlg = mod.LightPathEasyDialog(w.probes, w, db_path=lp_env.DB); dlg.resize(1000, 700); dlg.show(); settle(); dlg.grab().save(str(out / "before_populated_easy_dialog.png")); dlg.close()
# the menu
menu = w.menuBar().actions()[0].menu()
vals["menu"] = [a.text() for a in menu.actions() if a.text()]
vals["toolbar"] = [a.text() for a in w.findChildren(QtWidgets.QToolBar)[0].actions() if a.text()]
vals["toolbar_tooltips"] = {a.text(): a.toolTip() for a in w.findChildren(QtWidgets.QToolBar)[0].actions() if a.text()}
vals["palette_items"] = [w.palette.topLevelItem(0).child(i).text(0) for i in range(w.palette.topLevelItem(0).childCount())]
vals["dock_tabs"] = [w.dock_area.tabText(i) for i in range(w.dock_area.count())]
(out / "qt_values.json").write_text(json.dumps(vals, indent=1, default=str))
w._save_graph_state = lambda: None
w.close()
print("ok", vals["probes"], vals["nodes"], len(vals["signals"]))
