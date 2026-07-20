"""H2MM compute-engine selection — one dispatcher over the fitting back-ends.

The plugin offers several ways to estimate an H2MM model at a given state count;
they trade exactness for speed. This module is the single place that maps an
``engine`` name to the corresponding call, so the CLI, GUI, backend service, and
:func:`~.analysis.analyze` all agree.

Engines
-------
``em``
    Exact Baum-Welch EM with SQUAREM acceleration (the default). Reproduces the
    reference maximum-likelihood estimate.
``em-float32``
    The same EM in the approximate ``float32`` fast mode (~1.5–2× faster, small
    round-off; see :func:`~.h2mm.optimize`).
``surrogate``
    The optional amortised neural estimator (:mod:`.surrogate`): one forward pass,
    **approximate**, ~5–25× faster. Requires a trained surrogate for the state
    count; falls back to ``em`` where none is supplied.
``surrogate-refine``
    ``surrogate`` seed polished by ``refine_iters`` Baum-Welch maps.

For model selection over several state counts, the *scan* always scores fitted
models by BIC/ICL as usual; only *how each model is fitted* changes.
"""

from __future__ import annotations

import os

from .h2mm import BurstPhotons, H2mmModel, fit_states
from .h2mm import viterbi as _viterbi_numba

# Prefer the fast tttrlib C++ backend for the EM engines; fall back to numba.
# Set CHISURF_H2MM_BACKEND=numba to force the pure-numba engine.
try:
    from . import h2mm_tttrlib as _tttrlib_engine

    _HAVE_TTTRLIB = _tttrlib_engine.HAVE_TTTRLIB
except Exception:  # pragma: no cover - defensive
    _tttrlib_engine = None
    _HAVE_TTTRLIB = False

# The C++ surrogate is used only for surrogates stored in the language-neutral
# JSON schema; a pickled SurrogateModel stays on the scikit-learn path.
try:
    from . import surrogate_tttrlib as _tttrlib_surrogate

    _HAVE_TTTRLIB_SURROGATE = _tttrlib_surrogate.HAVE_TTTRLIB
except Exception:  # pragma: no cover - defensive
    _tttrlib_surrogate = None
    _HAVE_TTTRLIB_SURROGATE = False


def _use_tttrlib() -> bool:
    """Whether to route EM/Viterbi through the tttrlib C++ backend."""
    if os.environ.get("CHISURF_H2MM_BACKEND", "").strip().lower() == "numba":
        return False
    return _HAVE_TTTRLIB


def active_backend() -> str:
    """Return the H2MM compute backend in use: ``'tttrlib'`` or ``'numba'``."""
    return "tttrlib" if _use_tttrlib() else "numba"


def viterbi(model: H2mmModel, data: BurstPhotons):
    """Viterbi path + ICL, routed to the active backend (tttrlib or numba)."""
    if _use_tttrlib():
        try:
            return _tttrlib_engine.viterbi(model, data)
        except Exception:  # pragma: no cover - fall back on any backend issue
            pass
    return _viterbi_numba(model, data)


ENGINES: tuple[str, ...] = ("em", "em-float32", "surrogate", "surrogate-refine")

ENGINE_LABELS: dict[str, str] = {
    "em": "EM (exact)",
    "em-float32": "EM float32 (fast, approximate)",
    "surrogate": "Surrogate NN (fastest, approximate)",
    "surrogate-refine": "Surrogate NN + EM polish",
}


def normalize_engine(engine: str | None) -> str:
    """Return a valid engine name, defaulting unknown/empty values to ``em``."""
    e = (engine or "em").strip().lower()
    return e if e in ENGINES else "em"


def fit_one(
    data: BurstPhotons,
    n_states: int,
    engine: str = "em",
    *,
    surrogates: dict[int, object] | None = None,
    refine_iters: int = 20,
    n_restarts: int = 2,
    max_iter: int = 500,
    tol: float = 1e-7,
    seed: int = 0,
    on_iter=None,
) -> H2mmModel:
    """Fit a single ``n_states`` model with the selected ``engine``.

    Parameters
    ----------
    data : BurstPhotons
        Photon data in engine layout.
    n_states : int
        State count to fit.
    engine : str
        One of :data:`ENGINES`.
    surrogates : dict, optional
        Mapping ``n_states -> SurrogateModel`` (or path). Used by the surrogate
        engines; missing entries fall back to exact EM.
    refine_iters : int
        EM polish maps for ``surrogate-refine``.
    n_restarts, max_iter, tol, seed
        EM parameters (passed to :func:`~.h2mm.fit_states`).
    on_iter : callable, optional
        Per-EM-map progress callback ``on_iter(done, total)`` (EM engines only).

    Returns
    -------
    H2mmModel
        The fitted model.
    """
    engine = normalize_engine(engine)

    if engine in ("surrogate", "surrogate-refine"):
        sm = (surrogates or {}).get(int(n_states))
        if sm is not None:
            ri = int(refine_iters) if engine == "surrogate-refine" else 0
            # JSON surrogates run through the C++ estimator; pickled
            # SurrogateModel objects stay on the scikit-learn path. Both produce
            # the same numbers — the C++ feature extractor reproduces the numba
            # one to 1e-12 — so this is purely a speed/dependency choice.
            if (
                _use_tttrlib()
                and _HAVE_TTTRLIB_SURROGATE
                and _tttrlib_surrogate.is_json_surrogate(sm)
            ):
                try:
                    return _tttrlib_surrogate.estimate_model(
                        data, n_states, sm, refine_iters=ri, tol=tol)
                except Exception:  # pragma: no cover - fall back on any issue
                    pass
            return fit_states(data, n_states, surrogate=sm, refine_iters=ri, tol=tol)
        # No surrogate for this state count → exact EM keeps the scan usable.
        engine = "em"

    single_precision = engine == "em-float32"
    # Fast path: the tttrlib C++ backend (same algorithm, several-fold faster).
    if _use_tttrlib():
        try:
            return _tttrlib_engine.fit_states(
                data, n_states, n_restarts=n_restarts, max_iter=max_iter,
                tol=tol, seed=seed, single_precision=single_precision,
                on_iter=on_iter,
            )
        except Exception:  # pragma: no cover - fall back to numba on any issue
            pass

    return fit_states(
        data,
        n_states,
        n_restarts=n_restarts,
        max_iter=max_iter,
        tol=tol,
        seed=seed,
        single_precision=single_precision,
        on_iter=on_iter,
    )
