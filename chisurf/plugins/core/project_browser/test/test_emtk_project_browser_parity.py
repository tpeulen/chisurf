"""The native Project Browser at parity with the Qt ProjectBrowserTool.

Both talk to the same project service. The Qt tool runs in a subprocess on the same
scratch database (this process stays Qt-free) and the tree it shows is compared with
the emtk app's rows; save, restore, export/import and delete are driven through the
emtk app against a real scratch database.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from emtk.testing import PixelPainter, RecordingPainter

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A scratch project database with 'decay study' (two versions) and 'fcs titration' (public)."""
    path = tmp_path / "projects.sqlite"
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(path))
    from chisurf.macros.core_fit import get_project_payload
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    client = ProjectBrowserClient(inprocess=True)
    payload = get_project_payload("decay study").to_dict()
    first = client.save_project(project_name="decay study", project_payload=payload, notes="first fit",
                                visibility="private", fit_count=0, dataset_count=0)
    client.save_project(project_name="decay study", project_payload=payload, project_id=first["project_id"],
                        parent_version_id=first["version_id"], notes="refit with IRF", visibility="private",
                        fit_count=0, dataset_count=0)
    client.save_project(project_name="fcs titration", project_payload=get_project_payload("fcs titration").to_dict(),
                        notes="public set", visibility="public", fit_count=0, dataset_count=0)
    return path


def _app(**model_kwargs):
    from types import SimpleNamespace

    from chisurf.plugins.core.project_browser.gui.app import ProjectBrowserApp
    from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

    restored, reopened = [], []
    model = ProjectBrowserModel(context=SimpleNamespace(), payload_loader=restored.append,
                                window_restorer=reopened.append, **model_kwargs)
    app = ProjectBrowserApp(model=model)
    app.restored, app.reopened = restored, reopened
    return app


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _settle(app, timeout=60.0, **kw):
    end = time.monotonic() + timeout
    _draw(app, n=1, **kw)
    while app.jobs.future is not None:
        assert time.monotonic() < end, "the project job did not finish"
        time.sleep(0.02)
        _draw(app, n=1, **kw)
    _draw(app, n=1, **kw)


def _project(app, name):
    return next(p for p in app.model.projects if p["project_name"] == name)


_QT = r"""
import json
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.core.project_browser.gui.tool import ProjectBrowserTool
w = ProjectBrowserTool()
w.refresh()
rows = []
for i in range(w._tree.topLevelItemCount()):
    top = w._tree.topLevelItem(i)
    rows.append({"project": [top.text(c) for c in range(9)],
                 "versions": [[top.child(j).text(c) for c in range(9)] for j in range(top.childCount())]})
print("FACTS" + json.dumps({"rows": rows}))
"""


def _qt_rows():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT], capture_output=True, text=True, timeout=300, env=env,
                          cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None:
        pytest.skip(f"the Qt tool could not be built here: {proc.stderr[-800:]}")
    return json.loads(line[len("FACTS"):])["rows"]


# 1. the same projects and versions as the Qt tree
def test_the_list_shows_what_the_qt_tree_shows(db):
    qt = _qt_rows()
    app = _app()
    try:
        _settle(app)
        ours = {p["project_id"]: p for p in app.model.projects}
        assert sorted(ours) == sorted(r["project"][1] for r in qt)
        for row in qt:
            project = ours[row["project"][1]]
            assert row["project"][0] == f"{project['project_name']}  ({project['version_count']} versions)"
            assert row["project"][4] == project["visibility"]
            qt_versions = {v[1]: v for v in row["versions"]}
            assert sorted(qt_versions) == sorted(v["version_id"] for v in project["versions"])
            for version in project["versions"]:
                assert qt_versions[version["version_id"]][8] == (version.get("notes") or "")[:60]
                assert qt_versions[version["version_id"]][0].startswith(f"v{version['version_number']}")
    finally:
        app.close()


# 2. restore: the payload loaded, the fit windows reopened, the session told which version it is
def test_restore_loads_the_version_and_reopens_its_windows(db):
    app = _app()
    try:
        _settle(app)
        project = _project(app, "decay study")
        app.model.selected_id = project["project_id"]          # a project means its newest version
        app.open_selected()
        _settle(app)
        assert len(app.restored) == 1 and app.reopened == app.restored
        context = app.model.context
        assert context._current_project_id == project["project_id"]
        assert context._current_project_version_id == project["latest_version_id"]
        assert context._current_project_name == "decay study"
    finally:
        app.close()


def test_the_default_restorer_reopens_windows_only_with_a_main_window(monkeypatch):
    import chisurf
    from chisurf.plugins.core.project_browser.gui import model

    opened = []
    monkeypatch.setattr(chisurf, "cs", type("Main", (), {"_open_fit_subwindow": lambda self, f: opened.append(f)})(),
                        raising=False)
    fit = type("Fit", (), {"unique_identifier": "u1"})()
    monkeypatch.setattr(chisurf, "fits", [fit], raising=False)
    model.restore_fit_windows({"fits": [{"uid": "u1"}, {"uid": "missing"}]})
    assert opened == [fit]
    monkeypatch.setattr(chisurf, "cs", None, raising=False)
    model.restore_fit_windows({"fits": [{"uid": "u1"}]})       # no main window: nothing, no error
    assert opened == [fit]


