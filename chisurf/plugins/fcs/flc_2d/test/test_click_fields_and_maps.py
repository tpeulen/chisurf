"""2D-FLCS: typed and clamped fields, the Sim / Run buttons and the map controls, pressed on the drawn widgets.

The stream is the plugin's own two-state simulator (lifetimes 1 and 3 ns); what is asserted is what the user reads:
the value a field shows after typing, the grid of the resolved spectrum, the status line and the map's colormap.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from emtk import keys
from emtk.testing import Driver

CTRL_A = 0x04000000


@pytest.fixture
def app_driver():
    from chisurf.plugins.fcs.flc_2d.gui.app import make_app

    app = make_app()
    driver = Driver(app, (1400, 900))
    driver.frame(3)
    yield app, driver
    app.close()


def settle(app, driver, limit=240.0):
    end = time.monotonic() + limit
    driver.frame(1)
    while app.job.busy:
        assert time.monotonic() < end, "the worker did not finish"
        time.sleep(0.02)
        driver.frame(1)
    return driver.frame(3)


def type_into(driver, name, text):
    driver.click(name)
    driver.surface.on_key_press(0x41, "a", CTRL_A)
    driver.frame()
    driver.type(text)
    driver.press(keys.KEY_RETURN)


def shown(driver):
    return [t[5] for t in driver.painter.texts]


@pytest.mark.parametrize(
    ("name", "typed", "expected"),
    [
        ("n_components", "500", 80),
        ("n_components", "1", 4),
        ("n_components", "24", 24),
        ("tau_min_ns", "0", 0.01),
        ("tau_max_ns", "5000", 1000.0),
        ("log10_reg", "99", 6.0),
        ("log10_reg", "-99", -12.0),
        ("max_bins", "1000", 256),
        ("max_bins", "2", 16),
        ("tmax_ns", "5000", 1000.0),
        ("dT_ms", "-5", 0.0),
    ],
)
def test_typed_values_are_clamped_to_the_declared_range(app_driver, name, typed, expected):
    app, driver = app_driver
    type_into(driver, name, typed)
    assert getattr(app.model, name) == pytest.approx(expected)
    # the field shows the stored value, not what was typed
    assert any(float(t) == pytest.approx(expected) for t in shown(driver) if _is_number(t))


def _is_number(text):
    try:
        float(text)
    except ValueError:
        return False
    return True


def test_text_that_is_not_a_number_leaves_the_value_alone(app_driver):
    app, driver = app_driver
    before = app.model.tau_max_ns
    type_into(driver, "tau_max_ns", "abc")
    assert app.model.tau_max_ns == before


def test_sim_run_and_the_inversion_settings_shape_the_result(app_driver):
    app, driver = app_driver
    model = app.model
    assert not model.enabled("request_run")
    driver.click("Run")  # no stream yet: nothing starts
    assert not app.job.busy and model.spectrum_image() is None

    driver.click("Simulator.fold")
    type_into(driver, "sim_time_s", "30")
    assert model.sim_time_s == 30.0
    driver.click("Sim")
    settle(app, driver)
    assert not model.error_text, model.error_text
    assert model.tttr is not None and model.tttr.n_photons > 100000
    assert model.enabled("request_run")

    type_into(driver, "n_components", "24")
    type_into(driver, "tau_min_ns", "0.5")
    type_into(driver, "tau_max_ns", "6")
    driver.click("Run")
    assert app.job.busy
    settle(app, driver)
    assert not model.error_text, model.error_text
    lifetime = model._lifetime
    assert len(lifetime["tau"]) == 24
    assert lifetime["tau"][0] == pytest.approx(0.5) and lifetime["tau"][-1] == pytest.approx(6.0)
    assert model.spectrum_image().shape == (24, 24)
    assert model.status_text.startswith("Resolved lifetimes: tau =")
    assert model.status_text in shown(driver)
    # the status line names the resolved lifetimes, inside the typed grid; the dominant one is the 3 ns species
    resolved = [float(v) for v in model.status_text.split("tau =")[1].replace("ns", "").split(",")]
    assert resolved and all(0.5 <= tau <= 6.0 for tau in resolved), model.status_text
    assert resolved[-1] == pytest.approx(3.0, rel=0.2)
    first_residual = float(np.abs(model.residual_image()).sum())

    # a much stronger regularisation (typed log10 of lambda) fits the data worse
    type_into(driver, "log10_reg", "4")
    driver.click("Run")
    settle(app, driver)
    assert not model.error_text, model.error_text
    assert float(np.abs(model.residual_image()).sum()) > first_residual
    data = model.lcurve_data()
    assert data is not None and 0 <= int(data.corner_index) < len(data.residual_norm)


def test_the_map_colormap_control_recolours_both_maps(app_driver):
    app, driver = app_driver
    model = app.model
    driver.click("Simulator.fold")
    type_into(driver, "sim_time_s", "5")
    driver.click("Sim")
    settle(app, driver)
    type_into(driver, "n_components", "16")
    driver.click("Run")
    settle(app, driver)
    assert model.spectrum_image() is not None
    driver.click("2D-FLCS map")  # the dock's tab
    driver.frame(3)
    assert "Colormap" in shown(driver) and "Reset view" in shown(driver)
    assert model.colormap == "viridis"
    driver.click("viridis")
    driver.click("magma")
    driver.frame(3)
    assert model.colormap == "magma"
    driver.click("2D residual")
    driver.frame(3)
    assert "magma" in shown(driver), "the residual map follows the colormap chosen on the spectrum map"
    assert {c.colormap for c in app.canvases.values()} == {"magma"}
    driver.click("Reset view")
    driver.frame(2)
    assert not model.error_text
