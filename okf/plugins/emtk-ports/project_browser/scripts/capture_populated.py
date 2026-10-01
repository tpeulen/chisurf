"""Populated captures: a scratch project database with 'decay study' (2 versions) and 'fcs titration' (1).

usage: capture_populated.py <out_dir> qt|emtk <prefix> [<qt_head dir>]   (run from the repo root; MMFDB_DATABASE_PATH
must point at a scratch database -- env.sh does)
"""
import os, pathlib, sys, time

out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
assert "MMFDB_DATABASE_PATH" in os.environ, "use a scratch database"
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient


def seed():
    client = ProjectBrowserClient(inprocess=True)
    if client.list_projects(show_public=True, search=None):
        return
    from chisurf.macros.core_fit import get_project_payload
    payload = get_project_payload("decay study").to_dict()
    first = client.save_project(project_name="decay study", project_payload=payload, notes="first fit",
                                visibility="private", fit_count=0, dataset_count=0)
    client.save_project(project_name="decay study", project_payload=payload, project_id=first["project_id"],
                        parent_version_id=first["version_id"], notes="refit with IRF", visibility="private",
                        fit_count=0, dataset_count=0)
    client.save_project(project_name="fcs titration", project_payload=get_project_payload("fcs titration").to_dict(),
                        notes="public set", visibility="public", fit_count=0, dataset_count=0)


seed()
if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("project_browser")
    w = klass()
    w.refresh()
    w._tree.topLevelItem(0).setExpanded(True)
    w.resize(1200, 800); w.show()
    for _ in range(20):
        app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.core.project_browser.gui.app import make_app
    for size in [(1200, 800), (800, 600)]:
        a = make_app()
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        while a.jobs.future is not None:
            time.sleep(0.05); a.draw(RecordingPainter(), 0, 0, *size)
        a.expanded = {p["project_id"] for p in a.model.projects if p.get("version_count", 0) > 1}
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        a.close()
