"""Tests for the AutoForm-backed acquisition photon simulator."""

from __future__ import annotations

import queue
import threading

import pytest


def test_simulation_settings_model_serializes_enabled_channels():
    """The AutoForm model should emit tttrlib-compatible channel vectors.

    Brightness is per species and comes from ``species_q``, six slots each in
    the order (green parallel, green perpendicular, red ∥, red ⊥, yellow ∥,
    yellow ⊥). The single-species ``q_green_p``-style fields this test used to
    set were write-only -- ``to_parameters`` had stopped reading them, so the
    values here were silently replaced by the defaults -- and are now gone.
    """
    from chisurf.plugins.core.acq.tcspc_devices.simulation.settings_model import (
        SimulationSettingsModel,
    )

    model = SimulationSettingsModel(
        n_species=2,
        green_enabled=True,
        red_enabled=True,
        yellow_enabled=False,
        species_q=[11.0, 12.0, 21.0, 22.0, 0.0, 0.0] * 2,
        n_ph_max=123,
        n_ph_per_file=10,
    )

    params = model.to_parameters()

    assert params["N_species"] == 2
    assert params["N_channels"] == 4
    assert params["q"] == [11.0, 12.0, 21.0, 22.0, 11.0, 12.0, 21.0, 22.0]
    assert params["ch_conversion"] == [8, 9, 10, 11]
    assert params["N_ph_max"] == 123
    assert params["N_ph_per_file"] == 10


def test_simulation_setup_dialog_renders_autoform():
    """The setup dialog renders its AutoForm view.json and hands its parameters to OK."""
    from emtk.testing import RecordingPainter

    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel
    from chisurf.plugins.core.acq.gui.sim_setup import SimulationSetupDialog

    app = AcquisitionApp(AcquisitionNativeModel())
    applied = []
    try:
        dialog = SimulationSetupDialog(None, on_apply=applied.append)
        app.sim_setup = dialog
        dialog.show()
        for _ in range(3):
            painter = RecordingPainter()
            app.draw(painter, 0, 0, 900, 1000)
        assert "Simulation Setup" in painter.strings and "Acquisition" in painter.strings
        dialog.apply()
    finally:
        app.close()
    assert len(applied) == 1
    params = applied[0]
    assert params["N_species"] == 1
    assert params["N_channels"] == 2
    assert params["pulsed_exc"] == 0


def test_tttrlib_streaming_writes_split_spc_files(tmp_path):
    """The tttrlib backend should stream words and split SPC output files."""
    tttrlib = pytest.importorskip("tttrlib")
    if not hasattr(tttrlib, "SimEngine"):
        pytest.skip("tttrlib photon simulator is unavailable")

    from chisurf.plugins.core.acq.tcspc_devices.simulation.core.streaming import (
        TttrlibSimulator,
    )

    params = {
        "N_species": 1,
        "M": [1.0],
        "D": [1.0],
        "N_channels": 2,
        "q": [5.0, 5.0],
        "q_bg": [0.0, 0.0],
        "k_rad": [0.0],
        "k_nrad": [0.0],
        "box_xy": 2.0,
        "box_z": 4.0,
        "focus_param": [0.3, 2.0],
        "dt": 0.01,
        "N_ph_max": 12,
        "N_ph_per_file": 3,
        "spc_output_path": str(tmp_path),
        "stream_words_per_batch": 4,
    }
    data_queue = queue.Queue()
    stop_event = threading.Event()
    simulator = TttrlibSimulator()

    assert simulator.simulate_photons_streaming(params, data_queue, stop_event)
    simulator.generation_thread.join(timeout=30)
    assert not simulator.generation_thread.is_alive()

    chunks = []
    while True:
        item = data_queue.get_nowait()
        if item is None:
            break
        chunks.append(item)

    assert chunks
    files = sorted(tmp_path.glob("m*.spc"))
    assert files
    assert tttrlib.TTTR(str(files[0]), "SPC-130").get_n_valid_events() > 0
    assert (tmp_path / "simulation_config.json").exists()


def _decoded_channels(params, tmp_path):
    """Run the simulation for ``params`` and return decoded routing channels."""
    import numpy as np
    import tttrlib

    from chisurf.plugins.core.acq.tcspc_devices.simulation.core import algorithms as alg

    engine = alg.build_engine(params)
    engine.run()
    words = alg.encode_records(engine, params)
    path = str(tmp_path / "sim.spc")
    enc = tttrlib.SimMicrotimeEncoder()
    with open(path, "wb") as fh:
        fh.write(bytes(enc.file_bytes(bytes(words.tobytes()))))
    tttr = tttrlib.TTTR(path, "SPC-130")
    return set(int(c) for c in np.unique(tttr.routing_channels))




@pytest.mark.parametrize(
    "red,yellow,expected",
    [(False, False, {8, 9}), (True, False, {8, 9, 10, 11}), (True, True, set(range(8, 14)))],
)
def test_simulation_detectors_decode_to_declared_channels(tmp_path, red, yellow, expected):
    """Each simulated detector must decode to the hardware channel the model declares.

    ``ch_conversion`` is tttrlib's index map (entry ``i`` = hardware channel of
    simulated channel ``i``). A flat ``det, src`` pair list silently sends the
    second detector to channel 0.
    """
    from chisurf.plugins.core.acq.tcspc_devices.simulation.settings_model import (
        SimulationSettingsModel,
    )

    model = SimulationSettingsModel(
        n_species=1,
        green_enabled=True,
        red_enabled=red,
        yellow_enabled=yellow,
        species_q=[50.0] * 6,
        n_ph_max=20000,
        n_ph_per_file=20000,
    )
    params = model.to_parameters()
    assert params["ch_conversion"] == sorted(expected)
    assert _decoded_channels(params, tmp_path) == expected
