"""The kinetic reaction-scheme model, and the core reaction system under it.

Its predecessor ``ReactionWidget`` was abstract — it never implemented
``update_model`` — so nothing in this area had ever been exercised end to end and
the reaction system below it carried several failures that only a caller would
find. Each test here is one of them.
"""
from __future__ import annotations

import numpy as np
import pytest


def _reaction_system():
    """Return an ``A ⇌ B`` system with rates 2 and 1, ready to integrate."""
    from chisurf.core.math.reaction.continuous import ReactionSystem

    rs = ReactionSystem()
    rs.add_reaction(
        educts=[0], products=[1],
        educt_stoichiometry=[1], product_stoichometry=[1], rate=2.0,
    )
    rs.add_reaction(
        educts=[1], products=[0],
        educt_stoichiometry=[1], product_stoichometry=[1], rate=1.0,
    )
    return rs


def test_reaction_system_relaxes_to_the_analytic_equilibrium():
    """The integration reaches ``k_f/k_r`` — it used to return a flat line.

    ``reactions`` returned a ``zip``, and ``odeint`` calls ``rate_equation`` once
    per step with that same object: it is exhausted after the first call, so
    every subsequent derivative was zero and the concentrations never moved off
    their initial values. For ``A ⇌ B`` with k_f = 2, k_r = 1 the equilibrium is
    [A] = 1/3, [B] = 2/3.
    """
    rs = _reaction_system()
    rs.initial_concentrations = [1.0, 0.0]
    rs.species_brightness = [1.0, 2.0]
    rs.times = np.linspace(0.0, 20.0, 200)
    rs.calc()

    signal = np.asarray(rs.signal_intensity, dtype=float)
    assert signal.size == 200
    assert signal[0] == pytest.approx(1.0)
    # brightness-weighted equilibrium: 1*(1/3) + 2*(2/3)
    assert signal[-1] == pytest.approx(1.0 / 3.0 + 2.0 * 2.0 / 3.0, rel=1e-4)
    assert np.all(np.diff(signal) >= -1e-9), "the relaxation is not monotone"


def test_reaction_system_reactions_is_reusable():
    """``reactions`` can be iterated more than once (it is a list, not a ``zip``)."""
    rs = _reaction_system()
    assert len(list(rs.reactions)) == 2
    assert len(list(rs.reactions)) == 2


def test_reaction_system_n_species_counts_rather_than_raising():
    """``n_species`` no longer raises ``NameError``.

    ``reduce`` was never imported and the ``except`` only caught ``TypeError``,
    so *every* call raised — including the one the editor makes to size its
    species table.
    """
    rs = _reaction_system()
    assert rs.n_species == 2


def test_reaction_system_brightness_round_trips_a_plain_list():
    """Assigning a list of numbers to ``species_brightness`` reads back.

    The setter stored whatever it was given while the getter read ``.value`` off
    each entry, so the obvious assignment made every later read raise
    ``AttributeError``.
    """
    rs = _reaction_system()
    rs.species_brightness = [1.0, 2.5]
    assert rs.species_brightness == pytest.approx([1.0, 2.5])


def test_reaction_system_rates_are_fittable():
    """Rate constants are ``FittingParameter``s — they are what the fit varies."""
    from chisurf.core.fitting.parameter import FittingParameter

    rs = _reaction_system()
    assert all(isinstance(r, FittingParameter) for r in rs.rates)


# ---------------------------------------------------------------------------
# the model
# ---------------------------------------------------------------------------
def _make_fit():
    """Return a fit over a synthetic single-exponential relaxation."""
    import chisurf.core.fitting.fit as fit_mod

    from chisurf.core.data import DataCurve
    from chisurf.core.models.stopped_flow.reaction import ReactionModel

    x = np.linspace(0.0, 10.0, 200)
    data = DataCurve(
        name="stopped-flow", load_filename_on_init=False,
        x=x, y=1.0 - 0.5 * np.exp(-x),
    )
    return fit_mod.Fit(model_class=ReactionModel, data=data)


def test_reaction_model_opens_on_a_scheme_that_computes():
    """The model constructs, seeds a scheme, and produces a finite curve.

    Opening it at all is the assertion: the registered predecessor was abstract,
    so selecting it in the model menu raised ``TypeError`` before anything else
    could happen.
    """
    fit = _make_fit()
    model = fit.model
    assert model.n_reactions == 2
    assert model.species_names == ["A", "B"]

    model.update_model()
    y = np.asarray(model.y, dtype=float)
    assert y.size == np.asarray(fit.data.y).size
    assert np.all(np.isfinite(y))
    assert np.ptp(y) > 0.0, "the model produced a flat line"


def test_reaction_model_rate_changes_the_relaxation():
    """A faster forward rate reaches the plateau sooner."""
    model = _make_fit().model
    model.update_model()
    slow = np.asarray(model.y, dtype=float).copy()

    model.rates[0].value = 10.0 * float(model.rates[0].value)
    model.update_model()
    fast = np.asarray(model.y, dtype=float)

    # Both relax between the same two levels, so "sooner" is a larger integral of
    # the deviation from the start value early on.
    early = slice(0, 40)
    assert abs(fast[early] - fast[0]).sum() > abs(slow[early] - slow[0]).sum()


def test_reaction_model_scheme_round_trips_through_json():
    """``reaction_json`` rebuilds exactly the scheme it emitted."""
    model = _make_fit().model
    model.add_reaction_row()
    text = model.reaction_json
    before = model.reaction_rows()

    model.clear_reactions()
    assert model.n_reactions == 2

    model.reaction_json = text
    assert model.reaction_rows() == before


def test_reaction_model_ignores_json_that_does_not_parse():
    """Half-typed text cannot destroy the current scheme."""
    model = _make_fit().model
    before = model.reaction_rows()
    model.reaction_json = '{"reactions": ['
    assert model.reaction_rows() == before


def test_reaction_model_reaction_labels_use_species_names():
    """The reaction table reads ``A → B``, not ``1.0 * [0] -> 1.0 * [1]``."""
    model = _make_fit().model
    labels = [row["reaction"] for row in model.reaction_rows()]
    assert labels == ["A → B", "B → A"]


def test_reaction_model_remove_targets_the_selected_row():
    """Removing drops the *selected* reaction, not always the last one."""
    model = _make_fit().model
    model.selected_reaction = {"index": 0}
    model.remove_selected_reaction()
    assert [row["reaction"] for row in model.reaction_rows()] == ["B → A"]


def test_reaction_model_keeps_two_species():
    """The species floor holds: a reaction needs a side each."""
    model = _make_fit().model
    for _ in range(5):
        model.remove_species()
    assert len(model.species_names) == 2


def test_reaction_model_autoscale_matches_the_data_integral():
    """With autoscale on, the model's integral equals the data's over the window."""
    fit = _make_fit()
    model = fit.model
    model.autoscale = True
    model._background.value = 0.0
    model.update_model()

    lo, hi = model._fit_window()
    assert np.sum(np.asarray(model.y)[lo:hi]) == pytest.approx(
        np.sum(np.asarray(fit.data.y)[lo:hi]), rel=1e-6
    )