# 2. save a new version, export it, import it, delete one
def test_save_export_import_and_delete(db, tmp_path):
    app = _app(payload_provider=lambda name: {"datasets": {}, "fits": [], "name": name})
    try:
        _settle(app)
        project = _project(app, "decay study")
        app.model.update_current({"project_id": project["project_id"], "version_id": project["latest_version_id"],
                                  "project_name": "decay study"})
        app.begin_save()
        assert not app.allow_name_edit and app.modal_window.title == "Save New Version"
        app.notes = "third pass"
        app.save()
        _settle(app)
        project = _project(app, "decay study")
        assert project["version_count"] == 3 and app.notice == "Saved 'decay study' as version 3."
        app.model.selected_id = project["latest_version_id"]
        target = tmp_path / "decay.cs.pto"
        version = app.model.require_version()
        app.jobs.start("Exporting", lambda: app.model.export(version, target))
        _settle(app)
        assert target.is_file()
        app.import_preview(target)
        _settle(app)
        assert app.modal == "import"
        app.confirm_import()
        _settle(app)
        assert app.notice.startswith("Imported project")
        project = _project(app, "decay study")                 # the archive joins its project as the next version
        assert project["version_count"] == 4
        assert sorted(v["version_number"] for v in project["versions"]) == [1, 2, 3, 4]
        app.model.selected_id = _project(app, "fcs titration")["latest_version_id"]
        app.begin_delete()
        app.confirm_delete()
        _settle(app)
        assert "fcs titration" not in [p["project_name"] for p in app.model.projects if p.get("version_count")]
    finally:
        app.close()


def test_errors_reach_the_window(db):
    app = _app()
    try:
        _settle(app)
        app.error(app.open_selected)
        assert app.model.status == "Error: Select a project or version to restore."
        app.error(app.begin_delete)
        assert app.model.status == "Error: Select a version for this action."
        assert "Error: Select a version for this action." in " ".join(_draw(app).strings)
    finally:
        app.close()


# 3/5. the guide: every target drawn, the action steps wait for presses
def test_the_guide_points_at_real_controls_and_waits(db):
    app = _app()
    size = (1200, 800)
    try:
        _settle(app, painter=PixelPainter, size=size)
        app.model.selected_id = _project(app, "decay study")["project_id"]
        _draw(app, size, n=1, painter=PixelPainter)
        keys = {app.tour._target_key(s.get("target")) for s in app.tour.steps} - {""}
        assert keys and keys <= set(app.item_rects), keys - set(app.item_rects)

        def press(key):
            x, y, w, h = app.item_rects[key]
            app.pointer_move(x + 6, y + h / 2)
            app.press(x + 6, y + h / 2)
            _draw(app, size, n=1, painter=PixelPainter)
            app.release()
            _draw(app, size, n=1, painter=PixelPainter)

        for key in ("refresh", "inspect"):
            step = next(i for i, s in enumerate(app.tour.steps) if s.get("target", {}).get("name") == key)
            app.tour.start(step)
            assert app.tour.awaiting
            assert app.tour.steps[step]["title"] in " ".join(_draw(app, n=1).strings)   # the card is drawn
            _draw(app, size, n=1, painter=PixelPainter)
            press(key)
            assert not app.tour.awaiting, key
            _settle(app, painter=PixelPainter, size=size)
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes; settings round trip
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(db, size, monkeypatch):
    from emtk import im

    app = _app()
    try:
        _settle(app)
        app.expanded = {_project(app, "decay study")["project_id"]}
        strings = " ".join(_draw(app, size).strings)
        assert "decay study (2 versions)" in strings and "refit with IRF" in strings
        columns = []
        original = im.table_setup_column
        monkeypatch.setattr(im, "table_setup_column",
                            lambda label, flags=0, width=0.0: (columns.append((im.calc_text_size(label)[0], flags, width)),
                                                               original(label, flags, width))[1])
        _draw(app, size, n=1)
        assert columns and all(flags & im.TableColumnFlags.WIDTH_FIXED and width > text
                               for text, flags, width in columns)   # nothing overlaps; the table scrolls
    finally:
        app.close()


def test_settings_round_trip():
    app = _app()
    app.model.search, app.model.show_public, app.expanded = "decay", False, {"proj_x"}
    settings = app.export_settings()
    other = _app()
    other.restore_settings(settings)
    assert (other.model.search, other.model.show_public, other.expanded) == ("decay", False, {"proj_x"})


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("project_browser")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip(db):
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("project_browser")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
