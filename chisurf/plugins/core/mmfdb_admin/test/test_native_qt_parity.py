"""Behaviours of the retired Qt MMFDB Admin that the native app had to gain before the Qt went.

An audit of every reachable Qt action against the native app found no lost backend call, but
these interactions were missing: Enter in a connection field logs in, Enter in the eLabFTW
search lists, the Spectra search runs as you type (with Auto to turn it off), the Spectra
table's right-click menu, Find Duplicates' progress and Cancel, a click on a provenance edge
showing its record, and an entity row's UUID on hover. Each is driven here as a user drives
it (emtk Driver) over a seeded temporary MMFDB.
"""

from __future__ import annotations

import json
from pathlib import Path

from chisurf.plugins.core.mmfdb_admin.gui.native import dialogs as dlg
from chisurf.plugins.core.mmfdb_admin.gui.native import spectra
from chisurf.plugins.emtk_test_input import Driver

from .native_support import (  # noqa: F401
    admin_folder,
    app,
    client,
    driver,
    open_panel,
    seeded_template,
)


def _right_click(driver, rect):  # noqa: F811
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    driver.app.pointer_move(cx, cy)
    driver.draw(2)
    driver.app.pointer_press(cx, cy, 2)
    driver.draw(2)
    driver.app.pointer_release(cx, cy, 2)
    driver.draw(2)


def _pick(driver, label):  # noqa: F811
    driver.click(Driver.text_rect(driver.draw(2), label))
    driver.draw(2)


def _cell(driver, text):  # noqa: F811
    return Driver.text_rect(driver.draw(2), text, last=False)


# ── connection toolbar ─────────────────────────────────────────────────


def test_enter_in_the_password_field_logs_in(driver, app):  # noqa: F811
    driver.click_name("logout")
    assert app.model.connection == "disconnected"
    app.model.client.token = None
    driver.type_into_name("password", "admin")  # typed, then Enter
    assert app.model.connected and app.model.login_user == "admin"
    assert app.model.password == ""  # never kept past the attempt


def test_enter_in_a_field_while_connected_does_not_log_in_again(driver, app, monkeypatch):  # noqa: F811
    calls = []
    monkeypatch.setattr(app.model, "login", lambda: calls.append(1))
    driver.type_into_name("user", "admin")
    assert calls == []


# ── eLabFTW ────────────────────────────────────────────────────────────


def test_enter_in_the_elabftw_search_lists_the_experiments(driver, app, monkeypatch):  # noqa: F811
    queries = []
    client = app.model.client  # noqa: F811
    monkeypatch.setattr(
        client,
        "connect_elabftw",
        lambda url, key, **kw: {"connection_id": "h", "endpoint": url, "info": {}},
    )
    monkeypatch.setattr(
        client,
        "list_elabftw_experiments",
        lambda cid, query="", **kw: queries.append(query) or [{"id": 1, "title": "T"}],
    )
    monkeypatch.setattr(client, "list_experiments", lambda: [])
    panel = open_panel(driver, "elabftw", "eLabFTW")
    driver.type_into_name("endpoint", "https://lab.example")
    driver.type_into_name("api_key", "k")
    driver.click_name("connect_remote")
    assert panel.connection_id == "h" and queries == [""]
    driver.type_into_name("query", "tcspc")  # Enter, no button
    assert queries[-1] == "tcspc"


# ── Spectra: search as you type ────────────────────────────────────────


def _names(panel):
    return {r.get("chromophore_name") for r in panel.rows}


def test_the_spectra_search_runs_as_you_type(driver, app, monkeypatch):  # noqa: F811
    monkeypatch.setattr(spectra, "SEARCH_DELAY", 0.0)
    panel = open_panel(driver, "spectra", "Spectra")
    assert {"Donor GUI", "Acceptor GUI"} <= _names(panel)
    driver.type_into_name("search", "Accept", commit=False)  # no Enter
    driver.draw(2)
    assert _names(panel) == {"Acceptor GUI"}


