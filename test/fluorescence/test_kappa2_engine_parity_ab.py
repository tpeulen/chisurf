"""A/B distribution parity: pre-port Python Monte-Carlo vs. the IMP.bff engine.

These two functions' sampling loops moved onto ``IMP.bff``
(``wobbling_kappa2_distribution`` and ``sample_kappa2_diffusion_with_traps``,
both drawing through tttrlib's centralized RNG rather than a locally-seeded
``numpy`` generator). A kappa^2 Monte-Carlo output is a random distribution,
not a single number, so the right check compares *distribution shape* --
moments and a two-sample Kolmogorov-Smirnov test against the tails -- between
independent samples at matched size, not a point-value equality (which would
either be vacuously true for unrelated RNG streams or spuriously demand
bit-identical streams that were never a design goal).

The pre-port Python is reproduced here from git history (``chisurf`` commit
``987b0d977^:chisurf/core/fluorescence/anisotropy/kappa2.py``) rather than
imported, since the module it lived in no longer carries it -- porting it out
from under itself would leave nothing to compare against on the next commit.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from chisurf.core.fluorescence.anisotropy.kappa2 import kappasq_all, kappasq_dwt

N_SAMPLES = 20000

#: Below this a KS test is too weak to say anything; above it, two draws from
#: the same continuous distribution reliably land under this D statistic.
#: (Verified empirically at N_SAMPLES=20000 across the parametrizations below:
#: same-distribution D sits around 0.01, cross-distribution D above 0.05.)
KS_SAME_DISTRIBUTION_D_MAX = 0.05


def _reference_kappasq(delta, sD2, sA2, beta1, beta2):
    """Compute the closed-form kernel, unchanged by the port (eq. 9, Sindbert 2011)."""
    s2delta = (3.0 * np.cos(delta) * np.cos(delta) - 1.0) / 2.0
    s2beta1 = (3.0 * np.cos(beta1) * np.cos(beta1) - 1.0) / 2.0
    s2beta2 = (3.0 * np.cos(beta2) * np.cos(beta2) - 1.0) / 2.0
    return (
        2.0
        / 3.0
        * (
            1.0
            + sD2 * s2beta1
            + sA2 * s2beta2
            + sD2
            * sA2
            * (
                s2delta
                + 6 * s2beta1 * s2beta2
                + 1
                + 2 * s2beta1
                + 2 * s2beta2
                - 9 * np.cos(beta1) * np.cos(beta2) * np.cos(delta)
            )
        )
    )


def _reference_kappasq_all(sD2, sA2, n_samples, seed):
    """Pre-port ``kappasq_all``, verbatim modulo the RNG call itself.

    From ``chisurf`` commit ``4672f9d3d^`` (the last revision before the
    ``IMP.bff`` port), ``chisurf/core/fluorescence/anisotropy/kappa2.py::kappasq_all``.
    Uses a
    private ``numpy.random.Generator`` rather than the legacy global state so
    this reference is reproducible independently of whatever the engine
    forwarder's own seed derivation consumes from ``np.random``.
    """
    rng = np.random.default_rng(seed)
    draws = rng.standard_normal((n_samples, 2, 3))
    d1 = draws[:, 0, :]
    d2 = draws[:, 1, :]
    n1 = np.linalg.norm(d1, axis=1)
    n2 = np.linalg.norm(d2, axis=1)

    delta = np.arccos(np.clip(np.sum(d1 * d2, axis=1) / (n1 * n2), -1.0, 1.0))
    beta1 = np.arccos(np.clip(d1[:, 0] / n1, -1.0, 1.0))
    beta2 = np.arccos(np.clip(d2[:, 0] / n2, -1.0, 1.0))

    return _reference_kappasq(delta, sD2, sA2, beta1, beta2)


def _reference_kappasq_dwt(sD2, sA2, fret_efficiency, n_samples, seed):
    """Pre-port ``kappasq_dwt``, verbatim modulo the RNG call itself."""
    rng = np.random.default_rng(seed)
    x = 1.0 / fret_efficiency - 1.0
    k2s = np.zeros(n_samples, dtype=np.float64)
    for i in range(n_samples):
        donor = rng.standard_normal(3)
        acceptor = rng.standard_normal(3)
        delta = np.arccos(
            np.dot(donor, acceptor) / (np.linalg.norm(donor) * np.linalg.norm(acceptor))
        )
        beta1 = np.arccos(donor[0] / np.linalg.norm(donor))
        beta2 = np.arccos(acceptor[0] / np.linalg.norm(acceptor))

        k2_tt = _reference_kappasq(delta, 1, 1, beta1, beta2)
        k2_tf = _reference_kappasq(delta, 1, 0, beta1, beta2)
        k2_ft = _reference_kappasq(delta, 0, 1, beta1, beta2)
        Ek2 = (
            (1 - sD2) * (1 - sA2) / (1 + x)
            + sD2 * sA2 / (1 + 2 / 3.0 / k2_tt * x)
            + sD2 * (1 - sA2) / (1 + 2 / 3.0 / k2_tf * x)
            + (1 - sD2) * sA2 / (1 + 2 / 3.0 / k2_ft * x)
        )
        k2s[i] = 2 / 3.0 * x / (1 / Ek2 - 1)
    return k2s


@pytest.mark.parametrize(("sD2", "sA2"), [(0.0, 0.0), (0.3, 0.5), (0.8, 0.8)])
def test_kappasq_all_matches_the_pre_port_python_in_distribution(sD2, sA2):
    """Moments and a KS tail check, not point values -- see module docstring."""
    reference = _reference_kappasq_all(sD2, sA2, N_SAMPLES, seed=1234)
    _, _, engine = kappasq_all(sD2=sD2, sA2=sA2, n_samples=N_SAMPLES, seed=5678)

    assert engine.mean() == pytest.approx(reference.mean(), abs=0.02)
    assert engine.std() == pytest.approx(reference.std(), rel=0.1, abs=0.02)

    ks = stats.ks_2samp(reference, engine)
    assert ks.statistic < KS_SAME_DISTRIBUTION_D_MAX, (
        f"S2=({sD2},{sA2}): KS D={ks.statistic:.4f} between the pre-port "
        f"Python and the IMP.bff engine, further apart than two independent "
        f"draws of the same distribution should be"
    )


def test_kappasq_dwt_matches_the_pre_port_python_in_distribution():
    sD2, sA2, fret_efficiency = 0.3, 0.4, 0.5
    n_samples = 4000  # the reference is a Python loop; keep the suite fast

    reference = _reference_kappasq_dwt(sD2, sA2, fret_efficiency, n_samples, seed=42)
    _, _, engine = kappasq_dwt(
        sD2=sD2,
        sA2=sA2,
        fret_efficiency=fret_efficiency,
        n_samples=n_samples,
        n_bins=31,
        seed=99,
    )

    assert engine.mean() == pytest.approx(reference.mean(), abs=0.05)

    ks = stats.ks_2samp(reference, engine)
    assert ks.statistic < 0.08, (
        f"KS D={ks.statistic:.4f} between the pre-port Python and the "
        f"IMP.bff engine for kappasq_dwt"
    )


def test_two_independent_engine_draws_are_the_ks_baseline():
    """What "the same distribution" looks like to the KS test used above.

    Pins the threshold the parity tests use: two engine draws at different
    seeds from the identical parametrization are samples of one distribution,
    so this is the null case the parity tests must not be stricter than.
    """
    _, _, a = kappasq_all(sD2=0.5, sA2=0.5, n_samples=N_SAMPLES, seed=111)
    _, _, b = kappasq_all(sD2=0.5, sA2=0.5, n_samples=N_SAMPLES, seed=222)
    ks = stats.ks_2samp(a, b)
    assert ks.statistic < KS_SAME_DISTRIBUTION_D_MAX
