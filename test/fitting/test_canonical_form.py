"""Gaussians in canonical form, where conditioning is algebra not a re-fit.

`LaplaceEngine.condition` fixes a parameter and runs the optimiser again -- one
full re-fit per conditional query. For a Gaussian that is an expensive way to get
an answer that is a matrix update: the constrained minimum of a quadratic is
exactly its conditional mode. These tests pin the algebra against direct numpy,
and the engine against the re-fit it replaces.
"""
import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.core.fitting import engine as E
from chisurf.core.fitting.canonical import CanonicalForm


def _gaussian(seed: int = 0, d: int = 4):
    """Return ``(names, mean, covariance)`` of a random positive-definite Gaussian."""
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(d, d))
    cov = a @ a.T + d * np.eye(d)
    mean = rng.normal(size=d) * 3.0
    return tuple(f"x{i}" for i in range(d)), mean, cov


def _fit(func='c+a*x+b*x**2', seed=0):
    """Return a converged fit with a correlated posterior."""
    rng = np.random.default_rng(seed)
    x = np.linspace(1.0, 2.0, 96)
    y = 1.0 + 2.0 * x + 0.5 * x ** 2 + rng.normal(0.0, 0.02, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.02))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = func
    fit.model.find_parameters()
    fit.run()
    return fit


# -- the algebra ----------------------------------------------------------

def test_round_trip_through_canonical_form():
    """Moments in, moments out."""
    names, mean, cov = _gaussian()
    form = CanonicalForm.from_moments(names, mean, cov)
    assert form.names == names
    assert np.allclose(form.mean, mean)
    assert np.allclose(form.covariance, cov)
    # K is the inverse covariance, and h = K mu.
    assert np.allclose(form.K @ cov, np.eye(len(names)), atol=1e-9)
    assert np.allclose(form.h, form.K @ mean)


def test_the_form_integrates_to_the_mass_it_was_given():
    """``g`` is chosen so the total mass is meaningful, not a loose constant."""
    names, mean, cov = _gaussian(seed=1)
    for mass in (0.0, -12.5, 3.25):
        form = CanonicalForm.from_moments(names, mean, cov, log_mass=mass)
        assert form.log_mass == pytest.approx(mass, abs=1e-9)


def test_marginalising_matches_slicing_the_covariance():
    """The Schur complement must reproduce the textbook marginal."""
    names, mean, cov = _gaussian(seed=2, d=5)
    form = CanonicalForm.from_moments(names, mean, cov)
    keep = ('x0', 'x3')
    idx = [names.index(n) for n in keep]

    marginal = form.marginal(keep)
    assert marginal.names == keep
    assert np.allclose(marginal.mean, mean[idx])
    assert np.allclose(marginal.covariance, cov[np.ix_(idx, idx)])


def test_marginalising_preserves_the_mass():
    """Integrating a variable out must not change the total mass."""
    names, mean, cov = _gaussian(seed=3, d=4)
    form = CanonicalForm.from_moments(names, mean, cov, log_mass=-7.5)
    assert form.marginal(('x0', 'x1')).log_mass == pytest.approx(-7.5, abs=1e-8)
    assert form.marginal(('x2',)).log_mass == pytest.approx(-7.5, abs=1e-8)


def test_conditioning_matches_the_textbook_formula():
    """``mu_A + Sigma_AB Sigma_BB^-1 (v - mu_B)``, with the Schur covariance."""
    names, mean, cov = _gaussian(seed=4, d=5)
    form = CanonicalForm.from_moments(names, mean, cov)
    held = {'x1': 2.0, 'x4': -1.5}

    b = [names.index(n) for n in held]
    a = [i for i in range(len(names)) if i not in set(b)]
    v = np.array([held[names[i]] for i in b])
    s_ab, s_bb = cov[np.ix_(a, b)], cov[np.ix_(b, b)]
    want_mean = mean[a] + s_ab @ np.linalg.solve(s_bb, v - mean[b])
    want_cov = cov[np.ix_(a, a)] - s_ab @ np.linalg.solve(s_bb, cov[np.ix_(b, a)])

    got = form.condition(held)
    assert got.names == tuple(names[i] for i in a)
    assert np.allclose(got.mean, want_mean)
    assert np.allclose(got.covariance, want_cov)


