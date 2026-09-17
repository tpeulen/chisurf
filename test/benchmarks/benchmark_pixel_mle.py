"""A/B benchmark for the pixel-wise FLIM MLE core optimisations.

Compares, on a real confocal FLIM image, three configurations that must all
produce *identical* per-pixel lifetimes:

    baseline   engine="loop", n_workers=1   (per-pixel bincount + serial fits)
    +fast      engine="fast", n_workers=1   (vectorised C++ extraction)
    +parallel  engine="fast", n_workers=N   (vectorised extraction + threaded batch)

Run standalone for a printed table::

    PYTHONPATH=. python test/benchmarks/benchmark_pixel_mle.py

or as a (slow) regression test asserting equivalence + a speedup::

    pytest test/benchmarks/benchmark_pixel_mle.py -q -m slow
"""

from __future__ import annotations

import pathlib
import time

import numpy as np
import pytest

from chisurf.core.datastore import numeric_column

_FLIM_PTU = pathlib.Path("/Users/tpeulen/dev/tttr-data/imaging/pq/Microtime200_HH400/beads.ptu")
_BINNING = 8


def _settings(**overrides):
    from chisurf.plugins.microscopy.img_pixel_mle.core import PixelMleSettings

    n_ch = 2048 // _BINNING
    irf1 = np.exp(-0.5 * ((np.arange(n_ch) - 8) / 2.0) ** 2)
    irf1 /= irf1.sum()
    irf = np.concatenate([irf1, irf1])
    kw = dict(
        channels_parallel=[0],
        channels_perpendicular=[1],
        irf=irf,
        period=1000.0 / 26.0,
        binning_factor=_BINNING,
        min_photons=20,
        tau=2.0,
        fix_gamma=True,
        fix_r0=True,
        fix_rho=True,
    )
    kw.update(overrides)
    return PixelMleSettings(**kw)


def _time(fn, repeats=3):
    fn()  # warm-up (imports, JIT, first-touch)
    best = min(_timed(fn) for _ in range(repeats))
    return best


def _timed(fn):
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


def run_benchmark(ptu_path=_FLIM_PTU, workers=None):
    """Run the A/B benchmark; returns ``(timings, taus)`` dicts keyed by config."""
    from chisurf.plugins.microscopy.img_pixel_mle.core import (
        fit_pixel_lifetimes_from_file,
    )
    from chisurf.plugins.microscopy.img_pixel_mle.core import pixel_mle as pm

    if workers is None:
        workers = max(2, (__import__("os").cpu_count() or 4) - 1)

    # Force the multi-thread path to engage on the (small) benchmark image.
    orig = pm._MIN_ROWS_FOR_THREADS
    pm._MIN_ROWS_FOR_THREADS = 50
    configs = {
        "baseline (loop, serial)": dict(engine="loop", n_workers=1),
        "+fast extraction": dict(engine="fast", n_workers=1),
        f"+threaded ({workers}w)": dict(engine="fast", n_workers=workers),
    }
    timings, taus, n_fit = {}, {}, {}
    try:
        for label, cfg in configs.items():
            res_holder = {}

            def _run(cfg=cfg, res_holder=res_holder):
                res_holder["r"] = fit_pixel_lifetimes_from_file(str(ptu_path), _settings(**cfg))

            timings[label] = _time(_run)
            r = res_holder["r"]
            taus[label] = numeric_column(r.dataframe, "tau")
            n_fit[label] = r.n_pixels_fit
    finally:
        pm._MIN_ROWS_FOR_THREADS = orig
    return timings, taus, n_fit


@pytest.mark.slow
@pytest.mark.skipif(not _FLIM_PTU.exists(), reason="tttr-data FLIM image not available")
def test_pixel_mle_ab_benchmark():
    timings, taus, n_fit = run_benchmark()
    labels = list(timings)
    base = taus[labels[0]]
    # All configurations must recover identical lifetimes.
    for label in labels[1:]:
        assert np.allclose(base, taus[label], equal_nan=True), f"{label} differs"
        assert n_fit[label] == n_fit[labels[0]]
    # The optimised end-to-end path must be at least as fast as the baseline.
    assert timings[labels[-1]] <= timings[labels[0]] * 1.05


def _main():
    if not _FLIM_PTU.exists():
        print(f"FLIM image not found: {_FLIM_PTU}")
        return
    timings, taus, n_fit = run_benchmark()
    labels = list(timings)
    base_t = timings[labels[0]]
    print(
        f"\nPixel-wise FLIM MLE A/B benchmark  ({_FLIM_PTU.name}, {n_fit[labels[0]]} pixels fit)\n"
    )
    print(f"{'configuration':<28}{'time [s]':>10}{'speedup':>10}")
    print("-" * 48)
    for label in labels:
        print(f"{label:<28}{timings[label]:>10.3f}{base_t / timings[label]:>9.2f}x")
    base = taus[labels[0]]
    ok = all(np.allclose(base, taus[lbl], equal_nan=True) for lbl in labels[1:])
    print("\nresults identical across configurations:", ok)


if __name__ == "__main__":
    _main()