def test_with_auto_off_the_spectra_search_waits_for_enter(driver, app, monkeypatch):  # noqa: F811
    monkeypatch.setattr(spectra, "SEARCH_DELAY", 0.0)
    panel = open_panel(driver, "spectra", "Spectra")
    driver.click_name("auto_search")
    assert panel.auto_search is False
    before = _names(panel)
    driver.type_into_name("search", "Accept", commit=False)
    driver.draw(3)
    assert _names(panel) == before
    driver.enter()
    assert _names(panel) == {"Acceptor GUI"}


def test_the_search_waits_for_the_typing_pause(driver, app):  # noqa: F811
    panel = open_panel(driver, "spectra", "Spectra")
    before = _names(panel)
    panel.search = "Accept"
    panel.search_typed("Accept")
    panel.tick()  # 300 ms have not passed
    assert _names(panel) == before
    panel._search_due = 0.0  # the pause is over
    panel.tick()
    assert _names(panel) == {"Acceptor GUI"}


# ── Spectra: the row menu ──────────────────────────────────────────────


def test_the_spectra_row_menu(driver, app):  # noqa: F811
    copied = []
    app.model.copy = copied.append
    panel = open_panel(driver, "spectra", "Spectra")
    _right_click(driver, _cell(driver, "Acceptor GUI"))
    shown = set(driver.draw(2).strings)
    assert {
        "Open details",
        "Copy checked IDs",
        "Copy selected row",
        "Copy selected cell",
        "Check selected rows",
        "Uncheck selected rows",
        "Check all visible",
        "Uncheck all",
        "Invert visible checks",
        "Select all rows",
        "Clear selection",
    } <= shown
    _pick(driver, "Copy selected cell")
    assert copied[-1] == "Acceptor GUI"
    _right_click(driver, _cell(driver, "Acceptor GUI"))
    _pick(driver, "Open details")
    assert panel.values.chromophore_name == "Acceptor GUI" and panel.traces
    acceptor = panel.selected_id
    _right_click(driver, _cell(driver, "Acceptor GUI"))
    _pick(driver, "Copy selected row")
    assert "Acceptor GUI" in copied[-1] and "\t" in copied[-1]
    _right_click(driver, _cell(driver, "Acceptor GUI"))
    _pick(driver, "Check selected rows")
    assert panel.checked_ids() == [acceptor]
    _right_click(driver, _cell(driver, "Acceptor GUI"))
    _pick(driver, "Copy checked IDs")
    assert copied[-1] == acceptor
    _right_click(driver, _cell(driver, "Acceptor GUI"))
    _pick(driver, "Uncheck selected rows")
    assert panel.checked_ids() == []
    _right_click(driver, _cell(driver, "Acceptor GUI"))
    _pick(driver, "Invert visible checks")
    assert len(panel.checked_ids()) == len(panel.rows)
    _right_click(driver, _cell(driver, "Acceptor GUI"))
    _pick(driver, "Uncheck all")
    assert panel.checked_ids() == []
    _right_click(driver, _cell(driver, "Acceptor GUI"))
    _pick(driver, "Check all visible")
    assert len(panel.checked_ids()) == len(panel.rows)
    control = app.form("spectra").tables["component_rows"].control
    _right_click(driver, _cell(driver, "Acceptor GUI"))
    _pick(driver, "Select all rows")
    assert len(control.selected_indices()) == len(panel.rows)
    assert len(panel.selection) == len(panel.rows)
    _right_click(driver, _cell(driver, "Acceptor GUI"))
    _pick(driver, "Clear selection")
    driver.draw(2)
    assert control.selected_indices() == []


# ── Spectra: Find Duplicates progress and Cancel ───────────────────────


def test_find_duplicates_shows_progress_and_then_the_groups(driver, app, monkeypatch):  # noqa: F811
    seen = []
    real = spectra.find_duplicate_groups

    def watched(probes, progress=None, interrupted=None):
        top = app.model.dialog
        seen.append(isinstance(top, dlg.ProgressDialog))
        groups = real(probes, progress=progress, interrupted=interrupted)
        seen.append(top.fraction)
        return groups

    monkeypatch.setattr(spectra, "find_duplicate_groups", watched)
    open_panel(driver, "spectra", "Spectra")
    driver.click_name("find_duplicates")
    assert seen[0] is True and seen[1] == 1.0  # a progress dialog, moved to the end
    assert isinstance(app.model.dialog, spectra.DuplicatesDialog)  # the progress one closed
    assert not any(isinstance(d, dlg.ProgressDialog) for d in app.model.dialogs)