def test_a_product_of_forms_adds_them_on_the_union_scope():
    """What makes a factorised posterior composable."""
    f1 = CanonicalForm(names=('a', 'b'), K=np.array([[2.0, 0.5], [0.5, 3.0]]),
                       h=np.array([1.0, 2.0]), g=0.5)
    f2 = CanonicalForm(names=('b', 'c'), K=np.array([[1.0, 0.25], [0.25, 4.0]]),
                       h=np.array([3.0, 1.0]), g=-0.25)
    prod = f1 * f2
    assert prod.names == ('a', 'b', 'c')
    assert prod.g == pytest.approx(0.25)
    # 'b' is shared, so its precision and information add.
    i = prod.names.index('b')
    assert prod.K[i, i] == pytest.approx(3.0 + 1.0)
    assert prod.h[i] == pytest.approx(2.0 + 3.0)
    # And the density is the sum of the two log densities.
    x = {'a': 0.3, 'b': -0.7, 'c': 1.1}
    assert prod.log_density([x[n] for n in prod.names]) == pytest.approx(
        f1.log_density([x[n] for n in f1.names])
        + f2.log_density([x[n] for n in f2.names])
    )


def test_conditioning_everything_leaves_only_a_constant():
    """Fully conditioned, the form is the log density at that point."""
    names, mean, cov = _gaussian(seed=5, d=3)
    form = CanonicalForm.from_moments(names, mean, cov)
    point = mean + np.array([0.4, -0.2, 0.1])
    fully = form.condition(dict(zip(names, point)))
    assert len(fully) == 0
    assert fully.g == pytest.approx(form.log_density(point))


def test_an_unknown_name_is_refused():
    """Silently ignoring a name would answer a different question."""
    names, mean, cov = _gaussian(seed=6, d=3)
    form = CanonicalForm.from_moments(names, mean, cov)
    with pytest.raises(KeyError):
        form.marginal(('x0', 'nope'))
    with pytest.raises(KeyError):
        form.condition({'nope': 1.0})


def test_a_repeated_name_is_refused():
    """A duplicate scope entry would answer for the wrong variable.

    The scope is addressed by name, so ``('tau', 'tau', 'x')`` used to resolve
    ``'tau'`` to its *last* occurrence: the marginal reported the second
    variable's moments and conditioning dropped only that one, leaving a form
    that still contained a variable called ``'tau'``. Wrong answers, no
    exception -- so uniqueness is enforced at construction.
    """
    with pytest.raises(ValueError, match="unique"):
        CanonicalForm.from_moments(
            ('tau', 'tau', 'x'),
            np.array([1.0, 5.0, 0.0]),
            np.diag([0.01, 4.0, 1.0]),
        )
    with pytest.raises(ValueError, match="unique"):
        CanonicalForm(names=('a', 'a'), K=np.eye(2), h=np.zeros(2))
    # Asking for the same variable twice builds such a scope, too.
    names, mean, cov = _gaussian(seed=7, d=3)
    form = CanonicalForm.from_moments(names, mean, cov)
    with pytest.raises(ValueError, match="unique"):
        form.marginal(('x0', 'x0'))


# -- the engine -----------------------------------------------------------

def test_the_gaussian_engine_agrees_with_the_laplace_one():
    """Same approximation, different arithmetic -- so the same answer."""
    fit = _fit()
    names = list(fit._model.parameter_names)

    lap = E.LaplaceEngine(fit).add_all_targets().add_joint_target(names).run()
    gau = E.GaussianEngine(fit).add_all_targets().add_joint_target(names).run()

    for name in names:
        a, b = lap.marginal(name), gau.marginal(name)
        assert b.method == 'gaussian'
        assert b.value == pytest.approx(a.value, rel=1e-9)
        assert b.sd == pytest.approx(a.sd, rel=1e-6)

    ja, jb = lap.joint(tuple(names)), gau.joint(tuple(names))
    assert np.allclose(jb.covariance, ja.covariance, rtol=1e-6)
    assert gau.log_evidence() == pytest.approx(lap.log_evidence(), rel=1e-6)


