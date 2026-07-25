"""Blocked Metropolis with per-block covariance proposals (PRD-69, phase 2).

The historical ``walk_mcmc`` proposes from a *diagonal* Gaussian, which is the
worst available proposal for the collinear posteriors that polynomial and
multi-exponential models produce. These tests pin the block partition, the
correctness of the sampler, and the mixing improvement that justifies it.
"""
import numpy as np

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.fitting.sample
import chisurf.core.models.parse
from chisurf.core.fitting import diagnostics as dg
from chisurf.core.fitting.factorgraph import build_factor_graph, posterior_model

SIGMA = 0.02


def _collinear_fit(seed: int = 0):
    """Return a converged ``c + a*x + b*x**2`` fit over a narrow x-range.

    The narrow range makes the three polynomial terms nearly collinear, so the
    posterior has parameter correlations around 0.99 -- exactly the case a
    diagonal proposal cannot handle.
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(1.0, 2.0, 96)
    y = 1.0 + 2.0 * x + 0.5 * x ** 2 + rng.normal(0.0, SIGMA, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * SIGMA)
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x+b*x**2'
    fit.model.find_parameters()
    fit.run()
    return fit


def _global_fit(n_datasets: int = 4, seed: int = 0):
    """Return a star-linked global fit sharing ``a`` across datasets."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 48)
    curves = []
    for k in range(n_datasets):
        y = (3.0 + 0.3 * k) + 1.2 * x ** 2 + rng.normal(0.0, 0.05, x.size)
        curves.append(
            chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * 0.05)
        )
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup(curves),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    for f in fit:
        f.fit_range = 0, len(f.model.y)
        f.model.func = 'c+a*x**2'
        f.model.find_parameters()
    fit._model.find_parameters()
    master = [p for p in fit[0].model.parameters_all if p.name == 'a'][0]
    for local in list(fit)[1:]:
        [p for p in local.model.parameters_all if p.name == 'a'][0].link = master
    for local in fit:
        local.model.find_parameters()
    fit._model.find_parameters()
    fit.run(local_first=False)
    return fit


def test_sampling_blocks_partition_by_dataset_neighbourhood():
    """Private parameters block per dataset; the shared one gets its own."""
    fit = _global_fit(4)
    g = build_factor_graph(fit)
    blocks = g.sampling_blocks()

    # A partition: disjoint and covering.
    flat = [k for b in blocks for k in b]
    assert len(flat) == len(set(flat)) == len(g.variables)

    named = [tuple(g.variables[k].name for k in b) for b in blocks]
    assert ('1:a',) in named
    for i in range(1, 5):
        assert (f'{i}:c',) in named

    # Cheapest first: the private blocks touch one dataset, the shared one all.
    costs = [g.block_cost(b) for b in blocks]
    assert costs == sorted(costs)
    assert costs[0] == 1
    assert costs[-1] == 4


def test_a_single_fit_is_one_block():
    """One dataset has one neighbourhood, so blocking must not fragment it."""
    fit = _collinear_fit()
    g = build_factor_graph(fit, model=fit.model)
    blocks = g.sampling_blocks()
    assert len(blocks) == 1
    assert len(blocks[0]) == len(g.variables)


def test_blocked_sampler_recovers_the_posterior_mean():
    """The chain must sit on the least-squares optimum, not somewhere else."""
    np.random.seed(0)
    fit = _collinear_fit()
    optimum = {p.name: float(p.value) for p in fit.model.parameters}
    errors = {p.name: float(p.error_estimate) for p in fit.model.parameters}

    r = chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=fit, steps=4000, step_size=0.02, thin=1
    )
    chains = np.asarray(r['chains'])
    summary = dg.summarize(chains, names=r['parameter_names'])
    for e in summary:
        # Within one standard error of the optimum, and with a comparable width.
        assert abs(e['mean'] - optimum[e['name']]) < 1.5 * errors[e['name']]
        assert 0.4 < e['sd'] / errors[e['name']] < 2.5


