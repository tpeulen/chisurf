"""Populated captures of the Qt Imaging Tools window (temp HOME/settings). Usage: <out_dir>."""
import json, pathlib, sys
from qtpy import QtWidgets
out = pathlib.Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.microscopy.imaging_tools.gui.tool import ImagingToolsTool, IMAGING_PANELS
w = ImagingToolsTool(); w.resize(1200, 800); w.show()
def settle():
    for _ in range(40): app.processEvents()
def goto(role):
    w.goto_role(role); settle()
def grab(name):
    settle(); w.grab().save(str(out / f"before_populated_{name}.png"))
facts = {"rows": [w.nav_list.item(i).text() for i in range(w.nav_list.count())],
         "order": list(w.PIPELINE_ORDER), "analysis": list(w.ANALYSIS_ROLES),
         "descriptions": {p["role"]: p.get("description", "") for p in IMAGING_PANELS}}
json.dump(facts, open(out / "qt_facts.json", "w"), indent=1, ensure_ascii=False)
grab("browser_start")
for role in ("setup", "drift", "pixel_intensity", "calibration", "clsm_draw"):
    goto(role); grab(role)
w.advance_from("browser"); settle(); grab("after_next_from_browser")
w.resize(800, 600); settle(); grab("800x600")
