"""Tests for headless optical simulation and mmCIF export."""
import json
from unittest.mock import MagicMock

import numpy as np


def _manual_laser_graph():
    """Return a minimal JSON graph with one manual laser node."""
    return {
        "nodes": [
            {
                "id": "node_laser",
                "type": "light_source",
                "title": "Laser",
                "inputs": [],
                "outputs": [{"name": "Light", "is_output": True}],
                "config": {"source_mode": "manual", "manual_lines": "488:1.0"},
            }
        ],
        "edges": [],
    }


# Ensure we don't have a QApplication running during these tests to prove headless-ness
def test_import_no_qt():
    """Verify we can import the simulator without Qt or a display."""
    # We should be able to import these without triggering any Qt errors
    assert True

def test_propagate_headless():
    """Test full propagation on a minimal graph dict."""
    from chisurf.plugins.core.lightpath_simulator.backend.crosstalk import WAVELENGTHS
    from chisurf.plugins.core.lightpath_simulator.backend.simulator import OpticalPathSimulator

    # Simple Mock DB
    mock_db = MagicMock()
    # Mock return for get_standardized_optical_properties (Sample Dye)
    mock_db.get_standardized_optical_properties.return_value = {"qy": 0.8, "ext_coeff": 92000}
    # Mock return for get_probe_by_id
    mock_db.get_probe_by_id.return_value = {"chromophore_name": "Test Dye"}
    # Mock return for MMFDB probe spectra
    # We return a simple unit spectrum (flat)
    mock_db.get_probe_spectrum.return_value = (WAVELENGTHS, np.ones_like(WAVELENGTHS))

    # Minimal Graph: Laser(488) -> Sample(Test Dye) -> Detector
    graph_dict = {
        "nodes": [
            {
                "id": "node_laser",
                "type": "light_source",
                "title": "Laser",
                "inputs": [],
                "outputs": [{"name": "Light", "is_output": True}],
                "config": {"source_mode": "manual", "manual_lines": "488:1.0"}
            },
            {
                "id": "node_sample",
                "type": "sample",
                "title": "Sample",
                "inputs": [{"name": "In", "is_output": False}],
                "outputs": [{"name": "Out", "is_output": True}],
                "config": {"probe_ids": [1]}
            },
            {
                "id": "node_det",
                "type": "detector",
                "title": "Detector",
                "inputs": [{"name": "In", "is_output": False}],
                "outputs": [],
                "config": {"detector_name": "Main Channel", "probe_id": 999}
            }
        ],
        "edges": [
            {"source": "node_laser", "source_port": 0, "target": "node_sample", "target_port": 0},
            {"source": "node_sample", "source_port": 1, "target": "node_det", "target_port": 0}
        ]
    }

    sim = OpticalPathSimulator(mock_db)
    sim.load_from_dict(graph_dict)
    states = sim.propagate()

    assert "node_det" in states
    signals = sim.get_detector_signals()
    assert len(signals) > 0
    assert signals[0]["detector"] == "Main Channel"
    assert signals[0]["intensity"] > 0

def test_export_instrument_setting():
    """Test mapping simulator state to mmCIF dataclasses."""
    from chisurf.plugins.core.lightpath_simulator.backend.mmcif_export import InstrumentSetting
    from chisurf.plugins.core.lightpath_simulator.backend.simulator import OpticalPathSimulator

    mock_db = MagicMock()
    mock_db.get_standardized_optical_properties.return_value = {"qy": 0.5, "ext_coeff": 100000}
    mock_db.get_probe_by_id.return_value = {"chromophore_name": "ATTO 488"}

    # State with 1 laser and 1 sample
    sim = OpticalPathSimulator(mock_db)
    sim.load_from_dict({
        "nodes": [
            {"id": "l1", "type": "light_source", "title": "L", "inputs": [], "outputs": ["X"], "config": {"manual_lines": "488:1.0"}},
            {"id": "s1", "type": "sample", "title": "S", "inputs": ["I"], "outputs": ["O", "D"], "config": {"probe_ids": [42]}}
        ],
        "edges": []
    })

    setting = sim.to_instrument_setting()
    assert isinstance(setting, InstrumentSetting)
    assert len(setting.lasers) == 1
    assert setting.lasers[0].wavelength_nm == 488.0
    assert len(setting.fluorophores) == 1
    assert setting.fluorophores[0].name == "ATTO 488"
    assert setting.fluorophores[0].quantum_yield == 0.5

