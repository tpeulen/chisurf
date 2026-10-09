"""The number fields of the ALEX Suite take typed values, operated with real pointer and keyboard input.

Ranges are the Qt originals': the titration form's (``titration.view.json``), the alternation spin boxes' (period
up to 1e8, each gate edge inside the period).
"""

from __future__ import annotations

import pytest

from chisurf.plugins.burst.alex_suite.gui.app import make_app
from chisurf.plugins.emtk_test_input import Driver


@pytest.fixture
def drv():
    return Driver(make_app())


def test_titration_fit_and_filter_fields_take_typing(drv):
    drv.app.suite_gui.selected_tab = "titration"
    model = drv.app.suite_gui.titration_state.model
    drv.type_into_name("n_populations", "3")
    assert model.n_populations == 3
    drv.type_into_name("n_populations", "9")
    assert model.n_populations == 6
    drv.click_text("> Burst filters")
    drv.type_into_name("min_photons", "-5")
    assert model.min_photons == 0, "a negative photon count is clamped to the Qt minimum"
    drv.type_into_name("bins", "75")
    assert model.bins == 75
    drv.type_into_name("s_low", "-0.25")
    assert model.s_low == -0.25, "the S gate takes a negative value, as in the Qt form"
    drv.type_into_name("s_high", "0.8")
    assert model.s_high == 0.8
    drv.type_into_name("gamma", "1.5")
    assert model.gamma == 1.5
    drv.type_into_name("beta", "0.25")
    drv.type_into_name("beta", "abc")
    assert model.beta == 0.25, "text that is not a number leaves the value"


def test_alternation_period_and_gates_take_typing(drv):
    state = drv.app.suite_gui.alternation_state
    state.period = 1000
    state.windows = {"green": [0, 400], "red": [500, 1000]}
    drv.type_into_name("period", "2000")
    assert state.period == 2000
    drv.type_into_name("green_from", "100")
    assert state.windows["green"] == [100, 400]
    drv.type_into_name("red_to", "5000")
    assert state.windows["red"] == [500, 2000], "a gate edge is clamped to the period"
    drv.type_into_name("red_from", "-30")
    assert state.windows["red"] == [0, 2000]