def test_closed_form_conditioning_matches_the_re_fit_it_replaces():
    """The claim that makes this worth having.

    ``LaplaceEngine.condition`` fixes the parameter and re-runs the optimiser.
    ``GaussianEngine.condition`` is a matrix update. For a quadratic objective
    the constrained minimum *is* the conditional mode, so on a near-Gaussian
    posterior the two must agree.
    """
    fit = _fit()
    names = list(fit._model.parameter_names)
    held, target = names[0], names[1]

    base = E.GaussianEngine(fit).add_all_targets().run()
    centre = base.marginal(held).value
    sd = base.marginal(held).sd

    for offset in (-2.0, 0.0, 2.0):
        value = centre + offset * sd
        refit = E.LaplaceEngine(fit)
        refit.condition(held, value).add_target(target).run()
        closed = E.GaussianEngine(fit)
        closed.condition(held, value).add_target(target).run()

        a, b = refit.marginal(target), closed.marginal(target)
        assert b.method == 'gaussian'
        # Agreement to well inside the posterior width is the claim; the
        # residual difference is the optimiser's tolerance, not the algebra.
        assert b.value == pytest.approx(a.value, abs=0.05 * a.sd)


def test_many_conditionals_cost_one_curvature_evaluation():
    """The point of the canonical form: a scan is algebra, not a re-fit sweep."""
    fit = _fit()
    names = list(fit._model.parameter_names)

    calls = [0]
    model = fit.model
    original = model.update_model

    def counting(*a, _o=original, **k):
        calls[0] += 1
        return _o(*a, **k)

    model.update_model = counting

    engine = E.GaussianEngine(fit).add_all_targets().run()
    after_build = calls[0]

    centre = engine.marginal(names[0]).value
    sd = engine.marginal(names[0]).sd
    for offset in np.linspace(-3.0, 3.0, 25):
        out = engine.conditional({names[0]: centre + offset * sd})
        assert out and all(np.isfinite(m.value) for m in out)

    # Twenty-five conditional queries added no model evaluations at all.
    assert calls[0] == after_build


def test_a_conditioned_parameter_has_no_marginal():
    """It is held at a known value, so it carries no uncertainty."""
    fit = _fit()
    names = list(fit._model.parameter_names)
    engine = E.GaussianEngine(fit)
    engine.condition(names[0], 1.0).add_target(names[0]).run()
    assert engine.marginal(names[0]).method == 'none'


def test_the_engine_is_reachable_by_name():
    """It has to be selectable like every other estimator."""
    fit = _fit()
    engine = E.get_engine('gaussian', fit)
    assert isinstance(engine, E.GaussianEngine)
    r = engine.add_all_targets().run()
    assert all(m.method == 'gaussian' for m in r.marginals())


def test_a_second_curvature_evaluation_agrees_with_the_first():
    """``approx_grad`` must leave the model consistent with its parameters.

    It restores the parameter vector when it finishes. Assigning the values
    alone leaves the model's arrays holding the last finite-difference
    perturbation, and a later evaluation at those same values then correctly
    concludes that nothing changed and skips the update -- serving residuals
    that belong to a different parameter vector. Latent since the selective
    global update landed, because that is when "did a value change" started
    deciding whether to recompute.
    """
    fit = _fit()
    model = fit._model
    xk = np.asarray(model.parameter_values, dtype=np.float64)

    f0_a, grad_a = chisurf.core.fitting.fit.approx_grad(xk, fit, model=model)
    f0_b, grad_b = chisurf.core.fitting.fit.approx_grad(xk, fit, model=model)
    assert np.array_equal(np.asarray(f0_a), np.asarray(f0_b))
    assert np.allclose(grad_a, grad_b, rtol=1e-12, atol=0.0)

    # The derivatives are the analytic ones for c + a*x + b*x^2 weighted by
    # 1/sigma, so a wrong one is not merely inconsistent but identifiably wrong.
    weights = 1.0 / 0.02
    x_max = 2.0     # the data span used by ``_fit``
    for k, expected in enumerate((weights, weights * x_max, weights * x_max ** 2)):
        assert abs(grad_a[k]).max() == pytest.approx(expected, rel=0.02)


