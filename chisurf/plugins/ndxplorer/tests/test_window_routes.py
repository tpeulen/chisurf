"""Every route into ndX opens the same window: the emtk app, whichever shell hosts it.

The menu opens ndX through the manifest; tools hand it a file or a table. They
used to build ChiSurf's Qt ``NdxWindow`` (the app in a ``ChisurfDockTool``);
that window is retired. The manifest names only the emtk factory
(:func:`chisurf.plugins.ndxplorer.gui.app.make_app`): the emtk shell docks the
app and the ``--qt`` shell hosts it in a ``ControlHost`` (the generic route of
:func:`chisurf.core.plugin.registry.build_plugin_widget`). Tools reach the open
app through :func:`~chisurf.plugins.ndxplorer.gui.app.open_in_ndx` and
:func:`~chisurf.plugins.ndxplorer.gui.app.show_table_in_ndx`.

What the Qt window added to the app is kept and tested here without Qt: the
ChiSurf RPC client, the session autosave, the Global View slot (published while
open, withdrawn on close, kept by a newer window), closing when the host's
window goes (also when embedded in another window), File > Import > From MMFDB
and Save > Burst IDs recorded against an MMFDB product.
"""

from __future__ import annotations

import pathlib
import types

import pytest

pytest.importorskip("ndxplorer", reason="ndxplorer not on the path")

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]
MFD = PLUGIN_DIR.parents[2] / "modules" / "ndxplorer" / "tests" / "mfd" / "burstwise_All 0.1500#30"


@pytest.fixture(autouse=True)
def _scratch_settings(tmp_path, monkeypatch):
    """ndX's settings folder (dock layout, session store) is a scratch one."""
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path / "ndxplorer"))


@pytest.fixture
def make():
    """``make(**kwargs)`` builds apps through the plugin's factory and closes them after."""
    from chisurf.plugins.ndxplorer.gui.app import make_app

    built = []

    def _make(**kwargs):
        app = make_app(**kwargs)
        built.append(app)
        return app

    yield _make
    for app in built:
        app.close()


def test_the_manifest_names_only_the_emtk_factory():
    """No Qt window: both shells open ``make_app`` (the ``--qt`` one in a ``ControlHost``)."""
    from chisurf.core.plugin.manifest import load_manifest
    from chisurf.core.plugin.registry import select_gui_entrypoint

    manifest = load_manifest(PLUGIN_DIR / "manifest.json")
    assert manifest.entrypoints.gui is None
    emtk = "chisurf.plugins.ndxplorer.gui.app:make_app"
    assert manifest.entrypoints.emtk == emtk
    for mode in ("auto", "emtk", "qt"):
        assert select_gui_entrypoint(manifest, mode) == ("emtk", emtk), mode
    # The hosted window remembers its geometry, as the Qt window's did.
    assert manifest.statefulness.window.enabled
    source = (PLUGIN_DIR / "__init__.py").read_text()
    assert 'if __name__ == "plugin"' not in source, "the package must not open a window"


def test_the_menus_window_is_the_app_with_chisurfs_parts(make):
    """RPC client, session autosave and the Global View slot, published and withdrawn."""
    from ndxplorer.app.frame import NdxApp
    from ndxplorer.core.chisurf_binding import chisurf_group

    from chisurf.plugins.ndxplorer.global_view_slot import constants_group, published_group

    app = make()
    assert isinstance(app, NdxApp)
    assert app.chisurf_rpc is not None, "no ChiSurf RPC client"
    assert app.session_autosave, "the user's window keeps sessions"
    group = constants_group(app)
    assert group is not None
    # The app's own constants, through their one mirror -- not a copy.
    assert published_group() is chisurf_group(group)
    app.close()
    assert published_group() is None, "the closed window is still published"


def test_a_second_window_keeps_the_slot_when_the_first_closes(make):
    """Closing an older window does not withdraw a newer window's constants."""
    from ndxplorer.core.chisurf_binding import chisurf_group

    from chisurf.plugins.ndxplorer.global_view_slot import constants_group, published_group

    first = make(session_autosave=False)
    second = make(session_autosave=False)
    first.close()
    assert published_group() is chisurf_group(constants_group(second))
    second.close()
    assert published_group() is None


def test_the_hosts_window_closing_closes_the_app(make):
    """A host detaches its frame callback when its window closes or is destroyed --
    also a window the host was embedded in; that closes the app, once."""
    from chisurf.plugins.ndxplorer.global_view_slot import published_group

    app = make(session_autosave=False)
    app.set_frame_request_callback(lambda: None)  # a host shows it
    assert published_group() is not None and not app._chisurf_closed
    app.set_frame_request_callback(None)  # the host's window is gone
    assert app._chisurf_closed and published_group() is None


