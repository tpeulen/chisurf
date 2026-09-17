"""Benchmark for the TCSPC fitting hot path — where a fit actually spends time.

This exists to settle an assumption rather than to chase a number. The tree
reaches for numba whenever a decay kernel looks like a loop, on the belief that
the kernels are what a fit costs. They are not, and this measures it:

``convolution``
    The one genuinely expensive step, and it is already compiled — ``per`` mode
    (the default, ``settings_chisurf.yaml``) routes to the photon library's
    SIMD kernel. It is 40–60% of a fit.

``parameter plumbing``
    ``Parameter.value`` is read tens of thousands of times per fit — more total
    time than the convolution's own body. This is Python object overhead, and no
    kernel compiler touches it.

``the spectrum kernels``
    ``e1tn``/``ere2``/``invert_interleaved`` and the FRET rate converters
    operate on ``2 * n_components`` elements. At that size a JIT dispatch costs
    more than the arithmetic: numba's own type-resolution
    (``numba/core/types/abstract.py:__hash__``) profiles *above* the kernels it
    is dispatching to. Removing the decorator makes these faster, not slower.

So the table below is the baseline a numba removal is judged against, and the
bar it has to clear is "no slower", not "not much slower".

**Discard the first run in a fresh process.** The per-case warm-up below covers
JIT compilation and first-call caches *within* a run, but not the process-wide
costs — numba's on-disk cache, the loader's page cache — and a cold first run
came out uniformly slow, with one cell reading 2.983 s against the 0.61 s it
actually costs. That is large enough to credit an unrelated change with a
fivefold speedup. Run the script twice and use the second table; if a change
appears to move a fit by more than a few percent, re-measure the old code in the
same session before believing it.

Run standalone for a markdown table to paste into
``docs/development/benchmarks.md``::

    PYTHONPATH=. python test/benchmarks/benchmark_fit_hot_path.py

or as a (slow) regression test::

    pytest test/benchmarks/benchmark_fit_hot_path.py -q -m slow
"""

from __future__ import annotations

import cProfile
import pstats
import time

import numpy as np
import pytest

from chisurf.core.fluorescence.decay_fit_model import build_fret_fit, build_lifetime_fit

#: Micro-time bin width in nanoseconds — a 1024-channel window over ~14.4 ns,
#: which is the shape a 70 MHz repetition rate gives.
BIN_WIDTH = 0.0141

#: Channel counts to sweep. The convolution's share of a fit grows with the
#: axis (it is the only step that is O(channels x components)), so a single
#: length would hide the trend that decides whether a kernel is worth compiling.
CHANNELS = (1024, 4096, 16384)


def make_decay(n_channels, lifetime=4.0, background=5.0, seed=0):
    """Return ``(decay, irf)`` — a Poisson-sampled decay and its prompt.

    Poisson noise rather than a smooth curve because a noiseless decay
    converges in a handful of iterations and the fit is then dominated by
    setup rather than by evaluation.
    """
    rng = np.random.default_rng(seed)
    time_axis = np.arange(n_channels) * BIN_WIDTH
    irf = np.exp(-0.5 * ((time_axis - 1.0) / 0.05) ** 2) * 1e4
    ideal = np.convolve(np.exp(-time_axis / lifetime), irf)[:n_channels] + background
    return rng.poisson(np.clip(ideal, 0, None)).astype(float), irf


def _time_fit(build, n_channels, repeat=3):
    """Return ``(best seconds, evaluations)`` for one fit from its initial guess.

    Every timed run gets a **fresh** fit. Re-running a converged ``Fit`` starts
    at the optimum and stops after a couple of dozen evaluations, which measures
    the optimiser's exit condition rather than the cost of fitting; a fit from
    the default seed takes roughly forty times as many evaluations.

    One throwaway fit runs first, so JIT compilation and every first-call cache
    fill land outside the measurement. Those are real costs, but they are
    one-per-process costs and belong in a different number.
    """
    decay, irf = make_decay(n_channels)
    build(decay, bin_width=BIN_WIDTH, irf=irf).run()

    best = np.inf
    for _ in range(repeat):
        fit = build(decay, bin_width=BIN_WIDTH, irf=irf)
        start = time.perf_counter()
        fit.run()
        best = min(best, time.perf_counter() - start)

    fit = build(decay, bin_width=BIN_WIDTH, irf=irf)
    profile = cProfile.Profile()
    profile.enable()
    fit.run()
    profile.disable()
    return best, _evaluations(profile)


def _evaluations(profile):
    """Number of model evaluations in a profiled run.

    ``Convolve.convolve`` is called once per model evaluation, which makes it a
    more honest count than the optimiser's own iteration number (that counts
    Jacobian sweeps as one). A BFF model evaluates in C++ and reports 0.
    """
    for (_, _, name), (calls, *_rest) in pstats.Stats(profile).stats.items():
        if name == "convolve":
            return calls
    return 0


def run_case(n_channels):
    """Return one row per model family for one axis length."""
    rows = []
    for label, build in (
        ("tcspc_lifetime (BFF)", build_lifetime_fit),
        ("GaussianModel", build_fret_fit),
    ):
        seconds, evaluations = _time_fit(build, n_channels)
        per_evaluation = seconds / evaluations if evaluations else float("nan")
        rows.append((label, seconds, evaluations, per_evaluation * 1e6))
    return rows


def main():
    """Print the markdown table."""
    print("| channels | model | fit [s] | evaluations | per evaluation [us] |")
    print("| --- | --- | ---: | ---: | ---: |")
    for n_channels in CHANNELS:
        for label, seconds, evaluations, micros in run_case(n_channels):
            print(f"| {n_channels} | {label} | {seconds:.3f} | {evaluations} | {micros:.1f} |")


@pytest.mark.slow
def test_a_lifetime_fit_calls_no_numba_kernel():
    """A standard lifetime fit runs entirely on compiled and NumPy code.

    The convolution goes to the photon library and everything around it is
    array arithmetic, so nothing on this path needs a JIT. A numba frame
    appearing here means a kernel was reintroduced onto the hot path — which is
    the regression that cost 229.5 ms of GUI thread the last time it happened.
    """
    decay, irf = make_decay(1024)
    build_lifetime_fit(decay, bin_width=BIN_WIDTH, irf=irf).run()

    fit = build_lifetime_fit(decay, bin_width=BIN_WIDTH, irf=irf)
    profile = cProfile.Profile()
    profile.enable()
    fit.run()
    profile.disable()

    offenders = sorted(
        {f"{path}:{name}" for (path, _, name) in pstats.Stats(profile).stats if "numba" in path}
    )
    assert not offenders, "a lifetime fit now goes through numba:\n  " + "\n  ".join(offenders)


if __name__ == "__main__":
    main()