def test_the_covariance_is_the_same_inside_and_outside_a_freeze():
    """A freeze changes performance, never numbers."""
    from chisurf.core.fitting import factorgraph
    fit = _fit()
    model = fit._model

    cov_a, used_a = chisurf.core.fitting.fit.covariance_matrix(fit, model=model)
    with factorgraph.frozen_structure(fit, model):
        cov_b, used_b = chisurf.core.fitting.fit.covariance_matrix(fit, model=model)

    assert list(used_a) == list(used_b)
    assert np.allclose(np.atleast_2d(cov_a), np.atleast_2d(cov_b), rtol=1e-12)


# -- the what-if sweep ----------------------------------------------------

def test_the_sweep_agrees_exactly_with_conditioning_point_by_point():
    """It uses the closed form rather than one ``condition()`` per point.

    That is only legitimate if the two agree, so this pins it: for a Gaussian
    the conditional mean is linear in the held value and the conditional width
    does not depend on it at all, which is exactly what the closed form encodes.
    """
    fit = _fit()
    engine = E.GaussianEngine(fit).add_all_targets().run()
    form = engine.form()
    scan = engine.conditional_scan(form.names[0], points=9, span=2.0)
    assert scan is not None

    for i, held in enumerate(scan['held']):
        reference = {m.name: m for m in engine.conditional(
            {scan['name']: float(held)})}
        for target in scan['targets']:
            m = reference[target['name']]
            assert m.value == pytest.approx(target['mean'][i], rel=1e-9)
            assert m.sd == pytest.approx(target['sd'], rel=1e-9)


def test_the_slope_in_standardised_units_is_the_correlation():
    """Why the plot is drawn that way: the picture *is* the correlation."""
    fit = _fit()
    engine = E.GaussianEngine(fit).add_all_targets().run()
    scan = engine.conditional_scan(engine.form().names[0], points=21, span=3.0)
    for target in scan['targets']:
        slope = np.polyfit(scan['held_z'], target['z'], 1)[0]
        assert slope == pytest.approx(target['correlation'], abs=1e-9)
        assert -1.0 <= target['correlation'] <= 1.0


def test_pinning_a_parameter_narrows_the_others_by_the_right_amount():
    """The conditional width is ``sd * sqrt(1 - r^2)``, and it is the point."""
    fit = _fit()
    engine = E.GaussianEngine(fit).add_all_targets().run()
    scan = engine.conditional_scan(engine.form().names[0])
    for target in scan['targets']:
        expected = target['marginal_sd'] * np.sqrt(
            1.0 - target['correlation'] ** 2)
        assert target['sd'] == pytest.approx(expected, rel=1e-9)
        assert target['sd'] <= target['marginal_sd'] + 1e-12
    # This fit is strongly correlated, so the narrowing is dramatic, not marginal.
    assert any(t['sd'] < 0.2 * t['marginal_sd'] for t in scan['targets'])


def test_at_the_optimum_the_conditional_is_the_marginal():
    """Fixing a parameter at its own best value must change nothing."""
    fit = _fit()
    engine = E.GaussianEngine(fit).add_all_targets().run()
    scan = engine.conditional_scan(engine.form().names[0], points=11, span=2.0)
    centre = int(np.argmin(np.abs(scan['held_z'])))
    assert scan['held_z'][centre] == pytest.approx(0.0)
    for target in scan['targets']:
        assert target['mean'][centre] == pytest.approx(target['marginal'], rel=1e-9)


