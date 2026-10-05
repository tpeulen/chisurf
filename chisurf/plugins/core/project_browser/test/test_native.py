"""Native project browser against real temporary MMFDB/archive services."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from chisurf.plugins.core.project_browser.gui.app import ProjectBrowserApp
from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    _payload_with_fit,
    assert_scientific_roundtrip,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    authenticated_browser as authenticated_browser,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    sample_project_payload as sample_project_payload,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    standalone_server as standalone_server,
)


def browser_model(project_db, sample_project_payload):
    client = project_db["client"]
    sample_project_payload = _payload_with_fit(sample_project_payload)
    loaded = []
    context = SimpleNamespace()
    model = ProjectBrowserModel(
        client=client,
        payload_provider=lambda name: {
            **sample_project_payload,
            "meta": {**sample_project_payload["meta"], "name": name},
        },
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
    authenticated_browser, sample_project_payload
):
    project_db = authenticated_browser
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
        assert context._current_project_version_id == latest
        installed = assert_scientific_roundtrip(loaded[-1])
        import numpy as np

        import chisurf

        assert (
            chisurf.imported_datasets[0].unique_identifier
            == installed.datasets[0].unique_identifier
        )
        np.testing.assert_array_equal(chisurf.imported_datasets[0].y, installed.datasets[0].y)
        assert chisurf.fits[0].unique_identifier == installed.fits[0].unique_identifier
        np.testing.assert_array_equal(chisurf.fits[0].model.y, installed.fits[0].model.y)
        import json

        from mmfdb.repository import MFDatabase

        with MFDatabase(project_db["path"]) as db:
            rows = db.conn.execute(
                "SELECT metadata_json FROM mmfdb_operation WHERE operation_id IN (?, ?)",
                (first, latest),
            ).fetchall()
        assert len(rows) == 2
        assert sorted(json.loads(row[0])["version_number"] for row in rows) == [1, 2]
        exact = model.client.restore_project(first)
        assert exact["version_id"] == first and exact["project_id"] == project["project_id"]
        assert_scientific_roundtrip(exact["project_payload"])
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


def test_invalid_inputs_archive_errors_cancel_and_preferences(
    authenticated_browser, sample_project_payload
):
    project_db = authenticated_browser
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
    settings = tmp_path / "native-settings"
    settings.mkdir()
    env = dict(os.environ, CHISURF_SETTINGS_DIR=str(settings), MMFDB_SETTINGS_DIR=str(settings))
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        cwd=Path(__file__).resolve().parents[5],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "settings", [{}, {"client": {"mode": "embedded"}}, {"database_path": "bootstrap.sqlite"}]
)
def test_bootstrap_local_save_routes_portable(settings, sample_project_payload, monkeypatch):
    """Injecting a client or a local DB path must not select real database storage."""
    from chisurf.core.project.storage import ProjectStorageError, select_backend
    from chisurf.core.settings import cs_settings

    monkeypatch.setitem(cs_settings, "mmfdb", settings)
    assert select_backend() == "file"
    model = ProjectBrowserModel(
        client=object(),
        context=SimpleNamespace(),
        payload_provider=lambda name: sample_project_payload,
    )
    with pytest.raises(ProjectStorageError, match="Portable project save requires"):
        model.save_remote("Sample Project", "private", "", model.save_snapshot("Sample Project"))


def test_real_deployment_rejects_invalid_auth(authenticated_browser):
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    base = MMFDBClient(
        mode="remote",
        base_url=authenticated_browser["url"],
        allow_insecure_http=True,
        inprocess=False,
    )
    base.token = "invalid-token"
    client = ProjectBrowserClient(mmfdb_client=base)
    with pytest.raises(Exception, match="[Aa]uth|[Ss]ession|[Tt]oken"):
        client.list_projects()
