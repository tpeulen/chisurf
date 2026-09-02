"""Headless GUI tests for the per-parameter prior selector.

Exercises the single prior-family combo and the **inline** distribution editor
of ``FittingParameterDetailPopup``. The family used to be picked by a radio row
(Box/Gaussian/Log-normal/Custom) that duplicated a second combo listing the full
family set; one combo now selects among Box and every family. The prior
parameters likewise used to live behind a modal and are now edited in the popup
itself, so there is no ``exec_()`` to work around. No fitting client is
installed, so the popup's local echo (``fp.prior = ...``) is what these tests
observe.
"""

import numpy as np
import pytest
from qtpy import QtCore, QtWidgets

import chisurf as cs
import chisurf.core.data
import chisurf.core.fitting.fit
from chisurf.core.fitting import priors as _priors
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.gui.widgets.fitting.parameter_widgets import (
    FittingParameterDetailPopup,
    FittingParameterWidget,
)


class _SimpleModel(ModelCurve):
    name = "SimpleModel"

    def __init__(self, fit):
        super().__init__(fit)
        self.p1 = FittingParameter(name="p1", value=2.0)
        self.find_parameters()

    def _update_model(self, **kwargs):
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


def _select(popup, kind):
    """Pick a prior family in the combo the way a user would."""
    idx = popup.cb_prior_family.findData(kind)
    assert idx >= 0, f"no combo entry for {kind!r}"
    popup.cb_prior_family.setCurrentIndex(idx)


def test_default_selection_is_box(qtbot, param):
    popup = _popup(qtbot, param)
    assert popup.cb_prior_family.currentData() == "box"
    assert popup._bounds_box.isVisibleTo(popup)


def test_every_family_is_reachable_from_the_single_combo(qtbot, param):
    """The combo replaced a radio row that could not reach five of the families."""
    popup = _popup(qtbot, param)
    offered = {
        popup.cb_prior_family.itemData(i) for i in range(popup.cb_prior_family.count())
    }
    assert offered == {
        "box", "normal", "truncated_normal", "lognormal",
        "half_normal", "exponential", "gamma", "beta",
    }


def test_select_gaussian_sets_normal_prior(qtbot, param):
    popup = _popup(qtbot, param)
    _select(popup, "normal")
    assert isinstance(param.prior, _priors.NormalPrior)
    # Seeded from the current value (2.0), width scaled to its magnitude.
    assert param.prior.mu == pytest.approx(2.0)
    assert param.prior.sigma == pytest.approx(0.2)


def test_select_lognormal(qtbot, param):
    popup = _popup(qtbot, param)
    _select(popup, "lognormal")
    assert isinstance(param.prior, _priors.LogNormalPrior)


def test_select_box_clears_smooth_prior(qtbot, param):
    popup = _popup(qtbot, param)
    _select(popup, "normal")
    assert isinstance(param.prior, _priors.NormalPrior)
    _select(popup, "box")
    assert not isinstance(param.prior, _priors.NormalPrior)


def test_refresh_reflects_existing_prior(qtbot, param):
    param.prior = _priors.GammaPrior(2.0, 1.0)
    popup = _popup(qtbot, param)
    # The attached family is selected directly; the inline editor shows its
    # parameters rather than a repr string.
    assert popup.cb_prior_family.currentData() == "gamma"


def test_inline_editor_shows_the_prior_parameters(qtbot, param):
    """Selecting Gaussian must expose mu/sigma spin boxes in the popup itself."""
    popup = _popup(qtbot, param)
    _select(popup, "normal")

    assert set(popup._prior_spins) == {"mu", "sigma"}
    assert popup._prior_spins["mu"].value() == pytest.approx(2.0)
    assert popup.cb_prior_family.currentData() == "normal"


def test_editing_a_prior_parameter_applies_it(qtbot, param):
    """The regression this refactor is for: no OK button, edits apply directly."""
    popup = _popup(qtbot, param)
    _select(popup, "normal")

    popup._prior_spins["sigma"].setValue(0.25)
    popup._prior_spins["sigma"].editingFinished.emit()

    assert isinstance(param.prior, _priors.NormalPrior)
    assert param.prior.sigma == pytest.approx(0.25)