def test_find_duplicates_cancel_shows_nothing(driver, app, monkeypatch):  # noqa: F811
    def cancelled_halfway(probes, progress=None, interrupted=None):
        progress(50)
        top = app.model.dialog
        assert isinstance(top, dlg.ProgressDialog) and top.percent_text() == "50 %"
        top.cancel()  # the user presses Cancel
        return None if interrupted() else []

    monkeypatch.setattr(spectra, "find_duplicate_groups", cancelled_halfway)
    panel = open_panel(driver, "spectra", "Spectra")
    driver.click_name("find_duplicates")
    assert app.model.dialog is None
    assert panel.message == "Find duplicates cancelled"


def test_the_progress_dialog_draws_and_cancel_is_pressed(driver, app):  # noqa: F811
    progress = app.model.show(dlg.ProgressDialog("Finding Duplicates", "Analyzing probes..."))
    progress.set_percent(40)
    assert driver.drawn("40 %") and driver.drawn("Analyzing probes...")
    driver.click_name("dialog.cancel")
    assert progress.cancelled and app.model.dialog is None


# ── Provenance: a click on an edge ─────────────────────────────────────


def test_an_edge_or_a_node_picked_in_the_graph_shows_its_record(driver, app):  # noqa: F811
    panel = open_panel(driver, "provenance", "Provenance Graph")
    driver.type_into_name("seed_id", "prod_gui")
    driver.click_name("load_full")
    driver.draw(2)
    graph = app.graph
    assert graph.document.edges
    edge = graph.document.edges[0]
    graph.on_select("edge", graph._edge_payload(edge))
    record = json.loads(panel.details)
    assert record.get("relationship_type") and "proc_gui" in panel.details
    assert panel.selected_edge
    driver.draw(2)
    table = app.form("provenance").tables["edge_rows"].control
    assert table.selected_key == panel.selected_edge  # the table shows the picked edge
    node = next(n for n in graph.document.nodes if n.id == "artifact:raw_gui")
    graph.on_select("node", graph._node_payload(node))
    assert "raw_gui" in panel.details and "relationship_type" not in panel.details


# ── Processed Products: Open in ndX ────────────────────────────────────


def test_open_in_ndx_hands_the_product_over_and_records_back(driver, app):  # noqa: F811
    opened = []

    class FakeNdx:
        burst_ids_recorder = None

    ndx = FakeNdx()
    app.model.ndx_opener = lambda path: opened.append(str(path)) or ndx
    panel = open_panel(driver, "processed_product", "Processed Products")
    driver.click(_cell(driver, "prod_gui"))
    driver.click_name("open_in_ndx")
    assert opened and opened[0].endswith("prod_gui.json")
    assert callable(ndx.burst_ids_recorder)  # Save > Burst IDs records against prod_gui
    assert panel.message == "Opened prod_gui.json in ndX"


def test_open_in_ndx_says_why_when_the_file_is_gone(driver, app, tmp_path):  # noqa: F811
    app.model.ndx_opener = lambda path: (_ for _ in ()).throw(AssertionError("not opened"))
    panel = open_panel(driver, "processed_product", "Processed Products")
    driver.click(_cell(driver, "prod_gui"))
    Path(panel.selected_record()["location"]).unlink()
    driver.click_name("open_in_ndx")
    assert app.model.dialog.title == "File Not Found"


# ── entity rows: the UUID on hover ─────────────────────────────────────


def test_an_entity_row_shows_its_uuid_on_hover(driver, app):  # noqa: F811
    from chisurf.plugins.core.mmfdb_admin.gui.app import load_specs

    shell, _panels, _actions = load_specs()
    table = shell["entity"]["sections"][1]["options"]
    assert table["tooltip_key"] == "_tip"
    panel = open_panel(driver, "branch", "Branches")
    row = next(r for r in panel.rows if r["_id"] == "branch_gui")
    assert row["_tip"] == "UUID: branch_gui"