def test_blocked_sampler_mixes_far_better_than_the_diagonal_one():
    """The point of the covariance proposal, in effective samples per evaluation."""
    def _ess_per_eval(sampler):
        np.random.seed(11)
        fit = _collinear_fit()
        calls = [0]
        model = fit.model
        original = model.update_model

        def counting(*a, _o=original, **k):
            calls[0] += 1
            return _o(*a, **k)

        model.update_model = counting
        r = sampler(fit)
        ess = dg.effective_sample_size(np.asarray(r['chains']))
        return float(ess.min()) / max(1, calls[0])

    diagonal = _ess_per_eval(lambda f: chisurf.core.fitting.sample.walk_mcmc(
        fit=f, steps=4000, step_size=0.02, thin=1))
    blocked = _ess_per_eval(lambda f: chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=f, steps=4000, step_size=0.02, thin=1))

    # Measured at ~160x; assert an order of magnitude so the test is not brittle.
    assert blocked > 10.0 * diagonal


def test_blocked_sampler_honours_priors():
    """A dominant prior must move the blocked chain as it moves the others."""
    from chisurf.core.fitting.priors import NormalPrior
    np.random.seed(1)
    fit = _collinear_fit()
    c = [p for p in fit.model.parameters if p.name == 'c'][0]
    c_hat = float(c.value)
    mu = c_hat + 5.0
    c.prior = NormalPrior(mu=mu, sigma=0.01)

    r = chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=fit, steps=3000, step_size=0.02, thin=1
    )
    i = list(r['parameter_names']).index('c')
    sampled = np.asarray(r['parameter_values'])[:, i]
    mean = float(sampled[len(sampled) // 2:].mean())
    assert abs(mean - mu) < 0.5
    assert abs(mean - c_hat) > 2.0


def test_blocked_sampler_reports_per_block_acceptance():
    """Per-block acceptance is what says which block is badly scaled."""
    np.random.seed(2)
    fit = _global_fit(3)
    gm = posterior_model(fit)
    gm.update_model()
    r = chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=fit, steps=400, step_size=0.02, thin=1, model=gm
    )
    assert len(r['block_sizes']) == len(r['block_acceptance'])
    assert sum(r['block_sizes']) == gm.n_free
    acc = np.asarray(r['block_acceptance'], dtype=float)
    assert np.all((acc >= 0.0) & (acc <= 1.0))
    assert 0.0 <= r['acceptance_rate'] <= 1.0


def test_blocked_sampler_can_target_a_group_joint_posterior():
    """``fit.model`` is one member's model; the joint posterior needs ``model=``."""
    np.random.seed(3)
    fit = _global_fit(4)
    gm = posterior_model(fit)
    gm.update_model()
    assert gm.n_free > fit.model.n_free

    r = chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=fit, steps=400, step_size=0.02, thin=1, model=gm
    )
    assert r['parameter_values'].shape[1] == gm.n_free
    assert list(r['parameter_names']) == list(gm.parameter_names)
    # More than one block, since the datasets are only coupled through 'a'.
    assert len(r['block_sizes']) == 5


def test_explicit_blocks_are_respected():
    """A caller who knows better must be able to say so."""
    np.random.seed(4)
    fit = _collinear_fit()
    n = fit.model.n_free
    r = chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=fit, steps=200, step_size=0.02, thin=1,
        blocks=[[i] for i in range(n)],
    )
    assert r['block_sizes'] == [1] * n


def test_sample_fit_accepts_the_blocked_method(tmp_path, monkeypatch):
    """The new backend must be reachable from the top-level entry point."""
    np.random.seed(5)
    fit = _collinear_fit()

    import chisurf.macros.core_fit
    monkeypatch.setattr(
        chisurf.macros.core_fit, "save_project",
        lambda target_path, project_name="project", **kw: None,
    )

    report = chisurf.core.fitting.fit.sample_fit(
        fit=fit, target_directory=str(tmp_path), method='blocked',
        steps=2000, thin=1, n_runs=2,
    )
    assert report is not None
    assert report['n_chains'] == 2
    assert {e['name'] for e in report['parameters']} == set(fit.model.parameter_names)


def test_a_singular_block_covariance_does_not_crash():
    """A parameter the model ignores makes the covariance singular."""
    np.random.seed(6)
    fit = _collinear_fit()
    # 'b' is present in the vector but the formula below does not use it, so the
    # curvature in that direction is exactly zero.
    fit.model.func = 'c+a*x+0*b'
    fit.model.find_parameters()
    fit.model.update_model()
    r = chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=fit, steps=200, step_size=0.02, thin=1
    )
    assert np.all(np.isfinite(r['parameter_values']))
    assert r['parameter_values'].shape[0] == 200
