"""Populated captures of the Qt Plugin Check tool (temp HOME and settings). Usage: <out_dir>.

Qt window with the real plugin list, a sweep result injected through the tool's own callbacks (pass / fail / skipped),
a plugin selected (details + error pane). Also dumps the rows the tree shows to qt_rows.json (numeric reference).
"""
import json, pathlib, sys
from qtpy import QtWidgets, QtCore

out = pathlib.Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.core.plugin_check.gui.tool import PluginCheckTool

w = PluginCheckTool(); w.resize(1200, 800); w.show()


def settle():
    for _ in range(30): app.processEvents()


def rows():
    t = w.plugin_tree
    return [[t.topLevelItem(i).text(c) for c in range(5)] for i in range(t.topLevelItemCount())]


settle(); w.grab().save(str(out / "before_populated_listed.png"))
json.dump({"rows": rows(), "status": w.status_label.text()}, open(out / "qt_rows_listed.json", "w"), indent=1)
names = [r[0] for r in rows()]
w.update_plugin_result(names[0], True, None)
w.update_plugin_result(names[1], False, "Traceback (most recent call last):\n  File \"x.py\", line 1\nImportError: No module named 'foo'")
w.update_plugin_result(names[2], False, "Skipped: gui execution blocked")
w.update_plugin_result(names[3], True, None)
w.update_progress(4, len(names))
settle(); w.grab().save(str(out / "before_populated_results.png"))
t = w.plugin_tree
t.setCurrentItem(t.topLevelItem(1)); w.on_plugin_selected(t.topLevelItem(1), 0); settle()
w.grab().save(str(out / "before_populated_failed_selected.png"))
t.setCurrentItem(t.topLevelItem(0)); w.on_plugin_selected(t.topLevelItem(0), 0); settle()
w.grab().save(str(out / "before_populated_pass_selected.png"))
json.dump({"rows": rows(), "status": w.status_label.text(), "details": w.details_label.text()}, open(out / "qt_rows_results.json", "w"), indent=1)
w.resize(800, 600); settle(); w.grab().save(str(out / "before_populated_800x600.png"))
