"""MEM sampling uses the same dimensionless entropy as the fitted SDK objective."""

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.maxent_decay.core import sampling
from chisurf.plugins.fluorescence_decay.maxent_decay.core.solver import (
    solve_fret_mem,
    solve_lifetime_mem,
)


@pytest.fixture(scope="module", params=["lifetime", "fret", "lifetime-tiny", "fret-tiny"])
def fitted_result(request):
    """Share one SDK evaluation for each scientific objective scenario."""
    return _fit_real_case(request.param)


def _fit_real_case(mode):
    """Fit real D0 and DA decays with fixed, declared instrument parameters."""
    folder = Path(__file__).resolve().parents[5] / "test/data/tcspc/EasyTau300"
    lifetime = mode.startswith("lifetime")
    name = "D0" if lifetime else "DA"
    data = np.loadtxt(folder / f"215-268 {name}.dat")
    lamp = np.loadtxt(folder / f"215-268 {name} irf.dat")[:, 1]
    options = dict(
        decay=data[:, 1],
        lamp=lamp,
        dt=np.diff(data[:, 0]).mean(),
        fitrange=(700, data.shape[0] - 1),
        max_iter=80,
        nu=0.001,
        background=5.0,
        irf_background=1.0,
        optimize_nuisance=False,
    )
    prior = None if lifetime else np.linspace(1.0, 3.0, 24)
    if mode.endswith("tiny"):
        prior = np.linspace(1.0, 3.0, 24)
        prior[[0, 1, 2]] = [1e-20, 0.0, -1.0]
    if lifetime:
        result = solve_lifetime_mem(tau=np.linspace(0.4, 8.0, 24), prior=prior, **options)
    else:
        result = solve_fret_mem(
            R=np.linspace(20.0, 100.0, 24),
            donly=[0.6, 3.6, 0.4, 4.1],
            x_donly=0.15,
            timeshift=0.7,
            lamp_scatter=0.0001,
            period=10.0,
            prior=prior,
            **options,
        )
    return result


def _reference(result, u):
    """Evaluate the SDK objective independently from the measured design."""
    counts = np.maximum(result["y"] - result["fit_additive"], 0.0).sum()
    design = result["Fi"] * result["sigma"][:, None]
    scale = counts * result["p"].size / design.sum()
    p = result["p"] * np.exp(u)
    p *= result["p"].sum() / p.sum()
    fractions = p / scale
    entropy = np.sum(fractions - result["prior"] - fractions * np.log(fractions / result["prior"]))
    target = (result["y"] - result["fit_additive"]) / result["sigma"]
    chi = np.mean((target - result["Fi"] @ p) ** 2)
    objective = chi - 0.5 * result["nu"] * entropy
    return scale, entropy, chi, objective, np.mean(target**2)


def test_exported_inputs_reconstruct_sdk_entropy_and_objective(fitted_result):
    """The scale comes from observables, not the returned amplitude sum."""
    scale, entropy, chi, objective, _ = _reference(fitted_result, np.zeros(24))
    assert scale > 1.0
    assert fitted_result["p"].sum() / scale != pytest.approx(1.0, abs=1e-3)
    assert entropy == pytest.approx(fitted_result["S"], rel=1e-10, abs=1e-10)
    assert chi == pytest.approx(fitted_result["chisq"], rel=1e-10)
    assert objective == pytest.approx(fitted_result["Q"], rel=1e-10)


@pytest.mark.parametrize("vectorized", [False, True])
def test_sampling_scores_and_gradients_match_fitted_objective(
    fitted_result, monkeypatch, vectorized
):
    """Both callbacks preserve Q differences and gradients in fitted units."""
    result = fitted_result
    calls = []

    class InspectSampler:
        """Inspect callbacks without accepting a stochastic chain as a proof."""

        def __init__(self, walkers, ndim, callback, *, args, **kwargs):
            self.ndim = ndim
            self.callback, self.args = callback, args
            calls.append(self)

        def run_mcmc(self, state, **kwargs):
            return state

        def get_chain(self, flat):
            return np.zeros((4, self.ndim))

    monkeypatch.setattr(sampling, "EnsembleSampler", InspectSampler)
    stats = sampling.sample_mem_distribution_mcmc(
        result, steps_total=2, substeps=1, vectorized=vectorized
    )
    instance = calls[0]

    def score(u):
        value = instance.callback(u, *instance.args)
        return float(np.asarray(value).ravel()[0])

    u = np.linspace(-0.1, 0.1, 24)
    zero = np.zeros(24)
    _, _, _, fitted_q, constant = _reference(result, zero)
    assert -2.0 * score(zero) + constant == pytest.approx(fitted_q, rel=1e-9)
    expected = -0.5 * (_reference(result, u)[3] - _reference(result, zero)[3])
    assert score(u) - score(zero) == pytest.approx(expected, rel=1e-8, abs=1e-8)
    delta = np.zeros(24)
    delta[8] = 1e-5
    gradient = (score(u + delta) - score(u - delta)) / (2e-5)
    reference_gradient = (
        -0.5 * (_reference(result, u + delta)[3] - _reference(result, u - delta)[3]) / (2e-5)
    )
    assert gradient == pytest.approx(reference_gradient, rel=1e-6, abs=1e-5)
    np.testing.assert_allclose(stats["p_mean"], result["p"], rtol=1e-14)


