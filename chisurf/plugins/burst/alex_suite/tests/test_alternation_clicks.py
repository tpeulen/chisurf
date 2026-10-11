"""The alternation step's detection buttons and gate (range) fields, pressed and typed with real pointer input.

The known answer is the simulated measurement of :mod:`..demo` (period 8000 ticks, donor laser [0, 3900), acceptor
laser [4000, 7900), donor detector 0, acceptor detector 1). The model tests call ``run()`` directly; these press the
buttons a user presses, so a lost or unwired control fails here.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from chisurf.plugins.burst.alex_suite import demo
from chisurf.plugins.burst.alex_suite.gui.alternation_model import AlexAlternationModel
from chisurf.plugins.emtk_test_input import Driver


@pytest.fixture
def stream(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    return demo.make_demo(tmp_path / "data")


@pytest.fixture
def handed():
    return []


@pytest.fixture
def drv(stream, handed):
    from chisurf.plugins.burst.alex_suite.gui.step_apps import AlternationStepApp

    model = AlexAlternationModel(on_converted=lambda setup, files: handed.append((setup, files)))
    app = AlternationStepApp(model)
    model.set_files(
        [stream], auto=False
    )  # arrive without the automatic run: the buttons do the work
    driver = Driver(app, (1000, 700))
    driver.draw(2)
    return driver


def settle(drv, timeout=120.0):
    end = time.monotonic() + timeout
    while drv.app.running and time.monotonic() < end:
        time.sleep(0.01)
        drv.draw(1)
    assert not drv.app.running
    drv.draw(3)


def within(gate, planted):
    return planted[0] <= gate[0] < gate[1] <= planted[1] and gate[1] - gate[0] > 0.75 * (
        planted[1] - planted[0]
    )


def test_detect_only_button_measures_the_planted_alternation_and_writes_nothing(drv, stream):
    assert drv.app.model.period == 0 and "period" not in drv.app.item_rects  # auto until measured
    drv.click_name("detect_only")
    settle(drv)
    model = drv.app.model
    assert model.period == demo.PERIOD, model.status_text
    assert (model.donor_text, model.acceptor_text) == (
        str(demo.DONOR_CHANNEL),
        str(demo.ACCEPTOR_CHANNEL),
    )
    assert within(model.windows["green"], demo.DONOR_GATE)
    assert within(model.windows["red"], demo.ACCEPTOR_GATE)
    assert not model.converted
    assert sorted(p.name for p in stream.parent.iterdir()) == ["alex_demo.json", "alex_demo.spc"]
    # The measured period and the two gates are now editable fields on the panel.
    for name in ("period", "green_from", "green_to", "red_from", "red_to"):
        assert drv.rect(name)[2] > 0, name


def test_detect_and_convert_button_then_a_typed_gate_republishes_the_setup(
    drv, handed, monkeypatch
):
    monkeypatch.setattr("chisurf.plugins.burst.alex_suite.gui.alternation_model.GATE_SETTLE_S", 0.0)
    drv.click_name("run")
    settle(drv)
    model = drv.app.model
    assert model.period == demo.PERIOD and model.converted
    [(setup, files)] = handed
    assert [Path(p).name for p in files] == ["alex_demo_alex.pto"]
    assert setup["windows"]["prompt"] == model.windows["green"]
    # Define the donor range by hand: the planted laser edges, typed into the gate fields.
    drv.type_into_name("green_from", str(demo.DONOR_GATE[0]))
    drv.type_into_name("green_to", str(demo.DONOR_GATE[1]))
    drv.draw(3)
    assert model.windows["green"] == list(demo.DONOR_GATE)
    assert handed[-1][0]["windows"]["prompt"] == list(demo.DONOR_GATE)
    assert handed[-1][1] == files, "a gate edit republishes the setup and reconverts nothing"


def test_the_phase_tag_names_the_position_it_marks(drv, monkeypatch):
    """The x tag sits at half the period; it said "period 8000" at x = 4000."""
    from chisurf.plugins.burst.alex_suite.gui import app as app_module

    drv.click_name("detect_only")
    settle(drv)
    tags = []
    real = app_module.implot.tag_x
    monkeypatch.setattr(
        app_module.implot, "tag_x", lambda x, colour, fmt="", **kw: (tags.append((x, fmt)), real(x, colour, fmt=fmt, **kw))[1]
    )
    drv.draw(2)
    assert tags, "no phase tag drawn"
    for x, fmt in tags:
        assert fmt.endswith(f"{x:g}"), (x, fmt)
