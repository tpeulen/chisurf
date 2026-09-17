"""mmfdb-admin uses the shared NavigationPanelTool (left-nav / right-panel) shell.

Drives the full MMFDBWidget against the real in-process RPC layer and an empty
temp DB: it must be a NavigationPanelTool, expose the flattened nav panels, and
build every panel (entity docks + the workflow views) without raising.
"""

from __future__ import annotations

import os
from unittest import mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("qtpy")

from chisurf.gui.widgets.navigation import NavigationPanelTool
from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

from .conftest import patch_db


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


# Keep constructed widgets alive for the whole module: each MMFDBWidget builds
# docks that schedule QTimer.singleShot(0, refresh); if a widget is GC'd while a
# timer is pending, the callback hits a deleted C++ object. Holding references
# avoids that cross-test flake (the widgets are torn down at interpreter exit).
_WIDGETS: list = []


def _make_widget(db):
    from chisurf.plugins.core.mmfdb_admin.gui.tool import MMFDBWidget

    with patch_db(db):
        client = MMFDBClient(inprocess=True)
        with (
            mock.patch.object(MMFDBWidget, "_verify_admin_access", lambda s: None),
            mock.patch.object(MMFDBWidget, "_ensure_authenticated", lambda s: None),
        ):
            w = MMFDBWidget(client=client)
    _WIDGETS.append(w)
    return w


def test_widget_is_navigation_panel_tool(db, qapp):
    w = _make_widget(db)
    assert isinstance(w, NavigationPanelTool)
    # left nav + right stack from the shell
    assert hasattr(w, "nav_list") and hasattr(w, "stacked_widget")


def test_panels_flattened_with_separators_and_views(db, qapp):
    w = _make_widget(db)
    names = [p.get("name") for p in w.panels]
    # aggregate panels
    for n in ("Overview", "All items", "Measurements"):
        assert n in names
    # separator group headers
    assert sum(1 for p in w.panels if p.get("separator")) >= 4
    # entity panels are flattened in
    assert sum(1 for p in w.panels if p.get("entity_key")) >= 15
    # the previously-orphaned workflow views are now reachable
    for n in ("Studies", "Protocols", "Lifecycle", "Calibrations", "Reagent Lots", "Pipelines"):
        assert n in names
    # the spectra/optical component curation view is integrated from the optical_components module
    assert "Spectra" in names
    assert "eLabFTW" in names
    # nav items carry emoji icons
    assert any((p.get("icon") or "") for p in w.panels if p.get("entity_key"))


def test_fluorophore_panel_and_rpc_integrated(db, qapp):
    from chisurf.plugins.core.mmfdb_admin.gui.optical_components import OpticalComponentDock

    w = _make_widget(db)
    row = w._row_by_name["Spectra"]
    w.nav_list.setCurrentRow(row)
    inst = w._unwrap(w.panels[row]["instance"])
    assert isinstance(inst, OpticalComponentDock)
    # fluorophores.* RPC handlers are registered with the admin dispatcher
    res = w.client._call("fluorophores.list", {"limit": 1})
    assert "probes" in res and "total" in res


def test_every_panel_builds(db, qapp):
    from qtpy import QtWidgets

    w = _make_widget(db)
    for i, panel in enumerate(w.panels):
        if panel.get("separator"):
            continue
        w.nav_list.setCurrentRow(i)
        assert isinstance(panel.get("instance"), QtWidgets.QWidget), panel.get("name")


def test_entity_dock_uses_autoform(db, qapp):
    from chisurf.plugins.core.mmfdb_admin.gui.autoform_entity_form import EntityForm

    w = _make_widget(db)
    w.nav_list.setCurrentRow(w._row_by_entity["sample"])
    dock = w._entity_docks.get("sample")
    assert dock is not None
    assert isinstance(dock._form, EntityForm)


def test_overview_shows_connection_mode_and_database_type(db, qapp):
    """The Overview panel surfaces the client connection mode and DB backend."""
    w = _make_widget(db)
    w.client.login("admin", "admin")
    w.nav_list.setCurrentRow(w._row_by_name["Overview"])
    w._refresh_overview()
    text = w.overview_text.toPlainText()
    # Connection block: mode + endpoint (in-process embedded client here).
    assert "Mode:" in text
    assert "embedded" in text
    # Database type comes from the server status envelope (SQLite in tests).
    assert "SQLite" in text
    assert "Object store:" in text


def test_connection_labels_reflect_remote_mode(db, qapp):
    """Label helpers report a remote HTTP endpoint without a live server."""
    from chisurf.plugins.core.mmfdb_admin.gui.tool import MMFDBWidget

    w = _make_widget(db)
    # Reuse the real widget but point its label helpers at a remote-style client.
    w.client.mode = "remote"
    w.client.inprocess = False
    w.client.base_url = "http://mmfdb.example.org:8080"
    assert "remote" in w._connection_mode_label()
    assert w._connection_endpoint_label() == "http://mmfdb.example.org:8080"
    assert MMFDBWidget._database_type_label({"database_dialect": "postgresql"}) == "PostgreSQL"
