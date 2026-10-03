"""The menu and the ribbon open the same ndX window: the emtk app in a Qt host.

The menu opens ndX through the manifest's ``entrypoints.gui``; the ribbon
executes the plugin's ``__init__.py``. They used to build different Qt windows,
and then both built the legacy Qt window while the emtk app was finished. Both
now call :func:`~chisurf.plugins.ndxplorer.window.build_ndxplorer_window`, which
hosts :class:`ndxplorer.app.frame.NdxApp` in a ``ChisurfDockTool``.
"""

from __future__ import annotations

import os
import pathlib
import types

import pytest

pytest.importorskip("ndxplorer", reason="ndxplorer not on the path")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtWidgets  # noqa: E402

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    """The QApplication every window here needs."""
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(autouse=True)
def _scratch_settings(tmp_path, monkeypatch):
    """ndX's settings folder (dock layout, session store) is a scratch one."""
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path / "ndxplorer"))


def _open_from_menu():
    """Open ndX the way the menu does: through the manifest's GUI entry point."""
    from chisurf.gui import misc_helpers

    main_window = types.SimpleNamespace()
    assert misc_helpers._show_manifest_gui(main_window, PLUGIN_DIR)
    return main_window._plugin_windows[str(PLUGIN_DIR)]


def _open_from_ribbon():
    """Open ndX the way the ribbon's fallback does: execute ``__init__.py`` as ``plugin``."""
    from chisurf.gui import misc_helpers

    context = {"__name__": "plugin"}
    misc_helpers.run_macro(
        filename=str(PLUGIN_DIR / "__init__.py"),
        executor="exec",
        globals=context,
        main_window=None,
    )
    return context["ndx"]


def _hosted_app(window):
    """The NdxApp a route opened: the Qt ``NdxWindow``'s ``app`` or the emtk host's ``control``."""
    return getattr(window, "app", None) or getattr(window, "control", None)


def test_menu_and_ribbon_host_the_emtk_app(qapp):
    """Both routes host an ``NdxApp`` with ChiSurf's client, sessions and Global View slot.

    The menu follows the manifest's ``entrypoints.emtk`` (ndX's port is not on the
    preview list), so it opens the emtk app in emtk's Qt host; the ribbon's macro
    route still builds the Qt ``NdxWindow``. What the user gets is the same app,
    built the same way (:func:`chisurf.plugins.ndxplorer.gui.app.make_app` mirrors
    :func:`chisurf.plugins.ndxplorer.window.build_ndxplorer_window`).
    """
    from emtk.qt_host import host_class
    from ndxplorer.app.frame import NdxApp
    from ndxplorer.core.chisurf_binding import chisurf_group

    from chisurf.plugins.ndxplorer.window import NdxWindow, _constants_group, published_group

    for route, opener in (("menu", _open_from_menu), ("ribbon", _open_from_ribbon)):
        window = opener()
        try:
            app = _hosted_app(window)
            if route == "ribbon":
                # By name: the ribbon's macro runner reloads the plugin's modules.
                assert type(window).__name__ == NdxWindow.__name__, route
                assert isinstance(window.centralWidget(), host_class()), route
                window.host.grab()  # one frame, as on screen
            else:
                assert isinstance(window, host_class()), route
                window.grab()
            assert type(app).__name__ == NdxApp.__name__, route
            assert app.chisurf_rpc is not None, f"{route}: no ChiSurf RPC client"
            assert app.session_autosave, f"{route}: the user's window keeps sessions"
            group = _constants_group(app)
            assert group is not None
            # The app's own constants, through their one mirror -- not a copy.
            assert published_group() is not None, f"{route}: no Global View binding"
            assert published_group() is chisurf_group(group), route
        finally:
            window.close()
        assert published_group() is None, f"{route}: the closed window is still published"


