"""What Setup -> Settings -> Acquisition stores is where the Acquisition tool starts, and its fields reach the run.

Found walking guide 65 (2026-10-11): the guide sets the simulator to pulsed excitation in Setup -> Settings ->
Acquisition, but the native tool built its simulator from a hard-coded dictionary (CW, one species) and its device
type was always Simulation -- nothing stored there reached a run. And the tool's own *Peak brightness* and
*Deterministic seed* fields were read once, at open, into the advanced JSON the run used: editing them afterwards
changed nothing.
"""

from __future__ import annotations

import numpy as np

from chisurf.plugins.core.acq.gui.app import AcquisitionNativeModel
from chisurf.plugins.core.setup.gui.acq_app import simulation_defaults


def _stored(**changes):
    params = simulation_defaults()
    params.update(
        excitation_mode="Pulsed", pulsed_exc=1, N_species=2, q=[[100.0, 40.0], [50.0, 20.0]]
    )
    params.update(changes)
    return {"device_type": "Simulation", "simulation_params": params}


def test_the_stored_device_type_is_the_tools_device():
    for stored, expected in (
        ("Becker-Hickl", "BH_SPC"),
        ("PicoQuant", "PICOQUANT"),
        ("BrickMic", "BRICKMIC"),
        ("Simulation", "SIMULATION"),
        ("", "SIMULATION"),
    ):
        assert AcquisitionNativeModel(settings={"device_type": stored}).device_type == expected


def test_the_stored_simulator_parameters_are_the_runs_parameters():
    model = AcquisitionNativeModel(settings=_stored(rmt1seed=4242))
    params = model.simulation_params()
    assert (
        params["pulsed_exc"] == 1
        and params["excitation_mode"] == "Pulsed"
        and params["N_species"] == 2
    )
    assert model.brightness_khz == 100.0 and model.seed == 4242
    np.testing.assert_allclose(params["q"], [[100.0, 40.0], [50.0, 20.0]])
    assert params["N_ph_max"] == model.photon_limit


def test_without_stored_parameters_the_built_in_simulation_is_kept():
    model = AcquisitionNativeModel(settings={})
    assert model.stored_simulation is None and model.device_type == "SIMULATION"
    assert model.simulation_params()["q"] == [300.0, 225.0]


def test_brightness_and_seed_edited_after_opening_reach_the_run(monkeypatch):
    model = AcquisitionNativeModel(settings=_stored())
    seen = {}
    monkeypatch.setattr(model, "_run_simulation", lambda params: seen.update(params))
    model.brightness_khz, model.seed, model.photon_limit = 200.0, 7, 999
    assert model.start()
    model._thread.join(5)
    np.testing.assert_allclose(seen["q"], [[200.0, 80.0], [100.0, 40.0]])
    assert seen["rmt1seed"] == 7 and seen["rmt2seed"] == 8 and seen["N_ph_max"] == 999