@pytest.mark.parametrize("missing", ["Fi", "y", "sigma", "fit_additive"])
def test_incomplete_result_cannot_guess_entropy_units(fitted_result, missing):
    """An absent fitted contract must fail before starting a sampler."""
    result = {key: value for key, value in fitted_result.items() if key != missing}
    with pytest.raises(RuntimeError, match="recover fitted units"):
        sampling.sample_mem_distribution_mcmc(result, steps_total=1)


@pytest.mark.parametrize("mode", ["lifetime-tiny", "fret-tiny"])
def test_tiny_positive_prior_is_distinct_from_nonpositive_floor(mode):
    """A real SDK fit retains the tiny raw weight instead of replacing it."""
    result = _fit_real_case(mode)
    prior = result["prior"]
    assert prior[0] / prior[1] == pytest.approx(1e-8, rel=1e-14, abs=0.0)
    assert prior[1] == prior[2]
    _, entropy, _, objective, _ = _reference(result, np.zeros(24))
    assert entropy == pytest.approx(result["S"], rel=1e-10, abs=1e-10)
    assert objective == pytest.approx(result["Q"], rel=1e-10)


@pytest.mark.parametrize("bad_prior", [[1.0], np.zeros(24), np.full(24, np.nan)])
def test_malformed_exported_prior_cannot_silently_change_target(fitted_result, bad_prior):
    """Provided priors are authoritative and must match the fitted target."""
    result = dict(fitted_result, prior=bad_prior)
    with pytest.raises(RuntimeError, match="entropy prior"):
        sampling.sample_mem_distribution_mcmc(result, steps_total=1)


@pytest.mark.parametrize("substeps, expected", [(2, [2, 2, 1]), (10, [5])])
def test_requested_steps_include_final_partial_chunk(
    fitted_result, monkeypatch, tmp_path, substeps, expected
):
    """Chunking completes all requested steps and reports coherent progress."""
    calls = []
    progress = []

    class RecordingSampler:
        """Record requested work without making random-chain assertions."""

        def __init__(self, walkers, ndim, callback, **kwargs):
            self.walkers, self.ndim = walkers, ndim

        def run_mcmc(self, state, *, nsteps, **kwargs):
            calls.append(nsteps)
            return state

        def get_chain(self, flat):
            return np.zeros((sum(calls) * self.walkers, self.ndim))

    monkeypatch.setattr(sampling, "EnsembleSampler", RecordingSampler)
    archive_path = tmp_path / "samples.npz"
    stats = sampling.sample_mem_distribution_mcmc(
        fitted_result,
        steps_total=5,
        substeps=substeps,
        thin=1,
        progress_cb=lambda done, total: progress.append((done, total)) or False,
        filename=str(archive_path),
    )
    assert calls == expected
    assert progress == [(int(done), 5) for done in np.cumsum(expected)]
    assert stats["n_samples"] == 5 * stats["nwalkers"] // 2
    with np.load(archive_path) as archive:
        assert archive["steps_total"] == 5
        assert archive["n_samples"] == stats["n_samples"]


def test_real_short_chain_completes_five_requested_steps(fitted_result, tmp_path):
    """An actual unseeded chain proves execution, not stochastic convergence."""
    path = tmp_path / "short-chain.npz"
    stats = sampling.sample_mem_distribution_mcmc(
        fitted_result,
        steps_total=5,
        substeps=2,
        thin=1,
        vectorized=True,
        filename=str(path),
    )
    assert stats["n_samples"] == 5 * stats["nwalkers"] // 2
    with np.load(path) as archive:
        assert np.isfinite(archive["p_samples"]).all()
        np.testing.assert_allclose(
            archive["p_samples"].sum(axis=1),
            fitted_result["p"].sum(),
            rtol=1e-14,
        )
