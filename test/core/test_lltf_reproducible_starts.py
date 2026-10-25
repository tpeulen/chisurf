"""LLTF randomized starting values are seeded, so a run repeats exactly.

Known issue "LLTF fits are not reproducible" (2026-10-02) pinned the gap; the
fitter now derives a per-fit RNG from ``randomize_initial_values.seed``
(default 0, ``None`` = fresh). These tests pin that contract.
"""

from __future__ import annotations

import numpy as np

from chisurf.plugins.fluorescence_decay.lltf.core import fitter


def _noisy_bi_exponential(seed: int = 7):
    rng = np.random.default_rng(seed)
    time = np.arange(256, dtype=float) * 0.048
    counts = 2000 * np.exp(-time / 3.9) + 400 * np.exp(-time / 0.4)
    counts = rng.poisson(counts).astype(float)
    irf = np.zeros(256)
    irf[:3] = [0.2, 0.6, 0.2]
    return counts, irf, time


def _fit_randomized(seed):
    counts, irf, time = _noisy_bi_exponential()
    decay = fitter.Decay(counts, irf, time)
    result = decay.fit(
        n_lifetimes=2,
        randomize_initial_values=True,
        seed=seed,
        find_optimal=False,
        plot_probabilities=False,
        plot_weighted_residuals=False,
        save_intermediate_results=False,
    )
    spectrum = np.asarray(result["lifetime_spectrum"], dtype=float)
    lifetimes = np.sort(spectrum[:4:2])
    return lifetimes, float(result["chi_square"])


def test_same_seed_repeats_the_fit_exactly():
    a, sse_a = _fit_randomized(seed=0)
    b, sse_b = _fit_randomized(seed=0)
    np.testing.assert_allclose(a, b, rtol=1e-12)
    np.testing.assert_allclose(sse_a, sse_b, rtol=1e-12)


def test_different_seeds_change_the_start():
    a, _ = _fit_randomized(seed=0)
    b, _ = _fit_randomized(seed=1)
    assert not np.allclose(a, b, rtol=1e-9)