def test_a_host_attaching_first_does_not_close_the_app(make):
    """Only a callback removed *after* one was set means the window went away."""
    app = make(session_autosave=False)
    app.set_frame_request_callback(None)
    assert not app._chisurf_closed


def test_a_table_handed_over_is_shown(make, monkeypatch):
    """A tool that computed bursts hands the table over; the open app shows it."""
    from ndxplorer.core.data_source import DataSource

    from chisurf.core.plugin import handoff
    from chisurf.plugins.ndxplorer.gui.app import show_table_in_ndx

    monkeypatch.setattr(handoff, "available", lambda *a: False)  # the --qt shell
    app = make(session_autosave=False)
    source = DataSource.from_columns({"I_DD": [10.0, 20.0, 30.0], "I_DA": [4.0, 8.0, 3.0]})
    assert show_table_in_ndx(source) is app
    assert app.model.has_data and app.model.source.size == 3


def test_a_path_handed_over_opens_in_the_open_app(make, tmp_path, monkeypatch):
    from chisurf.core.plugin import handoff
    from chisurf.plugins.ndxplorer.gui.app import open_in_ndx

    monkeypatch.setattr(handoff, "available", lambda *a: False)
    table = tmp_path / "bursts.csv"
    table.write_text("I_DD,I_DA\n10,4\n20,8\n")
    app = make(session_autosave=False)
    assert open_in_ndx(table) is app
    assert app.model.has_data and app.model.source.size == 2


def test_the_opener_reaches_the_app_once_the_path_is_open(make, tmp_path, monkeypatch):
    """``on_opened(app)`` gets the app with the path open, standalone and through the shell."""
    from chisurf.core.plugin import handoff
    from chisurf.plugins.ndxplorer.gui.app import open_in_ndx

    table = tmp_path / "bursts.csv"
    table.write_text("I_DD,I_DA\n10,4\n20,8\n")
    monkeypatch.setattr(handoff, "available", lambda *a: False)
    app = make(session_autosave=False)
    reached = []
    open_in_ndx(table, on_opened=lambda a: reached.append((a, a.model.has_data)))
    assert reached == [(app, True)]
    # In the emtk shell the hand-off carries the callback; the shell calls it with the built app.
    calls = []
    monkeypatch.setattr(handoff, "available", lambda *a: True)
    monkeypatch.setattr(
        handoff, "hand_off", lambda *a, **kw: calls.append((a, kw)) or "dock record"
    )
    callback = reached.append
    assert open_in_ndx(table, on_opened=callback) == "dock record"
    assert calls == [(("ndxplorer", "open_path", {"path": str(table)}), {"on_delivered": callback})]


def test_with_no_app_open_the_chisurf_window_opens_one(make, monkeypatch):
    """No ndX open: the ChiSurf window opens the plugin as its menu does, and the table goes there."""
    import chisurf
    from ndxplorer.core.data_source import DataSource

    from chisurf.core.plugin import handoff
    from chisurf.plugins.ndxplorer.gui import app as ndx_app

    monkeypatch.setattr(handoff, "available", lambda *a: False)
    for open_app in ndx_app.open_ndx_apps():
        open_app.close()
    opened = []
    window = types.SimpleNamespace(
        load_and_show_plugin=lambda module: opened.append(module) or make(session_autosave=False)
    )
    monkeypatch.setattr(chisurf, "cs", window, raising=False)
    shown = ndx_app.show_table_in_ndx(DataSource.from_columns({"I_DD": [1.0, 2.0]}))
    assert opened == ["chisurf.plugins.ndxplorer"]
    assert shown.model.source.size == 2


def test_with_no_window_at_all_the_route_says_why(monkeypatch):
    import chisurf

    from chisurf.core.plugin import handoff
    from chisurf.plugins.ndxplorer.gui import app as ndx_app

    monkeypatch.setattr(handoff, "available", lambda *a: False)
    monkeypatch.setattr(ndx_app, "open_ndx_apps", lambda: [])
    monkeypatch.setattr(chisurf, "cs", None, raising=False)
    with pytest.raises(RuntimeError, match="no ChiSurf window"):
        ndx_app.open_in_ndx("x.csv")


def test_the_calibration_bridge_finds_the_open_windows(make):
    """Accurate FRET's Load from / Push to ndX find every open window, without Qt."""
    from chisurf.plugins.ndxplorer.calibration_bridge import find_ndx_windows

    before = len(find_ndx_windows())
    app = make(session_autosave=False)
    windows = find_ndx_windows()
    assert len(windows) == before + 1
    assert windows[-1].app is app and windows[-1].constants is app.model.manager.constants
    app.close()
    assert len(find_ndx_windows()) == before


# -- File > Import > From MMFDB ------------------------------------------------


