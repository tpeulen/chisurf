"""Native project browser against real temporary MMFDB/archive services."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from chisurf.plugins.core.project_browser.gui.app import ProjectBrowserApp
from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient
from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    project_db as project_db,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    sample_project_payload as sample_project_payload,
)


def browser_model(project_db, sample_project_payload):
    client = ProjectBrowserClient(inprocess=True)
    client.token = project_db["auth"]["token"]
    loaded = []
    context = SimpleNamespace()
    model = ProjectBrowserModel(
        client=client,
        payload_provider=lambda name: sample_project_payload,
        payload_loader=loaded.append,
        context=context,
    )
    return model, loaded, context


def finish(app):
    for _ in range(5):
        if app.jobs.future is None:
            return
        app.jobs.future.result(timeout=15)
        app.jobs.poll()
    raise AssertionError("Project actions did not finish")


def test_real_save_parent_versions_latest_restore_exact_export_and_import(
    project_db, sample_project_payload
):
    model, loaded, context = browser_model(project_db, sample_project_payload)
    app = ProjectBrowserApp(model, autoload=False)
    try:
        app.begin_save()
        app.name = "Native project"
        app.notes = "first native version"
        app.save()
        finish(app)
        first = context._current_project_version_id
        app.begin_save()
        assert not app.allow_name_edit
        app.notes = "second version"
        app.visibility = 1
        app.save()
        finish(app)
        latest = context._current_project_version_id
        assert latest != first and len(model.projects) == 1
        project = model.projects[0]
        assert project["version_count"] == 2 and project["visibility"] == "public"
        assert project["versions"][0]["parent_version_id"] == first
        model.selected_id = project["project_id"]
        app.open_selected()
        finish(app)
        assert context._current_project_version_id == latest and loaded[-1]["datasets"]
        model.selected_id = first
        version = model.require_version()
        archive = model.export(version, project_db["tmp_path"] / "portable")
        assert archive.suffix == ".pto" and archive.is_file()
        preview = model.preview_import(archive)
        assert any(preview["collisions"].values())
        app.import_preview(archive)
        finish(app)
        assert app.modal == "import"
        app.confirm_import()
        finish(app)
        assert sum(p["version_count"] for p in model.projects) == 3
        assert "Imported project" in app.notice
        model.selected_id = first
        app.inspect()
        finish(app)
        assert model.artifacts and model.branches and model.graph["nodes"]
        app.begin_delete()
        assert app.modal == "delete"
        app.confirm_delete()
        finish(app)
        assert all(v["version_id"] != first for p in model.projects for v in p["versions"])
    finally:
        app.close()


def test_invalid_inputs_archive_errors_cancel_and_preferences(project_db, sample_project_payload):
    model, _, _ = browser_model(project_db, sample_project_payload)
    app = ProjectBrowserApp(model, autoload=False)
    try:
        with pytest.raises(ValueError, match="Select"):
            model.require_version()
        with pytest.raises(ValueError, match="name"):
            model.save_snapshot(" ")
        with pytest.raises(FileNotFoundError):
            model.preview_import(project_db["tmp_path"] / "missing.csp")
        bad = project_db["tmp_path"] / "invalid.cs.pto"
        bad.write_text("invalid archive")
        with pytest.raises(Exception):
            model.preview_import(bad)
        app.begin_save()
        app.name = "Cancelled"
        app.modal = ""
        assert not model.client.list_projects()
        model.search = "test"
        model.show_public = False
        model.last_directory = str(project_db["tmp_path"])
        app.expanded = {"proj_test"}
        state = app.export_settings()
        other = ProjectBrowserApp(ProjectBrowserModel(client=model.client), autoload=False)
        try:
            other.restore_settings(state)
            assert other.export_settings() == state
        finally:
            other.close()
    finally:
        app.close()


def test_failed_background_action_reports_error_and_unlocks_ui():
    app = ProjectBrowserApp(ProjectBrowserModel(client=object()), autoload=False)
    try:
        app.refresh()
        app.jobs.future.exception(timeout=5)
        assert app.jobs.poll()
        assert app.jobs.future is None and app.model.status.startswith("Error:")
        from emtk.testing import RecordingPainter

        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    finally:
        app.close()


def test_factory_all_dialogs_and_context_menu_render_without_qt(tmp_path):
    script = """
import importlib.abc,sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:raise RuntimeError('Qt '+fullname)
sys.meta_path.insert(0,BlockQt())
from emtk.testing import RecordingPainter
import chisurf.plugins.core.project_browser.gui.app as app_module
from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient
from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel
version={'version_id':'v1','project_id':'p1','project_name':'Native project','version_number':1,'notes':'Reference sample','owner_user_id':'admin','dataset_count':1,'fit_count':1}
model=ProjectBrowserModel(client=object());model.projects=[{'project_id':'p1','project_name':'Native project','latest_version_id':'v1','version_count':1,'versions':[version]}];model.selected_id='v1'
app_module.ProjectBrowserModel=lambda:model
app=app_module.make_app();app.loaded=True;app.expanded.add('p1')
app.draw(RecordingPainter(),0,0,1200,800)
from emtk.events import RIGHT_BUTTON
painter=RecordingPainter();app.draw(painter,0,0,1200,800);app.draw(painter,0,0,1200,800)
x,y,w,h=next(t[:4] for t in painter.texts if t[5].startswith('v1 Native'))
app.pointer_move(x+w*.3,y+h*.5);app.draw(RecordingPainter(),0,0,1200,800)
app.pointer_press(x+w*.3,y+h*.5,RIGHT_BUTTON)
painter=RecordingPainter();app.draw(painter,0,0,1200,800)
assert 'Inspect version' in painter.strings, str((app.io.mouse_pos,painter.strings))
app.pointer_release(x+w*.3,y+h*.5,RIGHT_BUTTON)
app.draw(RecordingPainter(),0,0,1200,800)
app.begin_save();app.draw(RecordingPainter(),0,0,1200,800)
app.modal='';app.begin_delete();app.draw(RecordingPainter(),0,0,1200,800)
app.pending={'path':'archive','preview':{'origin':{'project_id':'p1'},'collisions':{'operations':['v1']},'entity_counts':{'operations':1}}};app.modal='import';app.draw(RecordingPainter(),0,0,1200,800)
app.modal='';app.choose_file('export');app.draw(RecordingPainter(),0,0,1200,800)
assert app.dialog.filename.endswith('.cs.pto')
app.dialog=None;app.help_window.show();app.draw(RecordingPainter(),0,0,1200,800)
assert 'chisurf.gui' not in sys.modules
app.close()
import chisurf,numpy as np
from chisurf.core.data import DataCurve
chisurf.imported_datasets=[DataCurve(x=np.array([0.,1.,2.]),y=np.array([10.,12.,11.]),name='Native session curve')]
chisurf.fits=[]
session_model=ProjectBrowserModel(client=object())
payload=session_model.save_snapshot('Native session')
assert payload['datasets']
chisurf.imported_datasets.clear()
session_model.payload_loader(payload)
restored=next(curve for curve in chisurf.imported_datasets if getattr(curve,'name','')=='Native session curve')
assert np.allclose(restored.y,[10.,12.,11.])
assert 'chisurf.gui' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[5],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
