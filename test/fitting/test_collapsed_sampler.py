"""Collapsing a global fit onto its shared parameters (PRD-69, phase 4).

Linking a parameter across datasets *lowers* the dimension of a fit but makes it
*harder* to sample: the shared parameter is strongly correlated with every
dataset's private parameters, and a conditional (block) move can only shift it
a little before the locals object. Integrating the private parameters out
analytically removes exactly that pathology. These tests pin the shared/private
split, the correctness of the collapsed posterior, and the mixing gain.
"""
import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.fitting.sample
import chisurf.core.models.parse
from chisurf.core.fitting import diagnostics as dg
from chisurf.core.fitting.factorgraph import posterior_model


def _linked_group(n_datasets=6, func='c+a*x**2', seed=0, sigma=0.05, npts=48):
    """Return a converged group sharing ``a`` across all datasets."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.5, 5.0, npts)
    curves = []
    for k in range(n_datasets):
        y = (3.0 + 0.3 * k) + 1.2 * x ** 2
        if 'b*x' in func:
            y = y + (0.5 + 0.1 * k) * x
        y = y + rng.normal(0.0, sigma, x.size)
        curves.append(
            chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * sigma)
        )
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup(curves),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    for f in fit:
        f.fit_range = 0, len(f.model.y)
        f.model.func = func
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


def test_shared_and_private_split_finds_the_separator():
    """The shared parameter is the one more than one dataset depends on."""
    fit = _linked_group(4)
    model = posterior_model(fit)
    split = chisurf.core.fitting.sample._shared_and_private(fit, model)
    assert split is not None
    shared_idx, groups = split

    names = list(model.parameter_names)
    assert [names[i] for i in shared_idx] == ['1:a']
    assert len(groups) == 4
    for _, joint_idx, local_pos in groups:
        assert joint_idx.size == 1          # one private 'c' per dataset
        assert local_pos.size == joint_idx.size


def test_the_link_master_dataset_does_not_get_to_move_the_shared_parameter():
    """The master lives on one local model, whose profile must not touch it.

    Optimising a local model's whole free-parameter list would re-optimise the
    shared parameter and undo every proposal, leaving a flat target and a chain
    that diffuses away. The split must therefore point at *positions* within
    each local model, not at the whole list.
    """
    fit = _linked_group(3)
    model = posterior_model(fit)
    shared_idx, groups = chisurf.core.fitting.sample._shared_and_private(fit, model)

    master_fit, _, local_pos = groups[0]
    # Dataset 0 owns the link master, so its own free list has both parameters
    # while only one position is offered to the profile.
    assert len(master_fit.model.parameters) == 2
    assert local_pos.size == 1
    moved = {master_fit.model.parameters[i].name for i in local_pos}
    assert moved == {'c'}


def test_collapsed_chain_recovers_the_joint_posterior():
    """The collapsed marginal must agree with a long joint run."""
    np.random.seed(0)
    fit = _linked_group(6)
    model = posterior_model(fit)
    model.update_model()
    collapsed = chisurf.core.fitting.sample.sample_marginal_shared(
        fit=fit, steps=2500, step_size=0.05, thin=1, model=model, seed=3
    )

    np.random.seed(0)
    fit2 = _linked_group(6)
    model2 = posterior_model(fit2)
    model2.update_model()
    joint = chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=fit2, steps=6000, step_size=0.02, thin=1, model=model2
    )

    i = list(collapsed['parameter_names']).index('1:a')
    j = list(joint['parameter_names']).index('1:a')
    a_collapsed = np.asarray(collapsed['parameter_values'])[:, i]
    a_joint = np.asarray(joint['parameter_values'])[:, j]

    # ``c + a*x**2`` is linear in the private ``c``, so the Laplace collapse is
    # exact here and the two marginals must agree closely.
    assert a_collapsed.mean() == pytest.approx(a_joint.mean(), abs=0.3 * a_joint.std())
    assert 0.6 < a_collapsed.std() / a_joint.std() < 1.7


def test_collapsing_fixes_the_mixing_of_the_shared_parameter():
    """The whole point: the shared parameter stops crawling."""
    def _tau(sampler):
        np.random.seed(5)
        fit = _linked_group(6)
        model = posterior_model(fit)
        model.update_model()
        r = sampler(fit, model)
        tau = dg.autocorrelation_time(np.asarray(r['chains']))
        return float(tau[list(r['parameter_names']).index('1:a')])

    blocked = _tau(lambda f, m: chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=f, steps=2000, step_size=0.02, thin=1, model=m))
    collapsed = _tau(lambda f, m: chisurf.core.fitting.sample.sample_marginal_shared(
        fit=f, steps=2000, step_size=0.05, thin=1, model=m, seed=3))
    assert collapsed < blocked / 2.0


def test_collapsing_wins_outright_with_several_private_parameters():
    """Where blocked sampling breaks down, per model evaluation."""
    def _ess_per_eval(sampler):
        np.random.seed(7)
        fit = _linked_group(6, func='c+b*x+a*x**2', sigma=0.03, npts=64)
        model = posterior_model(fit)
        model.update_model()
        calls = [0]
        for local in fit:
            m = local.model
            original = m.update_model

            def counting(*a, _o=original, **k):
                calls[0] += 1
                return _o(*a, **k)

            m.update_model = counting
        r = sampler(fit, model)
        ess = dg.effective_sample_size(np.asarray(r['chains']))
        return float(ess.min()) / max(1, calls[0])

    blocked = _ess_per_eval(lambda f, m: chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=f, steps=1500, step_size=0.02, thin=1, model=m))
    collapsed = _ess_per_eval(lambda f, m: chisurf.core.fitting.sample.sample_marginal_shared(
        fit=f, steps=1500, step_size=0.05, thin=1, model=m, seed=3))
    # Measured at ~26x with three private parameters; assert a clear win.
    assert collapsed > 3.0 * blocked


def test_the_result_is_a_full_joint_sample():
    """Private parameters are drawn conditionally, not left at the optimum."""
    np.random.seed(1)
    fit = _linked_group(4)
    model = posterior_model(fit)
    model.update_model()
    r = chisurf.core.fitting.sample.sample_marginal_shared(
        fit=fit, steps=800, step_size=0.05, thin=1, model=model, seed=2
    )
    assert r['collapsed'] is True
    assert r['n_shared'] == 1
    assert r['shared_names'] == ['1:a']
    assert r['parameter_values'].shape == (800, model.n_free)
    # Every parameter varies, including the private ones.
    assert np.all(r['parameter_values'].std(axis=0) > 0.0)
    assert np.all(np.isfinite(r['chi2r']))
    assert np.all(np.isfinite(r['lnprior']))


def test_an_unlinked_group_falls_back_to_the_component_decomposition():
    """Nothing shared means nothing to collapse onto."""
    np.random.seed(2)
    rng = np.random.default_rng(0)
    x = np.linspace(0.0, 5.0, 48)
    curves = [
        chisurf.core.data.DataCurve(
            x=x, y=(3.0 + 0.3 * k) + 1.2 * x ** 2 + rng.normal(0, 0.05, x.size),
            ey=np.full_like(x, 0.05))
        for k in range(3)
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
    model = posterior_model(fit)
    model.update_model()

    r = chisurf.core.fitting.sample.sample_marginal_shared(
        fit=fit, steps=400, step_size=0.02, thin=1, model=model, seed=1
    )
    assert 'collapsed' not in r
    assert r['n_components'] == 3


def test_a_plain_fit_falls_back_without_error():
    """A single-dataset fit has no shared parameters at all."""
    rng = np.random.default_rng(3)
    x = np.linspace(0.0, 5.0, 48)
    y = 3.0 + 1.2 * x ** 2 + rng.normal(0, 0.05, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(x, 0.05))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x**2'
    fit.model.find_parameters()
    fit.run()

    np.random.seed(4)
    r = chisurf.core.fitting.sample.sample_marginal_shared(
        fit=fit, steps=300, step_size=0.02, thin=1
    )
    assert 'collapsed' not in r
    assert r['parameter_values'].shape[1] == fit.model.n_free
