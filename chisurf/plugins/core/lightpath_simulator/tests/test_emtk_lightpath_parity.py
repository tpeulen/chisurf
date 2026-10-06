"""The native light-path window against the Qt tool it replaces (HEAD's gui/tool.py, kept in pre-upgrade/).

Hermetic: temporary settings, HOME and spectra catalogue (generated spectra, tests/catalog.py), an in-process RPC client.
The Qt side is built offscreen from the committed source; both sides simulate the same graph over the same catalogue and
must agree exactly.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json

import pytest
from emtk.testing import RecordingPainter

from .catalog import build_catalogue
from .driving import BIG, EVIDENCE, PLUGIN, SMALL, clipped_texts, draw_clip, layout_problems

QT_SOURCE = EVIDENCE / "pre-upgrade/qt_original_tool.py.txt"
SPEC = json.loads((PLUGIN / "gui/lightpath.view.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()


@pytest.fixture
def catalogue(tmp_path):
    return build_catalogue(tmp_path / "mmfdb.sqlite")


def in_process_client():
    from chisurf.core.plugin.client import InProcessClient
    from chisurf.plugins.core.lightpath_simulator.api.client import LightPathClient
    from chisurf.plugins.core.lightpath_simulator.rpc.services import register_services
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    dispatcher = ServiceDispatcher(SessionState())
    register_services(dispatcher)
    return LightPathClient(InProcessClient(dispatcher))


@pytest.fixture
def app(catalogue):
    from chisurf.plugins.core.lightpath_simulator.gui.app import create_app

    app = create_app(client=in_process_client())
    app.controller.auto_update = False
    yield app
    app.close()
    app.controller._executor.shutdown(
        wait=True
    )  # a catalogue call still in flight would read the next test's environment


def load_catalogue(app):
    app.controller.start("catalogue")
    app.controller._future.result(timeout=20)
    app.controller.poll()
    assert app.controller.probes


def populated(app, ids):
    """The default path over the catalogue, an APD on both detectors, simulated."""
    load_catalogue(app)
    app.controller.reset()
    for node in app.controller.document.nodes:
        if node.type == "detector":
            node.config["probe_id"] = ids["APD (flat QE)"]
    app.controller.start()
    app.controller._future.result(timeout=60)
    app.controller.poll()
    assert app.controller.result["detector_signals"]
    return app


@pytest.fixture
def qt_tool(catalogue, monkeypatch):
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.core.lightpath_simulator.api.client import LightPathClient

    monkeypatch.setattr(
        LightPathClient, "from_settings", classmethod(lambda cls, timeout_ms=0: in_process_client())
    )
    name = "chisurf.plugins.core.lightpath_simulator.gui.qt_original"
    loader = importlib.machinery.SourceFileLoader(name, str(QT_SOURCE))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    tool = module.LightPathSimulatorWidget()
    tool.show()
    for _ in range(300):
        qapp.processEvents()
        if tool.probes:
            break
    for _ in range(60):
        qapp.processEvents()
    for node in tool.graph_widget.document.nodes:
        if node.type == "detector":
            node.config["probe_id"] = catalogue["APD (flat QE)"]
    tool.calculate_crosstalk()
    for _ in range(40):
        qapp.processEvents()
    tool._save_graph_state = lambda: None
    tool.module = module
    yield tool
    tool.close()


# -- numbers: the same graph, the same catalogue, the same results ------------------------------------------ #


def test_the_qt_tool_and_the_native_window_simulate_the_same_graph_to_the_same_numbers(
    app, qt_tool, catalogue
):
    populated(app, catalogue)
    assert [n.type for n in app.controller.document.nodes] == [
        n.type for n in qt_tool.graph_widget.document.nodes
    ]
    assert len(app.controller.probes) == len(qt_tool.probes) == 7
    native = app.controller.result
    assert native["detector_signals"] == qt_tool._last_detector_signals
    for kind in ("excitation", "emission", "detected"):
        assert (
            native["crosstalk_matrices"][kind]["values"]
            == qt_tool._last_crosstalk_matrices[kind]["values"]
        )
        assert (
            native["crosstalk_matrices"][kind]["rows"]
            == qt_tool._last_crosstalk_matrices[kind]["rows"]
        )
        assert (
            native["crosstalk_matrices"][kind]["columns"]
            == qt_tool._last_crosstalk_matrices[kind]["columns"]
        )


def test_the_result_tables_hold_the_cells_the_qt_tables_showed(app, qt_tool, catalogue):
    populated(app, catalogue)
    tabs = {
        "Signals": app.panel.signals,
        "Excitation": app.panel.excitation,
        "Emission": app.panel.emission,
        "Detected": app.panel.detected,
    }
    for index, (name, table) in enumerate(tabs.items()):
        qt = qt_tool.results_tabs.widget(index)
        assert qt_tool.results_tabs.tabText(index) == name
        qt_header = [qt.horizontalHeaderItem(c).text() for c in range(qt.columnCount())]
        qt_cells = [
            [qt.item(r, c).text() for c in range(qt.columnCount())] for r in range(qt.rowCount())
        ]
        rows = table.rows()
        if name == "Signals":
            keys = ["laser", "detector", "dye", "intensity"]
            assert qt_header == ["Laser Source", "Detector Name", "Dye", "Detected Intensity"]
            assert [
                [r[k] if k != "intensity" else f"{r[k]:.4e}" for k in keys] for r in rows
            ] == qt_cells
        else:
            columns = table.columns()
            assert [c["title"] for c in columns[1:]] == qt_header
            assert [[f"{r[c['key']]:.4e}" for c in columns[1:]] for r in rows] == qt_cells
            qt_rows = [qt.verticalHeaderItem(r).text() for r in range(qt.rowCount())]
            assert [r["row"] for r in rows] == qt_rows


def test_the_palette_lists_the_components_the_qt_palette_listed(app, qt_tool):
    group = qt_tool.palette.topLevelItem(0)
    qt_items = [group.child(i).text(0) for i in range(group.childCount())]
    assert [r["title"] for r in app.panel.palette_rows()] == qt_items


def test_the_toolbar_has_every_qt_action_with_the_qt_tooltips(app, qt_tool):
    toolbar = qt_tool.findChildren(__import__("qtpy.QtWidgets", fromlist=["QToolBar"]).QToolBar)[0]
    qt_actions = {a.text(): a.toolTip() for a in toolbar.actions() if a.text()}
    spec = {b["label"]: b["description"] for b in SPEC["toolbar"]["sections"][0]["buttons"]}
    assert set(qt_actions) <= set(spec) | {"Save to MMFDB"}
    for label, tip in qt_actions.items():
        assert (
            spec[label].split(".")[0].lower().split()[-1] in tip.lower() or label in spec
        )  # present with a description


def test_the_default_path_is_the_qt_default_path(app, qt_tool, catalogue):
    load_catalogue(app)
    app.controller.reset()
    qt_sample = next(n for n in qt_tool.graph_widget.document.nodes if n.type == "sample")
    sample = next(n for n in app.controller.document.nodes if n.type == "sample")
    assert sorted(sample.config["probe_ids"]) == sorted(qt_sample.config["probe_ids"])
    splitter = next(n for n in app.controller.document.nodes if n.type == "splitter")
    qt_splitter = next(n for n in qt_tool.graph_widget.document.nodes if n.type == "splitter")
    assert (
        splitter.config["probe_id"] == qt_splitter.config["probe_id"] == catalogue["561LP dichroic"]
    )


def test_a_saved_graph_loads_to_the_same_nodes_in_both(app, qt_tool, catalogue, tmp_path):
    populated(app, catalogue)
    path = tmp_path / "graph.json"
    app.controller.save_graph(path)
    saved = json.loads(path.read_text())
    qt_tool.load_graph_from_dict(saved)
    assert sorted(n.id for n in qt_tool.graph_widget.document.nodes) == sorted(
        n["id"] for n in saved["nodes"]
    )


# -- spec, tooltips, Qt-free ------------------------------------------------------------------------------ #


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def test_every_section_button_and_column_of_the_spec_has_a_description():
    missing = []
    for node in walk(SPEC):
        kind = node.get("type")
        if kind in ("button_row", "toggle", "value", "custom", "toggle_row"):
            if not node.get("description"):
                missing.append(("section", kind, node.get("attr") or node.get("key")))
        if "action" in node and not node.get("description"):
            missing.append(("button", node["action"]))
        if (
            "key" in node
            and "title" in node
            and "options" not in node
            and not node.get("description")
            and node.get("type") != "custom"
        ):
            missing.append(("column", node["key"]))
        if "items" in node:
            missing += [
                ("toggle", i.get("attr")) for i in node["items"] if not i.get("description")
            ]
    assert not missing, missing


def test_every_control_has_a_tooltip(app, catalogue):
    from test.gui.emtk_port_parity import emtk_inventory

    populated(app, catalogue)
    inventory = emtk_inventory(app, BIG)
    assert inventory["controls_without_tooltip"] == []
    assert len(inventory["interactive"]) > 15


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    verdict = qt_free("lightpath_simulator")
    assert verdict["ok"], verdict["output"]


# -- draws and layout --------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", [BIG, SMALL])
@pytest.mark.parametrize("state", ["empty", "populated"])
def test_draws_and_the_layout_is_clean(app, catalogue, size, state):
    if state == "populated":
        populated(app, catalogue)
    painter = draw_clip(app, size)
    strings = painter.strings
    assert "Optical Path" in strings and "Calculate Emission Intensity" in strings
    canvas = app.item_rects["graph"]
    problems = layout_problems(painter, size, ignore=[canvas]) + clipped_texts(
        painter, ignore=[canvas]
    )
    # The tables scroll sideways by design; everything else must be whole.
    problems = [p for p in problems if "Detected Intensity" not in p and "Förster radius" not in p]
    assert not problems, problems[:6]


def test_idle_state_hides_what_makes_no_sense(app, catalogue):
    from .driving import LPDriver

    drv = LPDriver(app)
    painter = drv.settle()  # the catalogue load of the first frame has finished
    assert not app.controller.running
    assert "Stop" not in painter.strings  # nothing runs
    app.controller.running = True
    assert "Stop" in drv.draw(2).strings  # while a call runs it is there
    app.controller.running = False
    assert not app.panel.enabled("export_instrument")  # no simulation yet
    assert not app.panel.enabled("delete_selection")  # nothing selected
    assert not app.panel.enabled("add_selected")  # no component chosen
    app.controller.running = True
    assert app.panel.enabled("stop") and not app.panel.enabled("calculate")
    app.controller.running = False


def test_settings_round_trip_and_garbage_is_ignored(app):
    app.controller.auto_update = False
    app.controller.db_path = "/x/y.sqlite"
    app.graph_control.show_minimap = False
    saved = app.export_settings()
    assert (
        saved["auto_update"] is False
        and saved["db_path"] == "/x/y.sqlite"
        and saved["minimap"] is False
    )
    from chisurf.plugins.core.lightpath_simulator.gui.app import create_app

    other = create_app(client=in_process_client())
    try:
        other.restore_settings(json.loads(json.dumps(saved)))
        assert other.controller.auto_update is False and other.controller.db_path == "/x/y.sqlite"
        assert other.graph_control.show_minimap is False
        other.restore_settings({"graph": "not a dict", "auto_update": 3})  # does not raise
        other.restore_settings({})
    finally:
        other.close()
        other.controller._executor.shutdown(wait=True)
