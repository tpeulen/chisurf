"""The number fields of the ALEX Suite: integers step with the arrow keys, floats take typed values.

Ranges are the Qt originals': the titration form's (``titration.view.json``), the alternation spin boxes' (period
up to 1e8, each gate edge inside the period).
"""

from __future__ import annotations

import pytest
from emtk import keys

from chisurf.plugins.burst.alex_suite.gui.app import make_app
from chisurf.plugins.emtk_test_input import Driver


@pytest.fixture
def drv():
    return Driver(make_app())


def step_name(drv, name, code, times=1):
    """Click the integer field *name* and press an arrow key *times* times."""
    drv.click(drv.rect(name))
    for _ in range(times):
        drv.press(code)


def test_titration_integer_fields_step_and_float_fields_take_typing(drv):
    drv.app.suite_gui.selected_tab = "titration"
    model = drv.app.suite_gui.titration_state.model
    n0 = model.n_populations
    step_name(drv, "n_populations", keys.KEY_UP)
    assert model.n_populations == n0 + 1
    model.n_populations = 6
    step_name(drv, "n_populations", keys.KEY_UP)
    assert model.n_populations == 6, "the population count is clamped to the form's maximum"
    drv.click_text("> Burst filters")
    model.min_photons = 0
    step_name(drv, "min_photons", keys.KEY_DOWN)
    assert model.min_photons == 0, "a photon count is clamped to the Qt minimum"
    b0 = model.bins
    step_name(drv, "bins", keys.KEY_UP)
    assert model.bins == b0 + 1
    drv.type_into_name("s_low", "-0.25")
    assert model.s_low == -0.25, "the S gate takes a negative value, as in the Qt form"
    drv.type_into_name("s_high", "0.8")
    assert model.s_high == 0.8
    drv.type_into_name("gamma", "1.5")
    assert model.gamma == 1.5
    drv.type_into_name("beta", "0.25")
    drv.type_into_name("beta", "abc")
    assert model.beta == 0.25, "text that is not a number leaves the value"


def test_alternation_period_and_gates_step_with_the_arrows(drv):
    state = drv.app.suite_gui.alternation_state
    state.period = 1000
    state.windows = {"green": [0, 400], "red": [500, 1000]}
    step_name(drv, "period", keys.KEY_UP)
    assert state.period == 1001
    step_name(drv, "green_from", keys.KEY_UP)
    assert state.windows["green"] == [1, 400]
    step_name(drv, "red_to", keys.KEY_UP)
    assert state.windows["red"] == [500, 1001], "a gate edge steps up to the period"
    step_name(drv, "red_to", keys.KEY_UP)
    assert state.windows["red"] == [500, 1001], "a gate edge is clamped to the period"
    state.windows["red"] = [0, 1001]
    step_name(drv, "red_from", keys.KEY_DOWN)
    assert state.windows["red"] == [0, 1001], "a gate edge is clamped to zero"
