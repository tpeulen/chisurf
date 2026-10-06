"""Parity checks for the Qt-free spectra tool's four workflows."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from emtk import i18n
from emtk.testing import RecordingPainter

from chisurf.plugins.spectra_downloader.gui.app import PANELS, create_app
from chisurf.plugins.spectra_downloader.gui.translations import _ROWS, LOCALES, tr
from chisurf.plugins.spectra_downloader.mmfdb_adapter import FluorophoreDatabase


@pytest.fixture
def app(tmp_path):
    db = FluorophoreDatabase(tmp_path / "staging.db")
    db.connect()
    x = np.array([400.0, 500.0, 600.0])
    db.register_component(
        name="EGFP",
        source="fpbase,chroma",
        kind="fluorescent_protein",
        properties={"em_max": 509},
        spectra={"emission": (x, [0.0, 1.0, 0.0])},
    )
    db.register_component(name="ET525", source="chroma", kind="bandpass")
    a = create_app(db)
    yield a
    a.close()
    db.close()
    i18n.set_locale("en")


def test_overview_filter_selection_and_spectra(app):
    m = app.model
    assert m.overview()["total"] == 2
    assert m.overview()["with_spectra"] == 1
    assert m.overview()["fluorophores"] == m.overview()["filters"] == 1
    assert m.sources == ["chroma", "fpbase"]
    m.source = "fpbase"
    assert [r["chromophore_name"] for r in m.filtered()] == ["EGFP"]
    m.search = "gFp"
    assert len(m.filtered()) == 1
    m.category = "filter"
    assert not m.filtered()
    m.select(m.rows[0]["probe_id"])
    assert m.detail["spectra"][0]["intensity"] == [0.0, 1.0, 0.0]
    assert len(m.selected) == 1
    m.select(m.rows[0]["probe_id"], False)
    assert m.detail is None


def test_push_selected_and_all_keep_precise_ids(app, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "chisurf.plugins.spectra_downloader.download.merge.push_staging_to_mmfdb",
        lambda path, probe_ids=None: calls.append((path, probe_ids)),
    )
    with pytest.raises(ValueError, match="No components"):
        app.model.push(True)
    app.model.select(app.model.rows[0]["probe_id"])
    app.model.push(True)
    app.model.push(False)
    assert calls[0][1] == sorted(app.model.selected)
    assert calls[1][1] is None


def test_downloader_registry_command_and_log_completion(app):
    m = app.model
    m.module = "chroma"
    assert m.command() == [
        sys.executable,
        "-m",
        "chisurf.plugins.spectra_downloader.download.chroma",
        "--db",
        str(m.db.db_path),
    ]
    assert m.source_slug() == "chroma"
    app.browse_source()
    assert app.panel == "Browse" and m.source == "chroma"
    m.messages.put(("output", "test output\n"))
    m.messages.put(("finished", 3))
    m.poll()
    assert "test output" in m.log and "Finished (3)" in m.log


def test_import_local_with_replace_backup_and_approved_status(app, tmp_path):
    target = tmp_path / "live.db"
    live = FluorophoreDatabase(target)
    live.connect()
    live.close()
    m = app.model
    m.endpoint.db_path = str(target)
    m.endpoint.replace = True
    m.endpoint.mark_verified = True
    assert m.authorized()[0]
    before = target.read_bytes()
    result = m.add_all()
    assert result["probes"] == 2
    assert Path(str(target) + ".bak").read_bytes() == before
    live = FluorophoreDatabase(target)
    live.connect()
    assert {
        r[0]
        for r in live.conn.execute(
            "SELECT verification_status FROM probes WHERE deleted_at IS NULL"
        )
    } == {"approved"}
    live.close()


def test_server_import_reuses_session_and_checks_admin(app, monkeypatch):
    m = app.model
    m.endpoint.mode = "server"
    calls = []

    class Client:
        token = None

        def __init__(self, **kwargs):
            calls.append(kwargs)

        def login(self, *args):
            raise AssertionError("cached session must skip login")

        def list_users(self):
            return [{"user_id": m.endpoint.user, "is_admin": True}]

        def _call(self, method, params):
            calls.append((method, params))
            return {"probes": 2}

    monkeypatch.setattr("chisurf.plugins.core.mmfdb_admin.gui.client.MMFDBClient", Client)
    monkeypatch.setattr(
        "chisurf.plugins.spectra_downloader.gui.native.cached_token", lambda *a: "session-token"
    )
    assert m.server_client().token == "session-token"
    assert m.add_all() == {"probes": 2}
    assert calls[-1][0] == "fluorophores.import_reference_set"
    assert calls[-1][1]["source_path"] == str(m.db.db_path)
    monkeypatch.setattr(
        "chisurf.plugins.spectra_downloader.gui.native.client_is_admin", lambda *a: False
    )
    with pytest.raises(PermissionError):
        m.add_all()


def test_persisted_selection_excludes_password(app):
    app.model.select(app.model.rows[0]["probe_id"])
    app.model.endpoint.password = "secret"
    app.panel = "Browse"
    state = app.export_state()
    assert "password" not in state["endpoint"]
    assert "secret" not in json.dumps(state)
    app.model.selected.clear()
    app.restore_state(state)
    assert len(app.model.selected) == 1
    assert app.panel == "Browse"


@pytest.mark.parametrize("locale", LOCALES)
def test_all_panels_and_controls_have_translations_and_render(app, locale):
    i18n.set_locale(locale)
    for row in _ROWS:
        assert tr(row[0]) == row[LOCALES.index(locale)]
    app.model.select(app.model.rows[0]["probe_id"])
    for panel in PANELS:
        app.panel = panel
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 640, 700)
        assert painter.strings
    assert {
        "nav.Overview",
        "nav.Browse",
        "nav.Download",
        "nav.Add to MMFDB",
        "language",
        "help",
    } <= app.item_rects.keys()


def test_native_factory_rejects_any_qt_import(tmp_path):
    script = r"""
