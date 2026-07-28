"""Benchmark for the in-tree Gaussian HMM (:mod:`chisurf.core.math.hmm`).

Measures the two things that decide how a binned-trace HMM analysis feels:

``per E-step``
    Wall time of one Baum-Welch map (forward-backward + M-step) at a fixed
    iteration count. Machine-dependent but trajectory-independent, so it is the
    honest cost comparison between implementations.

``to convergence``
    E-steps and wall time until the log-likelihood gain drops below ``tol``,
    plus the log-likelihood actually reached. Two implementations that stop at
    different optima are *not* comparable on time alone, so the likelihood is
    always reported next to it.

``hmmlearn`` is compared against only when it happens to be installed -- ChiSurf
no longer depends on it, and this module is what replaced it.

Run standalone for a markdown table to paste into
``docs/development/benchmarks.md``::

    PYTHONPATH=. python test/benchmarks/benchmark_hmm.py

or as a (slow) regression test::

    pytest test/benchmarks/benchmark_hmm.py -q -m slow
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from chisurf.core.math.hmm import GaussianHMM

try:  # optional external reference, not a dependency
    from hmmlearn.hmm import GaussianHMM as _ReferenceHMM
except ImportError:  # pragma: no cover - depends on the environment
    _ReferenceHMM = None

#: ``(n_bins, n_states, n_channels, separation, covariance_type)`` per case. The
#: separation scales the spread of the state means: 1.0 is a clean two-state
#: trace, 0.1 states that overlap within the shot noise, where EM crawls.
CASES = [
    (5_000, 2, 1, 1.0, "diag"),
    (50_000, 3, 2, 1.0, "diag"),
    (50_000, 3, 2, 1.0, "full"),
    (200_000, 4, 2, 1.0, "diag"),
    (50_000, 8, 3, 1.0, "diag"),
    (50_000, 3, 2, 0.15, "full"),
    (20_000, 4, 1, 0.1, "full"),
]


def make_trace(n_bins, n_states, n_channels, separation=1.0, seed=1):
    """Return a binned trace drawn from a sticky ``n_states`` Markov chain.

    Parameters
    ----------
    n_bins : int
        Length of the trace.
    n_states : int
        Number of hidden states.
    n_channels : int
        Number of detection channels (emission dimensions).
    separation : float
        Scale of the spread of the state means, in units of the default range;
        small values make the states overlap.
    seed : int
        Seed of the generating random stream.

    Returns
    -------
    numpy.ndarray
        Intensities, shape ``(n_bins, n_channels)``.
    """
    rng = np.random.default_rng(seed)
    transmat = np.full((n_states, n_states), 0.02 / (n_states - 1))
    np.fill_diagonal(transmat, 0.98)
    means = rng.uniform(5, 5 + 55 * separation, size=(n_states, n_channels))
    states = np.zeros(n_bins, dtype=int)
    for t in range(1, n_bins):
        states[t] = rng.choice(n_states, p=transmat[states[t - 1]])
    return means[states] + rng.normal(0, 4, size=(n_bins, n_channels))


class _EStepCounter:
    """Count E-steps of one fit, the implementation-independent work unit."""

    def __enter__(self):
        self.n = 0
        self._original = GaussianHMM._do_estep

        def counted(model, X, lengths, _original=self._original):
            self.n += 1
            return _original(model, X, lengths)

        GaussianHMM._do_estep = counted
        return self

    def __exit__(self, *exc_info):
        GaussianHMM._do_estep = self._original
        return False


def _timed(fit):
    """Return ``(seconds, model)`` of a single fit call."""
    start = time.perf_counter()
    model = fit()
    return time.perf_counter() - start, model


def _warm_up():
    """Compile the numba kernels so that they are not timed."""
    trace = make_trace(200, 2, 2)
    for covariance_type in ("diag", "full"):
        GaussianHMM(
            n_components=2, covariance_type=covariance_type, n_iter=3, random_state=0
        ).fit(trace)


def run(cases=None, n_iter_fixed=20, verbose=True):
    """Run the benchmark and return one result dictionary per case and variant.

    Parameters
    ----------
    cases : list of tuple, optional
        Cases to run; defaults to :data:`CASES`.
    n_iter_fixed : int
        Iteration count used for the per-E-step measurement.
    verbose : bool
        Print a markdown table as the cases complete.

    Returns
    -------
    list of dict
        One record per (case, variant).
    """
    _warm_up()
    records = []
    variants = {"chisurf (SQUAREM)": dict(accelerate=True), "chisurf (plain EM)": dict(accelerate=False)}

    if verbose:
        print("| case | implementation | s / E-step | E-steps | fit [s] | log L |")
        print("| --- | --- | ---: | ---: | ---: | ---: |")

    for n_bins, n_states, n_channels, separation, covariance_type in cases or CASES:
        X = make_trace(n_bins, n_states, n_channels, separation)
        label = (
            f"T={n_bins:,} K={n_states} F={n_channels} "
            f"sep={separation} {covariance_type}"
        )
        implementations = dict(variants)
        if _ReferenceHMM is not None:
            implementations["hmmlearn"] = None

        for name, options in implementations.items():
            common = dict(
                n_components=n_states,
                covariance_type=covariance_type,
                random_state=0,
                tol=1e-2,
            )
            if options is None:
                fixed = _timed(
                    lambda: _ReferenceHMM(n_iter=n_iter_fixed, **common).fit(X)
                )[0]
                seconds, model = _timed(
                    lambda: _ReferenceHMM(n_iter=1000, **common).fit(X)
                )
                n_esteps = model.monitor_.iter
            else:
                fixed = _timed(
                    lambda: GaussianHMM(
                        n_iter=n_iter_fixed, accelerate=False, **common
                    ).fit(X)
                )[0]
                with _EStepCounter() as counter:
                    seconds, model = _timed(
                        lambda: GaussianHMM(n_iter=1000, **options, **common).fit(X)
                    )
                n_esteps = counter.n
            record = {
                "case": label,
                "implementation": name,
                "seconds_per_estep": fixed / n_iter_fixed,
                "n_esteps": n_esteps,
                "seconds": seconds,
                "log_likelihood": float(model.score(X)),
            }
            records.append(record)
            if verbose:
                print(
                    f"| {label} | {name} | {record['seconds_per_estep']:.4f} | "
                    f"{n_esteps} | {seconds:.2f} | {record['log_likelihood']:,.1f} |"
                )
    return records


@pytest.mark.slow
def test_acceleration_does_not_cost_likelihood():
    """SQUAREM must reach at least the plain-EM optimum on a crawling problem."""
    X = make_trace(20_000, 4, 1, separation=0.1)
    common = dict(
        n_components=4, covariance_type="full", n_iter=1000, tol=1e-2, random_state=0
    )
    plain = GaussianHMM(accelerate=False, **common).fit(X)
    fast = GaussianHMM(accelerate=True, **common).fit(X)
    assert fast.score(X) >= plain.score(X) - 1.0

    with _EStepCounter() as counter:
        GaussianHMM(accelerate=True, **common).fit(X)
    accelerated_esteps = counter.n
    with _EStepCounter() as counter:
        GaussianHMM(accelerate=False, **common).fit(X)
    plain_esteps = counter.n
    assert accelerated_esteps < plain_esteps


if __name__ == "__main__":
    run()
