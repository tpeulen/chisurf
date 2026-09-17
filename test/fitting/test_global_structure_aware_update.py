"""Structure-aware global model updates (PRD-68, phase 3).

``GlobalFitModel.update_model`` used to recompute every local model on every
objective evaluation, so a proposal touching one dataset's local parameter cost
N model evaluations. It now consults the fit's factor graph and recomputes only
the local models the change actually reached.

Correctness is the point, not just speed: the selective path must produce
byte-identical residuals to the full path, and it must arm *only* when the model
has just seen a complete parameter vector — anything else has to fall back to a
full recompute.
"""

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.core.fitting import factorgraph

SIGMA = 0.05
N_POINTS = 32


def _global_fit(n_datasets: int = 4, seed: int = 0):
    """Return a global fit of ``c + a*x**2`` over several datasets."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, N_POINTS)
    curves = []
    for k in range(n_datasets):
        y = 3.1 + (1.0 + 0.1 * k) * x**2 + rng.normal(0.0, SIGMA, x.size)
        curves.append(chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * SIGMA))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup(curves),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    for f in fit:
        f.fit_range = 0, len(f.model.y)
        f.model.func = "c+a*x**2"
        f.model.find_parameters()
    fit._model.find_parameters()
    return fit


def _link_across(fit, name: str = "a"):
    """Link the named parameter of every local fit to the first fit's copy."""
    master = [p for p in fit[0].model.parameters_all if p.name == name][0]
    for local in list(fit)[1:]:
        target = [p for p in local.model.parameters_all if p.name == name][0]
        target.link = master
    for local in fit:
        local.model.find_parameters()
    fit._model.find_parameters()
    return master


def _prime(gm):
    """Bring every local model up to date, as the first objective call does.

    Selective updating is only admissible once everything is current, so the
    first ``update_model`` after construction is always a full one. Tests that
    want to observe the selective path have to get past it first.
    """
    gm.update()
    assert gm._current_at_version is not None


def _count_updates(fit, monkeypatch):
    """Instrument every local model's ``update_model`` with a call counter."""
    counts = {i: 0 for i in range(len(fit))}

    for i, local in enumerate(fit):
        model = local.model
        original = model._update_model

        def counting(*args, _i=i, _orig=original, **kwargs):
            counts[_i] += 1
            return _orig(*args, **kwargs)

        monkeypatch.setattr(model, "_update_model", counting, raising=False)
    return counts


def test_a_local_parameter_only_recomputes_its_own_dataset(monkeypatch):
    """Moving one dataset's local parameter must not touch the other datasets."""
    fit = _global_fit(4)
    _link_across(fit, "a")
    gm = fit._model

    # Build the graph before instrumenting, so the counters start clean.
    graph = gm.factor_graph
    local_c = [v for v in graph.variables.values() if v.name == "3:c"][0]
    _prime(gm)

    counts = _count_updates(fit, monkeypatch)
    values = list(gm.parameter_values)
    values[local_c.index] += 0.1
    gm.parameter_values = values
    gm.update()

    assert counts[2] == 1
    assert [counts[i] for i in (0, 1, 3)] == [0, 0, 0]


def test_a_shared_parameter_recomputes_every_dataset(monkeypatch):
    """Moving the linked parameter must reach all datasets."""
    fit = _global_fit(4)
    _link_across(fit, "a")
    gm = fit._model

    graph = gm.factor_graph
    shared = [v for v in graph.variables.values() if v.name == "1:a"][0]
    _prime(gm)

    counts = _count_updates(fit, monkeypatch)
    values = list(gm.parameter_values)
    values[shared.index] += 0.05
    gm.parameter_values = values
    gm.update()

    assert all(counts[i] == 1 for i in range(4))


def test_an_unchanged_vector_recomputes_nothing(monkeypatch):
    """Re-assigning the same values leaves every local model current."""
    fit = _global_fit(3)
    gm = fit._model
    _prime(gm)

    counts = _count_updates(fit, monkeypatch)
    gm.parameter_values = list(gm.parameter_values)
    gm.update()

    assert all(counts[i] == 0 for i in range(3))


def test_a_value_written_on_the_parameter_object_is_not_skipped(monkeypatch):
    """A direct write, then the same vector assigned, must still reach its model.

    The dirty set used to be the difference between the new vector and the
    values the setter *found* -- so ``p.value = v`` followed by assigning a vector
    holding ``v`` looked like no change, and ``update`` skipped the dataset that
    had not seen ``v``. Every caller that holds a parameter by writing it and
    then evaluates (conditioning, a sweep, the optimiser's first call) read the
    old residuals: a Jacobian taken that way came out 1e11 times too large.
    """
    fit = _global_fit(3)
    gm = fit._model
    graph = gm.factor_graph
    local_c = [v for v in graph.variables.values() if v.name == "2:c"][0]
    _prime(gm)

    counts = _count_updates(fit, monkeypatch)
    gm.parameters[local_c.index].value = float(gm.parameters[local_c.index].value) + 0.5
    gm.parameter_values = list(gm.parameter_values)
    gm.update()
    assert counts[1] == 1
    selective = np.array(gm.weighted_residuals, dtype=float)

    gm.update()  # a bare update recomputes everything
    np.testing.assert_array_equal(selective, np.array(gm.weighted_residuals, dtype=float))


def test_a_bare_update_recomputes_everything(monkeypatch):
    """Without a preceding vector assignment nothing may be skipped."""
    fit = _global_fit(3)
    gm = fit._model
    gm.factor_graph

    counts = _count_updates(fit, monkeypatch)
    gm.update()
    assert all(counts[i] == 1 for i in range(3))


