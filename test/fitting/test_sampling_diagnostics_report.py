"""``sample_fit`` must report whether its chains are worth believing (PRD-69).

It used to run ``n_runs`` independent chains, write each to its own file and
forget about them -- discarding exactly the information a cross-run R-hat is
computed from. These tests pin the pooled report.
"""
import json
import os

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.fitting.sample
import chisurf.core.models.parse
from chisurf.core.fitting import diagnostics as dg

SIGMA = 0.05


def _quadratic_fit(seed: int = 1):
    """Return a converged ``c + a*x**2`` fit to noisy data with known sigma."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 64)
    y = 3.1 + 1.2 * x ** 2 + rng.normal(0.0, SIGMA, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * SIGMA)
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x**2'
    fit.model.find_parameters()
    fit.run()
    return fit


def test_walk_mcmc_returns_its_chain_structure():
    """The per-draw chain must survive, not only the flattened samples."""
    np.random.seed(0)
    fit = _quadratic_fit()
    r = chisurf.core.fitting.sample.walk_mcmc(
        fit=fit, steps=300, step_size=0.01, thin=1
    )
    chains = np.asarray(r['chains'])
    assert chains.ndim == 3
    assert chains.shape[0] == 1
    assert chains.shape[1] == r['parameter_values'].shape[0]
    assert chains.shape[2] == len(r['parameter_names'])
    assert 0.0 <= r['acceptance_rate'] <= 1.0
    # The diagnostics must accept it unchanged.
    assert len(dg.summarize(chains, names=r['parameter_names'])) == chains.shape[2]


def test_ensemble_returns_one_chain_per_walker():
    """Walkers are the natural chains of an ensemble sampler."""
    np.random.seed(1)
    fit = _quadratic_fit()
    r = chisurf.core.fitting.sample.sample_ensemble(
        fit, steps=60, nwalkers=8, thin=1
    )
    chains = np.asarray(r['chains'])
    assert chains.shape[0] == 8
    assert chains.shape[2] == len(r['parameter_names'])
    assert np.isfinite(r['acceptance_rate'])


def test_pool_chains_stacks_runs_and_truncates_to_the_shortest():
    """Independent runs become chains; a cancelled short run must not break it."""
    a = {'chains': np.zeros((2, 100, 3))}
    b = {'chains': np.ones((4, 70, 3))}
    pooled = chisurf.core.fitting.fit.pool_chains([a, b])
    assert pooled.shape == (6, 70, 3)
    assert chisurf.core.fitting.fit.pool_chains([{'chains': None}]) is None
    assert chisurf.core.fitting.fit.pool_chains([]) is None


def test_sample_fit_writes_a_pooled_diagnostics_report(tmp_path, monkeypatch):
    """The run must leave behind evidence about its own convergence."""
    np.random.seed(2)
    fit = _quadratic_fit()

    # ``sample_fit`` saves the whole project; stub that out, it is not under test.
    import chisurf.macros.core_fit
    monkeypatch.setattr(
        chisurf.macros.core_fit, "save_project",
        lambda target_path, project_name="project", **kw: None,
    )

    report = chisurf.core.fitting.fit.sample_fit(
        fit=fit,
        target_directory=str(tmp_path),
        method='ensemble',
        steps=60,
        thin=1,
        n_runs=3,
    )

    assert report is not None
    assert report['n_runs'] == 3
    # Three runs of eight walkers each, pooled.
    assert report['n_chains'] >= 3
    assert set(report) >= {
        'n_runs', 'n_chains', 'n_draws', 'burn_in',
        'acceptance_rate', 'parameters', 'warnings',
    }

    names = {e['name'] for e in report['parameters']}
    assert names == set(fit.model.parameter_names)
    for e in report['parameters']:
        assert {'mean', 'sd', 'quantiles', 'ess', 'rhat', 'tau', 'mcse'} <= set(e)

    # And it must be on disk next to the chains.
    run_dir = next(p for p in tmp_path.iterdir() if p.is_dir())
    written = run_dir / "diagnostics.json"
    assert written.exists()
    with open(written) as f:
        on_disk = json.load(f)
    assert on_disk['n_runs'] == report['n_runs']
    assert os.path.isdir(run_dir / "chains")


def test_sample_fit_chain_files_keep_every_draw(tmp_path, monkeypatch):
    """The burn-in is a recommendation; the stored chain must stay complete."""
    np.random.seed(3)
    fit = _quadratic_fit()

    import chisurf.macros.core_fit
    monkeypatch.setattr(
        chisurf.macros.core_fit, "save_project",
        lambda target_path, project_name="project", **kw: None,
    )

    report = chisurf.core.fitting.fit.sample_fit(
        fit=fit, target_directory=str(tmp_path), method='ensemble',
        steps=60, thin=1, n_runs=1,
    )
    run_dir = next(p for p in tmp_path.iterdir() if p.is_dir())
    chain_file = next((run_dir / "chains").glob("*.er4"))
    rows = np.genfromtxt(chain_file, skip_header=1)
    # Every recorded state is on disk -- steps x walkers, with the walker count
    # chosen by ``sample_fit`` itself -- even though a burn-in was suggested.
    n_walkers = max(int(fit.n_free * 2) + 2, 10)
    assert rows.shape[0] == 60 * n_walkers
    assert report['burn_in'] >= 0
    # chi2r, lnprior, then one column per parameter.
    assert rows.shape[1] == 2 + len(fit.model.parameter_names)


def test_a_deliberately_stuck_sampler_is_reported_as_such(tmp_path, monkeypatch):
    """A useless chain must produce warnings, not a clean-looking report."""
    np.random.seed(4)
    fit = _quadratic_fit()

    import chisurf.macros.core_fit
    monkeypatch.setattr(
        chisurf.macros.core_fit, "save_project",
        lambda target_path, project_name="project", **kw: None,
    )

    # A step size of essentially zero: the chain accepts everything but goes
    # nowhere, which is the classic silently-wrong MCMC result.
    report = chisurf.core.fitting.fit.sample_fit(
        fit=fit, target_directory=str(tmp_path), method='mcmc',
        steps=200, thin=1, n_runs=2, step_size=1e-12,
    )
    assert report is not None
    assert report['warnings'], "a frozen chain must not pass silently"


def test_posterior_summary_prefers_a_converged_chain(tmp_path, monkeypatch):
    """A chain describes the whole posterior, so it outranks the covariance."""
    np.random.seed(5)
    fit = _quadratic_fit()

    import chisurf.macros.core_fit
    monkeypatch.setattr(
        chisurf.macros.core_fit, "save_project",
        lambda target_path, project_name="project", **kw: None,
    )

    before = fit.posterior_summary(p_value=0.68)
    assert {e['method'] for e in before} <= {'laplace', 'none'}

    chisurf.core.fitting.fit.sample_fit(
        fit=fit, target_directory=str(tmp_path), method='ensemble',
        steps=4000, thin=1, n_runs=2,
    )
    after = fit.posterior_summary(p_value=0.68)
    assert {e['method'] for e in after} == {'mcmc'}, [e['method'] for e in after]

    # The credible interval must bracket the optimum and resemble the Laplace one.
    by_name = {e['name']: e for e in after}
    laplace = {e['name']: e for e in before}
    for name, e in by_name.items():
        assert e['low'] < e['value'] < e['high']
        width = e['high'] - e['low']
        ref = laplace[name]['high'] - laplace[name]['low']
        assert 0.4 * ref < width < 2.5 * ref


def test_an_unconverged_chain_is_not_quoted_as_a_credible_interval(tmp_path, monkeypatch):
    """A quantile of a chain that never mixed is a number without a meaning."""
    np.random.seed(6)
    fit = _quadratic_fit()

    import chisurf.macros.core_fit
    monkeypatch.setattr(
        chisurf.macros.core_fit, "save_project",
        lambda target_path, project_name="project", **kw: None,
    )

    chisurf.core.fitting.fit.sample_fit(
        fit=fit, target_directory=str(tmp_path), method='mcmc',
        steps=200, thin=1, n_runs=2, step_size=1e-12,
    )
    assert fit.sampling_diagnostics['warnings']
    summary = fit.posterior_summary(p_value=0.68)
    assert 'mcmc' not in {e['method'] for e in summary}
    # And the failure is visible in the printed report.
    assert 'Sampling did not converge' in str(fit)
