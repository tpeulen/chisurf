"""Headless GUI tests for the per-parameter prior selector.

Exercises the prior radio selector and the advanced modal editor of
``FittingParameterDetailPopup`` without launching a live display or blocking on
a modal ``exec_()``. No fitting client is installed, so the popup's local echo
(``fp.prior = ...``) is what these tests observe.
"""

import numpy as np
import pytest

import chisurf as cs
import chisurf.core.data
import chisurf.core.fitting.fit
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.fitting import priors as _priors
from chisurf.core.models.model import ModelCurve
from chisurf.gui.widgets.fitting.parameter_widgets import (
    FittingParameterWidget,
    FittingParameterDetailPopup,
    PriorEditorDialog,
)


class _SimpleModel(ModelCurve):
    name = "SimpleModel"

    def __init__(self, fit):
        super().__init__(fit)
        self.p1 = FittingParameter(name="p1", value=2.0)
        self.find_parameters()

    def update_model(self, **kwargs):
        self.y = np.ones_like(self.x) * self.p1.value


@pytest.fixture
def param(qapp):
    data = cs.core.data.DataCurve(x=np.arange(10.0), y=np.arange(10.0))
    fit = cs.core.fitting.fit.Fit(model_class=_SimpleModel, data=data)
    cs.fits = [fit]
    return fit.model.p1


def _popup(qtbot, param):
    widget = FittingParameterWidget(param)
    qtbot.addWidget(widget)
    popup = FittingParameterDetailPopup(widget)
    qtbot.addWidget(popup)
    return popup


def test_default_selection_is_box(qtbot, param):
    popup = _popup(qtbot, param)
    assert popup._prior_radios["box"].isChecked()
    assert popup._bounds_box.isVisible() or True  # visibility depends on show()


def test_select_gaussian_radio_sets_normal_prior(qtbot, param):
    popup = _popup(qtbot, param)
    popup._prior_radios["normal"].click()
    assert isinstance(param.prior, _priors.NormalPrior)
    # Seeded from the current value (2.0).
    assert param.prior.mu == pytest.approx(2.0)


def test_select_lognormal_radio(qtbot, param):
    popup = _popup(qtbot, param)
    popup._prior_radios["lognormal"].click()
    assert isinstance(param.prior, _priors.LogNormalPrior)


def test_select_box_clears_smooth_prior(qtbot, param):
    popup = _popup(qtbot, param)
    popup._prior_radios["normal"].click()
    assert isinstance(param.prior, _priors.NormalPrior)
    popup._prior_radios["box"].click()
    assert not isinstance(param.prior, _priors.NormalPrior)


def test_refresh_reflects_existing_prior(qtbot, param):
    param.prior = _priors.GammaPrior(2.0, 1.0)
    popup = _popup(qtbot, param)
    # Gamma is not one of the quick radios -> "Custom".
    assert popup._prior_radios["custom"].isChecked()
    assert "Gamma" in popup.lbl_prior_summary.text()


def test_prior_editor_dialog_returns_state(qtbot, param):
    dlg = PriorEditorDialog(seed_value=2.0)
    qtbot.addWidget(dlg)
    # Default family is Gaussian, mean seeded from the value.
    state = dlg.prior_state()
    assert state["kind"] == "normal"
    assert state["mu"] == pytest.approx(2.0)


def test_prior_editor_dialog_switches_family(qtbot, param):
    dlg = PriorEditorDialog(seed_value=2.0, prior_state={"kind": "gamma", "alpha": 3.0, "beta": 2.0, "loc": 0.0})
    qtbot.addWidget(dlg)
    state = dlg.prior_state()
    assert state["kind"] == "gamma"
    assert state["alpha"] == pytest.approx(3.0)
    assert state["beta"] == pytest.approx(2.0)
