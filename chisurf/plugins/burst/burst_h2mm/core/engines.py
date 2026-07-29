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

Decoders
--------
Fitting is one choice; deciding which state each photon belongs to is another.
:data:`DECODERS` lists the options and :func:`decode` dispatches them. ``viterbi``
answers *"what is the single most likely state sequence"*, which is not the
question most downstream products ask: an occupancy, a per-state decay, or a
state-labelled photon stream wants *"how do the photons distribute over the
states"*, and the argmax answers that with a one-directional bias — photons at
γ = (0.7, 0.3) all land in state 0, so the 30 % is erased. ``jitter`` and
``ffbs`` draw from the posterior instead and reproduce the distribution by
construction. See the tttrlib ``h2mm-state-decoding`` guide.
"""

from __future__ import annotations

import concurrent.futures
import logging
import os

import numpy as np

from .h2mm import BurstPhotons, H2mmModel, fit_states
from .h2mm import viterbi as _viterbi_numba

logger = logging.getLogger(__name__)

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


def _backend_fallback(what: str, exc: Exception) -> None:
    """Record that the C++ backend failed *what* and the numba engine takes over.

    A silent ``except Exception: pass`` makes a broken backend build look exactly
    like a working one, only slower; the fallback is a diagnosis the user needs.

    Parameters
    ----------
    what : str
        Name of the backend call that raised.
    exc : Exception
        The exception that triggered the fallback.
    """
    logger.warning(
        "tttrlib H2MM %s failed (%s: %s) - falling back to the numba engine.",
        what,
        type(exc).__name__,
        exc,
    )


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
        except concurrent.futures.CancelledError:
            raise  # a stop is not a backend failure - do not redo it on numba
        except Exception as exc:
            _backend_fallback("viterbi", exc)
    return _viterbi_numba(model, data)


def _require_tttrlib(what: str):
    """Return the tttrlib engine module, or explain why the decoder is missing.

    The faithful decoders (γ, the marginal draw, FFBS) live only in the C++
    engine; the numba engine implements Viterbi and EM. Rather than quietly
    substituting Viterbi — which is exactly the biased answer these decoders
    exist to avoid — say so.
    """
    if _use_tttrlib():
        return _tttrlib_engine
    raise RuntimeError(
        f"H2MM {what} needs the tttrlib backend, which is not active "
        f"(backend={active_backend()!r}). The numba engine implements EM and "
        f"Viterbi only. Unset CHISURF_H2MM_BACKEND=numba, or use "
        f"decoder='viterbi'."
    )


def posterior(model: H2mmModel, data: BurstPhotons) -> tuple[np.ndarray, int]:
    """Per-photon posterior state probabilities γ, ``(gamma, n_underflow)``.

    ``gamma[i, k]`` is the probability that photon ``i`` is in state ``k``. Its
    column means are the **unbiased** state occupancy — what counting a decoded
    path only approximates, and what counting a *Viterbi* path gets wrong in one
    direction.
    """
    return _require_tttrlib("posterior (gamma)").posterior(model, data)


def sample_states(
    model: H2mmModel, data: BurstPhotons, seed: int = 0
) -> tuple[np.ndarray, int]:
    """Draw each photon's state independently from its γ row.

    Faithful per photon, but the draws carry none of γ's temporal correlation,
    so the resulting path fragments: use it for photon-level products
    (occupancies, per-state decays, a state-labelled TTTR), never for dwell or
    transition statistics.
    """
    return _require_tttrlib("marginal state sampling").sample_states(model, data, seed)


def sample_paths(
    model: H2mmModel, data: BurstPhotons, seed: int = 0, n_samples: int = 1
) -> np.ndarray:
    """Draw whole trajectories from ``P(path | data)`` (FFBS).

    Each draw is an exact sample from the joint posterior, so unlike
    :func:`sample_states` the dwell structure is valid.
    """
    return _require_tttrlib("FFBS path sampling").sample_paths(
        model, data, seed, n_samples)


#: Per-photon state decoders. ``viterbi`` answers "what is the single most
#: likely state sequence"; the other two answer "how do the photons distribute
#: over the states", which is a different question and the one most downstream
#: products (occupancies, per-state decays, a state-labelled photon stream)
#: actually ask.
DECODERS: tuple[str, ...] = ("viterbi", "jitter", "ffbs")

#: Short enough to fit a combo box; the explanation lives in the tooltip and in
#: the state-decoding guide.
DECODER_LABELS: dict[str, str] = {
    "viterbi": "Viterbi (most likely path)",
    "jitter": "Jitter (draw per photon)",
    "ffbs": "FFBS (draw whole paths)",
}

#: Whether a decoder's path may be used for dwell/transition statistics.
DECODER_KEEPS_DWELLS: dict[str, bool] = {
    "viterbi": True,
    "jitter": False,   # independent draws shatter dwells into single photons
    "ffbs": True,
}


def normalize_decoder(decoder: str | None) -> str:
    """Return a valid decoder name, defaulting unknown/empty values to ``viterbi``."""
    d = (decoder or "viterbi").strip().lower()
    return d if d in DECODERS else "viterbi"


def decode(
    model: H2mmModel,
    data: BurstPhotons,
    decoder: str = "viterbi",
    seed: int = 0,
) -> tuple[np.ndarray, int]:
    """Assign one state per photon with the chosen decoder.

    Returns ``(path, n_underflow)``; ``n_underflow`` is 0 for ``viterbi``, which
    cannot underflow, and otherwise counts photons whose posterior row carried
    no information (they were drawn uniformly).
    """
    decoder = normalize_decoder(decoder)
    if decoder == "jitter":
        return sample_states(model, data, seed)
    if decoder == "ffbs":
        return sample_paths(model, data, seed, 1)[0], 0
    path, _icl = viterbi(model, data)
    return path, 0


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
                except concurrent.futures.CancelledError:
                    raise
                except Exception as exc:
                    _backend_fallback("surrogate estimate_model", exc)
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
        except concurrent.futures.CancelledError:
            # ``on_iter`` is how a GUI stop is delivered: it raises out of the
            # progress callback. Catching it here would abandon the backend and
            # silently restart the same state count on the slower engine.
            raise
        except Exception as exc:
            _backend_fallback("fit_states", exc)

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