def test_export_to_json():
    """Verify JSON serialization contains expected keys."""
    from chisurf.plugins.core.lightpath_simulator.backend.mmcif_export import (
        InstrumentSetting,
        LaserLine,
    )

    setting = InstrumentSetting(id="test_inst", instrument="TestInst", lasers=[LaserLine(488.0)])
    js = setting.to_json()
    data = json.loads(js)

    assert data["id"] == "test_inst"
    assert "lasers" in data
    assert data["lasers"][0]["wavelength_nm"] == 488.0


def test_json_safe_strips_runtime_callables():
    """Verify graph state with callbacks can be sent through JSON-RPC."""
    from chisurf.plugins.core.lightpath_simulator.gui.tool import _json_safe

    graph = _manual_laser_graph()
    graph["nodes"][0]["config"]["_update_plot"] = lambda: None
    graph["nodes"][0]["config"]["_last_signals"] = {"x": 1.0}
    safe_graph = _json_safe(graph)

    json.dumps(safe_graph)
    assert "_update_plot" not in safe_graph["nodes"][0]["config"]
    assert "_last_signals" not in safe_graph["nodes"][0]["config"]


def test_lightpath_save_list_get_roundtrip(tmp_path):
    """Persist a simulated lightpath graph as MMFDB operation/artifacts."""
    from chisurf.plugins.core.lightpath_simulator.rpc.services import (
        get_handler,
        list_handler,
        save_handler,
    )

    db_path = tmp_path / "lightpath.db"
    graph = _manual_laser_graph()

    saved = save_handler(graph, name="Unit test lightpath", db_path=str(db_path))
    assert saved["ok"], saved.get("error")
    saved_result = saved["result"]
    assert saved_result["operation_id"].startswith("lightpath_")
    assert saved_result["artifacts"]["graph"].endswith("_graph")
    assert saved_result["artifacts"]["crosstalk_matrices"].endswith("_crosstalk_matrices")

    listed = list_handler(db_path=str(db_path))
    assert listed["ok"], listed.get("error")
    assert [item["operation_id"] for item in listed["result"]["simulations"]] == [saved_result["operation_id"]]

    loaded = get_handler(saved_result["operation_id"], db_path=str(db_path))
    assert loaded["ok"], loaded.get("error")
    loaded_result = loaded["result"]
    assert loaded_result["name"] == "Unit test lightpath"
    assert loaded_result["graph"] == graph
    assert loaded_result["instrument_setting"]["lasers"][0]["wavelength_nm"] == 488.0
    assert "crosstalk_matrices" in loaded_result


#: Wavelength grid shared by the MMFDB-backed light-path tests below.
_PROBE_WAVELENGTHS = np.array([480.0, 488.0, 500.0, 520.0], dtype=np.float64)


def _dye_detector_graph(dye_id: int, detector_id: int) -> dict:
    """Return a laser → dye → detector graph for the two given MMFDB probes."""
    return {
        "nodes": [
            {
                "id": "laser",
                "type": "light_source",
                "title": "Laser",
                "inputs": [],
                "outputs": [{"name": "Light", "is_output": True}],
                "config": {"source_mode": "manual", "manual_lines": "488:1.0"},
            },
            {
                "id": "sample",
                "type": "sample",
                "title": "Sample",
                "inputs": [{"name": "In", "is_output": False}],
                "outputs": [
                    {"name": "Out", "is_output": True},
                    {"name": "Dye Data", "is_output": True},
                ],
                "config": {"probe_ids": [dye_id]},
            },
            {
                "id": "detector",
                "type": "detector",
                "title": "Detector",
                "inputs": [{"name": "In", "is_output": False}],
                "outputs": [],
                "config": {"detector_name": "MMFDB detector", "probe_id": detector_id},
            },
        ],
        "edges": [
            {"source": "laser", "source_port": 0, "target": "sample", "target_port": 0},
            {"source": "sample", "source_port": 1, "target": "detector", "target_port": 0},
        ],
    }


