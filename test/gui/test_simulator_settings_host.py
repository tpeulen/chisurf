"""Simulator settings model, picker contracts and project reader identity."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from chisurf.core.api import ChiSurfAPI
from chisurf.core.api.context import PluginContext
from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.experiments.modelling.reader import StructureReader
from chisurf.core.experiments.tcspc.simulator import TCSPCSimulatorSetup
from chisurf.emtk.tcspc_simulator import SimulatorSettingsModel
from chisurf.server.session import SessionState


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


def test_the_model_selects_the_actual_irf_group_member():
    """The frontend reads the requested member from its injected session owner."""
    first = DataCurve(x=np.arange(4.0), y=np.array([0.0, 1.0, 0.0, 0.0]), name="same")
    second = DataCurve(x=np.arange(4.0), y=np.array([0.0, 0.0, 9.0, 0.0]), name="same")
    group = DataCurveGroup([first, second])
    api = ChiSurfAPI(state=SessionState(datasets=[group], fits=[]))
    setup = _setup()
    model = SimulatorSettingsModel(setup, PluginContext(api=api, main_window=None))
    model.irf_candidate = next(
        value for value, label in model.irf_options() if second.unique_identifier in value
    )
    model.select_irf()
    np.testing.assert_array_equal(setup.instrument_response_function.y, second.y)
    np.testing.assert_array_equal(group.y, first.y)


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


def test_api_defaults_remain_empty_and_legacy_simulator_exports_are_absent():
    """Only shipped configuration supplies presets."""
    reader = TCSPCSimulatorSetup(record_provenance=False)
    assert reader.lifetime_spectrum.size == reader.rotation_spectrum.size == 0
    assert reader.sample_name == "TCSPC-Dummy" and reader.seed is None and reader.add_noise
    assert (reader.n_tac, reader.dt, reader.p0, reader.rep_rate) == (4096, 0.0141, 10000.0, 10.0)


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


