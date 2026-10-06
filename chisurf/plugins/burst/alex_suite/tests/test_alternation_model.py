"""The Qt-free alternation model (card AS1) on the simulated µs-ALEX measurement, whose answer is planted.

The demo stream (:mod:`..demo`) has a 8000-tick period, the donor laser on in [0, 3900) and the acceptor laser in
[4000, 7900), donor detector 0 and acceptor detector 1, and every micro-time 0. Arriving with it, the model must
measure all of that, fold the alternation into one ``.pto`` beside the file and hand on a setup in the Seidel names.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chisurf.plugins.burst.alex_suite import demo
from chisurf.plugins.burst.alex_suite.gui.alternation_model import (
    SETUP_NAME,
    AlexAlternationModel,
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
    assert (model.donor_text, model.acceptor_text) == (str(demo.DONOR_CHANNEL), str(demo.ACCEPTOR_CHANNEL))
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
    assert sorted(p.name for p in stream.parent.iterdir()) == ["alex_demo.spc"]


def test_bad_channel_fields_are_refused(stream):
    model = AlexAlternationModel()
    model.set_files([stream], auto=False)
    model.donor_text = "zero"
    assert not model.run()
    assert model.status_text.startswith("Channels:")
    model.donor_text, model.acceptor_text = "0", "auto"
    assert not model.run()
    assert "both channel assignments or neither" in model.status_text