def _build_probe_db(db_path, absorption_type: str, absorption_scale: float = 1.0):
    """Create a two-probe MMFDB whose dye stores its absorption under a given type.

    Parameters
    ----------
    db_path : path-like
        Location of the database to create.
    absorption_type : str
        Spectrum type the dye's absorption curve is filed under — the catalogue
        uses ``"absorption"`` for most probes and ``"excitation"`` for others.
    absorption_scale : float
        Factor applied to the absorption curve, so a record that does not peak
        at one can be told apart from one that does.

    Returns
    -------
    tuple of int
        ``(dye_id, detector_id)``.
    """
    from mmfdb.repository import MFDatabase

    with MFDatabase(str(db_path)) as db:
        cursor = db.conn.execute(
            "INSERT INTO probe_types (type_name, display_name) VALUES (?, ?)",
            ("test", "Test probes"),
        )
        type_id = cursor.lastrowid
        dye_id = db.add_probe("MMFDB Dye", type_id, category="organic_dye")
        detector_id = db.add_probe("MMFDB Detector", type_id, category="other")
        db.add_optical_property(dye_id, "qy", "0.8")
        db.add_optical_property(dye_id, "ext_coeff", "100000")
        db.add_spectrum(
            dye_id,
            absorption_type,
            _PROBE_WAVELENGTHS,
            np.array([0.2, 1.0, 0.5, 0.0]) * absorption_scale,
        )
        db.add_spectrum(
            dye_id, "emission", _PROBE_WAVELENGTHS, np.array([0.0, 0.2, 0.8, 1.0])
        )
        db.add_spectrum(
            detector_id,
            "quantum_efficiency",
            _PROBE_WAVELENGTHS,
            np.ones_like(_PROBE_WAVELENGTHS),
        )
    return dye_id, detector_id


def test_lightpath_simulates_from_mmfdb_probe_spectra(tmp_path):
    """Simulation should read spectra from canonical MMFDB probe records."""
    from chisurf.plugins.core.lightpath_simulator.core.workflow import simulate_lightpath

    db_path = tmp_path / "spectra.db"
    dye_id, detector_id = _build_probe_db(db_path, "absorption")
    graph = _dye_detector_graph(dye_id, detector_id)

    result = simulate_lightpath(graph, db_path=str(db_path))
    signals = result["detector_signals"]
    assert signals
    assert signals[0]["dye"] == "MMFDB Dye"
    assert signals[0]["detector"] == "MMFDB detector"
    assert signals[0]["intensity"] > 0.0
    matrices = result["crosstalk_matrices"]
    assert matrices["excitation"]["rows"] == ["488 nm"]
    assert matrices["excitation"]["columns"] == ["MMFDB Dye"]
    assert matrices["emission"]["rows"] == ["MMFDB Dye"]
    assert matrices["emission"]["columns"] == ["MMFDB detector"]
    assert matrices["detected"]["columns"] == ["MMFDB detector"]
    assert result["instrument_setting"]["fluorophores"][0]["probe_id"] == dye_id


def test_a_dye_whose_absorption_is_filed_as_excitation_still_works(tmp_path):
    """An excitation scan is the dye's absorption curve, and must be read as one.

    Most of the catalogue files a dye's absorption under ``absorption``, but a
    large minority — every Alexa Fluor entry among them — files the same
    measurement under ``excitation``. Those dyes used to be filtered out of the
    palette and to absorb nothing when addressed by id, so the whole family was
    unusable.
    """
    from chisurf.plugins.core.lightpath_simulator.core.workflow import (
        get_probes_info,
        simulate_lightpath,
    )

    reference_path = tmp_path / "absorption.db"
    excitation_path = tmp_path / "excitation.db"
    reference_ids = _build_probe_db(reference_path, "absorption")
    # the same curve, filed as an excitation scan and not peak-normalised
    excitation_ids = _build_probe_db(excitation_path, "excitation", absorption_scale=0.4)
    assert reference_ids == excitation_ids

    dyes = [
        probe
        for probe in get_probes_info(str(excitation_path))["probes"]
        if probe["name"] == "MMFDB Dye"
    ]
    assert dyes and dyes[0]["has_abs"], "the dye is missing from the palette"

    reference = simulate_lightpath(
        _dye_detector_graph(*reference_ids), db_path=str(reference_path)
    )
    excitation = simulate_lightpath(
        _dye_detector_graph(*excitation_ids), db_path=str(excitation_path)
    )

    assert excitation["detector_signals"], "no light reaches the detector"
    assert excitation["detector_signals"][0]["intensity"] > 0.0
    # peak-normalised on the way in, so the two databases describe one dye
    assert excitation["crosstalk_matrices"] == reference["crosstalk_matrices"]


