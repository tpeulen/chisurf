"""Benchmark for the ensemble samplers (:mod:`chisurf.core.fitting.ensemble`).

Samplers are compared on **effective samples per second** and **per
log-probability evaluation**. Raw steps per second says nothing: a slice step
costs several evaluations but travels much further than a stretch step, so only
the effective sample size (:func:`...fitting.diagnostics.effective_sample_size`)
divided by what was spent makes the two comparable.

The target is a correlated Gaussian, which is the case that separates the
proposals: a move that ignores the correlation has to take short steps to stay
inside the ridge, while one that learns the covariance steps along it.

Run standalone for a markdown table to paste into
``docs/development/benchmarks.md``::

    PYTHONPATH=. python test/benchmarks/benchmark_sampling.py

or as a (slow) regression test::

    pytest test/benchmarks/benchmark_sampling.py -q -m slow
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from chisurf.core.fitting.diagnostics import effective_sample_size
from chisurf.core.fitting.ensemble import (
    AdaptiveCovarianceMove,
    DifferentialMove,
    EnsembleSampler,
    EnsembleSliceSampler,
)

#: Dimensionalities and condition numbers to sample.
CASES = [(4, 1.0), (8, 100.0), (16, 100.0)]


def correlated_gaussian(n_dim, condition_number, seed=0):
    """Return ``(log_prob, covariance)`` of a correlated Gaussian target.

    Parameters
    ----------
    n_dim : int
        Number of dimensions.
    condition_number : float
        Ratio of the largest to the smallest variance along the principal axes;
        1.0 is isotropic.
    seed : int
        Seed of the random rotation.

    Returns
    -------
    log_prob : callable
        Log-density up to a constant.
    covariance : numpy.ndarray
        The covariance the density was built from.
    """
    rng = np.random.default_rng(seed)
    scales = np.geomspace(1.0, condition_number, n_dim)
    rotation = np.linalg.qr(rng.normal(size=(n_dim, n_dim)))[0]
    covariance = rotation @ np.diag(scales) @ rotation.T
    precision = np.linalg.inv(covariance)

    def log_prob(x):
        return -0.5 * float(x @ precision @ x)

    return log_prob, covariance


def _samplers(n_walkers, n_dim, log_prob, seed=0):
    """Return the samplers to compare, keyed by display name."""
    return {
        "stretch": EnsembleSampler(n_walkers, n_dim, log_prob, seed=seed),
        "slice (differential)": EnsembleSliceSampler(
            n_walkers, n_dim, log_prob, moves=DifferentialMove(), seed=seed
        ),
        "slice (adaptive covariance)": EnsembleSliceSampler(
            n_walkers, n_dim, log_prob, moves=AdaptiveCovarianceMove(), seed=seed
        ),
    }


def run(cases=None, n_steps=2000, burn_in=500, verbose=True):
    """Run the benchmark and return one record per (case, sampler).

    Parameters
    ----------
    cases : list of tuple, optional
        ``(n_dim, condition_number)`` pairs; defaults to :data:`CASES`.
    n_steps : int
        Stored steps per walker.
    burn_in : int
        Steps discarded before the effective sample size is measured.
    verbose : bool
        Print a markdown table as the cases complete.

    Returns
    -------
    list of dict
    """
    records = []
    if verbose:
        print("| target | sampler | ESS/s | ESS/eval | ESS (min) | wall [s] |")
        print("| --- | --- | ---: | ---: | ---: | ---: |")

    for n_dim, condition_number in cases or CASES:
        log_prob, _ = correlated_gaussian(n_dim, condition_number)
        n_walkers = 4 * n_dim
        start = np.random.default_rng(1).normal(size=(n_walkers, n_dim))
        label = f"{n_dim}-D Gaussian, κ={condition_number:g}"

        for name, sampler in _samplers(n_walkers, n_dim, log_prob).items():
            began = time.perf_counter()
            sampler.run_mcmc(start, n_steps)
            seconds = time.perf_counter() - began
            chain = sampler.get_chain(discard=burn_in)
            # (steps, walkers, dim) -> one chain per walker, as the diagnostic wants.
            ess = float(np.nanmin(effective_sample_size(chain.transpose(1, 0, 2))))
            record = {
                "target": label,
                "sampler": name,
                "ess_per_second": ess / seconds,
                "ess_per_evaluation": ess / max(sampler.n_evaluations, 1),
                "ess": ess,
                "seconds": seconds,
            }
            records.append(record)
            if verbose:
                print(
                    f"| {label} | {name} | {record['ess_per_second']:,.0f} | "
                    f"{record['ess_per_evaluation']:.4f} | {ess:,.0f} | {seconds:.2f} |"
                )
    return records


@pytest.mark.slow
def test_covariance_move_wins_on_a_correlated_target():
    """Learning the covariance must pay off where the target is correlated."""
    records = run(cases=[(8, 100.0)], n_steps=1500, burn_in=500, verbose=False)
    by_name = {r["sampler"]: r for r in records}
    assert (
        by_name["slice (adaptive covariance)"]["ess_per_evaluation"]
        > by_name["stretch"]["ess_per_evaluation"]
    )


if __name__ == "__main__":
    run()
