"""One query API over every uncertainty estimator (PRD-70).

The covariance, the profile scan and the sampled posterior answer the same
question three different ways, and used to have three different calling
conventions, return shapes and storage locations. These tests pin that they now
answer the *same* question through the same interface, that they agree where
they should, and that each still refuses to claim more than it knows.
"""
import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.core.fitting import engine as E


def _fit(seed: int = 0, npts: int = 64, sigma: float = 0.05):
    """Return a converged ``c + a*x**2`` fit with a near-Gaussian posterior."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, npts)
    y = 3.1 + 1.2 * x ** 2 + rng.normal(0.0, sigma, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, sigma))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x**2'
    fit.model.find_parameters()
    fit.run()
    return fit


def _group(n: int = 3, seed: int = 0):
    """Return a converged group of three independent fits."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 48)
    curves = [
        chisurf.core.data.DataCurve(
            x=x, y=(3.0 + 0.3 * k) + 1.2 * x ** 2 + rng.normal(0, 0.05, x.size),
            ey=np.full_like(x, 0.05))
        for k in range(n)
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
    fit.run(local_first=False)
    return fit


def test_get_engine_rejects_an_unknown_name():
    """A typo must not silently give the wrong estimator."""
    fit = _fit()
    with pytest.raises(ValueError, match="unknown posterior engine"):
        E.get_engine("bayes", fit)
    for name in ("laplace", "profile", "mcmc", "stored", "auto"):
        assert isinstance(E.get_engine(name, fit), E.PosteriorEngine)


def test_reading_before_running_is_an_error():
    """An empty answer must not be mistaken for a computed one."""
    fit = _fit()
    eng = E.LaplaceEngine(fit).add_target('1:c')
    with pytest.raises(RuntimeError):
        eng.marginal('1:c')
    eng.run()
    assert eng.marginal('1:c').method == 'laplace'
    # Changing the query invalidates the previous run.
    eng.add_target('1:a')
    with pytest.raises(RuntimeError):
        eng.marginal('1:a')


def test_only_declared_targets_are_computed():
    """The point of having targets: nothing else is computed."""
    fit = _fit()
    eng = E.LaplaceEngine(fit).add_target('1:c').run()
    assert [m.name for m in eng.marginals()] == ['1:c']
    # An undeclared parameter comes back empty rather than computed.
    assert eng.marginal('1:a').method == 'none'


def test_the_three_engines_agree_on_a_near_gaussian_posterior():
    """They approximate the same thing, so they must give the same answer."""
    np.random.seed(0)
    fit = _fit()

    laplace = E.LaplaceEngine(fit).add_all_targets().run()
    profile = E.ProfileEngine(fit).add_all_targets().run()
    sampled = E.SamplingEngine(fit).add_all_targets().run(steps=4000, n_runs=2)

    for name in laplace.parameter_names:
        a = laplace.marginal(name)
        b = profile.marginal(name)
        c = sampled.marginal(name)
        assert a.method == 'laplace'
        assert c.method == 'mcmc', c.diagnostics

        # Same point estimate.
        assert c.value == pytest.approx(a.value, abs=0.5 * a.sd)
        # Comparable widths: the posterior really is close to Gaussian here.
        lo_a, hi_a = a.interval(0.68)
        lo_c, hi_c = c.interval(0.68)
        assert (hi_c - lo_c) == pytest.approx(hi_a - lo_a, rel=0.35)
        if b.method == 'profile':
            lo_b, hi_b = b.interval(0.68)
            assert (hi_b - lo_b) == pytest.approx(hi_a - lo_a, rel=1.0)


def test_only_a_chain_gives_a_real_joint_answer():
    """A profile scan handles one parameter at a time and must say so."""
    np.random.seed(1)
    fit = _fit()
    names = tuple(fit._model.parameter_names)

    sampled = E.SamplingEngine(fit).add_joint_target(names).run(steps=4000, n_runs=2)
    joint = sampled.joint(names)
    assert joint is not None
    assert joint.covariance.shape == (len(names), len(names))
    assert joint.samples is not None
    # c and a trade off against each other in this model.
    assert abs(joint.correlation[0, 1]) > 0.1
    assert np.allclose(np.diag(joint.correlation), 1.0, atol=1e-9)

    profile = E.ProfileEngine(fit).add_joint_target(names).run()
    assert profile.joint(names) is None


def test_laplace_and_sampling_joints_agree():
    """The joint answer is the same object seen two ways."""
    np.random.seed(2)
    fit = _fit()
    names = tuple(fit._model.parameter_names)

    lap = E.LaplaceEngine(fit).add_joint_target(names).run().joint(names)
    mcmc = E.SamplingEngine(fit).add_joint_target(names).run(
        steps=5000, n_runs=2).joint(names)
    assert lap is not None and mcmc is not None
    assert mcmc.correlation[0, 1] == pytest.approx(lap.correlation[0, 1], abs=0.15)


def test_an_unconverged_chain_refuses_to_answer():
    """A quantile of a chain that never mixed is a number without a meaning."""
    np.random.seed(3)
    fit = _fit()
    eng = E.SamplingEngine(fit).add_all_targets()
    # Essentially zero step size: accepts everything, goes nowhere.
    eng.run(steps=200, n_runs=2, method='mcmc', step_size=1e-12)
    for m in eng.marginals():
        assert m.method == 'none'
        assert not np.isfinite(m.low)
        assert m.diagnostics['converged'] is False


def test_conditioning_fixes_a_parameter_and_refits_the_rest():
    """The counterpart of setting evidence, and it must be undone afterwards."""
    np.random.seed(4)
    fit = _fit()
    model = fit._model
    names = list(model.parameter_names)
    before = dict(zip(names, model.parameter_values))
    target = names[0]

    eng = E.LaplaceEngine(fit)
    eng.condition(target, before[target] + 0.05).add_target(names[1]).run()
    assert np.isfinite(eng.marginal(names[1]).sd)

    # Everything is restored: value and fixed-state. Group parameter names are
    # prefixed, so resolve through the engine rather than matching q.name.
    after = dict(zip(model.parameter_names, model.parameter_values))
    assert after[target] == pytest.approx(before[target])
    assert eng._parameter(target).fixed is False

    eng.erase_evidence()
    assert eng._evidence == {}


def test_only_integrating_engines_report_evidence():
    """A profile scan maximises rather than integrates, so it has none."""
    fit = _fit()
    lap = E.LaplaceEngine(fit).add_all_targets().run()
    assert np.isfinite(lap.log_evidence())
    prof = E.ProfileEngine(fit).add_all_targets().run()
    assert not np.isfinite(prof.log_evidence())


def test_marginal_interval_widens_with_coverage():
    """The interval must respond to the requested probability mass."""
    fit = _fit()
    m = E.LaplaceEngine(fit).add_all_targets().run().marginals()[0]
    lo68, hi68 = m.interval(0.68)
    lo95, hi95 = m.interval(0.95)
    assert (hi95 - lo95) > (hi68 - lo68)
    assert lo95 < lo68 and hi95 > hi68


def test_stored_engine_computes_nothing_new():
    """Reading a summary must never kick off a scan or a sampling run."""
    fit = _fit()
    eng = E.StoredEngine(fit).add_all_targets().run()
    for m in eng.marginals():
        # A converged fit leaves covariance error estimates behind.
        assert m.method in ('laplace', 'none')
    # No scan was performed.
    for p in fit.model.parameters:
        assert getattr(p, 'scan_result', None) is None


def test_stored_engine_prefers_a_converged_chain(tmp_path, monkeypatch):
    """Ranking: a sampled posterior outranks the quadratic approximation."""
    np.random.seed(5)
    fit = _fit()

    import chisurf.macros.core_fit
    monkeypatch.setattr(
        chisurf.macros.core_fit, "save_project",
        lambda target_path, project_name="project", **kw: None,
    )
    before = {m.name: m.method for m in
              E.StoredEngine(fit).add_all_targets().run().marginals()}
    assert set(before.values()) == {'laplace'}

    chisurf.core.fitting.fit.sample_fit(
        fit=fit, target_directory=str(tmp_path), method='blocked',
        steps=4000, thin=1, n_runs=2,
    )
    after = {m.name: m.method for m in
             E.StoredEngine(fit).add_all_targets().run().marginals()}
    assert set(after.values()) == {'mcmc'}


def test_auto_engine_takes_the_best_available_answer():
    """``auto`` must label the answer with whichever engine actually produced it."""
    np.random.seed(6)
    fit = _fit()
    eng = E.AutoEngine(fit, use=('laplace', 'mcmc')).add_all_targets()
    eng.run(steps=4000, n_runs=2)
    for m in eng.marginals():
        # The chain outranks the covariance when it converged.
        assert m.method == 'mcmc'
        assert np.isfinite(m.low) and np.isfinite(m.high)


def test_a_group_is_queried_about_its_joint_posterior():
    """``FitGroup.model`` is one member; the engine must default to the group."""
    fit = _group(3)
    eng = E.LaplaceEngine(fit)
    assert eng.model is fit._model
    assert len(eng.parameter_names) == 6
    eng.add_all_targets().run()
    assert len(eng.marginals()) == 6
    assert all(np.isfinite(m.sd) for m in eng.marginals())


def test_a_profile_scan_is_routed_to_the_member_that_owns_the_parameter():
    """Group names are prefixed; a member only knows its own."""
    fit = _group(2)
    eng = E.ProfileEngine(fit).add_target('2:c').run()
    m = eng.marginal('2:c')
    assert m.method == 'profile', m.diagnostics
    assert np.isfinite(m.low) or np.isfinite(m.high)


def test_marginal_serialises_to_plain_types():
    """An answer has to survive the trip to a report or an RPC payload."""
    import json
    fit = _fit()
    m = E.LaplaceEngine(fit).add_all_targets().run().marginals()[0]
    payload = m.as_dict()
    json.dumps(payload)
    assert payload['method'] == 'laplace'
    assert payload['name'] == m.name
