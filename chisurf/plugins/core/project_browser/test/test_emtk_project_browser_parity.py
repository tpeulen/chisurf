"""The native Project Browser at parity with the Qt ProjectBrowserTool.

Both talk to the same project service. The Qt tool's tree on the seeded scratch database is
``qt_reference.json`` (recorded from the live widget, ids normalised; this file imports no Qt) and
is compared with the emtk app's rows; save, restore, export/import and delete are driven through the
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

from chisurf.plugins.core.project_browser.test.driving import MetricPainter
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

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())


@pytest.fixture(autouse=True)
def project_threads_finish():
    """A background project call still running when a test ends would read the next test's database: wait for them."""
    yield
    import threading

    for thread in threading.enumerate():
        if thread.name.startswith("project-browser"):
            thread.join(timeout=15)


@pytest.fixture
def db(authenticated_browser, sample_project_payload):
    """Seed measured canonical snapshots in the authenticated standalone service."""
    import copy

    deployment = authenticated_browser
    client = deployment["client"]
    payload = copy.deepcopy(sample_project_payload)
    payload["meta"]["name"] = "decay study"
    first = client.save_project(
        project_name="decay study", project_payload=payload, notes="first fit", visibility="private"
    )
    assert first["ok"], first
    second = client.save_project(
        project_name="decay study",
        project_payload=payload,
        project_id=first["project_id"],
        parent_version_id=first["version_id"],
        notes="refit with IRF",
        visibility="private",
    )
    assert second["ok"] and second["parent_version_id"] == first["version_id"]
    public_payload = copy.deepcopy(payload)
    public_payload["meta"]["name"] = "fcs titration"
    public = client.save_project(
        project_name="fcs titration",
        project_payload=public_payload,
        notes="public set",
        visibility="public",
    )
    assert public["ok"], public
    deployment["payload"] = payload
    return deployment


def _app(db=None, **model_kwargs):
    from types import SimpleNamespace

    from chisurf.plugins.core.project_browser.gui.app import ProjectBrowserApp
    from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel

    restored, reopened = [], []
    if db is not None:
        model_kwargs.setdefault("client", db["client"])
        model_kwargs.setdefault(
            "payload_provider",
            lambda name: {
                **db["payload"],
                "meta": {**db["payload"]["meta"], "name": name},
            },
        )
    model = ProjectBrowserModel(
        context=SimpleNamespace(),
        payload_loader=restored.append,
        window_restorer=reopened.append,
        **model_kwargs,
    )
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


#: The legacy Qt ``ProjectBrowserTool`` tree on this file's seeded database (fixture ``db``), recorded
#: from the live widget and frozen. The tree is a function of the service's ``list_projects`` answer;
#: what changes run to run (project and version ids, ``created_at``, the account) is normalised to
#: ``<project NAME>`` / ``<version NAME vN>`` / ``<timestamp>`` / ``<user>``, so the record holds.
QT = json.loads((HERE / "qt_reference.json").read_text(encoding="utf-8"))


def _normalised_rows(projects, owner):
    """The emtk model's projects as the Qt tree's nine columns, normalised like the record.

    Parameters
    ----------
    projects : list of dict
        ``app.model.projects``.
    owner : str
        The account the database was seeded by.

    Returns
    -------
    list of dict
    """
    def who(user):
        return "<user>" if user == owner else user

    rows = []
    for p in projects:
        name = p["project_name"]
        rows.append(
            {
                "project": [
                    f"{name}  ({p['version_count']} versions)",
                    f"<project {name}>",
                    who(p.get("owner_user_id", "")),
                    "",
                    p.get("visibility", "private"),
                    "",
                    "",
                    "<timestamp>" if p.get("created_at") else "",
                    "",
                ],
                "versions": [
                    [
                        f"v{v['version_number']}  {v.get('project_name', name)}",
                        f"<version {name} v{v['version_number']}>",
                        who(v.get("owner_user_id", "")),
                        v.get("status", ""),
                        "",
                        str(v.get("dataset_count", 0)),
                        str(v.get("fit_count", 0)),
                        "<timestamp>" if v.get("created_at") else "",
                        (v.get("notes") or "")[:60],
                    ]
                    for v in p["versions"]
                ],
            }
        )
    return rows


# 1. the same projects and versions as the Qt tree
def test_the_list_shows_what_the_qt_tree_shows(db):
    app = _app(db)
    try:
        _settle(app)
        ours = _normalised_rows(app.model.projects, db["settings"]["client"]["username"])
        key = lambda row: row["project"][1]  # noqa: E731
        assert sorted(ours, key=key) == sorted(QT["rows"], key=key)
        assert len({p["project_id"] for p in app.model.projects}) == len(QT["rows"]) == 2
    finally:
        app.close()


# 2. restore: the payload loaded, the fit windows reopened, the session told which version it is
def test_restore_loads_the_version_and_reopens_its_windows(db):
    app = _app(db)
    try:
        _settle(app)
        project = _project(app, "decay study")
        app.model.selected_id = project["project_id"]  # a project means its newest version
        app.open_selected()
        _settle(app)
        assert len(app.restored) == 1
        assert len(app.reopened) == 1
        assert app.reopened[0]["ui"] == app.restored[0]["ui"]
        session = assert_scientific_roundtrip(app.restored[0])
        import numpy as np

        import chisurf

        assert (
            chisurf.imported_datasets[0].unique_identifier == session.datasets[0].unique_identifier
        )
        np.testing.assert_array_equal(chisurf.imported_datasets[0].y, session.datasets[0].y)
        context = app.model.context
        assert context._current_project_id == project["project_id"]
        assert context._current_project_version_id == project["latest_version_id"]
        assert context._current_project_name == "decay study"
    finally:
        app.close()