import importlib.abc, sys, tempfile
attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6','sip','pyqtgraph'}:
            attempts.append(fullname)
            raise AssertionError('Qt import attempted: '+fullname)
sys.meta_path.insert(0,Block())
from chisurf.emtk.plugins import native_factory, load_plugin
from chisurf.plugins.spectra_downloader.gui.app import create_app
from chisurf.plugins.spectra_downloader.mmfdb_adapter import FluorophoreDatabase
from emtk.testing import RecordingPainter
assert native_factory('spectra_downloader').endswith(':create_app')
db=FluorophoreDatabase(sys.argv[1]); db.connect()
import chisurf.plugins.spectra_downloader as plugin
plugin.get_db=lambda: db
app=load_plugin("spectra_downloader",locale="en",persist=False)
for panel in ('Overview','Browse','Download','Add to MMFDB'):
    app.panel=panel; app.draw(RecordingPainter(),0,0,640,700)
app.close(); db.close()
assert not attempts, attempts
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "native.db")], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_scraper_process_streams_output_and_rejects_concurrent_run(app, monkeypatch):
    import io
    import time

    calls = []

    class Process:
        stdout = io.StringIO("downloaded 2 spectra\n")

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(
        "chisurf.plugins.spectra_downloader.gui.native.subprocess.Popen",
        lambda command, **kwargs: calls.append((command, kwargs)) or Process(),
    )
    assert app.model.run_script()
    assert not app.model.run_script()
    deadline = time.monotonic() + 2
    while app.model.process is not None and time.monotonic() < deadline:
        app.model.poll()
    assert app.model.process is None
    assert "downloaded 2 spectra" in app.model.log
    assert calls[0][0] == app.model.command()
    assert calls[0][1]["stderr"] == subprocess.STDOUT


def test_descriptive_tooltips_translate(app):
    from chisurf.plugins.spectra_downloader.gui.translations import _HELP_ROWS, TOOLTIPS

    for locale in LOCALES:
        i18n.set_locale(locale)
        for row in _HELP_ROWS:
            assert tr(row[0]) == row[LOCALES.index(locale)]
        assert TOOLTIPS["Push selected"] != "Push selected"
