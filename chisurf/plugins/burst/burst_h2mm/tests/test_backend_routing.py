"""Every compute path goes through the backend selector, not around it.

``engines.py`` picks tttrlib-or-fallback per call, but four places imported the
fallback engine *directly* and so always got it, even where the C++ backend was
available and ~44x faster on the same data: ``analysis.fixed_loglik``,
``burst_gs``'s cross-check fit, ``surrogate``'s EM polish, and --- least
intentionally --- ``surrogate_tttrlib``, the C++ surrogate, which refined its
own estimate with the fallback optimiser.

The routing is only safe because the two engines agree, which is what the first
test here pins: a future divergence has to fail loudly rather than change what
``fixed_loglik`` returns depending on which backend happens to be installed.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_h2mm.core import engines, h2mm
from chisurf.plugins.burst.burst_h2mm.core import h2mm_tttrlib as tttrlib_engine

needs_tttrlib = pytest.mark.skipif(
    not tttrlib_engine.HAVE_TTTRLIB, reason="tttrlib H2MM backend not available"
)


@pytest.fixture(scope="module")
def data():
    """Bursts alternating between a low- and a high-FRET state."""
    rng = np.random.default_rng(0)
    times, streams = [], []
    clock = 0
    for index in range(30):
        efficiency = 0.25 if index % 2 == 0 else 0.75
        burst_times, burst_streams = [], []
        for _ in range(int(rng.integers(60, 140))):
            clock += int(rng.integers(1, 40))
            burst_times.append(clock)
            burst_streams.append(1 if rng.random() < efficiency else 0)
        times.append(np.asarray(burst_times, dtype=np.int64))
        streams.append(np.asarray(burst_streams, dtype=np.int64))
        clock += 5000
    return h2mm.prepare_bursts(times, streams, n_streams=2)


@pytest.fixture(scope="module")
def model():
    """A fixed starting model, so every comparison below is like-for-like."""
    return h2mm.factory_model(2, 2, seed=1)


# -- the semantics the routing rests on ---------------------------------------

@needs_tttrlib
def test_the_two_engines_report_the_same_log_likelihood(data, model):
    """Routing `optimize` is a speed choice only if this holds.

    Checked at ``max_iter=1`` because that is the case ``fixed_loglik`` depends
    on -- the reported value is the *input* model's forward log-likelihood, and
    an engine that reported the post-update value instead would silently change
    every confidence interval built on it.
    """
    one_fallback = h2mm.optimize(model, data, max_iter=1, tol=0.0).loglik
    one_tttrlib = tttrlib_engine.optimize(model, data, max_iter=1, tol=0.0).loglik
    assert one_tttrlib == pytest.approx(one_fallback, rel=1e-10)

    two_fallback = h2mm.optimize(model, data, max_iter=2, tol=0.0).loglik
    two_tttrlib = tttrlib_engine.optimize(model, data, max_iter=2, tol=0.0).loglik
    assert two_tttrlib == pytest.approx(two_fallback, rel=1e-10)
    # An EM map improves the likelihood, so the two calls must differ -- if they
    # did not, `max_iter` would not be doing anything and the check above would
    # pass for the wrong reason.
    assert two_fallback > one_fallback


def test_fixed_loglik_is_the_input_models_own_likelihood(data, model):
    """What `fixed_loglik` documents, pinned against the engine it now routes to."""
    from chisurf.plugins.burst.burst_h2mm.core.analysis import fixed_loglik

    assert fixed_loglik(model, data) == pytest.approx(
        engines.optimize(model, data, max_iter=1, tol=0.0).loglik, rel=1e-12
    )


# -- the selector is actually consulted ---------------------------------------

def test_fixed_loglik_respects_the_backend_setting(data, model, monkeypatch):
    """`fixed_loglik` used to import the fallback directly and ignore this."""
    from chisurf.plugins.burst.burst_h2mm.core import analysis

    called = []
    real = engines._optimize_numba

    def spy(*args, **kwargs):
        called.append(1)
        return real(*args, **kwargs)

    monkeypatch.setenv("CHISURF_H2MM_BACKEND", "numba")
    monkeypatch.setattr(engines, "_optimize_numba", spy)
    analysis.fixed_loglik(model, data)
    assert called, "the fallback engine was not reached with the backend forced to it"


@needs_tttrlib
def test_the_selector_reaches_the_compiled_engine_by_default(data, model, monkeypatch):
    """The other half: with nothing forced, the C++ engine is the one that runs."""
    monkeypatch.delenv("CHISURF_H2MM_BACKEND", raising=False)
    called = []
    real = tttrlib_engine.optimize

    def spy(*args, **kwargs):
        called.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(engines._tttrlib_engine, "optimize", spy)
    engines.optimize(model, data, max_iter=1, tol=0.0)
    assert called, "the compiled engine was available but not used"


# -- the results do not depend on which one ran -------------------------------

@needs_tttrlib
def test_fit_states_agrees_across_backends(data, monkeypatch):
    """`burst_gs`'s cross-check calls this; its answer must not move."""
    monkeypatch.delenv("CHISURF_H2MM_BACKEND", raising=False)
    compiled = engines.fit_states(data, 2, n_restarts=1, max_iter=200, seed=0)

    monkeypatch.setenv("CHISURF_H2MM_BACKEND", "numba")
    fallback = engines.fit_states(data, 2, n_restarts=1, max_iter=200, seed=0)

    assert compiled.loglik == pytest.approx(fallback.loglik, rel=1e-8)


def test_no_module_imports_compute_entry_points_from_the_engine(monkeypatch):
    """The guard behind all of the above: only ``engines`` may reach past it.

    Data structures (``BurstPhotons``, ``H2mmModel``, ``prepare_bursts``,
    ``factory_model``, ``simulate_bursts``) are fine to import from ``h2mm``;
    the compute entry points are not, because importing them pins the caller to
    one engine.
    """
    import pathlib

    compute = ("optimize", "fit_states", "viterbi", "posterior", "sample_states",
               "sample_paths")
    # parents[5], not [4]: this file is chisurf/plugins/burst/burst_h2mm/tests/,
    # so [4] is the `chisurf` package and `root / "chisurf"` would be a path
    # that does not exist -- rglob yields nothing and the test passes vacuously.
    root = pathlib.Path(__file__).resolve().parents[5]
    package = root / "chisurf"
    assert package.is_dir(), f"scan root is wrong: {package}"

    allowed = {
        "chisurf/plugins/burst/burst_h2mm/core/engines.py",
        "chisurf/plugins/burst/burst_h2mm/core/h2mm.py",
        "chisurf/plugins/burst/burst_h2mm/core/h2mm_tttrlib.py",
    }

    offenders = []
    for path in package.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel in allowed or "/tests/" in rel or "/test/" in rel:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("from") or "h2mm import" not in stripped:
                continue
            if "engines" in stripped or "h2mm_tttrlib" in stripped:
                continue
            imported = stripped.split("import", 1)[1]
            if any(name in imported for name in compute):
                offenders.append(f"{rel}: {stripped}")

    assert not offenders, (
        "these import a compute entry point from the fallback engine and so "
        "bypass the backend selector:\n  " + "\n  ".join(offenders)
    )
