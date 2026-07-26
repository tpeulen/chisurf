"""AutoForm must not aim a fit-targeted action at somebody else's fit.

``_own_fit_index`` answers "which fit does this bound model belong to". When
the model's fit is not registered with the fit machinery — a scripted or
headless fit, or a tool with no fit at all — it used to answer ``0``, which is
not "unknown" but *another fit*. Against an empty ``chisurf.fits`` that raised
(the edit was logged as a failed commit and the host was never rebuilt);
against a populated one it would have dispatched the edit at whichever fit
happened to be first. It now answers ``-1`` and the dispatch is skipped.
"""

import numpy as np
import pytest

import chisurf as cs


@pytest.fixture()
def unregistered_fit():
    """Return a fit that was never added to ``chisurf.fits``."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader
    from chisurf.core.models.pda3c.tcpda import TcPdaModel

    data = Pda3cSimulatorReader(n_bursts=100, seed=5).read()[0]
    fit = fit_mod.Fit(model_class=TcPdaModel, data=data)
    assert all(fit is not group and fit not in list(group) for group in cs.fits)
    return fit


def test_an_unregistered_fit_reports_no_index(qapp, unregistered_fit):
    """The lookup says "not mine" rather than naming fit zero."""
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.builtin import _BoundControlMixin

    form = AutoForm(unregistered_fit.model)
    bound = form.findChildren(_BoundControlMixin)
    assert bound, "expected at least one bound control in the tcPDA editor"
    assert all(widget._own_fit_index() < 0 for widget in bound)


def test_committing_a_value_still_applies_it(qapp, unregistered_fit, caplog):
    """The edit reaches the model, and nothing is logged as a failed commit."""
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.builtin import _BoundControlMixin

    model = unregistered_fit.model
    form = AutoForm(model)
    toggle = [
        widget for widget in form.findChildren(_BoundControlMixin)
        if getattr(getattr(widget, "_section", None), "attr", "") == "dynamic"
    ]
    assert toggle, "the Exchange panel should bind the dynamic toggle"

    assert model.dynamic is False
    with caplog.at_level("WARNING"):
        toggle[0]._commit(True)

    assert model.dynamic is True
    assert not [r for r in caplog.records if "commit failed" in r.getMessage()]


def test_the_guard_skips_dispatch_for_a_negative_index(monkeypatch):
    """``_dispatch_fit_update`` is the single place the guard is spelled."""
    from chisurf.gui.autoform.sections import builtin

    dispatched = []
    monkeypatch.setattr(
        builtin.cs.core.actions, "dispatch",
        lambda **kwargs: dispatched.append(kwargs),
    )
    builtin._dispatch_fit_update(-1)
    assert dispatched == []
    builtin._dispatch_fit_update(0)
    assert dispatched == [{"name": "fit.update", "payload": {"fit_index": 0}}]


def test_a_registered_fit_is_found(qapp, unregistered_fit):
    """A fit the machinery knows about still resolves to its own index."""
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.builtin import _BoundControlMixin

    fit = unregistered_fit
    cs.fits.append(fit)
    try:
        form = AutoForm(fit.model)
        bound = form.findChildren(_BoundControlMixin)
        assert any(widget._own_fit_index() == cs.fits.index(fit) for widget in bound)
        assert all(widget._own_fit_index() >= 0 for widget in bound)
    finally:
        cs.fits.remove(fit)


def test_the_rate_grid_survives_an_unregistered_fit(qapp, unregistered_fit):
    """The scheme grid still edits the parameters without a registered fit.

    The failure this guards is silent: the commit raised on the fit dispatch
    *after* writing the value, so the value stuck but the form never rebuilt.
    """
    from chisurf.gui.autoform import AutoForm

    model = unregistered_fit.model
    model.species.append(r_gr=68.0, r_bg=62.0, r_br=80.0)
    model.find_parameters()
    AutoForm(model)

    model.rate_values = [0.0, 250.0, 400.0, 0.0]
    assert model.rates_by_name()["k1_2"].value == pytest.approx(250.0)
    assert np.allclose(model.rate_matrix, np.array([[0.0, 400.0], [250.0, 0.0]]))