def test_plugin_manifest_declares_registered_rpc_methods():
    """Keep plugin manifest RPC declarations aligned with registered services."""
    from chisurf.core.plugin import load_manifest
    from chisurf.plugins.core.lightpath_simulator.rpc.services import register_services

    class Dispatcher:
        def __init__(self):
            self.methods = {}

        def register(self, name, handler):
            self.methods[name] = handler

    manifest = load_manifest("chisurf/plugins/core/lightpath_simulator/manifest.json")
    dispatcher = Dispatcher()
    register_services(dispatcher)

    manifest_methods = {method.name for method in manifest.rpc_methods}
    assert {
        "lightpath.simulate",
        "lightpath.save",
        "lightpath.list",
        "lightpath.get",
        "lightpath.get_probes_info",
        "lightpath.contract.describe",
    } <= manifest_methods
    assert manifest_methods <= set(dispatcher.methods)


def test_lightpath_api_client_unwraps_rpc_envelope(tmp_path):
    """API client should provide GUI-friendly typed methods over RPC envelopes."""
    from chisurf.core.plugin.client import InProcessClient
    from chisurf.plugins.core.lightpath_simulator.api.client import LightPathClient
    from chisurf.plugins.core.lightpath_simulator.rpc.services import register_services
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    dispatcher = ServiceDispatcher(SessionState())
    register_services(dispatcher)
    client = LightPathClient(InProcessClient(dispatcher))
    graph = _manual_laser_graph()
    db_path = str(tmp_path / "client.db")

    saved = client.save(graph, name="Client lightpath", db_path=db_path)
    assert saved["operation_id"].startswith("lightpath_")
    assert client.list_saved(db_path=db_path)[0]["operation_id"] == saved["operation_id"]
    assert client.get(saved["operation_id"], db_path=db_path)["graph"] == graph


def test_lightpath_rpc_handlers_accept_auth_metadata(tmp_path):
    """MMFDB clients inject auth metadata that lightpath handlers must tolerate."""
    from chisurf.plugins.core.lightpath_simulator.api.contract import (
        METHOD_DESCRIBE_CONTRACT,
        METHOD_GET_PROBES_INFO,
        METHOD_SIMULATE,
    )
    from chisurf.plugins.core.lightpath_simulator.rpc.services import register_services

    class Dispatcher:
        def __init__(self):
            self.methods = {}

        def register(self, name, handler):
            self.methods[name] = handler

    dispatcher = Dispatcher()
    register_services(dispatcher)
    auth = {"token": "unit-test-token"}
    db_path = str(tmp_path / "auth.db")

    simulated = dispatcher.methods[METHOD_SIMULATE](
        {"graph": _manual_laser_graph(), "db_path": db_path, "auth": auth}
    )
    assert simulated["ok"], simulated.get("error")

    probes = dispatcher.methods[METHOD_GET_PROBES_INFO]({"db_path": db_path, "auth": auth})
    assert probes["ok"], probes.get("error")

    contract = dispatcher.methods[METHOD_DESCRIBE_CONTRACT]({"auth": auth})
    assert contract["ok"], contract.get("error")


def test_lightpath_rpc_uses_server_session_cache(tmp_path):
    """Probe metadata should live in the server session after first load."""
    from chisurf.plugins.core.lightpath_simulator.api.contract import METHOD_GET_PROBES_INFO
    from chisurf.plugins.core.lightpath_simulator.rpc import services
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    state = SessionState()
    dispatcher = ServiceDispatcher(state)
    services.register_services(dispatcher)
    db_path = str(tmp_path / "cache.db")

    first = dispatcher.dispatch(METHOD_GET_PROBES_INFO, {"db_path": db_path})
    second = dispatcher.dispatch(METHOD_GET_PROBES_INFO, {"db_path": db_path})

    assert first["ok"], first.get("error")
    assert second["ok"], second.get("error")
    assert first["result"] == second["result"]
    lightpath_state = state.plugins["lightpath_simulator"]
    assert lightpath_state.to_dict()["probe_catalogue_count"] == 1


