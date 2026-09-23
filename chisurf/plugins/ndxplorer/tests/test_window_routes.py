"""The menu and the ribbon open the same ndX window, and MMFDB is not skipped silently.

Two regressions, both of the "degraded without a word" kind:

* The menu opens ndX through the manifest's ``entrypoints.gui``; the ribbon
  executes the plugin's ``__init__.py``. They used to build different windows:
  only the ribbon added the Accurate FRET and MMFDB toolbars and bound the
  constants into the Global View.
* The MMFDB toolbar never appeared: the window probed ``mmfdb.status`` with a
  private ``MMFDBClient(inprocess=True)`` that carried no session token, and a
  bare ``except: pass`` swallowed the "Authentication required".
"""

from __future__ import annotations

import logging
import os
import pathlib
import types

import pytest

pytest.importorskip("ndxplorer", reason="ndxplorer not on the path")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtWidgets  # noqa: E402

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]
MMFDB_TOOLBAR = "ndxplorerMmfdbToolbar"
FRET_TOOLBAR = "ndxplorerAccurateFretToolbar"


@pytest.fixture(scope="module")
def qapp():
    """The QApplication every window here needs."""
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _AnsweringMmfdb:
    """An MMFDB client that answers ``mmfdb.status`` (a logged-in session)."""

    token = "session-token"

    def status(self):
        return {"ok": True}


@pytest.fixture
def mmfdb_answers(monkeypatch):
    """ChiSurf's shared MMFDB session client is logged in and answering."""
    from chisurf.gui.widgets.mmfdb import picker

    monkeypatch.setattr(picker, "inprocess_client", lambda: _AnsweringMmfdb())


def _toolbars(ndx) -> set[str]:
    return {
        bar.objectName() or bar.windowTitle() for bar in ndx.findChildren(QtWidgets.QToolBar)
    }


def _close(ndx) -> None:
    from chisurf.plugins.ndxplorer.parameters import unbind_ndx_parameters

    unbind_ndx_parameters()
    ndx.close()
    ndx.deleteLater()
    QtWidgets.QApplication.processEvents()


def _open_from_menu():
    """Open ndX the way the menu does: through the manifest's GUI entry point."""
    from chisurf.gui import misc_helpers

    main_window = types.SimpleNamespace()
    assert misc_helpers._show_manifest_gui(main_window, PLUGIN_DIR)
    return main_window._plugin_windows[str(PLUGIN_DIR)]


def _open_from_ribbon():
    """Open ndX the way the ribbon does: execute ``__init__.py`` as ``plugin``."""
    from chisurf.gui import misc_helpers

    context = {"__name__": "plugin"}
    misc_helpers.run_macro(
        filename=str(PLUGIN_DIR / "__init__.py"),
        executor="exec",
        globals=context,
        main_window=None,
    )
    return context["ndx"]


def test_menu_and_ribbon_build_the_same_window(qapp, mmfdb_answers):
    """Same toolbars, and both bind the window's constants into the Global View."""
    from chisurf.plugins.ndxplorer.parameters import bound_ndx_parameters

    seen = {}
    for route, opener in (("menu", _open_from_menu), ("ribbon", _open_from_ribbon)):
        ndx = opener()
        try:
            qapp.processEvents()
            seen[route] = _toolbars(ndx)
            group = bound_ndx_parameters()
            assert group is not None, f"{route}: no Global View binding"
            assert group._window is ndx, f"{route}: the Global View is bound to another window"
        finally:
            _close(ndx)

    assert seen["menu"] == seen["ribbon"]
    assert {MMFDB_TOOLBAR, FRET_TOOLBAR} <= seen["menu"], seen["menu"]


def test_the_manifest_points_at_the_single_construction():
    """The manifest's GUI entry point is the function the ribbon calls."""
    from chisurf.core.plugin.manifest import load_manifest

    manifest = load_manifest(PLUGIN_DIR / "manifest.json")
    assert manifest.entrypoints.gui == "chisurf.plugins.ndxplorer.window:build_ndxplorer_window"
    assert "build_ndxplorer_window()" in (PLUGIN_DIR / "__init__.py").read_text()


@pytest.fixture
def embedded_mmfdb(tmp_path, monkeypatch):
    """A real in-process MMFDB on a throw-away database.

    Resets ChiSurf's shared session client before and after, so the client is
    built -- and adopts the session token -- inside the test.
    """
    pytest.importorskip("mmfdb")
    from chisurf.gui.widgets.mmfdb import picker

    monkeypatch.setenv("MMFDB_DATABASE_URL", f"sqlite:///{tmp_path / 'mmfdb.db'}")
    import chisurf.core.settings as cs_settings

    mmfdb = dict(cs_settings.cs_settings.get("mmfdb", {}) or {})
    for key in ("last_server", "last_port"):
        mmfdb.pop(key, None)
    mmfdb["default_user_id"] = "user"
    monkeypatch.setitem(cs_settings.cs_settings, "mmfdb", mmfdb)
    picker.reset_session_client()
    yield
    picker.reset_session_client()


def _log_in_like_chisurf_startup() -> None:
    """Log in as ChiSurf's start-up does, and keep the token for the process."""
    from mmfdb.security.credentials import store_runtime_session_token

    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    login = MMFDBClient(inprocess=True)
    result = login.login("user", "user", quiet=True)
    assert result.get("ok"), result
    store_runtime_session_token(login.host, login.cmd_port, "user", result["token"])


def test_mmfdb_toolbar_appears_with_the_chisurf_session(qapp, embedded_mmfdb):
    """Logged in to the in-process MMFDB, the window offers "Open from MMFDB"."""
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    _log_in_like_chisurf_startup()
    ndx = build_ndxplorer_window()
    try:
        assert MMFDB_TOOLBAR in _toolbars(ndx)
    finally:
        _close(ndx)


def test_without_mmfdb_session_the_reason_is_logged(qapp, embedded_mmfdb, caplog, monkeypatch):
    """No session: no toolbar, and a warning that says why -- not a silent pass."""
    from mmfdb.security import credentials

    from chisurf.plugins.core.mmfdb_admin.gui import session
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    monkeypatch.setattr(credentials, "load_runtime_session_token", lambda *a, **k: None)
    monkeypatch.setattr(session, "cached_token", lambda *a, **k: None)
    with caplog.at_level(logging.WARNING, logger="chisurf.plugins.ndxplorer.window"):
        ndx = build_ndxplorer_window()
    try:
        assert MMFDB_TOOLBAR not in _toolbars(ndx)
        reasons = [r.getMessage() for r in caplog.records if "MMFDB toolbar" in r.getMessage()]
        assert reasons and "not logged in" in reasons[0], caplog.text
        assert "MMFDB toolbar" in ndx.statusBar().currentMessage()
    finally:
        _close(ndx)


def test_mmfdb_client_missing_is_logged(qapp, caplog, monkeypatch):
    """No in-process MMFDB at all: no toolbar, and the warning says so."""
    from chisurf.gui.widgets.mmfdb import picker
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    monkeypatch.setattr(picker, "inprocess_client", lambda: None)
    with caplog.at_level(logging.WARNING, logger="chisurf.plugins.ndxplorer.window"):
        ndx = build_ndxplorer_window()
    try:
        assert MMFDB_TOOLBAR not in _toolbars(ndx)
        assert "could not be started" in caplog.text
    finally:
        _close(ndx)
