"""The existing shell composes simulator settings with one owned session context."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from qtpy import QtWidgets

from chisurf.core.api import ChiSurfAPI
from chisurf.core.api.context import PluginContext
from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.experiments.modelling.reader import StructureReader
from chisurf.core.experiments.tcspc.simulator import TCSPCSimulatorSetup
from chisurf.gui.main_helper import SetupMixin
from chisurf.server.session import SessionState


def _main(qtbot, reader):
    """Use the production shell method with an isolated existing layout."""
    widget = QtWidgets.QWidget()
    qtbot.addWidget(widget)
    widget.resize(900, 760)
    widget.layout_experiment_reader = QtWidgets.QVBoxLayout(widget)
    widget.current_setup = reader
    widget.current_experiment = SimpleNamespace(readers=[reader])
    widget.comboBox_setupSelect = QtWidgets.QComboBox()
    widget.comboBox_setupSelect.addItem("Simulator")
    widget.open_context_help_for_reader = lambda: None
    return widget


def _setup():
    """Configure supplied scientific values that a view must never replace."""
    return TCSPCSimulatorSetup(
        lifetime_spectrum=np.array([0.7, 3.1, 0.3, 1.2]),
        rotation_spectrum=[0.31, 2.4],
        g_factor=1.7,
        l1=0.05,
        l2=0.08,
        seed=154,
        record_provenance=False,
    )


@pytest.mark.parametrize("mode", ["local", "server"])
def test_injected_context_is_retained_and_native_host_is_reused(qtbot, mode):
    """Local/server injection survives construction and reselection without new clients."""
    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp

    setup = _setup()
    main = _main(qtbot, setup)
    transport = SimpleNamespace(dataset__list=lambda: []) if mode == "server" else None
    api = ChiSurfAPI(client=transport, mode=mode, state=SessionState())
    context = PluginContext(api=api, client=transport, main_window=main)
    main.plugin_context = context
    SetupMixin._refresh_setup_ui(main)
    host = main.layout_experiment_reader.itemAt(0).widget()
    assert isinstance(host.control, SimulatorSettingsApp)
    assert host.control.model.context is context and host.control.reader is setup
    assert context.api is api and context.client is transport
    np.testing.assert_array_equal(setup.lifetime_spectrum, [0.7, 3.1, 0.3, 1.2])
    assert (setup.g_factor, setup.l1, setup.l2, setup.seed) == (1.7, 0.05, 0.08, 154)
    SetupMixin._refresh_setup_ui(main)
    assert main.layout_experiment_reader.count() == 1
    assert main.layout_experiment_reader.itemAt(0).widget() is host
    host.close()


def test_injected_api_is_cached_and_shared_across_reader_surfaces(qtbot):
    """Changing reader views reuses the same main-owned API/context, including plain views."""
    setup = _setup()
    main = _main(qtbot, setup)
    api = ChiSurfAPI(state=SessionState())
    main.api = api
    SetupMixin._refresh_setup_ui(main)
    first = main.layout_experiment_reader.itemAt(0).widget()
    context = first.control.model.context
    assert context.api is api
    structure = StructureReader(record_provenance=False)
    main.current_setup = structure
    main.current_experiment.readers.append(structure)
    SetupMixin._refresh_setup_ui(main)
    second = main._native_reader_settings_hosts[id(structure)]
    assert second.control.context is context
    assert SetupMixin._reader_plugin_context(main) is context
    first.close()
    second.close()


def test_default_embedded_context_reuses_state_and_installed_transport(qtbot, monkeypatch):
    """Composition consults existing objects without connecting, pinging or starting servers."""
    import chisurf as cs
    from chisurf.core.api import fitting_client

    state = SessionState()
    transport = SimpleNamespace(call=lambda *a, **kw: pytest.fail("composition performed RPC"))
    monkeypatch.setattr(cs, "__chisurf_rpc_server__", SimpleNamespace(state=state), raising=False)
    monkeypatch.setattr(
        fitting_client, "get_fitting_client", lambda: SimpleNamespace(_client=transport)
    )
    main = _main(qtbot, _setup())
    context = SetupMixin._reader_plugin_context(main)
    assert context.api._state is state and context.api.client is transport
    assert context.api.mode == "hybrid" and context.main_window is main
    assert SetupMixin._reader_plugin_context(main) is context


def test_default_external_transport_is_reused_in_server_mode(qtbot, monkeypatch):
    """An installed external service transport is never recreated or reconnected."""
    import chisurf as cs
    from chisurf.core.api import fitting_client

    transport = SimpleNamespace(call=lambda *a, **kw: pytest.fail("composition performed RPC"))
    monkeypatch.setattr(cs, "__chisurf_rpc_server__", None, raising=False)
    monkeypatch.setattr(
        fitting_client, "get_fitting_client", lambda: SimpleNamespace(_client=transport)
    )
    main = _main(qtbot, _setup())
    context = SetupMixin._reader_plugin_context(main)
    assert context.api.client is transport and context.api.mode == "server"


def test_default_without_transport_uses_the_actual_live_session_lists(qtbot, monkeypatch):
    """The local fallback aliases current session lists rather than inventing a new session."""
    import chisurf as cs
    from chisurf.core.api import fitting_client

    datasets, fits = [], []
    monkeypatch.setattr(cs, "imported_datasets", datasets)
    monkeypatch.setattr(cs, "fits", fits)
    monkeypatch.setattr(cs, "__chisurf_rpc_server__", None, raising=False)
    monkeypatch.setattr(fitting_client, "get_fitting_client", lambda: None)
    main = _main(qtbot, _setup())
    context = SetupMixin._reader_plugin_context(main)
    assert context.api.mode == "local" and context.api.client is None
    assert context.api._state.datasets is datasets and context.api._state.fits is fits


def test_host_selects_the_actual_irf_group_member(qtbot):
    """The composed frontend reads the requested member from its injected session owner."""
    first = DataCurve(x=np.arange(4.0), y=np.array([0.0, 1.0, 0.0, 0.0]), name="same")
    second = DataCurve(x=np.arange(4.0), y=np.array([0.0, 0.0, 9.0, 0.0]), name="same")
    group = DataCurveGroup([first, second])
    api = ChiSurfAPI(state=SessionState(datasets=[group], fits=[]))
    setup = _setup()
    main = _main(qtbot, setup)
    main.plugin_context = PluginContext(api=api, main_window=main)
    SetupMixin._refresh_setup_ui(main)
    host = main.layout_experiment_reader.itemAt(0).widget()
    model = host.control.model
    model.irf_candidate = next(
        value for value, label in model.irf_options() if second.unique_identifier in value
    )
    model.select_irf()
    np.testing.assert_array_equal(setup.instrument_response_function.y, second.y)
    np.testing.assert_array_equal(group.y, first.y)
    host.close()


@pytest.mark.parametrize("inherited_filename", ["", "stale-input.csv"])
def test_header_generates_data_without_picking_an_auxiliary_spectrum(
    qtbot, monkeypatch, inherited_filename
):
    """The declared absence of primary inputs wins over an inherited file attribute."""
    import chisurf as cs
    from chisurf.gui.main import Main

    setup = _setup()
    setup.filename = inherited_filename
    main = _main(qtbot, setup)
    main.plugin_context = PluginContext(api=ChiSurfAPI(state=SessionState()), main_window=main)
    SetupMixin._refresh_setup_ui(main)
    host = main.layout_experiment_reader.itemAt(0).widget()
    monkeypatch.setattr(
        host.control, "choose_input", lambda *a: pytest.fail("picked auxiliary spectrum")
    )
    generated = []

    def dispatch(name, payload):
        """Exercise the original generator owner behind the actual header action."""
        assert name == "dataset.add"
        assert payload["experiment_reader"] is setup and payload["filename"] is None
        generated.append(setup.read(filename=payload["filename"]))

    monkeypatch.setattr(cs.core.actions, "dispatch", dispatch)
    Main.onAddDataset(main)
    assert len(generated) == 1 and generated[0][0].data_reader is setup
    np.testing.assert_array_equal(generated[0][0].y, setup.read()[0].y)
    host.close()


def test_primary_picker_ignores_auxiliary_filename_and_delivers_once(tmp_path):
    """A sole primary source wins even when an auxiliary source is named filename."""
    from emtk.testing import Driver

    from chisurf.emtk.reader_settings import ReaderSettingsApp

    sections = [
        {
            "type": "custom",
            "key": "data_source",
            "options": {"attr": attr, "primary": primary, "mmfdb": False},
        }
        for attr, primary in (("filename", False), ("measurement", True))
    ]
    reader = SimpleNamespace(filename="", measurement="", view_spec=lambda: {"sections": sections})
    app = ReaderSettingsApp(reader)
    events = []
    try:
        chosen = tmp_path / "measurement.csv"
        chosen.write_text("0 1\n1 2\n")
        driver = Driver(app, (900, 1050))
        app.choose_input(events.append)
        source = app.sources["measurement"]
        assert app.file_source is source
        app.file_dialog.directory = str(tmp_path)
        driver.frame(2)
        driver.click(chosen.name)
        driver.click("Open")
        source.path = "second.csv"
        driver.frame(2)
        assert events == [str(chosen)]
        assert reader.filename == ""
    finally:
        app.close()


def test_auxiliary_only_picker_is_an_explicit_error():
    """A direct primary-input request cannot silently choose an auxiliary file."""
    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp

    app = SimulatorSettingsApp(_setup(), context=SimpleNamespace(api=None))
    try:
        with pytest.raises(ValueError, match="unambiguous"):
            app.choose_input()
        assert app.file_dialog is None
    finally:
        app.close()


def _shipped_simulator():
    """Construct the actual configured reader without changing API constructor defaults."""
    import importlib

    from chisurf.core.experiments import _load_yaml_config

    config = _load_yaml_config(
        Path(__file__).resolve().parents[2] / "chisurf/core/settings/experiment_configs.yaml"
    )
    row = next(
        row
        for row in config["tcspc"]["readers"]
        if row["reader_class"].endswith("TCSPCSimulatorSetup")
    )
    assert row["controller_class"] is None
    module, name = row["reader_class"].rsplit(".", 1)
    return getattr(importlib.import_module(module), name)(
        **row["reader_params"], record_provenance=False
    )


def test_shipped_simulator_defaults_and_missing_measurement_source_use_native_host(
    qtbot, monkeypatch
):
    """The shipped setup has familiar presets, no Qt controller and a generator header."""
    import chisurf as cs
    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp
    from chisurf.gui.main import Main

    reader = _shipped_simulator()
    assert reader.controller is None and not isinstance(reader, QtWidgets.QWidget)
    np.testing.assert_array_equal(reader.lifetime_spectrum, [0.4, 1.1, 0.6, 4.1])
    np.testing.assert_array_equal(reader.rotation_spectrum, [0.2, 1])
    assert reader.sample_name == "Dummy-sample" and reader.name == "Simulator"
    main = _main(qtbot, reader)
    main.plugin_context = PluginContext(api=ChiSurfAPI(state=SessionState()), main_window=main)
    SetupMixin._refresh_setup_ui(main)
    host = main.layout_experiment_reader.itemAt(0).widget()
    assert isinstance(host.control, SimulatorSettingsApp)
    assert not host.control.primary_sources
    imports = []
    monkeypatch.setattr(cs.core.actions, "dispatch", lambda name, payload: imports.append(payload))
    Main.onAddDataset(main)
    assert imports == [{"filename": None, "experiment_reader": reader}]
    host.close()


def test_api_defaults_remain_empty_and_legacy_simulator_exports_are_absent():
    """Only shipped GUI configuration supplies presets; no obsolete controller remains."""
    import importlib.util

    reader = TCSPCSimulatorSetup(record_provenance=False)
    assert reader.lifetime_spectrum.size == reader.rotation_spectrum.size == 0
    assert reader.sample_name == "TCSPC-Dummy" and reader.seed is None and reader.add_noise
    assert (reader.n_tac, reader.dt, reader.p0, reader.rep_rate) == (4096, 0.0141, 10000.0, 10.0)
    assert (
        importlib.util.find_spec(
            "chisurf.gui.widgets.experiments.tcspc.tcspc_simulator_setup_widget"
        )
        is None
    )
    from chisurf.gui.widgets.experiments import tcspc
    from chisurf.gui.widgets.experiments.tcspc import controller

    assert "TCSPCSimulatorSetupWidget" not in tcspc.__all__
    assert "TCSPCSimulatorSetupWidget" not in controller.__all__


def test_simulator_project_reader_identity_stays_core_without_alias():
    """Project snapshots retain the existing core reader class through the GUI switch."""
    from chisurf.core.experiments.core.experiment import Experiment
    from chisurf.core.project.session import _reader_state, _restore_reader

    reader = _shipped_simulator()
    snapshot = _reader_state(reader)
    assert snapshot["module"] == "chisurf.core.experiments.tcspc.simulator"
    assert snapshot["class"] == "TCSPCSimulatorSetup"
    restored = _restore_reader(snapshot, Experiment(name="TCSPC"), {})
    assert type(restored) is TCSPCSimulatorSetup and restored.controller is None
    np.testing.assert_array_equal(restored.lifetime_spectrum, reader.lifetime_spectrum)


def test_production_experiment_factory_builds_shipped_simulator_without_controller(
    qtbot, monkeypatch
):
    """The same registration method as Main consumes the shipped row without Qt fallback."""
    import copy
    from types import MethodType

    import chisurf as cs
    from chisurf.core.experiments import _load_yaml_config

    config = _load_yaml_config(
        Path(__file__).resolve().parents[2] / "chisurf/core/settings/experiment_configs.yaml"
    )
    row = next(
        item
        for item in config["tcspc"]["readers"]
        if item["reader_class"].endswith("TCSPCSimulatorSetup")
    )
    monkeypatch.setattr(cs.core.experiments, "types", {})
    monkeypatch.setattr(cs, "experiment", {})
    main = _main(qtbot, _setup())
    main._resolve_class = MethodType(SetupMixin._resolve_class, main)
    main._make_controller = lambda *args: pytest.fail("constructed a legacy controller")
    SetupMixin._setup_experiment(
        main, "tcspc", {"name": "TCSPC", "readers": [copy.deepcopy(row)], "models": []}
    )
    experiment = cs.experiment["TCSPC"]
    assert len(experiment.readers) == 1
    reader = experiment.readers[0]
    assert type(reader) is TCSPCSimulatorSetup and reader.controller is None
    np.testing.assert_array_equal(reader.lifetime_spectrum, [0.4, 1.1, 0.6, 4.1])
    main.current_setup, main.current_experiment = reader, experiment
    main.plugin_context = PluginContext(api=ChiSurfAPI(state=SessionState()), main_window=main)
    SetupMixin._refresh_setup_ui(main)
    host = main.layout_experiment_reader.itemAt(0).widget()
    assert host.control.reader is reader and host.control.model.context is main.plugin_context
    host.close()
