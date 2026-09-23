"""Every compute path goes through the engine seam, not around it.

Four places used to import the in-tree engine directly and so always got it,
even where the compiled one was available and 44x faster: ``fixed_loglik``,
``burst_gs``'s cross-check fit, ``surrogate``'s EM polish, and --- least
intentionally --- ``surrogate_tttrlib`` (now ``surrogate_bff``), the C++ surrogate, which refined its
own estimate with the in-tree optimiser.

That second engine has since been deleted, so those imports no longer resolve
and the mistake is unrepeatable *in that form*. The guard at the bottom stays
anyway: :mod:`~chisurf.plugins.burst.burst_h2mm.core.h2mm` still holds the data
types, and a compute helper added beside them later would be reachable the same
way.

What the cross-engine comparisons here used to check --- that the answer does
not depend on which engine ran --- now lives in ``test_ab_vs_h2mm_c.py``,
against the independent ``H2MM_C`` reference rather than against a port of
ourselves, which is the stronger check of the two.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_h2mm.core import engines, h2mm


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


def test_fixed_loglik_is_the_input_models_own_likelihood(data, model):
    """What ``fixed_loglik`` documents, pinned against the engine it routes to.

    At ``max_iter=1`` the reported value must be the log-likelihood of the model
    that went *in*. An engine reporting the post-update value instead would
    silently shift every confidence interval built on this.
    """
    from chisurf.plugins.burst.burst_h2mm.core.analysis import fixed_loglik

    assert fixed_loglik(model, data) == pytest.approx(
        engines.optimize(model, data, max_iter=1, tol=0.0).loglik, rel=1e-12
    )


def test_an_em_map_improves_the_likelihood(data, model):
    """``max_iter`` does something -- else the test above passes vacuously."""
    one = engines.optimize(model, data, max_iter=1, tol=0.0).loglik
    two = engines.optimize(model, data, max_iter=2, tol=0.0).loglik
    assert two > one


def test_fit_states_recovers_the_simulated_states(data):
    """The engine is reached *and* returns the right answer.

    The bursts alternate between E = 0.25 and E = 0.75, so a fit that ran but
    collapsed onto one state -- which a broken seam could still produce -- fails
    here rather than passing as "it did not raise".
    """
    fit = engines.fit_states(data, 2, n_restarts=1, max_iter=300, seed=0)
    path, _ = engines.viterbi(fit, data)

    assert path.shape == data.streams.shape
    assert len(set(np.unique(path))) == 2, "the fit collapsed onto one state"

    fractions = sorted(
        float(np.mean(data.streams[path == state] == 1)) for state in np.unique(path)
    )
    assert fractions[0] == pytest.approx(0.25, abs=0.12), fractions
    assert fractions[1] == pytest.approx(0.75, abs=0.12), fractions


def test_no_module_imports_compute_entry_points_from_the_types_module():
    """Only ``engines`` may hand out compute; ``h2mm`` is data types.

    ``BurstPhotons``, ``H2mmModel``, ``prepare_bursts``, ``factory_model`` and
    ``simulate_bursts`` are fine to import from ``h2mm``. A compute entry point
    would not be: importing one pins the caller to whatever sits behind it,
    which is exactly how four call sites ended up on the slow engine.
    """
    import pathlib

    compute = ("optimize", "fit_states", "viterbi", "posterior", "sample_states", "sample_paths")
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
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped.startswith("from") or "h2mm import" not in stripped:
                continue
            if "engines" in stripped or "h2mm_tttrlib" in stripped:
                continue
            imported = stripped.split("import", 1)[1]
            if any(name in imported for name in compute):
                offenders.append(f"{rel}: {stripped}")

    assert not offenders, (
        "these import a compute entry point from the types module and so bypass "
        "the engine seam:\n  " + "\n  ".join(offenders)
    )
