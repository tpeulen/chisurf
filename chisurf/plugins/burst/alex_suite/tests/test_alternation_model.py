"""The Qt-free alternation model (card AS1) on the simulated µs-ALEX measurement, whose answer is planted.

The demo stream (:mod:`..demo`) has a 8000-tick period, the donor laser on in [0, 3900) and the acceptor laser in
[4000, 7900), donor detector 0 and acceptor detector 1, and every micro-time 0. Arriving with it, the model must
measure all of that, fold the alternation into one ``.pto`` beside the file and hand on a setup in the Seidel names.
"""

from __future__ import annotations

from pathlib import Path

import copy

import numpy as np
import pytest

from chisurf.plugins.burst.alex_suite import demo
from chisurf.plugins.burst.alex_suite.gui.alternation_model import (
    SETUP_NAME,
    AlexAlternationModel,
    container_setup,
    needs_conversion,
)


@pytest.fixture
def stream(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    return demo.make_demo(tmp_path / "data")


def test_arrival_detects_and_converts_the_demo(stream):
    handed = []
    model = AlexAlternationModel(on_converted=lambda setup, files: handed.append((setup, files)))
    assert needs_conversion(stream)
    model.set_files([stream])
    assert model.running or model.result is not None
    model.wait()
    assert model.period == demo.PERIOD
    assert (model.donor_text, model.acceptor_text) == (
        str(demo.DONOR_CHANNEL),
        str(demo.ACCEPTOR_CHANNEL),
    )
    green, red = model.windows["green"], model.windows["red"]
    assert demo.DONOR_GATE[0] <= green[0] < green[1] <= demo.DONOR_GATE[1]
    assert demo.ACCEPTOR_GATE[0] <= red[0] < red[1] <= demo.ACCEPTOR_GATE[1]
    assert "100.0 µs" in model.detail_text
    assert model.phase_hist["donor"].size == 200
    [(setup, files)] = handed
    assert [Path(p).name for p in files] == ["alex_demo_alex.pto"]
    assert Path(files[0]).parent == stream.parent, "the container is written beside the measurement"
    assert not needs_conversion(files[0]), "the container has its micro-time: never folded twice"
    assert setup["setup_name"] == SETUP_NAME
    assert setup["windows"] == {"prompt": green, "delayed": red}
    assert setup["detectors"]["yellow"]["chs"] == [demo.ACCEPTOR_CHANNEL]
    assert "Press Next" in model.status_text


def test_a_gate_edit_republishes_the_setup_without_reconverting(stream, monkeypatch):
    handed = []
    model = AlexAlternationModel(on_converted=lambda setup, files: handed.append(setup))
    model.set_files([stream])
    model.wait()
    container = list(model.converted)
    model.set_gate("green", 300, 3600)
    monkeypatch.setattr("chisurf.plugins.burst.alex_suite.gui.alternation_model.GATE_SETTLE_S", 0.0)
    assert model.poll()
    assert handed[-1]["windows"]["prompt"] == [300, 3600]
    assert model.converted == container
    model.set_gate("red", 5000, 4000)  # inverted: refused, setup unchanged
    model.poll()
    assert "start below its end" in model.status_text
    assert handed[-1]["windows"]["prompt"] == [300, 3600]


def test_detect_only_writes_nothing(stream):
    model = AlexAlternationModel()
    model.set_files([stream], auto=False)
    assert model.run(convert=False)
    model.wait()
    assert model.period == demo.PERIOD and not model.converted
    assert sorted(p.name for p in stream.parent.iterdir()) == ["alex_demo.json", "alex_demo.spc"]


def test_bad_channel_fields_are_refused(stream):
    model = AlexAlternationModel()
    model.set_files([stream], auto=False)
    model.donor_text = "zero"
    assert not model.run()
    assert model.status_text.startswith("Channels:")
    model.donor_text, model.acceptor_text = "0", "auto"
    assert not model.run()
    assert "both channel assignments or neither" in model.status_text


# -- the "pie" pass-through: a container converted earlier carries its setup ------------------------- #

STORED_DETECTORS = {
    "green": {
        "chs": [demo.DONOR_CHANNEL],
        "g_factor": 1.0,
        "l1": 0.0,
        "l2": 0.0,
        "micro_time_ranges": [[100, 3900]],
    },
    "yellow": {
        "chs": [demo.ACCEPTOR_CHANNEL],
        "g_factor": 1.0,
        "l1": 0.0,
        "l2": 0.0,
        "micro_time_ranges": [[4000, 7900]],
    },
}


def _store_background_estimate(container: Path, detectors: dict, *, wrapped: bool) -> None:
    """Record a background estimate in the container, the way the Background step writes it."""
    from chisurf.core.fio.pto import Measurement

    names = list(detectors)
    parameters = {"detectors": copy.deepcopy(detectors)} if wrapped else copy.deepcopy(detectors)
    with Measurement.open(container, writable=True) as measurement:
        measurement.put_table(
            "background",
            {
                "Detector": np.array(names, dtype=object),
                "Rate": np.array([2.0] * len(names)),
                "Amplitude": np.array([1.0] * len(names)),
            },
            artifact_kind="background_data",
            operation_type="background_correction",
            row_grain="channel",
            parameters=parameters,
            derived_from=measurement.instrument_uids or measurement.instrument_uid,
        )


@pytest.fixture
def converted(stream):
    """The demo measurement converted once by this suite (a container with a micro-time)."""
    model = AlexAlternationModel()
    model.set_files([stream])
    model.wait()
    container = Path(model.converted[0])
    assert not needs_conversion(container)
    return container


@pytest.mark.parametrize("wrapped", [True, False], ids=["current-writer", "bare-detectors"])
def test_a_converted_container_adopts_its_stored_setup(converted, wrapped):
    """Arriving with a container this suite converted earlier republishes the setup it stores.

    The fold is already in the micro-time (decision "pie", nothing re-detected, no file written) —
    but without the stored setup every later step was handed the measurement and no detectors,
    and the Background step refused the estimate and swallowed the reason.
    """
    _store_background_estimate(converted, STORED_DETECTORS, wrapped=wrapped)
    handed = []
    model = AlexAlternationModel(on_converted=lambda setup, files: handed.append((setup, files)))
    model.set_files([converted])
    assert model.decision == "pie" and not model.converted and not model.running
    [(setup, files)] = handed
    assert files == [], "the container stays the workflow's measurement"
    assert setup["setup_name"] == SETUP_NAME
    assert setup["detectors"] == STORED_DETECTORS
    assert setup["windows"] == {
        "prompt": STORED_DETECTORS["green"]["micro_time_ranges"][0],
        "delayed": STORED_DETECTORS["yellow"]["micro_time_ranges"][0],
    }
    assert setup["tttr_reading"]["file_type"] == "PTO"
    assert "stored detector setup" in model.status_text
    # reading it again gives the same answer (the hub may adopt on every arrival)
    assert container_setup(converted)["detectors"] == STORED_DETECTORS


def test_a_container_without_a_stored_setup_is_left_alone(converted):
    handed = []
    model = AlexAlternationModel(on_converted=lambda setup, files: handed.append(setup))
    model.set_files([converted])
    assert model.decision == "pie" and handed == []
    assert "nothing to convert" in model.status_text


def test_the_stored_setup_reader_refuses_what_is_not_its_own(tmp_path):
    plain = tmp_path / "measurement.spc"
    plain.write_bytes(b"not a container")
    assert container_setup(plain) == {}
    assert container_setup(tmp_path / "missing.pto") == {}
