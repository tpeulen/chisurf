"""Real simulator buttons import cached groups through local and JSON-RPC APIs."""

from pathlib import Path

import numpy as np
import pytest
from emtk.testing import Driver

import chisurf as cs
from chisurf.core.api import ChiSurfAPI
from chisurf.core.api.context import PluginContext
from chisurf.core.experiments.core.experiment import Experiment
from chisurf.core.experiments.tcspc.reader import TCSPCReader
from chisurf.core.experiments.tcspc.simulator import TCSPCSimulatorSetup
from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp
from chisurf.server.session import SessionState
from test.server.test_grouped_dataset_import import _client

PROMPT = Path(__file__).resolve().parents[1] / "data/tcspc/ibh_sample/Prompt.txt"


@pytest.mark.parametrize("mode", ["local", "server"])
@pytest.mark.parametrize("polarization", ["vm", "vv/vh"])
def test_real_add_keeps_cached_simulation_in_its_owning_session(mode, polarization, monkeypatch):
    """Real callbacks preserve all cached scientific identities without regeneration."""
    monkeypatch.setattr(cs.core.base.Base, "_uuid_index", dict(cs.core.base.Base._uuid_index))
    global_datasets, global_fits = cs.imported_datasets, cs.fits
    datasets_before, fits_before = tuple(global_datasets), tuple(global_fits)
    experiment = Experiment(name="TCSPC")
    source = TCSPCReader(experiment=experiment, skiprows=10, record_provenance=False)
    irf = source.read(filename=str(PROMPT))[0]
    reader = TCSPCSimulatorSetup(
        experiment=experiment, sample_name="Cached native preview", n_tac=1024,
        lifetime_spectrum=[.4, 1.1, .6, 4.1], rotation_spectrum=[.2, 1],
        polarization=polarization, instrument_response_function=irf,
        g_factor=1.42, l1=.04, l2=.11, vh_shift=.7, seed=154, record_provenance=False,
    )
    state = SessionState(datasets=[irf], fits=[])
    client = _client(state) if mode == "server" else None
    api = ChiSurfAPI(mode=mode, state=state, client=client)
    app = SimulatorSettingsApp(reader, context=PluginContext(api=api, client=client))
    try:
        driver = Driver(app, size=(900, 760))
        driver.draw()
        driver.click("simulator.preview")
        driver.click("simulate_preview")
        cached = app.model.preview
        expected_count = 1 if polarization == "vm" else 2
        assert len(cached) == expected_count
        cached.current_dataset = expected_count - 1
        cached.meta_data.update(note="native cached preview", axes=("time", "channel"),
                                calibration=np.array([reader.g_factor, reader.l1, reader.l2]))
        expected = []
        for index, member in enumerate(cached):
            member.meta_data["channel"] = index
            expected.append({
                "uid": member.unique_identifier, "name": member.name,
                "arrays": {field: np.asarray(getattr(member, field)).copy()
                           for field in ("x", "y", "ex", "ey", "mask")},
            })
        uid, current = cached.unique_identifier, cached._current_dataset

        def forbidden(*args, **kwargs):
            """Adding a displayed preview must never ask the reader to compute again."""
            raise AssertionError("cached preview was regenerated")

        monkeypatch.setattr(TCSPCSimulatorSetup, "read", forbidden)
        monkeypatch.setattr(TCSPCSimulatorSetup, "get_data", forbidden)
        driver.click("add_preview")
        assert app.model.status == "Simulation added."
        assert len(state.datasets) == 2 and state.datasets[0] is irf
        imported = state.datasets[1]
        assert len(imported) == expected_count
        assert imported.unique_identifier == uid and imported.name == cached.name
        assert imported._current_dataset == current and cached._current_dataset == current
        assert imported.experiment.unique_identifier == experiment.unique_identifier
        assert imported.experiment.name == experiment.name
        assert imported.meta_data["note"] == "native cached preview"
        assert imported.meta_data["axes"] == ("time", "channel")
        np.testing.assert_array_equal(imported.meta_data["calibration"], [1.42, .04, .11])
        for index, (actual, original) in enumerate(zip(imported, expected)):
            assert actual.unique_identifier == original["uid"] and actual.name == original["name"]
            assert actual.meta_data["channel"] == index
            for field, value in original["arrays"].items():
                assert np.asarray(getattr(actual, field)).dtype == value.dtype
                np.testing.assert_array_equal(getattr(actual, field), value)
            restored = actual.data_reader
            assert restored.experiment is actual.experiment
            for field in ("g_factor", "l1", "l2", "vh_shift", "polarization", "is_vv_vh",
                          "dt", "rep_rate", "seed", "add_noise", "n_tac", "p0"):
                assert getattr(restored, field) == getattr(reader, field)
            np.testing.assert_array_equal(restored.lifetime_spectrum, reader.lifetime_spectrum)
            np.testing.assert_array_equal(restored.rotation_spectrum, reader.rotation_spectrum)
            restored_irf = restored.instrument_response_function
            assert restored_irf.unique_identifier == irf.unique_identifier
            assert restored_irf.name == irf.name and restored_irf.filename == irf.filename
            for field in ("x", "y", "ex", "ey", "mask"):
                assert np.asarray(getattr(restored_irf, field)).dtype == np.asarray(getattr(irf, field)).dtype
                np.testing.assert_array_equal(getattr(restored_irf, field), getattr(irf, field))
        if mode == "local":
            assert imported is cached
        else:
            imports = [request for request in client._client.requests if request["method"] == "dataset.load"]
            assert len(imports) == 1
        assert cs.imported_datasets is global_datasets and cs.fits is global_fits
        assert tuple(global_datasets) == datasets_before and tuple(global_fits) == fits_before
    finally:
        app.close()