def test_a_second_window_keeps_the_slot_when_the_first_closes(qapp):
    """Closing an older window does not withdraw a newer window's constants."""
    from ndxplorer.core.chisurf_binding import chisurf_group

    from chisurf.plugins.ndxplorer.window import (
        _constants_group,
        build_ndxplorer_window,
        published_group,
    )

    first = build_ndxplorer_window(session_autosave=False, layout_store=None)
    second = build_ndxplorer_window(session_autosave=False, layout_store=None)
    try:
        first.close()
        assert published_group() is not None
        assert published_group() is chisurf_group(_constants_group(second.app))
    finally:
        second.close()
    assert published_group() is None


def test_the_manifest_points_at_the_single_construction():
    """The manifest's GUI entry point is the function the ribbon calls."""
    from chisurf.core.plugin.manifest import load_manifest

    manifest = load_manifest(PLUGIN_DIR / "manifest.json")
    assert manifest.entrypoints.gui == "chisurf.plugins.ndxplorer.window:build_ndxplorer_window"
    assert "build_ndxplorer_window()" in (PLUGIN_DIR / "__init__.py").read_text()


def test_a_table_handed_over_is_shown(qapp):
    """A tool that computed bursts hands the table over; the app shows it."""
    from ndxplorer.core.data_source import DataSource

    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    source = DataSource.from_columns({"I_DD": [10.0, 20.0, 30.0], "I_DA": [4.0, 8.0, 3.0]})
    window = build_ndxplorer_window(
        data_source=source, session_autosave=False, layout_store=None
    )
    try:
        assert window.app.model.has_data
        assert window.app.model.source.size == 3
    finally:
        window.close()


# -- File > Import > From MMFDB ------------------------------------------------


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


def test_from_mmfdb_opens_the_picked_selection(qapp, embedded_mmfdb, tmp_path, monkeypatch):
    """Logged in: the entry is enabled, and the picked selection opens in the window."""
    from chisurf.plugins.ndxplorer import mmfdb_launcher
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    table = tmp_path / "selection.csv"
    table.write_text("I_DD,I_DA\n10,4\n20,8\n")
    picked = {}

    def pick(parent=None, scope="all", *, client):
        picked["client"] = client
        return str(table)

    monkeypatch.setattr(mmfdb_launcher, "pick_burst_selection_path", pick)
    _log_in_like_chisurf_startup()
    window = build_ndxplorer_window(session_autosave=False, layout_store=None)
    try:
        assert window.app.panel.available("open_from_mmfdb")
        assert window.app.run_action("open_from_mmfdb")
        assert picked["client"].token, "the picker got a client without the session"
        assert window.app.model.has_data and window.app.model.source.size == 2
        assert window.app.message is None
    finally:
        window.close()


def test_from_mmfdb_without_a_session_says_why(qapp, embedded_mmfdb, monkeypatch):
    """No session: nothing is picked, and the window says it is not logged in."""
    from mmfdb.security import credentials

    from chisurf.plugins.core.mmfdb_admin.gui import session
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    monkeypatch.setattr(credentials, "load_runtime_session_token", lambda *a, **k: None)
    monkeypatch.setattr(session, "cached_token", lambda *a, **k: None)
    window = build_ndxplorer_window(session_autosave=False, layout_store=None)
    try:
        assert window.open_from_mmfdb() is None
        title, text = window.app.message
        assert title == "Open from MMFDB" and "not logged in" in text
    finally:
        window.close()


def test_from_mmfdb_without_a_client_says_why(qapp, monkeypatch):
    """No in-process MMFDB at all: the message says the client could not start."""
    from chisurf.gui.widgets.mmfdb import picker
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    monkeypatch.setattr(picker, "inprocess_client", lambda: None)
    window = build_ndxplorer_window(session_autosave=False, layout_store=None)
    try:
        assert window.open_from_mmfdb() is None
        assert "could not be started" in window.app.message[1]
    finally:
        window.close()


# -- Save > Burst IDs records the selection in MMFDB ---------------------------


