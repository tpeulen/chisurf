"""Error bars on the numbers a fit reports but does not fit.

A FRET efficiency is a ratio of two averaged lifetimes. ChiSurf has always
printed it as a bare number, and the obvious way to give it an error bar --
linear propagation of the covariance -- is symmetric by construction, which a
bounded ratio's posterior is not. These tests pin the propagation against draws
computed independently, and pin the *size* of the error the linear route makes,
because the whole justification for evaluating a model a few thousand times is
that the cheap answer is wrong by more than it looks.
"""
import tempfile

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.core.fitting import derived


def _fit(noise: float = 0.02, seed: int = 0):
    """Return a converged quadratic fit whose parameters are correlated."""
    rng = np.random.default_rng(seed)
    x = np.linspace(1.0, 2.0, 96)
    y = 1.0 + 2.0 * x + 0.5 * x ** 2 + rng.normal(0.0, noise, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, noise))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x+b*x**2'
    fit.model.find_parameters()
    fit.run()
    fit.model.__dict__['derived_quantities'] = ('ratio',)
    return fit


def _sampled(fit, steps: int = 3000):
    """Sample the fit so a chain is on it, and return it."""
    chisurf.core.fitting.fit.sample_fit(
        fit, tempfile.mkdtemp(), steps=steps, thin=1, n_runs=2, method='de')
    return fit


def _reference(fit):
    """Compute the derived quantity from the stored chain, independently."""
    chain = fit.sampling_chain
    names = list(chain['parameter_names'])
    v = np.asarray(chain['parameter_values'], dtype=float)
    return 1.0 - v[:, names.index('b')] / v[:, names.index('a')]


@pytest.fixture(scope="module", autouse=True)
def _ratio_property():
    """Give ParseModel a bounded, non-linear derived quantity to report."""
    klass = chisurf.core.models.parse.ParseModel
    klass.ratio = property(
        lambda m: 1.0 - m.parameters_all_dict['b'].value
        / m.parameters_all_dict['a'].value)
    yield
    del klass.ratio


# -- what a model declares ------------------------------------------------

def test_a_model_declaring_nothing_reports_nothing():
    """No quantities declared is an empty report, not a guess at what to show."""
    fit = _fit()
    del fit.model.__dict__['derived_quantities']
    assert derived.derived_quantity_names(fit.model) == []
    assert derived.derived_posterior(fit) == []


def test_a_subclass_keeps_what_it_inherited():
    """Adding a quantity in a subclass must not shadow the parent's list."""
    class Parent:
        derived_quantities = ("a", "b")

    class Child(Parent):
        derived_quantities = ("c",)

    assert derived.derived_quantity_names(Child()) == ["a", "b", "c"]


def test_an_instance_may_add_one_the_class_never_anticipated():
    """A script or plugin can ask about its own quantity."""
    fit = _fit()
    assert derived.derived_quantity_names(fit.model) == ["ratio"]


def test_the_tcspc_models_declare_the_quantities_they_print():
    """The reason this exists: these were printed with no error bar at all."""
    from chisurf.core.models.tcspc.fret import FRETModel
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    lifetime = LifetimeModel.__dict__['derived_quantities']
    assert 'species_averaged_lifetime' in lifetime
    assert 'fluorescence_averaged_lifetime' in lifetime
    # FRETModel must *extend*, not replace: <tau>x is still reported there.
    collected = []
    for klass in reversed(FRETModel.__mro__):
        for n in klass.__dict__.get('derived_quantities', ()) or ():
            if n not in collected:
                collected.append(n)
    assert 'fret_efficiency' in collected
    assert 'species_averaged_lifetime' in collected


def test_a_quantity_that_raises_costs_one_value_not_the_whole_report():
    """One bad property must not take the others down with it."""
    class Model:
        derived_quantities = ("good", "bad")
        good = 1.5

        @property
        def bad(self):
            raise ZeroDivisionError

    values = derived.evaluate_derived(Model(), ["good", "bad"])
    assert values[0] == pytest.approx(1.5)
    assert np.isnan(values[1])


# -- the delta method -----------------------------------------------------

def test_linear_propagation_needs_no_chain():
    """Without sampling there is still an answer, and it says which one it is."""
    fit = _fit()
    rows = fit.derived_summary()
    assert len(rows) == 1
    row = rows[0]
    assert row['method'] == 'delta'
    assert row['low'] < row['value'] < row['high']
    assert np.isfinite(row['sd']) and row['sd'] > 0.0


def test_linear_propagation_says_it_cannot_express_a_skew():
    """The limitation travels with the number, not in the documentation."""
    fit = _fit()
    row = fit.derived_summary()[0]
    assert 'symmetric' in row['warning']


def test_the_gradient_is_measured_on_the_parameter_and_restored():
    """Reporting must not move the fit it is reporting on."""
    fit = _fit()
    before = list(fit.model.parameter_values)
    fit.derived_summary()
    assert list(fit.model.parameter_values) == pytest.approx(before)


def test_a_well_determined_ratio_is_where_the_delta_method_is_right():
    """Where linear propagation works, the flag must stay off.

    The companion to the skew test below: with a denominator this well
    determined the ratio is near-linear over its own posterior, the two routes
    agree to a small fraction of the interval, and nothing is reported. A
    diagnostic that fired here would be worthless.
    """
    fit = _sampled(_fit(noise=0.02))
    row = fit.derived_summary(max_draws=4000)[0]
    assert row['method'] == 'draws'
    assert row['warning'] == ''

    linear = derived._from_covariance(fit, fit.model, ['ratio'], 0.68)[0]
    # Agreement is judged against the interval's own width; an absolute
    # tolerance here would only be a record of one run's Monte-Carlo noise.
    arm = row['high'] - row['low']
    assert linear['low'] == pytest.approx(row['low'], abs=0.2 * arm)
    assert linear['high'] == pytest.approx(row['high'], abs=0.2 * arm)