def test_a_whole_sweep_costs_no_model_evaluations():
    """The reason this can be a slider rather than a batch job."""
    fit = _fit()
    engine = E.GaussianEngine(fit).add_all_targets().run()
    engine.form()          # build the curvature once, up front

    calls = [0]
    model = fit.model
    original = model.update_model

    def counting(*a, _o=original, **k):
        calls[0] += 1
        return _o(*a, **k)

    model.update_model = counting
    try:
        for name in engine.form().names:
            out = engine.conditional_scan(name, points=101, span=3.0)
            assert out is not None and out['targets']
    finally:
        model.update_model = original
    assert calls[0] == 0


def test_the_sweep_spans_the_requested_number_of_standard_deviations():
    """The axis has to mean what the label says."""
    fit = _fit()
    engine = E.GaussianEngine(fit).add_all_targets().run()
    scan = engine.conditional_scan(engine.form().names[0], points=41, span=2.5)
    assert scan['held_z'][0] == pytest.approx(-2.5)
    assert scan['held_z'][-1] == pytest.approx(2.5)
    assert scan['held'][0] == pytest.approx(scan['centre'] - 2.5 * scan['sd'])
    assert scan['held'][-1] == pytest.approx(scan['centre'] + 2.5 * scan['sd'])
    assert len(scan['held']) == 41


def test_an_unknown_parameter_gives_nothing_rather_than_a_guess():
    """Sweeping a name that is not in the posterior answers a different question."""
    fit = _fit()
    engine = E.GaussianEngine(fit).add_all_targets().run()
    assert engine.conditional_scan('not-a-parameter') is None


# -- when the posterior is not Gaussian -----------------------------------

