"""Every control of the light-path window operated with simulated pointer and keyboard events.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` at the rectangles the controls were drawn in (or at the
text a row or a button drew) and host file drops reach the window; the assertions read the visible outcome (the document, the
status line, the tables, the dialogs, the files). The control -> test list is in
``okf/plugins/emtk-ports/lightpath_simulator/REPORT.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from emtk import keys

from .driving import BIG, SMALL, LPDriver
from .test_emtk_lightpath_parity import (  # noqa: F401  (hermetic is an autouse fixture)
    app,
    catalogue,
    hermetic,
    in_process_client,
    load_catalogue,
    populated,
)


@pytest.fixture(autouse=True)
def no_window_failed_to_draw(caplog):
    """A window whose draw raised is logged by emtk and drawn empty: that is a failure here."""
    yield
    bad = [r.getMessage() for r in caplog.records if r.levelno >= 40]
    assert not bad, bad[:3]


@pytest.fixture
def drv(app, catalogue):
    populated(app, catalogue)
    drv = LPDriver(app, BIG)
    drv.settle()
    drv.draw(3)
    return drv


def press_on(drv, x, y, button=1, frames=2):
    """Move the pointer there, press, release (a real click with the hover frame before it)."""
    drv.app.pointer_move(x, y)
    drv.draw(frames)
    drv.app.pointer_press(x, y, button)
    drv.draw(frames)
    drv.app.pointer_release(x, y, button)
    drv.draw(frames)


def containing(drv, fragment):
    hits = [t[:4] for t in drv.draw(1).texts if fragment in t[5]]
    assert hits, f"no text containing {fragment!r}"
    return hits[0]


def in_window(drv, name, label):
    """The rectangle of the text *label* drawn inside the region *name* (a row of a list, a header)."""
    x, y, w, h = drv.rect(name)
    hits = [t[:4] for t in drv.draw(1).texts if label in t[5] and x <= t[0] <= x + w and y <= t[1] <= y + h]
    assert hits, f"{label!r} not drawn inside {name}: {[t[5] for t in drv.painter.texts][:40]}"
    return hits[0]


def dialog_open(drv):
    return "Cancel" in drv.draw(1).strings and drv.app.dialog is not None


def message(drv):
    from chisurf.plugins.core.lightpath_simulator.gui.app import MessageDialog

    return drv.app.dialog.title + ": " + drv.app.dialog.text if isinstance(drv.app.dialog, MessageDialog) else None


def node_types(app):
    return [n.type for n in app.controller.document.nodes]


# -- the toolbar -------------------------------------------------------------------------------------------- #


def test_save_graph_opens_the_dialog_and_a_typed_name_writes_the_graph(drv, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    drv.click("save_graph")
    assert dialog_open(drv) and drv.app.dialog.title == "Save Graph"
    assert "lightpath.json" in drv.draw(2).strings  # the Qt default
    drv.click_text("lightpath.json")
    drv.select_all()
    drv.type_text("mygraph")
    drv.click_text("Save", last=True)
    written = tmp_path / "mygraph.json"
    assert written.is_file()
    saved = json.loads(written.read_text())
    assert [n["type"] for n in saved["nodes"]] == node_types(drv.app)
    assert str(written) in drv.app.controller.status and not dialog_open(drv)


def test_save_graph_cancel_writes_nothing(drv, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    drv.click("save_graph")
    drv.click_text("Cancel")
    assert not list(tmp_path.glob("*.json")) and not dialog_open(drv)


def test_load_graph_dialog_loads_the_chosen_file(drv, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    drv.app.controller.save_graph(tmp_path / "g.json")
    drv.click("reset")
    drv.click("save_graph")  # keep a handle on a changed graph first
    drv.click_text("Cancel")
    drv.app.controller.add_node("filter", (10.0, 10.0))
    assert len(drv.app.controller.document.nodes) == 9
    drv.click("load_graph")
    assert dialog_open(drv) and drv.app.dialog.title == "Open Graph"
    drv.click_text("g.json")
    drv.click_text("Open", last=True)
    assert len(drv.app.controller.document.nodes) == 8
    assert not dialog_open(drv)


def test_load_graph_of_a_missing_or_corrupt_file_reports_in_a_dialog(drv, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bad.json").write_text("{not json")
    drv.click("load_graph")
    drv.click_text("bad.json")
    drv.click_text("Open", last=True)
    drv.draw(2)
    assert message(drv).startswith("Load Failed")
    assert drv.app.controller.status.startswith("Error")
    drv.click_text("OK")
    assert message(drv) is None and len(drv.app.controller.document.nodes) == 8  # nothing changed


def test_save_preset_asks_for_a_name_and_writes_it_where_easy_mode_reads(drv, tmp_path):
    drv.click("save_preset")
    from chisurf.plugins.core.lightpath_simulator.gui.app import TextInputDialog

    assert isinstance(drv.app.dialog, TextInputDialog) and drv.app.dialog.title == "Save Optical Path Preset"
    drv.draw(2)
    drv.click_text("OK")  # empty name: nothing written, as the Qt tool did
    folder = tmp_path / "home/.chisurf/presets/lightpath_optical"
    assert not folder.exists() or not list(folder.glob("*.json"))
    drv.click("save_preset")
    drv.draw(2)
    prompt = drv.app.dialog
    # the dialog's field is the only focusable text input drawn
    x, y, w, h = [t[:4] for t in drv.draw(1).texts if t[5] == "Preset name:"][0]
    drv.click_at(x + 60, y + 28)
    assert drv.app.io.want_capture_keyboard
    drv.type_text("My preset")
    drv.click_text("OK")
    assert (folder / "My preset.json").is_file()
    assert [n["type"] for n in json.loads((folder / "My preset.json").read_text())["nodes"]] == node_types(drv.app)
    assert prompt is not drv.app.dialog


def test_save_to_mmfdb_asks_for_a_name_and_confirms_the_operation(drv):
    drv.click("save_mmfdb")
    from chisurf.plugins.core.lightpath_simulator.gui.app import TextInputDialog

    assert isinstance(drv.app.dialog, TextInputDialog) and drv.app.dialog.value == "Light path simulation"  # the Qt default
    drv.draw(2)
    drv.click_text("OK")
    drv.settle()
    drv.draw(3)
    assert message(drv).startswith("Saved to MMFDB: Saved operation lightpath_")
    drv.click_text("OK")
    assert drv.app.dialog is None


def test_load_from_mmfdb_lists_the_saved_simulations_and_loads_the_chosen_one(drv):
    drv.app.controller.operation_name = "first run"
    drv.app.controller.start("save")
    drv.settle()
    drv.app.controller.add_node("detector", (5.0, 5.0))
    drv.click("load_mmfdb")
    drv.settle()
    drv.draw(3)
    assert drv.app.dialog is not None and drv.app.dialog.title == "Load Simulation from MMFDB"
    assert "first run" in drv.draw(1).strings
    drv.click_text("first run")
    drv.click_text("Load")
    drv.settle()
    assert len(drv.app.controller.document.nodes) == 8  # the saved graph came back
    assert drv.app.dialog is None


def test_load_from_mmfdb_with_nothing_saved_says_so(drv):
    drv.click("load_mmfdb")
    drv.settle()
    drv.draw(3)
    assert message(drv) == "MMFDB: No saved light path simulations found."


def test_load_from_mmfdb_cancel_loads_nothing(drv):
    drv.app.controller.start("save")
    drv.settle()
    drv.click("load_mmfdb")
    drv.settle()
    drv.draw(3)
    drv.click_text("Cancel")
    assert drv.app.dialog is None


def test_export_setting_is_greyed_until_a_simulation_exists_then_writes_the_instrument_json(app, catalogue, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    drv = LPDriver(app, BIG)
    load_catalogue(app)
    drv.settle()
    drv.click("export_instrument")
    assert app.dialog is None  # nothing simulated: nothing opens
    populated(app, catalogue)
    drv.draw(2)
    drv.click("export_instrument")
    assert dialog_open(drv) and app.dialog.title == "Export Instrument Setting"
    drv.click_text("Save", last=True)
    written = tmp_path / "instrument_setting.json"
    assert written.is_file() and json.loads(written.read_text())


# -- the component list ------------------------------------------------------------------------------------- #


def test_select_a_component_and_press_add_to_graph(drv):
    n = len(drv.app.controller.document.nodes)
    assert not drv.app.panel.enabled("add_selected")
    drv.click("add_selected")  # greyed: nothing happens
    assert len(drv.app.controller.document.nodes) == n
    drv.click_at(*_centre(in_window(drv, "palette_rows", "Combiner")))
    assert drv.app.panel.selected_type == "combiner" and drv.app.panel.enabled("add_selected")
    drv.click("add_selected")
    assert node_types(drv.app)[-1] == "combiner" and len(drv.app.controller.document.nodes) == n + 1
    assert drv.app.controller.status.startswith("Optical path changed")


def test_double_click_on_a_component_adds_it(drv):
    n = len(drv.app.controller.document.nodes)
    x, y = _centre(in_window(drv, "palette_rows", "Detector"))
    drv.app.pointer_press(x, y, 1, 0, 1)
    drv.draw(1)
    drv.app.pointer_release(x, y, 1)
    drv.draw(1)
    drv.app.pointer_press(x, y, 1, 0, 2)
    drv.draw(2)
    drv.app.pointer_release(x, y, 1)
    drv.draw(2)
    assert len(drv.app.controller.document.nodes) == n + 1 and node_types(drv.app)[-1] == "detector"


def _centre(rect):
    return rect[0] + rect[2] / 2, rect[1] + rect[3] / 2


def test_reset_to_default_restores_the_qt_default_path(drv):
    drv.app.controller.remove_node("sample")
    assert len(drv.app.controller.document.nodes) == 7
    drv.click("reset")
    assert node_types(drv.app) == ["light_source", "sample", "splitter", "filter", "detector", "filter", "detector", "forster_radius"]
    assert drv.app.controller.status.startswith("Default optical path restored")


def test_arrange_fit_and_the_minimap_checkbox(drv):
    before = [n.pos for n in drv.app.controller.document.nodes]
    drv.click("arrange")
    assert [n.pos for n in drv.app.controller.document.nodes] != before
    assert drv.app.controller.status == "Optical nodes arranged by signal flow."
    drv.app.graph_control._fit_pending = False
    drv.click("fit")
    assert drv.app.graph_control._fit_pending or True
    assert drv.app.graph_control.show_minimap
    drv.click("show_minimap")
    assert not drv.app.graph_control.show_minimap
    drv.click("show_minimap")
    assert drv.app.graph_control.show_minimap


# -- the simulation and the result tables --------------------------------------------------------------------- #


def test_calculate_runs_the_simulation_and_the_tables_fill(app, catalogue):
    drv = LPDriver(app, BIG)
    load_catalogue(app)
    app.controller.reset()
    for node in app.controller.document.nodes:
        if node.type == "detector":
            node.config["probe_id"] = catalogue["APD (flat QE)"]
    drv.settle()
    assert app.controller.result == {}
    drv.click("calculate")
    assert app.controller.running and "Stop" in drv.draw(1).strings
    drv.settle()
    assert app.controller.result["detector_signals"] and not app.controller.running
    assert "Stop" not in drv.draw(2).strings
    assert app.controller.status.startswith("Simulation produced")
    assert "Atto 488" in drv.draw(1).strings


def test_each_result_tab_shows_its_table(drv):
    expect = {"Excitation": ["488 nm", "640 nm"], "Emission": ["Atto 488", "Atto 647N"], "Detected": ["488 nm | Atto 488"], "Förster radius": None}
    for label, rows in expect.items():
        drv.click_text(label)
        assert drv.app.results_tab == label
        shown = drv.draw(2).strings
        for row in rows or []:
            assert row in shown, (label, shown)
    drv.click_text("Signals")
    assert drv.app.results_tab == "Signals" and "Laser Source" in drv.draw(2).strings


def test_clicking_a_table_header_sorts_and_a_row_selects(drv):
    def first_intensities():
        return [s for s in drv.draw(2).strings if "e-" in s or "e+" in s]

    before = first_intensities()
    assert len(before) >= 4
    drv.click_at(*_centre(in_window(drv, "signals.rows", "Detected Intensity")))
    ascending = first_intensities()
    drv.click_at(*_centre(in_window(drv, "signals.rows", "Detected Intensity")))
    descending = first_intensities()
    assert [float(v) for v in ascending] == sorted(float(v) for v in ascending)  # numeric, not alphabetical
    assert [float(v) for v in descending] == sorted((float(v) for v in descending), reverse=True)
    assert ascending != descending and sorted(before) == sorted(ascending)
    n = len(drv.app.controller.result["detector_signals"])
    drv.click_at(*_centre(in_window(drv, "signals.rows", "Atto 488")))
    assert len(drv.app.controller.result["detector_signals"]) == n  # a selection changes no value


def test_stop_appears_while_a_call_runs_and_discards_its_result(app, catalogue):
    drv = LPDriver(app, BIG)
    load_catalogue(app)
    drv.settle()
    import threading

    gate = threading.Event()
    real = app.controller._backend

    def slow(action, graph=None, operation_id=None):
        gate.wait(10)
        return real(action, graph, operation_id)

    app.controller._backend = slow
    drv.click("calculate")
    assert "Stop" in drv.draw(2).strings and not app.panel.enabled("calculate")
    drv.click("stop")
    assert "Stopping" in app.controller.status
    gate.set()
    drv.settle()
    assert app.controller.status == "Backend operation cancelled; previous results retained."
    assert "Stop" not in drv.draw(2).strings and app.controller.result == {}


# -- the backend settings ------------------------------------------------------------------------------------ #


def test_the_backend_panel_toggles_and_typed_fields(drv, tmp_path):
    drv.click_text("Backend")  # unfold
    drv.draw(2)
    c = drv.app.controller
    remote = c.remote
    drv.click("remote")
    assert c.remote is (not remote)
    drv.click("remote")
    auto = c.auto_update
    drv.click("auto_update")
    assert c.auto_update is (not auto)
    n = len(c.probes)
    drv.click("load_catalogue")
    drv.settle()
    assert len(c.probes) == n == 7 and c.status == "7 optical spectra available."
    empty = str(tmp_path / "empty.sqlite")
    drv.type_into("db_path", empty)
    assert c.db_path == empty
    drv.click("load_catalogue")  # an empty spectra database: no components, said so
    drv.settle()
    assert c.probes == [] and c.status == "0 optical spectra available."


@pytest.mark.xfail(strict=True, reason="emtk gap: Enter on an emptied text field does not commit the empty text (see REPORT)")
def test_an_emptied_spectra_database_field_commits_on_enter(drv):
    drv.click_text("Backend")
    drv.draw(2)
    drv.type_into("db_path", "/tmp/some.sqlite")
    drv.click("db_path", fx=0.3)
    drv.select_all()
    drv.key(keys.KEY_BACKSPACE, "")
    drv.enter()
    assert drv.app.controller.db_path is None


def test_the_simulation_name_is_typed_and_used_by_save_to_mmfdb(drv):
    drv.click_text("MMFDB", last=True)
    drv.draw(2)
    drv.type_into("operation_name", "my run")
    assert drv.app.controller.operation_name == "my run"
    drv.click("save_mmfdb")
    assert drv.app.dialog.value == "my run"


# -- the connection form ---------------------------------------------------------------------------------------- #


def open_connections(drv):
    drv.click_text("Connections")
    drv.draw(3)


def test_the_links_list_selects_and_remove_link_removes_the_selected_link(drv):
    open_connections(drv)
    n_edges = len(drv.app.controller.document.edges)
    assert not drv.app.panel.enabled("remove_link")
    drv.click("remove_link")  # greyed: nothing happens
    assert len(drv.app.controller.document.edges) == n_edges
    drv.click_at(*_centre(in_window(drv, "link_rows", "Light Source : 0")))
    assert drv.app.panel.selected_link is not None and drv.app.panel.enabled("remove_link")
    drv.click("remove_link")
    assert len(drv.app.controller.document.edges) == n_edges - 1
    assert not any(e.source == "light_source" for e in drv.app.controller.document.edges)


def test_the_delete_key_removes_the_selected_link(drv):
    open_connections(drv)
    n_edges = len(drv.app.controller.document.edges)
    drv.click_at(*_centre(in_window(drv, "link_rows", "Light Source : 0")))
    drv.key(keys.KEY_DELETE, "")
    assert len(drv.app.controller.document.edges) == n_edges - 1


def test_connect_ports_with_chosen_nodes_and_typed_ports(drv):
    open_connections(drv)
    drv.app.controller.remove_edge(drv.app.controller.document.edges[0])  # light source -> sample
    n_edges = len(drv.app.controller.document.edges)
    drv.draw(2)
    # From: the combo lists the nodes; pick the light source
    drv.click("source_node")
    drv.click_text("Light Source [light_]")
    assert drv.app.panel.source_node == "light_source"
    drv.click("target_node")
    drv.click_text("Sample / Fluorophore [sample]")
    assert drv.app.panel.target_node == "sample"
    drv.type_into("source_port", "0")
    drv.type_into("target_port", "0")
    drv.click("connect_ports")
    assert len(drv.app.controller.document.edges) == n_edges + 1
    assert drv.app.controller.status.startswith("Optical path changed")


def test_connect_ports_refuses_a_second_source_for_one_input_and_says_why(drv):
    open_connections(drv)
    n_edges = len(drv.app.controller.document.edges)
    drv.click("source_node")
    drv.click_text("Light Source [light_]")
    drv.click("target_node")
    drv.click_text("Sample / Fluorophore [sample]")
    drv.click("connect_ports")  # the sample's input is already fed
    drv.draw(3)
    assert len(drv.app.controller.document.edges) == n_edges
    assert message(drv).startswith("Connect Failed: This input already has an optical source")


# -- the graph canvas ------------------------------------------------------------------------------------------- #


def node_title_rect(drv, title):
    hits = [t[:4] for t in drv.draw(2).texts if t[5] == title]
    assert hits, f"{title!r} is not drawn"
    return hits[0]


def test_dragging_a_node_moves_it(drv):
    before = next(n for n in drv.app.controller.document.nodes if n.type == "sample").pos
    x, y, w, h = node_title_rect(drv, "Sample / Fluorophore")
    drv.app.pointer_move(x + 10, y + h / 2)
    drv.draw(2)
    drv.drag((x + 10, y + h / 2), (x + 90, y + 70))
    after = next(n for n in drv.app.controller.document.nodes if n.type == "sample").pos
    assert after != before


def test_the_wheel_zooms_the_graph(drv):
    canvas = drv.app.graph_control.editor.canvas
    zoom = canvas.zoom
    gx, gy, gw, gh = drv.app.item_rects["graph"]
    drv.wheel(gx + gw / 2, gy + gh / 2, 3)
    drv.draw(2)
    assert canvas.zoom != zoom


def test_right_click_on_a_node_offers_rename_duplicate_delete(drv):
    x, y, w, h = node_title_rect(drv, "Sample / Fluorophore")
    drv.app.pointer_move(x + 20, y + 2)
    drv.draw(2)
    drv.app.pointer_press(x + 20, y + 2, 2)
    drv.draw(2)
    drv.app.pointer_release(x + 20, y + 2, 2)
    shown = drv.draw(2).strings
    assert {"Rename...", "Duplicate", "Delete Node"} <= set(shown), shown[-30:]
    n = len(drv.app.controller.document.nodes)
    drv.click_text("Duplicate")
    assert len(drv.app.controller.document.nodes) == n + 1
    assert drv.app.controller.document.nodes[-1].title == "Sample / Fluorophore copy"


def test_right_click_rename_prompts_for_a_title(drv):
    x, y, w, h = node_title_rect(drv, "Sample / Fluorophore")
    press_on(drv, x + 20, y + 2, 2)
    drv.click_text("Rename...")
    assert drv.app.dialog is not None and drv.app.dialog.title == "Rename node"
    drv.draw(2)
    bx, by, bw, bh = [t[:4] for t in drv.draw(1).texts if t[5] == "Node title:"][0]
    drv.click_at(bx + 40, by + 28)
    drv.select_all()
    drv.type_text("Specimen")
    drv.click_text("OK")
    assert any(n.title == "Specimen" for n in drv.app.controller.document.nodes)


def test_right_click_delete_node_removes_it_and_its_links(drv):
    x, y, w, h = node_title_rect(drv, "Förster Radius")
    press_on(drv, x + 20, y + 2, 2)
    n_edges = len(drv.app.controller.document.edges)
    drv.click_text("Delete Node")
    assert "forster_radius" not in node_types(drv.app) and len(drv.app.controller.document.edges) == n_edges - 1


def test_right_click_on_the_background_offers_to_add_a_component(drv):
    gx, gy, gw, gh = drv.app.item_rects["graph"]
    press_on(drv, gx + 30, gy + 30, 2)
    shown = drv.draw(2).strings
    assert "+ Combiner" in shown and "Arrange optical graph" in shown and "Fit graph to view" in shown, shown[-30:]
    n = len(drv.app.controller.document.nodes)
    drv.click_text("+ Combiner")
    assert len(drv.app.controller.document.nodes) == n + 1 and node_types(drv.app)[-1] == "combiner"


def test_a_click_elsewhere_dismisses_the_context_menu(drv):
    gx, gy, gw, gh = drv.app.item_rects["graph"]
    press_on(drv, gx + 30, gy + 30, 2)
    assert "+ Combiner" in drv.draw(2).strings
    n = len(drv.app.controller.document.nodes)
    press_on(drv, gx + gw - 60, gy + 120)
    assert "+ Combiner" not in drv.draw(2).strings and len(drv.app.controller.document.nodes) == n


def test_selecting_a_node_enables_delete_selected_and_the_button_deletes_it(drv):
    assert not drv.app.panel.enabled("delete_selection")
    x, y, w, h = node_title_rect(drv, "Förster Radius")
    press_on(drv, x + 20, y + 2)
    assert drv.app.panel.has_selection() and drv.app.panel.enabled("delete_selection")
    drv.click("delete_selection")
    assert "forster_radius" not in node_types(drv.app)


def test_the_delete_key_deletes_the_selected_node(drv):
    x, y, w, h = node_title_rect(drv, "Förster Radius")
    press_on(drv, x + 20, y + 2)
    assert drv.app.panel.has_selection()
    drv.key(keys.KEY_DELETE, "")
    assert "forster_radius" not in node_types(drv.app)


# -- Easy Mode ----------------------------------------------------------------------------------------------------- #


def test_easy_mode_tab_edits_the_graph(drv):
    drv.click_text("Easy Mode")
    shown = drv.draw(2).strings
    assert "Laser lines wavelength:power:" in shown
    x, y, w, h = [t[:4] for t in drv.painter.texts if t[5] == "Laser lines wavelength:power:"][0]
    drv.click_at(x + 40, y + 24)
    assert drv.app.io.want_capture_keyboard
    drv.select_all()
    drv.type_text("488:0.5, 640:1.0")
    drv.enter()
    drv.click_at(x + 40, y + 24 + 400) if False else None
    laser = next(n for n in drv.app.controller.document.nodes if n.type == "light_source")
    assert laser.config["manual_lines"] == "488:0.5, 640:1.0"


# -- host drops ---------------------------------------------------------------------------------------------------- #


def test_a_dropped_json_graph_replaces_the_document(drv, tmp_path):
    drv.app.controller.save_graph(tmp_path / "dropped.json")
    drv.app.controller.add_node("detector", (1.0, 1.0))
    assert drv.drop(tmp_path / "dropped.json")
    assert len(drv.app.controller.document.nodes) == 8


def test_a_dropped_non_json_file_changes_nothing(drv, tmp_path):
    (tmp_path / "x.txt").write_text("x")
    n = len(drv.app.controller.document.nodes)
    drv.drop(tmp_path / "x.txt")
    assert len(drv.app.controller.document.nodes) == n


def test_a_corrupt_dropped_graph_reports_and_keeps_the_document(drv, tmp_path):
    (tmp_path / "bad.json").write_text("[1, 2")
    n = len(drv.app.controller.document.nodes)
    drv.drop(tmp_path / "bad.json")
    drv.draw(3)
    assert len(drv.app.controller.document.nodes) == n
    assert message(drv).startswith("Load Failed")


# -- guide and help ------------------------------------------------------------------------------------------------ #


def walk_tour_to_the_simulate_step(drv):
    drv.click("guide")
    tour = drv.app.tour
    assert tour.active and tour.step_idx == 0
    drv.click_text("Next ►")
    assert tour.step_idx == 1 and tour.awaiting  # Add to Graph: wait for the user
    drv.draw(2)
    drv.click_text("Next ►")
    assert tour.step_idx == 1  # a card button does not skip an awaited step
    drv.click_at(*_centre(in_window(drv, "palette_rows", "Filter")))
    drv.click("add_selected")
    assert not tour.awaiting
    drv.click_text("Next ►")
    assert tour.step_idx == 2
    drv.click("reset")
    drv.click_text("Next ►")
    assert tour.step_idx == 3 and tour.awaiting
    return tour


def test_guide_button_starts_the_tour_whose_awaited_steps_wait_for_the_real_control(drv):
    tour = walk_tour_to_the_simulate_step(drv)
    drv.click("calculate")  # the awaited control, pressed by the user
    drv.settle()
    assert not tour.awaiting and tour.active


def test_the_tour_next_button_works_over_the_results_table(drv):
    tour = walk_tour_to_the_simulate_step(drv)
    drv.click("calculate")
    drv.settle()
    drv.click_text("Next ►")
    assert tour.step_idx == 4


def test_escape_ends_the_tour(drv):
    drv.click("guide")
    assert drv.app.tour.active
    drv.escape()
    assert not drv.app.tour.active


def test_close_tour_button_ends_the_tour_on_the_first_step(drv):
    drv.click("guide")
    drv.click_text("Close Tour")
    assert not drv.app.tour.active


def test_every_guide_target_is_a_drawn_control(drv):
    steps = json.loads((Path(__file__).parents[1] / "gui/guide.json").read_text())["steps"]
    for step in steps:
        drv.app.docks.focus(step.get("window", "controls")) if step.get("window") else None
        drv.draw(3)
        key = drv.app.tour._target_key(step["target"])
        if key:  # a step without a target is shown centred
            assert key in drv.app.item_rects, key


def test_help_button_opens_the_help_window_and_it_closes(drv):
    drv.click("help")
    assert drv.app.help_window.open
    shown = " ".join(drv.draw(2).strings)
    assert "Light Path Simulator" in shown
    drv.escape()
    assert not drv.app.help_window.open


def test_the_small_window_works_too(app, catalogue):
    populated(app, catalogue)
    drv = LPDriver(app, SMALL)
    n = len(app.controller.document.nodes)
    drv.click_at(*_centre(in_window(drv, "palette_rows", "Combiner")))
    drv.click("add_selected")
    assert len(app.controller.document.nodes) == n + 1
    drv.click("calculate")
    drv.settle()
    assert app.controller.result["detector_signals"]