# -- draws ----------------------------------------------------------------

def test_draws_reproduce_the_quantity_computed_by_hand():
    """The propagation is checked against the same chain done independently."""
    fit = _sampled(_fit(noise=0.5))
    row = fit.derived_summary(max_draws=10 ** 6)[0]
    truth = _reference(fit)
    low, median, high = np.percentile(truth, [16.0, 50.0, 84.0])
    assert row['median'] == pytest.approx(median, rel=1e-6)
    assert row['low'] == pytest.approx(low, rel=1e-6)
    assert row['high'] == pytest.approx(high, rel=1e-6)


def test_thinning_does_not_move_the_interval_it_only_costs_precision():
    """A capped evaluation must still describe the whole posterior.

    The centre is held tightly and the ends loosely on purpose: a quantile in
    the long tail of a skewed quantity is the noisiest thing here, and pinning it
    to a tolerance the estimator cannot honour would only record one run.
    """
    fit = _sampled(_fit(noise=0.5))
    full = fit.derived_summary(max_draws=10 ** 6)[0]
    thinned = fit.derived_summary()[0]
    arm = full['high'] - full['low']
    assert thinned['median'] == pytest.approx(full['median'], abs=0.05 * arm)
    assert thinned['low'] == pytest.approx(full['low'], abs=0.25 * arm)
    assert thinned['high'] == pytest.approx(full['high'], abs=0.25 * arm)


def test_a_skewed_ratio_is_where_the_symmetric_interval_is_wrong_at_both_ends():
    """The measurement that justifies evaluating the model thousands of times.

    At this noise the denominator is poorly determined and the ratio's posterior
    is visibly one-sided. Linear propagation reports one width for both arms, so
    it must be too narrow on one side and too wide on the other -- not a rounding
    difference but a factor.
    """
    fit = _sampled(_fit(noise=0.5))
    row = fit.derived_summary(max_draws=10 ** 6)[0]
    linear = derived._from_covariance(fit, fit.model, ['ratio'], 0.68)[0]

    true_lower = row['median'] - row['low']
    true_upper = row['high'] - row['median']
    assert max(true_upper / true_lower, true_lower / true_upper) > 2.0
    assert row['warning'] and 'skewed' in row['warning']

    # The one symmetric width cannot match both arms.
    assert linear['sd'] > 1.5 * true_upper       # too wide above
    assert linear['sd'] < 0.75 * true_lower      # too narrow below


def test_a_chain_that_did_not_converge_is_not_laundered_through_a_function():
    """The rule that guards a parameter must guard what is computed from one.

    A quantity mixing every parameter is only as good as the worst-mixed one, so
    a report that rejected any parameter rejects the derived interval too --
    otherwise passing the draws through ``1 - b/a`` would quietly reinstate a
    chain that R-hat had just refused.
    """
    fit = _sampled(_fit(noise=0.5))
    assert fit.derived_summary()[0]['method'] == 'draws'

    report = fit.sampling_diagnostics
    report['parameters'][0]['rhat'] = 1.9
    assert derived.chain_verdict(fit) is False

    row = fit.derived_summary()[0]
    assert row['method'] == 'delta'
    assert row['converged'] is False
    assert 'did not converge' in row['warning']
    assert 'did not converge' in str(fit)


def test_draws_without_a_report_are_unverified_not_approved():
    """No convergence report is not a pass; the row must not claim one."""
    fit = _sampled(_fit(noise=0.5))
    fit.sampling_diagnostics = None
    assert derived.chain_verdict(fit) is None
    row = fit.derived_summary()[0]
    assert row['method'] == 'draws'
    assert row['converged'] is None


def test_a_quantity_that_never_moves_says_so_rather_than_failing_silently():
    """Zero width is an answer; a bare "n/a" reads as a broken calculation."""
    fit = _sampled(_fit(noise=0.5))
    fit.model.__dict__['derived_quantities'] = ('constant',)
    type(fit.model).constant = property(lambda m: 7.0)
    try:
        row = fit.derived_summary()[0]
    finally:
        del type(fit.model).constant
    assert row['value'] == pytest.approx(7.0)
    assert row['warning'] == 'constant over the posterior'


def test_a_chain_for_different_parameters_is_refused():
    """Zipping a stale chain onto a re-parameterised model would be silent."""
    fit = _sampled(_fit(noise=0.5))
    fit.sampling_chain['parameter_names'] = ['q'] + \
        list(fit.sampling_chain['parameter_names'][1:])
    row = fit.derived_summary()[0]
    assert row['method'] == 'delta'


def test_the_report_a_user_reads_carries_the_interval():
    """It has to reach the text, or the propagation might as well not exist."""
    fit = _sampled(_fit(noise=0.5))
    text = str(fit)
    assert 'Derived quantities' in text
    assert 'ratio' in text
    assert 'posterior draws' in text
    assert 'skewed' in text


def test_the_report_without_a_chain_says_the_interval_is_symmetric():
    """Silence would read as a fully honest number."""
    text = str(_fit())
    assert 'Derived quantities' in text
    assert 'linear propagation' in text