def _weak_component(seed=0, weak=0.10):
    """Return a two-exponential fit whose second component is barely there.

    The realistic non-Gaussian case: amplitudes and lifetimes are bounded below
    by zero, and a weak component's posterior is visibly skewed — measured on
    this fit at a +0.033/-0.026 interval where the Gaussian claims ±0.0295.
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(0.05, 10.0, 160)
    y = 1.6 * np.exp(-x / 0.7) + weak * np.exp(-x / 4.0) + rng.normal(0, 0.02, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.02))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'a*exp(-x/s)+b*exp(-x/t)'
    fit.model.find_parameters()
    for p in fit.model.parameters_all:
        if p.name in ('a', 'b', 's', 't'):
            p.bounds = (0.0, np.inf)
            p.bounds_on = True
    fit.run()
    return fit


def test_the_exact_scan_matches_the_gaussian_one_on_a_linear_model():
    """Where the posterior really is Gaussian, re-fitting must confirm it.

    A model linear in its parameters with Gaussian noise has an exactly
    quadratic objective, so the straight lines are not an approximation at all
    and the check must say so rather than manufacturing a discrepancy.
    """
    fit = _fit()          # c + a*x + b*x**2 — linear in every parameter
    engine = E.GaussianEngine(fit).add_all_targets().run()
    name = engine.form().names[0]
    approximate = engine.conditional_scan(name, points=9, span=2.0)
    exact = engine.exact_conditional_scan(name, points=9, span=2.0)
    assert exact is not None and exact['exact'] is True

    verdict = E.gaussian_validity(approximate, exact)
    assert verdict['worst'] < 0.05, verdict
    assert verdict['valid_to'] == float('inf')
    assert 'holds everywhere' in verdict['verdict']


def test_a_weak_component_is_caught_as_not_gaussian():
    """The case the check exists for, and the one that is common in practice."""
    fit = _weak_component()
    engine = E.GaussianEngine(fit).add_all_targets().run()
    name = [n for n in engine.form().names if n.split(':')[-1] == 't'][0]
    approximate = engine.conditional_scan(name, points=61, span=3.0)
    exact = engine.exact_conditional_scan(name, points=13, span=3.0)

    verdict = E.gaussian_validity(approximate, exact)
    # Measured at 4.0 sd of disagreement, breaking down beyond ~1.5 sd.
    assert verdict['worst'] > 1.0, verdict
    assert verdict['valid_to'] < 3.0, verdict
    assert 'not' in verdict['verdict'] or 'breaks down' in verdict['verdict']


def test_the_grids_need_not_match():
    """The cheap sweep is naturally run at far more points than the re-fit one.

    Requiring them to line up would either force a coarse picture or an
    expensive check; the Gaussian curve has a closed form, so it is evaluated
    wherever the re-fit actually happened.
    """
    fit = _fit()
    engine = E.GaussianEngine(fit).add_all_targets().run()
    name = engine.form().names[0]
    coarse = engine.exact_conditional_scan(name, points=7, span=2.0)
    for points in (5, 61, 200):
        approximate = engine.conditional_scan(name, points=points, span=2.0)
        verdict = E.gaussian_validity(approximate, coarse)
        assert np.isfinite(verdict['worst'])


def test_the_exact_scan_puts_the_fit_back_exactly():
    """It walks the optimiser over the whole sweep, so it must leave no trace."""
    fit = _weak_component()
    engine = E.GaussianEngine(fit).add_all_targets().run()
    before = [float(p.value) for p in fit.model.parameters_all]
    fixed_before = [bool(getattr(p, 'fixed', False))
                    for p in fit.model.parameters_all]

    name = [n for n in engine.form().names if n.split(':')[-1] == 't'][0]
    engine.exact_conditional_scan(name, points=9, span=2.0)

    after = [float(p.value) for p in fit.model.parameters_all]
    fixed_after = [bool(getattr(p, 'fixed', False))
                   for p in fit.model.parameters_all]
    assert after == pytest.approx(before, rel=1e-9)
    assert fixed_after == fixed_before, "the held parameter must be freed again"


def test_the_exact_scan_records_the_profile_chi2():
    """The chi² at each held value is the profile likelihood, and is worth having."""
    fit = _weak_component()
    engine = E.GaussianEngine(fit).add_all_targets().run()
    name = [n for n in engine.form().names if n.split(':')[-1] == 't'][0]
    exact = engine.exact_conditional_scan(name, points=11, span=2.0)
    chi2 = np.asarray(exact['chi2'], dtype=float)
    finite = np.isfinite(chi2)
    assert finite.sum() >= 8
    # The minimum sits at the optimum, because that is what the optimum means.
    centre = int(np.argmin(np.abs(exact['held_z'])))
    assert chi2[centre] == pytest.approx(np.nanmin(chi2), rel=1e-6)


def test_the_exact_scan_can_be_cancelled():
    """A re-fit per point is slow enough that a caller must be able to stop it."""
    fit = _weak_component()
    engine = E.GaussianEngine(fit).add_all_targets().run()
    name = [n for n in engine.form().names if n.split(':')[-1] == 't'][0]

    calls = [0]

    def cancel():
        calls[0] += 1
        return calls[0] > 3

    exact = engine.exact_conditional_scan(
        name, points=21, span=2.0, check_cancel=cancel)
    assert exact is not None
    done = np.isfinite(np.asarray(exact['targets'][0]['mean'], dtype=float))
    assert done.sum() <= 4, "must stop when asked"
    # And still restore the fit.
    assert all(np.isfinite(float(p.value)) for p in fit.model.parameters_all)


# -- flagging a symmetric interval on a skewed posterior ------------------

def _with_chain(fit, steps=6000, burn=2000, seed=1):
    """Sample the fit and leave the chain on it, as ``sample_fit`` would."""
    import chisurf.core.fitting.sample
    np.random.seed(0)
    r = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=steps, thin=1, seed=seed)
    chains = np.asarray(r['chains'])[:, burn:, :]
    fit.sampling_chain = {
        'parameter_names': list(r['parameter_names']),
        'parameter_values': chains.reshape(-1, chains.shape[2]),
        'chains': chains,
        'burn_in': burn,
    }
    return fit


def test_the_asymmetry_threshold_is_calibrated_to_the_effective_draws():
    """A fixed cut is wrong at both ends, and measurably so.

    Measured against true Gaussians (including autocorrelated ones), the 99th
    percentile of the observed asymmetry ratio tracks ``1 + 2.4/sqrt(n_eff)``:
    1.17 at 200 effective draws, 1.04 at 3000. A single number therefore either
    fires on honest Gaussians when the chain is short, or misses real skew when
    it is long.
    """
    assert E.asymmetry_threshold(200) > E.asymmetry_threshold(3000)
    assert E.asymmetry_threshold(200) == pytest.approx(1.17, abs=0.02)
    # ...but never drops below what is worth telling anyone about.
    assert E.asymmetry_threshold(10 ** 9) == pytest.approx(E.ASYMMETRY_FLOOR)
    # A chain too short to say anything cannot flag anything.
    assert E.asymmetry_threshold(1.0) == float('inf')
    assert E.asymmetry_threshold(float('nan')) == float('inf')


def test_a_true_gaussian_is_not_flagged():
    """The false-alarm case, on the model whose posterior really is Gaussian."""
    fit = _with_chain(_fit(), steps=4000, burn=1000)
    for m in E.LaplaceEngine(fit).add_all_targets().run().marginals():
        assert 'warning' not in m.diagnostics, (m.name, m.diagnostics)


def test_a_skewed_posterior_is_flagged_on_a_symmetric_interval():
    """The whole point: the number looks the same either way, so it must say so."""
    fit = _with_chain(_weak_component())
    marginals = {m.name.split(':')[-1]: m
                 for m in E.LaplaceEngine(fit).add_all_targets().run().marginals()}

    flagged = {n: m for n, m in marginals.items() if 'warning' in m.diagnostics}
    assert flagged, {n: m.diagnostics for n, m in marginals.items()}
    for name, m in flagged.items():
        evidence = m.diagnostics['asymmetry']
        assert not evidence['gaussian_ok']
        assert evidence['lower'] > 0 and evidence['upper'] > 0
        # The note carries both arms, so the reader sees the actual interval.
        assert '+' in m.diagnostics['warning'] and '-' in m.diagnostics['warning']
        # And the flag agrees with the skewness, rather than firing on noise.
        assert abs(evidence['skew']) > 0.15, (name, evidence)


def test_no_chain_is_not_reported_as_symmetry():
    """Absence of evidence is not evidence of absence, and must not read as it."""
    fit = _weak_component()          # never sampled
    assert E.marginal_asymmetry(fit, 'b') is None
    for m in E.LaplaceEngine(fit).add_all_targets().run().marginals():
        assert m.diagnostics == {} or 'warning' not in m.diagnostics


def test_the_flag_reaches_the_summary_a_user_reads():
    """A diagnostic nobody sees is not a diagnostic."""
    fit = _with_chain(_weak_component())
    rows = fit.posterior_summary()
    assert rows
    warned = [r for r in rows if r.get('warning')]
    assert warned, [r['name'] for r in rows]
    for row in warned:
        assert 'skewed' in row['warning']
        assert row['asymmetry'] > 0.0


def test_the_gaussian_engine_flags_it_too():
    """Both quadratic engines quote a symmetric interval, so both must warn."""
    fit = _with_chain(_weak_component())
    laplace = {m.name: m for m in
               E.LaplaceEngine(fit).add_all_targets().run().marginals()}
    gaussian = {m.name: m for m in
                E.GaussianEngine(fit).add_all_targets().run().marginals()}
    warned_l = {n for n, m in laplace.items() if 'warning' in m.diagnostics}
    warned_g = {n for n, m in gaussian.items() if 'warning' in m.diagnostics}
    assert warned_l and warned_l == warned_g


def test_the_asymmetry_survives_the_trip_to_json():
    """It travels in ``diagnostics``, which the RPC payload already carries."""
    import json
    fit = _with_chain(_weak_component())
    for m in E.LaplaceEngine(fit).add_all_targets().run().marginals():
        json.loads(json.dumps(m.as_dict()))