def test_from_mmfdb_is_the_emtk_dataset_picker(make, monkeypatch):
    """The entry is enabled and opens the authenticated dataset picker in the window."""
    from chisurf.emtk import dataset_picker

    monkeypatch.setattr(dataset_picker, "session_client", lambda: object())
    monkeypatch.setattr(
        dataset_picker.DatasetPicker, "open", lambda self: setattr(self, "is_open", True)
    )
    app = make(session_autosave=False)
    assert app.panel.available("open_from_mmfdb")
    assert app.run_action("open_from_mmfdb")
    feature = next(f for f in app.features if f.name == "chisurf_mmfdb")
    assert feature.picker is not None and feature.picker.is_open


def test_a_picked_selection_opens_and_a_failure_says_why(make, tmp_path):
    app = make(session_autosave=False)
    feature = next(f for f in app.features if f.name == "chisurf_mmfdb")
    table = tmp_path / "selection.csv"
    table.write_text("I_DD,I_DA\n10,4\n20,8\n")
    feature.open_paths([str(table)])
    assert app.model.has_data and app.model.source.size == 2
    with pytest.raises(ValueError):
        feature.open_paths([str(tmp_path / "missing.csv")])


# -- Save > Burst IDs records the selection in MMFDB ---------------------------


@pytest.fixture
def embedded_mmfdb(tmp_path, monkeypatch):
    """A real in-process MMFDB on a throw-away database, logged in as ChiSurf's start-up does."""
    pytest.importorskip("mmfdb")
    from mmfdb.security.credentials import store_runtime_session_token

    import chisurf.core.settings as cs_settings
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    monkeypatch.setenv("MMFDB_DATABASE_URL", f"sqlite:///{tmp_path / 'mmfdb.db'}")
    mmfdb = dict(cs_settings.cs_settings.get("mmfdb", {}) or {})
    for key in ("last_server", "last_port"):
        mmfdb.pop(key, None)
    mmfdb["default_user_id"] = "user"
    monkeypatch.setitem(cs_settings.cs_settings, "mmfdb", mmfdb)
    client = MMFDBClient(inprocess=True)
    result = client.login("user", "user", quiet=True)
    assert result.get("ok"), result
    store_runtime_session_token(client.host, client.cmd_port, "user", result["token"])
    return client


def test_saved_burst_ids_are_recorded_against_the_mmfdb_product(make, embedded_mmfdb, tmp_path):
    """Opened on an MMFDB product (the admin's *Open in ndX*), Save > Burst IDs
    records an ``ndxplorer_selection`` run with the gate and the selection mask,
    linked to that product."""
    import shutil

    from emtk.testing import RecordingPainter
    from mmfdb.repository import MFDatabase
    from mmfdb.store.database_resolver import resolve_database_path

    from chisurf.plugins.ndxplorer.selection_provenance import record_burst_ids_against_product

    if not MFD.exists():
        pytest.skip("ndX's MFD fixture folder is missing")
    mfd = tmp_path / MFD.name
    shutil.copytree(MFD, mfd)
    db_path = str(resolve_database_path())
    with MFDatabase(db_path) as db:
        db.add_sample("sample_1")
        db.add_experiment("exp_1", sample_id="sample_1", status="complete")
        run_id = db.add_processing_run(
            experiment_id="exp_1", input_raw_data_ids=[], settings={}, status="succeeded"
        )
        prod_id = db.add_processed_data_product(
            processing_id=run_id,
            product_type="derived_product",
            storage_mode="folder",
            folder_path=str(mfd),
            checksum="1" * 64,
            validation_status="valid",
        )

    app = make(session_autosave=False)
    assert app.open_path(str(mfd)) and app.model.has_data
    record_burst_ids_against_product(app, prod_id, "exp_1", client=embedded_mmfdb)
    out = tmp_path / "bids"
    out.mkdir()
    assert app.run_action("save_burst_ids")
    app.io_service.answer(str(out))
    io = next(f for f in app.features if f.name == "io")
    if io.task is not None:
        io.task.wait(120.0)
        io.task = None
    for _ in range(2):
        app.draw(RecordingPainter(), 0.0, 0.0, 1400.0, 900.0)
    assert list(out.glob("*.bst")), "the burst-ID files were not written"
    assert app.status.startswith("Recorded the selection"), app.status
    app.close()

    with MFDatabase(db_path) as db:
        edges = db.get_provenance_edges(
            source_node_type="processed_data", source_node_id=prod_id, relationship_type="input_to"
        )
        assert len(edges) == 1
        run = db.get_processing_run_full(edges[0]["target_node_id"])
        assert run["processing_type"] == "ndxplorer_selection"
        assert run["settings"]["folder"] == str(out)
        produced = db.get_provenance_edges(
            source_node_type="processing_run",
            source_node_id=run["processing_id"],
            relationship_type="produced",
        )
        assert len(produced) == 1
