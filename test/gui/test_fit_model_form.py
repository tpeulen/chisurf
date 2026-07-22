"""The registry-driven MLE fit-model parameter form widget.

:class:`~chisurf.gui.widgets.fit_model_form.FitModelForm` builds its model
chooser and parameter form from tttrlib's ``fit`` registry (fit23/24/25/26), so
there is no per-model widget code to test — only that the widget reflects the
registry, switches cleanly, restores saved state, and degrades when no registry
is published.
"""

import pytest

pytest.importorskip("qtpy.QtWidgets", reason="no Qt binding installed")

from chisurf.core.fluorescence.mle import registry as fit_registry  # noqa: E402
from chisurf.gui.widgets.fit_model_form import FitModelForm  # noqa: E402

pytestmark = pytest.mark.skipif(
    not fit_registry.is_available(),
    reason="installed tttrlib publishes no fit-model registry",
)


def test_combobox_offers_every_registry_model(qapp):
    form = FitModelForm()
    offered = {form.combo_model.itemData(i) for i in range(form.combo_model.count())}
    assert offered == set(fit_registry.fit_models())
    assert form.combo_model.isEnabled()


def test_parameters_default_to_the_registry_values(qapp):
    form = FitModelForm(model="fit23")
    assert form.model == "fit23"
    # tttrlib describes fit23 as tau/gamma/r0/rho with these defaults.
    assert set(form.parameters) == {"tau", "gamma", "r0", "rho"}
    assert form.parameters["tau"] == pytest.approx(2.0)


def test_switching_model_reflows_the_parameters(qapp):
    form = FitModelForm(model="fit23")
    form.set_state("fit25")
    assert form.model == "fit25"
    # fit25 selects among four lifetimes — a different parameter set entirely.
    # r0 is a fixed input in its initial_values vector (schema-declared).
    assert list(form.parameters) == ["tau1", "tau2", "tau3", "tau4", "gamma", "r0"]


def test_saved_state_is_restored(qapp):
    form = FitModelForm()
    form.set_state("fit23", {"tau": 3.5})
    assert form.model == "fit23"
    assert form.parameters["tau"] == pytest.approx(3.5)


def test_parameters_changed_signal_fires_on_model_switch(qapp):
    form = FitModelForm(model="fit23")
    fired = []
    form.parametersChanged.connect(lambda: fired.append(1))
    idx = form.combo_model.findData("fit24")
    form.combo_model.setCurrentIndex(idx)
    assert fired and form.model == "fit24"
