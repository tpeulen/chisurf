"""Drive the Qt PTO inspector into populated states. Usage: <tempdir> <out dir> (repo root).

The container is built by the plugin's own test fixture (a private copy of test/data/clsm/Leica_SP5.ptu
with burst, background, lifetime and FCS results). Temporary settings only.
"""
import json, os, pathlib, sys
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.core.pto_inspector.test.test_core import container
path = container.__wrapped__(T)
from chisurf.plugins.core.pto_inspector.gui.tool import PtoInspectorTool
w = PtoInspectorTool(); w.resize(1300, 850); w.show()
def grab(name):
    for _ in range(40): app.processEvents()
    w.grab().save(str(O / name))
grab("before_populated_empty.png")
w.model.set_filename(str(path))
m = w.model
out = {"status": w.statusBar().currentMessage(), "selected": m.selected.name,
       "rows": m.artifact_rows(), "summary": m.summary_html(), "detail": m.detail_html(), "lineage": m.lineage_text(),
       "tool_enabled": w._a_tool.isEnabled(), "tools": [t.id for t in m.tool_manifests()]}
grab("before_populated.png")
for name in ("bursts", "lifetimes", "fcs"):
    uid = next(i.uid for i in m.inspection.infos() if i.name == name)
    m.select_uid(uid)
    out["after_select_" + name] = {"status": w.statusBar().currentMessage(), "tool_enabled": w._a_tool.isEnabled(),
        "detail": m.detail_html(), "curve_axes": m.curve_axes(), "n_curve": len(m.curve_series()),
        "store_cols": [c for c in (m.current_store() and __import__("chisurf.core.datastore", fromlist=["x"]).column_names(m.current_store())) or []]}
    if name == "lifetimes": grab("before_populated_lifetimes.png")
    if name == "fcs": grab("before_populated_fcs.png")
out["verify"] = m.verify(); grab("before_populated_verified.png")
bad = T / "broken.pto"; bad.write_bytes(b"not a pto")
m.set_filename(str(bad)); out["error_status"] = m.status; grab("before_populated_error.png")
print(json.dumps(out, indent=1, default=str)[:3000]); (O / "before_populated.json").write_text(json.dumps(out, indent=1, default=str))