def test_the_dirty_set_is_consumed_once(monkeypatch):
    """A second update after one assignment must fall back to a full recompute."""
    fit = _global_fit(3)
    _link_across(fit, "a")
    gm = fit._model
    graph = gm.factor_graph
    local_c = [v for v in graph.variables.values() if v.name == "2:c"][0]
    _prime(gm)

    counts = _count_updates(fit, monkeypatch)
    values = list(gm.parameter_values)
    values[local_c.index] += 0.1
    gm.parameter_values = values
    gm.update()
    assert [counts[i] for i in range(3)] == [0, 1, 0]

    gm.update()
    assert [counts[i] for i in range(3)] == [1, 2, 1]


def test_selective_and_full_updates_give_identical_residuals():
    """The optimisation must be invisible in the objective's value."""
    reference = None
    for structure_aware in (False, True):
        opt = chisurf.core.settings.cs_settings["optimization"]
        previous = opt.get("global_structure_aware_update", True)
        opt["global_structure_aware_update"] = structure_aware
        try:
            fit = _global_fit(4, seed=7)
            _link_across(fit, "a")
            gm = fit._model
            rng = np.random.default_rng(11)
            trace = []
            for _ in range(25):
                values = np.asarray(gm.parameter_values, dtype=float)
                # Move a random subset, as a Metropolis proposal or a
                # finite-difference Jacobian column would.
                mask = rng.random(values.size) < 0.4
                values[mask] += rng.normal(0.0, 0.02, int(mask.sum()))
                gm.parameter_values = list(values)
                gm.update()
                trace.append(np.asarray(gm.weighted_residuals, dtype=float).copy())
            stacked = np.vstack(trace)
        finally:
            opt["global_structure_aware_update"] = previous

        if reference is None:
            reference = stacked
        else:
            assert np.array_equal(reference, stacked)


def test_get_wres_agrees_with_a_full_recompute():
    """The objective used by the optimiser and the samplers must be unchanged."""
    fit = _global_fit(3, seed=3)
    _link_across(fit, "a")
    gm = fit._model

    rng = np.random.default_rng(5)
    values = list(np.asarray(gm.parameter_values, float) + rng.normal(0, 0.02, len(gm.parameters)))

    selective = chisurf.core.fitting.fit.get_wres(values, gm)
    # Force the full path: a bare update_model always recomputes everything.
    gm.update()
    full = np.asarray(gm.weighted_residuals, dtype=float)

    assert np.array_equal(np.asarray(selective, dtype=float), full)


def test_structure_change_invalidates_the_cached_graph():
    """Linking a parameter must not leave a stale graph behind."""
    fit = _global_fit(3)
    gm = fit._model
    before = gm.factor_graph
    assert len(before) == 6

    _link_across(fit, "a")
    after = gm.factor_graph
    assert after is not before
    assert len(after) == 4
    assert after.version == factorgraph.structure_version()


def test_appending_a_fit_invalidates_the_cached_graph():
    """Group membership changes must rebuild the graph."""
    fit = _global_fit(2)
    other = _global_fit(1, seed=99)
    gm = fit._model
    n_before = len(gm.factor_graph.likelihood_factors())

    gm.append_fit(other[0])
    assert len(gm.factor_graph.likelihood_factors()) == n_before + 1


def test_disabling_the_setting_restores_the_full_update(monkeypatch):
    """The escape hatch must actually recompute everything."""
    fit = _global_fit(3)
    _link_across(fit, "a")
    gm = fit._model
    graph = gm.factor_graph
    local_c = [v for v in graph.variables.values() if v.name == "2:c"][0]

    opt = chisurf.core.settings.cs_settings["optimization"]
    previous = opt.get("global_structure_aware_update", True)
    opt["global_structure_aware_update"] = False
    try:
        counts = _count_updates(fit, monkeypatch)
        values = list(gm.parameter_values)
        values[local_c.index] += 0.1
        gm.parameter_values = values
        gm.update()
        assert all(counts[i] == 1 for i in range(3))
    finally:
        opt["global_structure_aware_update"] = previous


def test_global_fit_still_converges():
    """End to end: a linked global fit must recover the truly shared parameter.

    The datasets here share ``a`` and differ only in ``c`` -- the situation a
    global fit is actually for -- so linking ``a`` is the correct model and the
    optimum must reach both the true value and a sane chi2.
    """
    rng = np.random.default_rng(13)
    x = np.linspace(0.0, 5.0, N_POINTS)
    a_true, c_true = 1.2, [3.1, 4.0, 2.5, 5.2]
    curves = []
    for c in c_true:
        y = c + a_true * x**2 + rng.normal(0.0, SIGMA, x.size)
        curves.append(chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * SIGMA))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup(curves),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    for f in fit:
        f.fit_range = 0, len(f.model.y)
        f.model.func = "c+a*x**2"
        f.model.find_parameters()
    fit._model.find_parameters()
    _link_across(fit, "a")

    fit.run(local_first=False)

    shared = [p for p in fit[0].model.parameters_all if p.name == "a"][0]
    assert float(shared.value) == pytest.approx(a_true, abs=0.02)
    for local, c in zip(fit, c_true):
        got = [p for p in local.model.parameters_all if p.name == "c"][0]
        assert float(got.value) == pytest.approx(c, abs=0.05)
    assert fit.chi2r < 2.0
