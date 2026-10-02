"""More Qt baseline states of the project browser (the committed gui/tool.py): a project expanded and a version selected, the search
filter, the save dialog, the collision dialog. Usage: capture_qt_more.py <out_dir>. Hermetic: temp HOME, settings and scratch database."""
import os, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
tmp = pathlib.Path(tempfile.mkdtemp(prefix="pb_"))
os.environ.update(HOME=str(tmp / "home"), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"),
                  MMFDB_DATABASE_PATH=str(tmp / "projects.sqlite"), QT_QPA_PLATFORM="offscreen")
(tmp / "home").mkdir()
out = pathlib.Path(sys.argv[1]).resolve()
from qtpy import QtWidgets
from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient
from chisurf.macros.core_fit import get_project_payload

client = ProjectBrowserClient(inprocess=True)
payload = get_project_payload("decay study").to_dict()
first = client.save_project(project_name="decay study", project_payload=payload, notes="first fit", visibility="private", fit_count=0, dataset_count=0)
client.save_project(project_name="decay study", project_payload=payload, project_id=first["project_id"], parent_version_id=first["version_id"],
                    notes="refit with IRF", visibility="private", fit_count=0, dataset_count=0)
client.save_project(project_name="fcs titration", project_payload=get_project_payload("fcs titration").to_dict(), notes="public set", visibility="public", fit_count=0, dataset_count=0)
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.core.project_browser.gui import tool as T

w = T.ProjectBrowserTool(); w.resize(1200, 800); w.show(); w.refresh()
spin = lambda: [app.processEvents() for _ in range(30)]
spin()
tree = w._tree
tree.expandAll(); spin()
v = tree.topLevelItem(1).child(0); tree.setCurrentItem(v); spin()
w.grab().save(str(out / "before_populated_expanded_selected.png"))
w.resize(800, 600); spin(); w.grab().save(str(out / "before_populated_expanded_selected_800x600.png")); w.resize(1200, 800)
w._search_edit.setText("fcs"); spin(); w.grab().save(str(out / "before_populated_search_fcs.png")); w._search_edit.setText(""); spin()
dlg = T.SaveProjectDialog(current_name="", parent=w); dlg.show(); spin(); dlg.grab().save(str(out / "before_populated_save_dialog.png")); dlg.close()
dlg = T.SaveProjectDialog(current_name="decay study", parent=w, allow_name_edit=False, title="Save New Version"); dlg.show(); spin(); dlg.grab().save(str(out / "before_populated_save_new_version_dialog.png")); dlg.close()
dlg = T.CollisionDialog({"operations": ["op_1", "op_2"], "artifacts": ["art_1"]}, {"project_id": "proj_x", "version_number": 2}, w); dlg.show(); spin()
dlg.grab().save(str(out / "before_populated_collision_dialog.png")); dlg.close()
w.close()
print("ok")
