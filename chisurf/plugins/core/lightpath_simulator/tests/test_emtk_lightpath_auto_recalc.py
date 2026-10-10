"""Easy Mode "Auto recalculate": an edited input re-runs the simulation; unticked, only the button does."""

from __future__ import annotations

import time

import pytest

from .driving import BIG, LPDriver
from .test_emtk_lightpath_parity import load_catalogue


@pytest.fixture(autouse=True)
def no_window_failed_to_draw(caplog):
    yield
    bad = [r.getMessage() for r in caplog.records if r.levelno >= 40]
    assert not bad, bad[:3]


def easy_mode(app, catalogue):
    drv = LPDriver(app, BIG)
    load_catalogue(app)
    app.controller.reset()
    for node in app.controller.document.nodes:
        if node.type == "detector":
            node.config["probe_id"] = catalogue["APD (flat QE)"]
    drv.settle()
    drv.click_text("Easy Mode")
    drv.draw(3)
    assert app.controller.result == {}
    return drv


def edit_laser_lines(drv, text):
    x, y, w, h = [t[:4] for t in drv.draw(2).texts if t[5] == "Laser lines wavelength:power:"][0]
    drv.click_at(x + 40, y + 24)
    drv.select_all()
    drv.type_text(text)
    drv.enter()


def wait_for_the_pause(drv):
    time.sleep(drv.app.easy.recalculate_delay + 0.1)
    drv.draw(2)
    drv.settle()


def test_an_edited_input_recalculates_by_itself(app, catalogue):
    drv = easy_mode(app, catalogue)
    assert "Auto recalculate" in drv.draw(2).strings
    assert app.easy.auto_recalculate
    edit_laser_lines(drv, "488:0.5, 640:1.0")
    assert app.controller.result == {}  # not before the pause
    wait_for_the_pause(drv)
    assert app.controller.result["detector_signals"]
    assert app.controller.status.startswith("Simulation produced")


def test_unticking_auto_recalculate_leaves_the_button_as_the_only_trigger(app, catalogue):
    drv = easy_mode(app, catalogue)
    drv.click_text("Auto recalculate")
    assert not app.easy.auto_recalculate
    edit_laser_lines(drv, "488:0.5, 640:1.0")
    wait_for_the_pause(drv)
    assert app.controller.result == {}
    drv.click_text("Simulate optical setup")
    drv.settle()
    assert app.controller.result["detector_signals"]


def test_reticking_after_an_edit_recalculates(app, catalogue):
    drv = easy_mode(app, catalogue)
    drv.click_text("Auto recalculate")
    edit_laser_lines(drv, "488:0.5, 640:1.0")
    wait_for_the_pause(drv)
    assert app.controller.result == {}
    drv.click_text("Auto recalculate")
    assert app.easy.auto_recalculate
    wait_for_the_pause(drv)
    assert app.controller.result["detector_signals"]