def test_switching_family_in_the_combo_applies_it(qtbot, param):
    popup = _popup(qtbot, param)
    _select(popup, "normal")
    _select(popup, "gamma")

    assert isinstance(param.prior, _priors.GammaPrior)
    assert set(popup._prior_spins) == {"alpha", "beta", "loc"}


def test_editor_is_hidden_for_box(qtbot, param):
    popup = _popup(qtbot, param)
    _select(popup, "normal")
    _select(popup, "box")
    assert not popup._prior_box.isVisibleTo(popup)
    assert popup._bounds_box.isVisibleTo(popup)


def test_existing_prior_populates_the_editor(qtbot, param):
    """Reopening the popup must show the prior that is actually attached."""
    param.prior = _priors.GammaPrior(3.0, 2.0)
    popup = _popup(qtbot, param)

    assert popup.cb_prior_family.currentData() == "gamma"
    assert popup._prior_spins["alpha"].value() == pytest.approx(3.0)
    assert popup._prior_spins["beta"].value() == pytest.approx(2.0)


def test_uneditable_prior_falls_back_to_a_summary(qtbot, param):
    """Callable priors have no parameter list; show what it is, offer no controls."""
    param.prior = _priors.CallablePrior(lambda v: 0.0)
    popup = _popup(qtbot, param)

    # The combo reports it through a read-only "other" entry instead of showing
    # an unrelated family, and no parameter form is offered.
    assert popup.cb_prior_family.currentData() == "__other__"
    assert not popup._prior_form_host.isVisibleTo(popup)
    assert popup.lbl_prior_summary.isVisibleTo(popup)


def test_other_entry_does_not_overwrite_a_script_attached_prior(qtbot, param):
    """Re-selecting the read-only entry must not replace the prior with a guess."""
    prior = _priors.CallablePrior(lambda v: 0.0)
    param.prior = prior
    popup = _popup(qtbot, param)

    popup._on_prior_family_changed()

    assert param.prior is prior


def test_other_entry_is_removed_once_a_real_family_is_picked(qtbot, param):
    param.prior = _priors.CallablePrior(lambda v: 0.0)
    popup = _popup(qtbot, param)
    assert popup.cb_prior_family.findData("__other__") >= 0

    _select(popup, "normal")

    assert popup.cb_prior_family.findData("__other__") < 0


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

    def _update_model(self, **kwargs):
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


# --------------------------------------------------------------------------
# Dismissal: outside click / focus loss only, never an interaction inside
# --------------------------------------------------------------------------

def test_focus_moving_to_a_child_keeps_the_popup_open(qtbot, param):
    """The regression this guards: clicking a spin box closed the popup.

    The popup gets a ``FocusOut`` when one of its own children takes focus, so
    hiding on that event dismissed it on the very interactions it exists for.
    """
    popup = _popup(qtbot, param)
    popup.show()
    qtbot.waitExposed(popup)

    popup.sb_value.setFocus(QtCore.Qt.MouseFocusReason)
    popup._hide_if_focus_left()

    assert popup.isVisible()


def test_focus_leaving_the_popup_hides_it(qtbot, param):
    popup = _popup(qtbot, param)
    popup.show()
    qtbot.waitExposed(popup)

    # Focus owned by nothing inside the popup. Asserting on the check itself
    # rather than on a second window taking focus: an offscreen Qt::Popup holds
    # the keyboard grab, so a real focus hand-off is not reproducible here.
    popup.sb_value.clearFocus()
    popup.clearFocus()
    popup._hide_if_focus_left()

    assert not popup.isVisible()


@pytest.mark.parametrize("child", ["sb_value", "cb_fixed", "cb_bounds_on", "cb_prior_family"])
def test_clicking_a_control_keeps_the_popup_open(qtbot, param, child):
    """Every interactive control must survive being clicked."""
    popup = _popup(qtbot, param)
    popup.show()
    qtbot.waitExposed(popup)
    widget = getattr(popup, child)

    qtbot.mouseClick(widget, QtCore.Qt.LeftButton, pos=widget.rect().center())
    qtbot.wait(20)
    try:
        assert popup.isVisible(), f"clicking {child} dismissed the popup"
    finally:
        if isinstance(widget, QtWidgets.QComboBox):
            # Leaving the drop-down window open crashes qtbot's teardown.
            widget.hidePopup()
            qtbot.wait(20)


