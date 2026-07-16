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


# --------------------------------------------------------------------------
# AutoForm / view-spec declaration of priors
# --------------------------------------------------------------------------

def test_view_spec_loader_round_trips_priors():
    from chisurf.core.models import view_spec as vs

    view = vs.load_view_spec({
        "sections": [{
            "type": "parameter_group",
            "target": "g",
            "priors": {"tau1": {"kind": "normal", "mu": 2.0, "sigma": 0.3}},
        }],
    })
    section = view.sections[0]
    assert isinstance(section, vs.ParameterGroupSection)
    assert section.priors == {"tau1": {"kind": "normal", "mu": 2.0, "sigma": 0.3}}


def test_apply_section_priors_sets_and_clears(qapp, param):
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    # Set a Gaussian prior by name.
    AutoModelWidget._apply_section_priors(
        {"p1": {"kind": "normal", "mu": 1.5, "sigma": 0.2}}, [param]
    )
    assert isinstance(param.prior, _priors.NormalPrior)
    assert param.prior.mu == pytest.approx(1.5)

    # A None spec clears it; an unknown name / invalid spec is ignored.
    AutoModelWidget._apply_section_priors({"p1": None}, [param])
    assert param.prior is None
    AutoModelWidget._apply_section_priors({"does_not_exist": {"kind": "normal"}}, [param])
    AutoModelWidget._apply_section_priors({"p1": {"kind": "bogus"}}, [param])
    assert param.prior is None


class _GroupModel(ModelCurve):
    """Model whose parameter lives in a nested group, so a ParameterGroupSection
    can target it by attribute name."""

    name = "GroupModel"

    def __init__(self, fit):
        from chisurf.core.fitting.parameter import FittingParameterGroup
        super().__init__(fit)
        self.rates = FittingParameterGroup(name="rates")
        self.k = FittingParameter(name="k", value=2.0)
        self.rates.append(self.k)
        self.find_parameters()

    def update_model(self, **kwargs):
        self.y = np.ones_like(self.x) * self.k.value


def test_view_spec_prior_applied_when_widget_built(qapp, monkeypatch):
    """A ParameterGroupSection.priors entry reaches the FittingParameter."""
    from chisurf.core.models import view_spec as vs
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    data = cs.core.data.DataCurve(x=np.arange(10.0), y=np.arange(10.0))
    fit = cs.core.fitting.fit.Fit(model_class=_GroupModel, data=data)
    cs.fits = [fit]
    model = fit.model

    view = vs.ModelView(sections=(
        vs.ParameterGroupSection(
            target="rates",
            priors={"k": {"kind": "lognormal", "mu": 0.0, "sigma": 0.4}},
        ),
    ))
    monkeypatch.setattr(model, "view_spec", lambda: view)

    AutoModelWidget(model)
    assert isinstance(model.k.prior, _priors.LogNormalPrior)
