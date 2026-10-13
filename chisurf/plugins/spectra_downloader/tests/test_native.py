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
from chisurf.plugins.spectra_downloader.gui.translations import LOCALES, SOURCES, TOOLTIPS, tr
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


def catalogue(locale):
    """ChiSurf's finished translations for *locale* (the one source of the window's strings)."""
    from chisurf.emtk.i18n import read_catalog

    root = Path(__file__).resolve().parents[4]
    path = root / "chisurf" / "gui" / "i18n" / f"chisurf_{locale}.ts"
    return read_catalog(path, include_unfinished=False)["chisurf"]


def expected(locale, source):
    """What *source* must read in *locale*: English as is, otherwise the catalogue's translation."""
    if locale == "en":
        return source
    translations = catalogue(locale)
    assert source in translations, f"{locale}: no catalogue translation for {source!r}"
    return translations[source]


@pytest.mark.parametrize("locale", LOCALES)
def test_all_panels_and_controls_have_translations_and_render(app, locale):
    i18n.set_locale(locale)
    for source in SOURCES:
        assert tr(source) == expected(locale, source)
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
    for locale in LOCALES:
        i18n.set_locale(locale)
        for text in TOOLTIPS.values():
            assert tr(text) == expected(locale, text)
        assert TOOLTIPS["Push selected"] != "Push selected"


# -- the staging browser, the Add-to-MMFDB panel and the overview, ported from the Qt widgets' tests -------------- #


@pytest.fixture
def staged(tmp_path):
    """A staging database with a protein, a detector and (second source) a bandpass filter."""
    db = FluorophoreDatabase(tmp_path / "staged.db")
    db.connect()
    wl = np.linspace(400, 700, 8)
    with db:
        db.register_component(
            name="EGFP",
            source="fpbase",
            kind="fluorescent_protein",
            spectra={"absorption": (wl, np.ones_like(wl)), "emission": (wl, np.ones_like(wl))},
        )
        db.register_component(
            name="Thorlabs SPCMxxA",
            source="fpbase",
            kind="detector",
            source_ref="9342",
            spectra={"quantum_efficiency": (wl, np.linspace(0, 1, 8))},
        )
        db.conn.commit()
    a = create_app(db)
    yield a
    a.close()
    db.close()
    i18n.set_locale("en")


def _probes(path):
    import sqlite3

    return sqlite3.connect(path).execute(
        "SELECT chromophore_name, category, source FROM probes WHERE deleted_at IS NULL"
    ).fetchall()


def test_browser_lists_and_shows_detail_on_selection(staged):
    m = staged.model
    assert len(m.rows) == 2
    assert {"detector", "protein"} <= set(staged.category_options())
    m.search = "SPCM"
    assert len(m.filtered()) == 1
    m.select(m.filtered()[0]["probe_id"])
    assert m.detail["probe"]["chromophore_name"] == "Thorlabs SPCMxxA"
    assert m.detail["probe"]["category"] == "detector"
    assert "component_kind" in {p["property_name"] for p in m.detail["optical_properties"]}
    m.search, m.category = "", "protein"
    assert len(m.filtered()) == 1
    # the metadata view is the probe plus its spectra
    assert any(s["spectrum_type"] == "quantum_efficiency" for s in m.detail["spectra"])


def test_overview_panel_counts(staged):
    ov = staged.model.overview()
    assert ov["by_category"].get("protein") == 1 and ov["by_category"].get("detector") == 1
    assert ov["detectors"] == 1


def test_add_to_mmfdb_local_has_sane_defaults_and_adds_every_category(staged, tmp_path):
    m = staged.model
    assert m.endpoint.mode == "local" and m.endpoint.cmd_port == 8765
    m.endpoint.db_path = str(tmp_path / "fresh.mmfdb")
    m.add_all()
    assert {"protein", "detector"} <= {c for _, c, _ in _probes(m.endpoint.db_path)}


def test_add_to_mmfdb_session_admin_gate(staged, tmp_path):
    """Admins add without a login; non-admins are refused (session-first)."""
    from mmfdb.repository import MFDatabase

    mmfdb = str(tmp_path / "gate.mmfdb")
    with MFDatabase(mmfdb) as d:
        d.add_user("user_default", "Default User", is_admin=1)
        d.add_user("guest", "Guest", is_admin=0)
    m = staged.model
    m.endpoint.db_path, m.endpoint.password = mmfdb, ""
    m.endpoint.user = "user_default"
    m.add_all()
    assert len(_probes(mmfdb)) >= 2
    m.endpoint.user = "guest"
    with pytest.raises(PermissionError, match="not an administrator"):
        m.add_all()


def test_source_filter_and_push(staged, tmp_path):
    from chisurf.plugins.spectra_downloader.download.merge import push_staging_to_mmfdb

    wl = np.linspace(400, 700, 8)
    db = staged.model.db
    with db:
        db.register_component(
            name="FB340-10",
            source="thorlabs",
            kind="bandpass",
            spectra={"transmission": (wl, np.ones_like(wl))},
        )
        db.conn.commit()
    m = staged.model
    m.refresh()
    m.source = "thorlabs"
    assert [r["chromophore_name"] for r in m.filtered()] == ["FB340-10"]
    m.pick(m.filtered()[0]["probe_id"])
    mmfdb = str(tmp_path / "push.mmfdb")
    summary = push_staging_to_mmfdb(
        str(db.db_path), probe_ids=sorted(m.selected), mmfdb_path=mmfdb
    )
    assert summary["merged"] == 1
    assert _probes(mmfdb) == [("FB340-10", "filter", "thorlabs")]
    push_staging_to_mmfdb(str(db.db_path), mmfdb_path=mmfdb)
    assert len(_probes(mmfdb)) == 3
