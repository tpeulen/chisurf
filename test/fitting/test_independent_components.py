"""Independent sub-problems are sampled apart and merged exactly (PRD-69).

When a fit's factor graph falls into several connected components the posterior
factorises exactly -- no dataset likelihood and no prior links a parameter in one
component to a parameter in another. Sampling them jointly is then pure waste.
These tests pin that the decomposition is used, that the merge reproduces the
joint posterior, and that the reconstructed chi2 and log-prior are exact rather
than approximate.
"""

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.fitting.sample
import chisurf.core.models.parse
from chisurf.core.fitting import diagnostics as dg
from chisurf.core.fitting.factorgraph import build_factor_graph, posterior_model

SIGMA = 0.05


def _group(n_datasets: int = 4, link: bool = False, seed: int = 0):
    """Return a converged group of ``c + a*x**2`` fits, optionally star-linked."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 48)
    curves = []
    for k in range(n_datasets):
        y = (3.0 + 0.3 * k) + (1.2 + 0.05 * k) * x**2 + rng.normal(0.0, SIGMA, x.size)
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
    if link:
        master = [p for p in fit[0].model.parameters_all if p.name == "a"][0]
        for local in list(fit)[1:]:
            [p for p in local.model.parameters_all if p.name == "a"][0].link = master
        for local in fit:
            local.model.find_parameters()
        fit._model.find_parameters()
    fit.run(local_first=False)
    return fit


def test_an_unlinked_group_has_one_component_per_dataset():
    """Nothing shared means nothing to sample jointly."""
    fit = _group(4, link=False)
    graph = build_factor_graph(fit)
    assert len(graph.connected_components()) == 4


def test_a_linked_group_is_one_component():
    """A shared parameter couples every dataset, so it cannot be decomposed."""
    fit = _group(4, link=True)
    graph = build_factor_graph(fit)
    assert len(graph.connected_components()) == 1


def test_components_are_sampled_separately_and_cover_the_vector():
    """Each component contributes its own parameters to the merged chain."""
    np.random.seed(0)
    fit = _group(4, link=False)
    joint_model = posterior_model(fit)
    joint_model.update()

    r = chisurf.core.fitting.sample.sample_independent_components(
        fit=fit, steps=1500, step_size=0.02, thin=1, model=joint_model, seed=1
    )
    assert r["n_components"] == 4
    assert sorted(r["component_sizes"]) == [2, 2, 2, 2]
    assert r["parameter_values"].shape == (1500, joint_model.n_free)
    assert list(r["parameter_names"]) == list(joint_model.parameter_names)
    # Every parameter actually moved -- none was left frozen at the reference.
    assert np.all(r["parameter_values"].std(axis=0) > 0.0)


def test_a_single_component_falls_back_to_the_joint_sampler():
    """With nothing to decompose the result must be an ordinary blocked run."""
    np.random.seed(1)
    fit = _group(3, link=True)
    joint_model = posterior_model(fit)
    joint_model.update()

    r = chisurf.core.fitting.sample.sample_independent_components(
        fit=fit, steps=300, step_size=0.02, thin=1, model=joint_model
    )
    assert "n_components" not in r
    assert r["parameter_values"].shape[1] == joint_model.n_free


def test_merged_marginals_match_a_joint_run():
    """The decomposition must be exact, not merely cheaper."""

    def _summary(sampler):
        np.random.seed(3)
        fit = _group(3, link=False)
        joint_model = posterior_model(fit)
        joint_model.update()
        r = sampler(fit, joint_model)
        return {
            e["name"]: e for e in dg.summarize(np.asarray(r["chains"]), names=r["parameter_names"])
        }

    decomposed = _summary(
        lambda f, m: chisurf.core.fitting.sample.sample_independent_components(
            fit=f, steps=4000, step_size=0.02, thin=1, model=m, seed=5
        )
    )
    joint = _summary(
        lambda f, m: chisurf.core.fitting.sample.walk_mcmc_blocked(
            fit=f, steps=4000, step_size=0.02, thin=1, model=m
        )
    )

    assert set(decomposed) == set(joint)
    for name, a in decomposed.items():
        b = joint[name]
        # Same marginal: means agree to well inside a posterior width, and the
        # widths themselves agree.
        assert abs(a["mean"] - b["mean"]) < 0.5 * b["sd"]
        assert 0.6 < a["sd"] / b["sd"] < 1.6


def test_merged_chi2_and_prior_are_exact_not_approximate():
    """The closed-form merge must reproduce a direct re-evaluation exactly."""
    np.random.seed(4)
    fit = _group(3, link=False)
    joint_model = posterior_model(fit)
    joint_model.update()

    r = chisurf.core.fitting.sample.sample_independent_components(
        fit=fit, steps=400, step_size=0.02, thin=1, model=joint_model, seed=7
    )
    dof = float(joint_model.n_points - joint_model.n_free - 1.0)
    bounds = joint_model.parameter_bounds

    # Re-evaluate the objective at a handful of merged draws and compare with
    # what the analytic merge claimed.
    for i in (0, 17, 199, 399):
        state = list(r["parameter_values"][i])
        _, lnprior, chi2 = chisurf.core.fitting.fit.lnprob_parts(
            parameter_values=state, fit=fit, bounds=bounds, model=joint_model
        )
        assert r["chi2r"][i] == pytest.approx(chi2 / dof, rel=1e-9, abs=1e-9)
        assert r["lnprior"][i] == pytest.approx(lnprior, rel=1e-9, abs=1e-9)


def test_components_are_shuffled_so_no_spurious_correlation_appears():
    """Independent components must not inherit correlation from chain order."""
    np.random.seed(6)
    fit = _group(4, link=False)
    joint_model = posterior_model(fit)
    joint_model.update()

    r = chisurf.core.fitting.sample.sample_independent_components(
        fit=fit, steps=3000, step_size=0.02, thin=1, model=joint_model, seed=11
    )
    values = r["parameter_values"]
    names = list(r["parameter_names"])
    corr = np.corrcoef(values, rowvar=False)

    # Parameters of *different* datasets are independent, so their sample
    # correlation must be consistent with zero at this chain length.
    for i, ni in enumerate(names):
        for j, nj in enumerate(names):
            if i >= j or ni.split(":")[0] == nj.split(":")[0]:
                continue
            assert abs(corr[i, j]) < 0.15, f"{ni} vs {nj}: {corr[i, j]:.3f}"


def test_decomposition_costs_far_fewer_model_evaluations():
    """The point of the exercise, in local-model evaluations for equal draws."""

    def _cost(sampler):
        np.random.seed(9)
        fit = _group(6, link=False)
        joint_model = posterior_model(fit)
        joint_model.update()
        calls = [0]
        for local in fit:
            m = local.model
            original = m._update_model

            def counting(*a, _o=original, **k):
                calls[0] += 1
                return _o(*a, **k)

            m._update_model = counting
        r = sampler(fit, joint_model)
        ess = dg.effective_sample_size(np.asarray(r["chains"]))
        return calls[0], float(ess.min())

    split_cost, split_ess = _cost(
        lambda f, m: chisurf.core.fitting.sample.sample_independent_components(
            fit=f, steps=2000, step_size=0.02, thin=1, model=m, seed=2
        )
    )
    joint_cost, joint_ess = _cost(
        lambda f, m: chisurf.core.fitting.sample.walk_mcmc_blocked(
            fit=f, steps=2000, step_size=0.02, thin=1, model=m
        )
    )

    # Same number of recorded draws either way, so the comparison is in cost
    # and in how many of those draws are worth anything.
    assert (split_ess / split_cost) > 1.5 * (joint_ess / joint_cost)


def test_sample_fit_can_target_the_group_joint_posterior(tmp_path, monkeypatch):
    """The whole stack -- joint posterior, decomposition, diagnostics -- in one call."""
    np.random.seed(12)
    fit = _group(4, link=False)

    import chisurf.macros.core_fit

    monkeypatch.setattr(
        chisurf.macros.core_fit,
        "save_project",
        lambda target_path, project_name="project", **kw: None,
    )

    report = chisurf.core.fitting.fit.sample_fit(
        fit=fit,
        target_directory=str(tmp_path),
        method="blocked",
        steps=1500,
        thin=1,
        n_runs=2,
        global_posterior=True,
    )
    joint_model = posterior_model(fit)
    assert report is not None
    assert {e["name"] for e in report["parameters"]} == set(joint_model.parameter_names)
    assert len(report["parameters"]) == joint_model.n_free == 8


def test_global_posterior_requires_the_blocked_backend(tmp_path, monkeypatch):
    """The other backends cannot target a model other than fit.model."""
    fit = _group(2, link=False)

    import chisurf.macros.core_fit

    monkeypatch.setattr(
        chisurf.macros.core_fit,
        "save_project",
        lambda target_path, project_name="project", **kw: None,
    )

    with pytest.raises(ValueError, match="blocked"):
        chisurf.core.fitting.fit.sample_fit(
            fit=fit,
            target_directory=str(tmp_path),
            method="ensemble",
            steps=50,
            n_runs=1,
            global_posterior=True,
        )


def test_sample_fit_without_the_flag_still_samples_one_member(tmp_path, monkeypatch):
    """The default must not change: a group samples its selected member."""
    np.random.seed(13)
    fit = _group(3, link=False)

    import chisurf.macros.core_fit

    monkeypatch.setattr(
        chisurf.macros.core_fit,
        "save_project",
        lambda target_path, project_name="project", **kw: None,
    )

    report = chisurf.core.fitting.fit.sample_fit(
        fit=fit,
        target_directory=str(tmp_path),
        method="blocked",
        steps=400,
        thin=1,
        n_runs=1,
    )
    assert {e["name"] for e in report["parameters"]} == set(fit.model.parameter_names)
    assert len(report["parameters"]) == 2
