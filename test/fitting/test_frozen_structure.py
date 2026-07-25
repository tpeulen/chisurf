"""Holding the parameter structure fixed for the duration of a run (PRD-69).

Nothing about a fit's structure changes while it is optimised or sampled --
parameters are not linked, freed, fixed or rediscovered between two objective
evaluations. Deciding which parameters are free nevertheless costs three
attribute reads each, two of them crossing into the backing chinet port, and it
was being re-derived several times per evaluation. These tests pin that the
frozen view is faithful, re-entrant, and self-checking.
"""
import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.core.fitting import factorgraph


def _group(n_datasets: int = 3, seed: int = 0):
    """Return a converged group of ``c + a*x**2`` fits."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 48)
    curves = [
        chisurf.core.data.DataCurve(
            x=x, y=(3.0 + 0.3 * k) + 1.2 * x ** 2 + rng.normal(0, 0.05, x.size),
            ey=np.full_like(x, 0.05))
        for k in range(n_datasets)
    ]
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup(curves),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    for f in fit:
        f.fit_range = 0, len(f.model.y)
        f.model.func = 'c+a*x**2'
        f.model.find_parameters()
    fit._model.find_parameters()
    return fit


def test_frozen_views_match_the_live_ones():
    """A freeze must change performance, not answers."""
    fit = _group(3)
    model = factorgraph.posterior_model(fit)

    live_parameters = list(model.parameters)
    live_names = list(model.parameter_names)
    live_bounds = list(model.parameter_bounds)
    live_free = model.n_free

    with factorgraph.frozen_structure(fit):
        assert list(model.parameters) == live_parameters
        assert list(model.parameter_names) == live_names
        assert list(model.parameter_bounds) == live_bounds
        assert model.n_free == live_free
        for local in fit:
            assert list(local.model.parameters) == list(local.model.parameters)

    # And released afterwards.
    assert model.__dict__.get("_frozen_structure") is None
    assert list(model.parameters) == live_parameters


def test_the_freeze_is_re_entrant():
    """A sampler calling another sampler must not release the outer freeze."""
    fit = _group(2)
    model = factorgraph.posterior_model(fit)

    with factorgraph.frozen_structure(fit):
        outer = model.__dict__.get("_frozen_structure")
        assert outer is not None
        with factorgraph.frozen_structure(fit):
            # The inner context finds it already frozen and leaves it alone.
            assert model.__dict__.get("_frozen_structure") is outer
        # ... and must not have released it on the way out.
        assert model.__dict__.get("_frozen_structure") is outer
    assert model.__dict__.get("_frozen_structure") is None


def test_a_structure_change_inside_a_freeze_is_reported(caplog):
    """The assumption is checked, not merely assumed."""
    fit = _group(2)
    with caplog.at_level("WARNING"):
        with factorgraph.frozen_structure(fit):
            factorgraph.bump_structure_version()
    assert any("frozen_structure" in r.message for r in caplog.records)


def test_a_window_change_inside_a_freeze_is_reported(caplog):
    """Residual lengths are frozen too, so a window change must be flagged."""
    fit = _group(2)
    with caplog.at_level("WARNING"):
        with factorgraph.frozen_structure(fit):
            factorgraph.bump_window_version()
    assert any("window" in r.message for r in caplog.records)


def test_freezing_nothing_is_harmless():
    """The context must be usable with no targets."""
    with factorgraph.frozen_structure():
        pass


def test_window_version_moves_with_the_fit_range():
    """Caches keyed on the window need the counter to actually track it."""
    fit = _group(2)
    before = factorgraph.window_version()
    fit[0].xmin = 3
    assert factorgraph.window_version() != before

    before = factorgraph.window_version()
    fit[0].xmax = 40
    assert factorgraph.window_version() != before

    before = factorgraph.window_version()
    fit[0].mask = np.ones(48)
    assert factorgraph.window_version() != before


def test_redundant_is_serialised_under_its_public_name():
    """Making ``redundant`` a property must not change the saved form."""
    from chisurf.core.fitting.parameter import FittingParameter
    p = FittingParameter(name="a", value=1.0)
    assert p.redundant is False
    state = p.to_dict()
    assert 'redundant' in state
    assert '_redundant' not in state


def test_redundant_invalidates_the_free_parameter_list():
    """It is one of the three tests that decide freedom, so it must invalidate."""
    fit = _group(1)
    model = fit[0].model
    before = [p.name for p in model.parameters]
    assert len(before) == 2

    version = factorgraph.structure_version()
    model.parameters_all[0].redundant = True
    assert factorgraph.structure_version() != version

    after = [p.name for p in model.parameters]
    assert len(after) == 1
    assert set(after) < set(before)

    # Setting the same value again must not churn the version.
    version = factorgraph.structure_version()
    model.parameters_all[0].redundant = True
    assert factorgraph.structure_version() == version


def test_a_fit_run_inside_a_freeze_still_converges():
    """End to end: the optimiser runs under a freeze and reaches the optimum."""
    fit = _group(3, seed=5)
    fit.run(local_first=False)
    assert fit.chi2r < 2.0
    for local in fit:
        c = [p for p in local.model.parameters_all if p.name == 'a'][0]
        assert float(c.value) == pytest.approx(1.2, abs=0.05)
    # The freeze must have been released.
    assert fit._model.__dict__.get("_frozen_structure") is None


def test_frozen_parameter_reads_are_identical_to_unfrozen_ones():
    """The read fast path must be a shortcut, not a different rule.

    Reading a parameter costs six property dispatches purely to decide *how* to
    read it -- linked? callable? bounded? -- and none of those answers can change
    during a run. The freeze stamps them, so the fast path has to reproduce
    clamping, link-following and callables exactly.
    """
    from chisurf.core.fitting.parameter import FittingParameter

    plain = FittingParameter(name="plain", value=2.5)

    bounded = FittingParameter(name="bounded", value=2.5)
    bounded.bounds = (0.0, 1.0)
    bounded.bounds_on = True

    below = FittingParameter(name="below", value=-3.0)
    below.bounds = (0.0, 1.0)
    below.bounds_on = True

    master = FittingParameter(name="master", value=7.25)
    follower = FittingParameter(name="follower", value=0.0)
    follower.link = master

    fixed = FittingParameter(name="fixed", value=4.0)
    fixed.bounds = (0.0, 1.0)
    fixed.bounds_on = True
    fixed.fixed = True

    class _Model:
        """Minimal carrier so the freeze has something to walk."""

        parameters_all = [plain, bounded, below, master, follower, fixed]
        parameters = parameters_all
        parameter_names = [p.name for p in parameters_all]
        parameter_bounds = [p.bounds for p in parameters_all]

    model = _Model()
    before = [float(p.value) for p in model.parameters_all]
    with factorgraph.frozen_structure(model):
        during = [float(p.value) for p in model.parameters_all]
        # The flags really were stamped.
        assert all(p.__dict__.get("_frozen_flags") is not None
                   for p in model.parameters_all)
    after = [float(p.value) for p in model.parameters_all]

    assert during == before == after
    # And the individual rules still hold.
    named = dict(zip(model.parameter_names, during))
    assert named['plain'] == 2.5
    assert named['bounded'] == 1.0        # clamped to the upper bound
    assert named['below'] == 0.0          # clamped to the lower bound
    assert named['follower'] == 7.25      # follows its master
    assert named['fixed'] == 1.0          # clamped on read, but never written
    # Released afterwards.
    assert all(p.__dict__.get("_frozen_flags") is None
               for p in model.parameters_all)


def test_a_frozen_read_still_writes_a_clamped_value_back():
    """Clamping on read writes back, and the fast path must do it too."""
    from chisurf.core.fitting.parameter import FittingParameter

    p = FittingParameter(name="p", value=5.0)
    p.bounds = (0.0, 1.0)
    p.bounds_on = True

    class _Model:
        parameters_all = [p]
        parameters = parameters_all
        parameter_names = ['p']
        parameter_bounds = [p.bounds]

    with factorgraph.frozen_structure(_Model()):
        assert float(p.value) == 1.0
        # Persisted, so repeated reads agree and match the unfrozen rule.
        assert float(p.value) == 1.0
    assert float(p.value) == 1.0