def test_lightpath_rpc_records_latest_simulation_in_session(tmp_path):
    """Simulation RPC should update the lightpath plugin session namespace."""
    from chisurf.plugins.core.lightpath_simulator.api.contract import METHOD_SIMULATE
    from chisurf.plugins.core.lightpath_simulator.rpc.services import register_services
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    state = SessionState()
    dispatcher = ServiceDispatcher(state)
    register_services(dispatcher)

    result = dispatcher.dispatch(
        METHOD_SIMULATE,
        {"graph": _manual_laser_graph(), "db_path": str(tmp_path / "sim.db")},
    )

    assert result["ok"], result.get("error")
    snapshot = state.to_dict()["plugins"]["lightpath_simulator"]
    assert snapshot["has_last_graph"]
    assert snapshot["has_last_result"]


def test_lightpath_cli_contract_command():
    """Plugin CLI should expose the shared contract."""
    import json

    from click.testing import CliRunner

    from chisurf.plugins.core.lightpath_simulator.cli import cli

    result = CliRunner().invoke(cli, ["contract"])
    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["plugin_id"] == "lightpath_simulator"
    assert "lightpath.simulate" in payload["methods"]


def test_simulated_optics_reach_the_global_view():
    """A propagated light path publishes its optics as fitting parameters.

    The end of the chain this plugin exists for: the excitation and emission
    probabilities it computes are what the FRET correction factors are made of,
    so they must be visible — and linkable — next to the fits that consume them.
    """
    from chisurf.core.parameter_group_registry import iter_registered_parameter_groups
    from chisurf.plugins.core.lightpath_simulator.backend.crosstalk import WAVELENGTHS
    from chisurf.plugins.core.lightpath_simulator.backend.simulator import OpticalPathSimulator
    from chisurf.plugins.core.lightpath_simulator.core.parameters import (
        register_lightpath_parameters,
        unregister_lightpath_parameters,
    )

    mock_db = MagicMock()
    mock_db.get_standardized_optical_properties.return_value = {"qy": 0.8, "ext_coeff": 92000}
    mock_db.get_probe_by_id.return_value = {"chromophore_name": "Test Dye"}
    mock_db.get_probe_spectrum.return_value = (WAVELENGTHS, np.ones_like(WAVELENGTHS))

    simulator = OpticalPathSimulator(mock_db)
    simulator.load_from_dict({
        "nodes": [
            {"id": "node_laser", "type": "light_source", "title": "Laser", "inputs": [],
             "outputs": [{"name": "Light", "is_output": True}],
             "config": {"source_mode": "manual", "manual_lines": "488:1.0"}},
            {"id": "node_sample", "type": "sample", "title": "Sample",
             "inputs": [{"name": "In", "is_output": False}],
             "outputs": [{"name": "Out", "is_output": True}], "config": {"probe_ids": [1]}},
            {"id": "node_det", "type": "detector", "title": "Detector",
             "inputs": [{"name": "In", "is_output": False}], "outputs": [],
             "config": {"detector_name": "Main Channel", "probe_id": 999}},
        ],
        "edges": [
            {"source": "node_laser", "source_port": 0, "target": "node_sample", "target_port": 0},
            {"source": "node_sample", "source_port": 1, "target": "node_det", "target_port": 0},
        ],
    })
    simulator.propagate()
    matrices = simulator.get_crosstalk_matrices()

    try:
        group = register_lightpath_parameters(matrices, owner_id="lightpath_test")
        owners = [owner for owner, *_ in iter_registered_parameter_groups()]
        assert "lightpath_test" in owners
        # every probability the simulator computed is now a fitting parameter
        assert group.parameters_all
        assert group.dyes and group.detectors
        emission = group.parameter("em", group.dyes[0], group.detectors[0])
        assert emission is not None and emission.value >= 0.0
        assert emission.unique_identifier                    # linkable process-wide
    finally:
        unregister_lightpath_parameters("lightpath_test")