def test_saved_burst_ids_are_recorded_against_the_mmfdb_product(
    qapp, embedded_mmfdb, tmp_path
):
    """Opened on an MMFDB product (the admin's *Open in ndX*), Save > Burst IDs
    records an ``ndxplorer_selection`` run with the gate and the selection mask,
    linked to that product."""
    from emtk.testing import RecordingPainter
    from mmfdb.repository import MFDatabase
    from mmfdb.store.database_resolver import resolve_database_path

    from chisurf.gui.widgets.mmfdb import picker
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    mfd = PLUGIN_DIR.parents[2] / "modules" / "ndxplorer" / "test" / "mfd" / "burstwise_All 0.1500#30"
    if not mfd.exists():
        pytest.skip("ndX's MFD fixture folder is missing")
    _log_in_like_chisurf_startup()
    client = picker.inprocess_client()
    assert client is not None
    db_path = str(resolve_database_path())
    with MFDatabase(db_path) as db:
        db.add_sample("sample_1")
        db.add_experiment("exp_1", sample_id="sample_1", status="complete")
        run_id = db.add_processing_run(experiment_id="exp_1", input_raw_data_ids=[],
                                       settings={}, status="succeeded")
        prod_id = db.add_processed_data_product(
            processing_id=run_id, product_type="derived_product", storage_mode="folder",
            folder_path=str(mfd), checksum="1" * 64, validation_status="valid")

    window = build_ndxplorer_window(mfd, session_autosave=False, layout_store=None)
    try:
        app = window.app
        assert app.model.has_data
        window.record_burst_ids_in_mmfdb(prod_id, "exp_1", client=client)
        out = tmp_path / "bids"
        out.mkdir()
        assert app.run_action("save_burst_ids")
        app.io_service.answer(str(out))
        io = window._feature("io")
        if io.task is not None:
            io.task.wait(120.0)
            io.task = None
        for _ in range(2):
            app.draw(RecordingPainter(), 0.0, 0.0, 1400.0, 900.0)
        assert list(out.glob("*.bst")), "the burst-ID files were not written"
        assert app.status.startswith("Recorded the selection"), app.status
    finally:
        window.close()

    with MFDatabase(db_path) as db:
        edges = db.get_provenance_edges(source_node_type="processed_data",
                                        source_node_id=prod_id, relationship_type="input_to")
        assert len(edges) == 1
        run = db.get_processing_run_full(edges[0]["target_node_id"])
        assert run["processing_type"] == "ndxplorer_selection"
        assert run["settings"]["folder"] == str(out)
        produced = db.get_provenance_edges(source_node_type="processing_run",
                                           source_node_id=run["processing_id"],
                                           relationship_type="produced")
        assert len(produced) == 1


# -- embedded (the ALEX Suite's E-S step) ----------------------------------------


def _embedded_in_a_shell():
    """An ndX window flattened into another window, as the ALEX Suite does."""
    from chisurf.gui.widgets.navigation import embed_mainwindow
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    window = build_ndxplorer_window(session_autosave=False, layout_store=None)
    container = embed_mainwindow(window)
    shell = QtWidgets.QMainWindow()
    shell.setCentralWidget(container)
    return window, container, shell


def test_closing_the_window_ndx_is_embedded_in_closes_the_app(qapp):
    """The embedded window never gets a close event; its shell's close reaches the app."""
    from chisurf.plugins.ndxplorer.window import published_group

    window, _container, shell = _embedded_in_a_shell()
    shell.show()
    qapp.processEvents()
    assert published_group() is not None and not getattr(window.app, "_closed", False)
    shell.close()
    for _ in range(3):
        qapp.processEvents()
    assert window.app._closed
    assert published_group() is None


def test_a_refused_close_keeps_the_embedded_app(qapp):
    """A shell that refuses to close keeps ndX open."""
    window, _container, shell = _embedded_in_a_shell()
    shell.closeEvent = lambda event: event.ignore()
    shell.show()
    qapp.processEvents()
    shell.close()
    for _ in range(3):
        qapp.processEvents()
    assert not getattr(window.app, "_closed", False)
    del shell.closeEvent
    shell.close()
    for _ in range(3):
        qapp.processEvents()
    assert window.app._closed


def test_destroying_the_embedded_host_closes_the_app(qapp):
    """A shell deleted without a close (a panel torn down) closes the app too."""
    window, _container, shell = _embedded_in_a_shell()
    shell.deleteLater()
    from qtpy import QtCore

    qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    qapp.processEvents()
    assert window.app._closed