def test_prior_dropdown_survives_being_used(qtbot, param):
    """The drop-down lives in its own window, which deactivates this one.

    ``QWidget.isAncestorOf`` is confined to one window and so reported the
    drop-down as foreign, dismissing the popup the moment it opened.
    """
    popup = _popup(qtbot, param)
    popup.show()
    qtbot.waitExposed(popup)

    combo = popup.cb_prior_family
    qtbot.mouseClick(combo, QtCore.Qt.LeftButton, pos=combo.rect().center())
    qtbot.wait(20)
    try:
        assert popup.isVisible(), "opening the prior drop-down dismissed the popup"

        _select(popup, "truncated_normal")
        qtbot.wait(20)
        assert popup.isVisible(), "choosing a family dismissed the popup"
        assert isinstance(param.prior, _priors.TruncatedNormalPrior)
    finally:
        # Leaving the drop-down window open crashes qtbot's teardown.
        combo.hidePopup()
        qtbot.wait(20)


def test_own_dropdown_does_not_count_as_deactivation(qtbot, param):
    """Our own drop-down deactivates this window; an unrelated one must not.

    The deactivation path deliberately ignores the focus widget (Qt keeps it
    pointing into the popup while the app is in the background), so the open
    child window is the only thing telling the two cases apart.
    """
    popup = _popup(qtbot, param)
    popup.show()
    qtbot.waitExposed(popup)

    popup.cb_prior_family.showPopup()
    qtbot.wait(20)
    assert popup._child_window_is_open()
    popup._hide_if_window_deactivated()
    assert popup.isVisible()

    popup.cb_prior_family.hidePopup()
    qtbot.wait(20)
    assert not popup._child_window_is_open()
    popup._hide_if_window_deactivated()
    assert not popup.isVisible()


def test_owns_reaches_across_window_boundaries(qtbot, param):
    """The ownership test must see widgets parented into child windows."""
    popup = _popup(qtbot, param)
    unrelated = QtWidgets.QLineEdit()
    qtbot.addWidget(unrelated)

    assert popup._owns(popup)
    assert popup._owns(popup.sb_value)
    assert popup._owns(popup.cb_prior_family.view())  # separate top-level window
    assert not popup._owns(None)
    assert not popup._owns(unrelated)


def test_click_inside_does_not_hide_the_popup(qtbot, param):
    popup = _popup(qtbot, param)
    popup.show()
    qtbot.waitExposed(popup)

    inside = popup.rect().center()
    qtbot.mouseClick(popup, QtCore.Qt.LeftButton, pos=inside)

    assert popup.isVisible()


def test_click_outside_hides_the_popup(qtbot, param):
    """``Qt.Popup`` grabs the mouse, so an outside click arrives at the popup."""
    popup = _popup(qtbot, param)
    popup.show()
    qtbot.waitExposed(popup)

    outside = QtCore.QPoint(popup.width() + 50, popup.height() + 50)
    qtbot.mouseClick(popup, QtCore.Qt.LeftButton, pos=outside)

    assert not popup.isVisible()


def test_auto_hide_is_suspended_while_a_menu_is_open(qtbot, param):
    """Opening the link menu deactivates the window; the popup must survive."""
    popup = _popup(qtbot, param)
    popup.show()
    qtbot.waitExposed(popup)

    def deactivate():
        QtWidgets.QApplication.sendEvent(
            popup, QtCore.QEvent(QtCore.QEvent.WindowDeactivate)
        )
        qtbot.wait(20)  # the dismissal check is deferred to the event loop

    popup._begin_suspend_auto_hide()
    deactivate()
    assert popup.isVisible(), "the popup closed while its link menu was open"

    # Once the menu is done, the same deactivation does dismiss it.
    popup._end_suspend_auto_hide()
    deactivate()
    assert not popup.isVisible()
