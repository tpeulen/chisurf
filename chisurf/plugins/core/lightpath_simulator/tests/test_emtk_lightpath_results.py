"""The light-path window: simulated numbers, result tables, default path, spec, drawing.

Hermetic: temporary settings, HOME and spectra catalogue (generated spectra, tests/catalog.py), an in-process RPC client.
The catalogue's spectra are analytic, so every simulated number has a closed form here (:func:`expected_excitation`,
:func:`expected_emission`) that the window must reproduce.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from .catalog import WAVELENGTHS, _band, build_catalogue
from .driving import BIG, PLUGIN, SMALL, clipped_texts, draw_clip, layout_problems

SPEC = json.loads((PLUGIN / "gui/lightpath.view.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    # The runtime config is process-wide and outranks the environment variables above: a test elsewhere that
    # configured MMFDB (and did not reset it) would point this window at its database, not the empty one here.
    from mmfdb.config import reset_runtime_config

    reset_runtime_config()
    yield
    reset_runtime_config()


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


# -- the planted answer ------------------------------------------------------------------------------------ #
#: The dyes and channels of tests/catalog.py: Gaussian absorption/emission bands (centre, sigma 18 / 22 nm),
#: quantum yield and extinction coefficient; a 561 nm sigmoid long-pass splitter sends the long side to the red
#: filter (BP 650/60) and the short side to the green one (BP 500/50); both filters pass 0.92, both detectors have
#: a flat quantum efficiency of 0.6. The default path excites at 488 and 640 nm with power 1.
DYES = {"Atto 488": (500.0, 520.0, 0.8, 90000.0), "Atto 647N": (645.0, 668.0, 0.65, 150000.0)}
LASERS = {"488 nm": 488.0, "640 nm": 640.0}
QE, FILTER_T = 0.6, 0.92
#: Detector signals at or below this are not reported (``LightPathSimulator.get_detector_signals``).
SIGNAL_FLOOR = 1e-12


def _channels(x):
    long_pass = 1.0 / (1.0 + np.exp(-(WAVELENGTHS - 561.0) / 4.0))
    green = ((WAVELENGTHS > 475) & (WAVELENGTHS < 525)) * FILTER_T
    red = ((WAVELENGTHS > 620) & (WAVELENGTHS < 680)) * FILTER_T
    interp = lambda curve: np.interp(x, WAVELENGTHS, curve)  # noqa: E731
    return {
        "Green Channel": interp(1.0 - long_pass) * interp(green),
        "Red Channel": interp(long_pass) * interp(red),
    }


def expected_excitation(laser, dye):
    """Extinction coefficient times the absorption band, linearly interpolated at the laser line."""
    absorption_centre, _, _, ext_coeff = DYES[dye]
    return ext_coeff * float(np.interp(LASERS[laser], WAVELENGTHS, _band(absorption_centre, 18.0)))


def expected_emission(dye, detector):
    """Quantum yield times QE times the fraction of the emission band the channel passes (1 nm grid)."""
    _, emission_centre, qy, _ = DYES[dye]
    x = np.arange(WAVELENGTHS[0], WAVELENGTHS[-1] + 0.5, 1.0)
    emission = np.interp(x, WAVELENGTHS, _band(emission_centre, 22.0))
    return qy * QE * float(np.sum(emission * _channels(x)[detector]) / np.sum(emission))


DEFAULT_TYPES = ["light_source", "sample", "splitter", "filter", "detector", "filter", "detector",
                 "forster_radius"]


# -- numbers: the simulation against the planted spectra --------------------------------------------------- #


def test_the_simulation_reproduces_the_planted_spectra(app, catalogue):
    populated(app, catalogue)
    assert sorted(n.type for n in app.controller.document.nodes) == sorted(DEFAULT_TYPES)
    assert len(app.controller.probes) == len(catalogue) == 7
    matrices = app.controller.result["crosstalk_matrices"]

    excitation = matrices["excitation"]
    assert excitation["rows"] == list(LASERS) and excitation["columns"] == list(DYES)
    for i, laser in enumerate(LASERS):
        for j, dye in enumerate(DYES):
            assert excitation["values"][i][j] == pytest.approx(expected_excitation(laser, dye), rel=1e-9)

    emission = matrices["emission"]
    assert emission["rows"] == list(DYES) and emission["columns"] == ["Green Channel", "Red Channel"]
    for i, dye in enumerate(DYES):
        for j, detector in enumerate(emission["columns"]):
            assert emission["values"][i][j] == pytest.approx(expected_emission(dye, detector), rel=1e-6)

    # what a detector sees is the excitation times the emission probability of that channel
    detected = matrices["detected"]
    assert detected["rows"] == [f"{laser} | {dye}" for laser in LASERS for dye in DYES]
    signals = {(s["laser"], s["detector"], s["dye"]): s["intensity"]
               for s in app.controller.result["detector_signals"]}
    for i, row in enumerate(detected["rows"]):
        laser, dye = row.split(" | ")
        for j, detector in enumerate(detected["columns"]):
            expected = expected_excitation(laser, dye) * expected_emission(dye, detector)
            if expected <= SIGNAL_FLOOR:  # the simulator drops signals at or below the floor
                assert detected["values"][i][j] == 0.0 and (laser, detector, dye) not in signals
                continue
            assert detected["values"][i][j] == pytest.approx(expected, rel=1e-6)
            assert signals[(laser, detector, dye)] == pytest.approx(expected, rel=1e-6)
    # each dye lands in its own channel; the leak into the other one is orders of magnitude below
    assert signals[("488 nm", "Green Channel", "Atto 488")] > 1e5 * signals[("488 nm", "Red Channel", "Atto 488")]
    assert signals[("640 nm", "Red Channel", "Atto 647N")] > 1e9 * signals[("640 nm", "Green Channel", "Atto 647N")]


def test_the_result_tables_show_the_simulated_numbers(app, catalogue):
    populated(app, catalogue)
    result = app.controller.result
    rows = app.panel.signals.rows()
    assert [[r["laser"], r["detector"], r["dye"], r["intensity"]] for r in rows] == [
        [s["laser"], s["detector"], s["dye"], s["intensity"]] for s in result["detector_signals"]
    ]
    for kind in ("excitation", "emission", "detected"):
        table, matrix = getattr(app.panel, kind), result["crosstalk_matrices"][kind]
        columns = table.columns()[1:]
        assert [c["title"] for c in columns] == matrix["columns"]
        assert [r["row"] for r in table.rows()] == matrix["rows"]
        assert [[r[c["key"]] for c in columns] for r in table.rows()] == matrix["values"]


def test_the_palette_offers_every_registered_component_once(app):
    rows = app.panel.palette_rows()
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)) and set(DEFAULT_TYPES) <= set(ids)
    assert all(r["title"] for r in rows)


def test_the_default_path_picks_its_components_from_the_catalogue_by_name(app, catalogue):
    load_catalogue(app)
    app.controller.reset()
    nodes = app.controller.document.nodes
    assert [n.type for n in nodes] == DEFAULT_TYPES
    by_id = {n.id: n for n in nodes}
    sample = next(n for n in nodes if n.type == "sample")
    assert sorted(sample.config["probe_ids"]) == sorted(catalogue[d] for d in DYES)
    splitter = next(n for n in nodes if n.type == "splitter")
    assert splitter.config["probe_id"] == catalogue["561LP dichroic"]
    assert by_id["green_filter"].config["probe_id"] == catalogue["BP 500/50 filter"]
    assert by_id["red_filter"].config["probe_id"] == catalogue["BP 650/60 filter"]


def test_a_saved_graph_reloads_to_the_same_nodes(app, catalogue, tmp_path):
    populated(app, catalogue)
    path = tmp_path / "graph.json"
    app.controller.save_graph(path)
    saved = json.loads(path.read_text())
    assert len(saved["nodes"]) == len(DEFAULT_TYPES)
    app.controller.reset()
    app.controller.load_graph(path)
    assert sorted(n.id for n in app.controller.document.nodes) == sorted(
        n["id"] for n in saved["nodes"]
    )


# -- spec, tooltips, no Qt ------------------------------------------------------------------------------ #


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