def test_the_default_restorer_reopens_windows_only_with_a_main_window(
    monkeypatch, sample_project_payload
):
    import chisurf
    from chisurf.core.project.transition import ProjectTransitionError
    from chisurf.plugins.core.project_browser.gui import model

    fit = assert_scientific_roundtrip(_payload_with_fit(sample_project_payload)).fits[0]
    opened = []
    monkeypatch.setattr(
        chisurf,
        "cs",
        type(
            "Main",
            (),
            {
                "_open_fit_subwindow": lambda self, f, *, restored=False: opened.append(
                    (f, restored)
                ),
            },
        )(),
        raising=False,
    )
    monkeypatch.setattr(chisurf, "fits", [fit], raising=False)
    uid = fit.unique_identifier
    presentation = model.restore_fit_windows(
        {"fits": [{"uid": uid}], "ui": {"current_fit_uid": uid, "current_fit_index": 0}}
    )
    presentation.commit()
    assert opened == [(fit, True)]
    with pytest.raises(ProjectTransitionError, match="missing.*not available"):
        model.restore_fit_windows({"fits": [{"uid": "missing"}]})
    monkeypatch.setattr(chisurf, "cs", None, raising=False)
    model.restore_fit_windows({"fits": [{"uid": uid}]})
    assert opened == [(fit, True)]


# 2. save a new version, export it, import it, delete one
def test_save_export_import_and_delete(db, tmp_path):
    app = _app(db)
    try:
        _settle(app)
        project = _project(app, "decay study")
        current = app.model.client.restore_project(project["latest_version_id"])
        assert current["ok"] and current["project_id"] == project["project_id"]
        app.model.update_current(current)
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
        project = _project(app, "decay study")  # the archive joins its project as the next version
        assert project["version_count"] == 4
        assert sorted(v["version_number"] for v in project["versions"]) == [1, 2, 3, 4]
        app.model.selected_id = _project(app, "fcs titration")["latest_version_id"]
        app.begin_delete()
        app.confirm_delete()
        _settle(app)
        assert "fcs titration" not in [
            p["project_name"] for p in app.model.projects if p.get("version_count")
        ]
    finally:
        app.close()


def test_errors_reach_the_window(db):
    app = _app(db)
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
    app = _app(db)
    size = (1200, 800)
    try:
        _settle(app, painter=MetricPainter, size=size)
        app.model.selected_id = _project(app, "decay study")["project_id"]
        _draw(app, size, n=1, painter=MetricPainter)
        keys = {app.tour._target_key(s.get("target")) for s in app.tour.steps} - {""}
        assert keys and keys <= set(app.item_rects), keys - set(app.item_rects)

        def press(key):
            x, y, w, h = app.item_rects[key]
            app.pointer_move(x + 6, y + h / 2)
            app.press(x + 6, y + h / 2)
            _draw(app, size, n=1, painter=MetricPainter)
            app.release()
            _draw(app, size, n=1, painter=MetricPainter)

        for key in ("refresh", "inspect"):
            step = next(
                i for i, s in enumerate(app.tour.steps) if s.get("target", {}).get("name") == key
            )
            app.tour.start(step)
            assert app.tour.awaiting
            assert app.tour.steps[step]["title"] in " ".join(
                _draw(app, n=1).strings
            )  # the card is drawn
            _draw(app, size, n=1, painter=MetricPainter)
            press(key)
            assert not app.tour.awaiting, key
            _settle(app, painter=MetricPainter, size=size)
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes; settings round trip
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(db, size):
    app = _app(db)
    try:
        _settle(app)
        app.expanded = {_project(app, "decay study")["project_id"]}
        strings = _draw(app, size).strings
        # the cells are drawn whole (emtk shortens a cell that does not fit with a trailing dot)
        for text in ("decay study (2 versions)", "v2 decay study", "fcs titration (1 versions)"):
            assert any(s.startswith(text) and not s.endswith(".") for s in strings), (text, size)
    finally:
        app.close()


def test_settings_round_trip(db):
    app = _app(db)
    app.model.search, app.model.show_public, app.expanded = "decay", False, {"proj_x"}
    settings = app.export_settings()
    other = _app(db)
    other.restore_settings(settings)
    try:
        assert (other.model.search, other.model.show_public, other.expanded) == (
            "decay",
            False,
            {"proj_x"},
        )
    finally:
        app.close()
        other.close()


# 6/7. no Qt, tooltips
def test_port_is_qt_free(tmp_path):
    script = """
import importlib.abc, sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
            raise RuntimeError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from test.gui.emtk_port_parity import build_emtk_app, draw_app
app = build_emtk_app('project_browser')
try:
    draw_app(app, (1200, 800))
    assert not any(m == 'chisurf.gui' or m.startswith('chisurf.gui.') for m in sys.modules)
finally:
    app.close()
"""
    settings = tmp_path / "qt-free-settings"
    settings.mkdir()
    env = dict(os.environ, CHISURF_SETTINGS_DIR=str(settings), MMFDB_SETTINGS_DIR=str(settings))
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_control_has_a_tooltip(db):
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("project_browser")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
