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
    round-off; see :func:`optimize`).
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

import logging

import numpy as np

from .h2mm import BurstPhotons, H2mmModel

logger = logging.getLogger(__name__)

# H2MM compute lives in the photon library. There is no second implementation
# to fall back to: the in-tree one was deleted once it was 44x slower than this
# for identical numbers (see .h2mm), which made it a slower way to be wrong
# about which engine had run rather than a safety net.
from . import h2mm_tttrlib as _tttrlib_engine

# The C++ surrogate is used only for surrogates stored in the language-neutral
# JSON schema; a pickled SurrogateModel stays on the scikit-learn path.
from . import surrogate_bff as _bff_surrogate


def _use_tttrlib() -> bool:
    """Whether the compiled H2MM backend is usable.

    Retained as the single place that answers the question; it is no longer a
    *choice*, because there is nothing else to choose: the
    ``CHISURF_H2MM_BACKEND`` escape went with the second engine.
    """
    return bool(_tttrlib_engine.HAVE_TTTRLIB)


def active_backend() -> str:
    """Return the H2MM compute backend: ``'tttrlib'``, or raise if unusable."""
    _require_backend("compute")
    return "tttrlib"


def _require_backend(what: str) -> None:
    """Raise a diagnosable error when the compiled engine is missing.

    Parameters
    ----------
    what : str
        The operation being attempted, named in the message.

    Raises
    ------
    RuntimeError
        When :class:`tttrlib.HMM` is unavailable.
    """
    if not _tttrlib_engine.HAVE_TTTRLIB:
        raise RuntimeError(
            f"H2MM {what} needs tttrlib's HMM engine, which this build does "
            f"not have. ChiSurf no longer ships a second implementation to "
            f"fall back to. Install or rebuild tttrlib (>= 0.27)."
        )


def viterbi(model: H2mmModel, data: BurstPhotons):
    """Viterbi path + ICL."""
    _require_backend("Viterbi decoding")
    return _tttrlib_engine.viterbi(model, data)


def _require_tttrlib(what: str):
    """Return the engine module, or say why *what* cannot run.

    Kept as a distinct name because the decoders that call it (γ, the marginal
    draw, FFBS) used to be the *only* things the second engine could not do;
    now nothing can run without this one.
    """
    _require_backend(what)
    return _tttrlib_engine


def posterior(model: H2mmModel, data: BurstPhotons) -> tuple[np.ndarray, int]:
    """Per-photon posterior state probabilities γ, ``(gamma, n_underflow)``.

    ``gamma[i, k]`` is the probability that photon ``i`` is in state ``k``. Its
    column means are the **unbiased** state occupancy — what counting a decoded
    path only approximates, and what counting a *Viterbi* path gets wrong in one
    direction.
    """
    return _require_tttrlib("posterior (gamma)").posterior(model, data)


def sample_states(model: H2mmModel, data: BurstPhotons, seed: int = 0) -> tuple[np.ndarray, int]:
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
    return _require_tttrlib("FFBS path sampling").sample_paths(model, data, seed, n_samples)


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
    "jitter": False,  # independent draws shatter dwells into single photons
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
        EM parameters (passed to the engine).
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
            # A format dispatch, not two implementations: both paths extract
            # features with the same (compiled) extractor and differ only in
            # which regressor was serialised -- a C++ estimator in msgpack, or a
            # pickled scikit-learn model.
            if _bff_surrogate.is_native_surrogate(sm):
                # A msgpack surrogate is the C++ estimator's format. If that engine
                # is missing, say so -- quietly handing it to the scikit-learn
                # path would answer with a different estimator than the one the
                # surrogate was trained for.
                if not _bff_surrogate.HAVE_BFF:
                    raise RuntimeError(
                        "this surrogate is in the compiled estimator's msgpack "
                        "format, but IMP.bff has no HmmSurrogate (it was "
                        "built without tttrlib); rebuild it"
                    )
                return _bff_surrogate.estimate_model(
                    data, n_states, sm, refine_iters=ri, tol=tol
                )
            # A pickled SurrogateModel stays on the scikit-learn path. This
            # used to go through the in-tree `fit_states`, whose surrogate arm
            # only forwarded here -- so it kept a whole EM engine alive to make
            # one call.
            from .surrogate import estimate_model

            return estimate_model(data, n_states, sm, refine_iters=ri, tol=tol)
        # No surrogate for this state count → exact EM keeps the scan usable.
        engine = "em"

    single_precision = engine == "em-float32"
    _require_backend("fitting")
    # `on_iter` is how a GUI stop is delivered: it raises CancelledError out of
    # the progress callback, and that must reach the caller unfitted rather than
    # be treated as a backend problem. Nothing is caught here.
    return _tttrlib_engine.fit_states(
        data,
        n_states,
        n_restarts=n_restarts,
        max_iter=max_iter,
        tol=tol,
        seed=seed,
        single_precision=single_precision,
        on_iter=on_iter,
    )


def optimize(
    model: H2mmModel,
    data: BurstPhotons,
    max_iter: int = 500,
    tol: float = 1e-7,
    min_trans: float = 1e-12,
    accelerate: bool = True,
    single_precision: bool = False,
    on_iter=None,
) -> H2mmModel:
    """Baum-Welch EM from ``model``.

    At ``max_iter=1`` the reported ``loglik`` is the *input* model's forward
    log-likelihood, which is what :func:`~.analysis.fixed_loglik` rests on.

    Parameters
    ----------
    model : H2mmModel
        Starting model.
    data : BurstPhotons
        Photon data in engine layout.
    max_iter : int
        Maximum EM maps.
    tol : float
        Convergence tolerance on the log-likelihood.
    min_trans : float
        Floor on transition probabilities.
    accelerate : bool
        Use SQUAREM acceleration.
    single_precision : bool
        Run the float32 kernel.
    on_iter : callable, optional
        Progress callback ``on_iter(done, total)``.

    Returns
    -------
    H2mmModel
        The optimised model.
    """
    _require_backend("optimisation")
    return _tttrlib_engine.optimize(
        model,
        data,
        max_iter=max_iter,
        tol=tol,
        min_trans=min_trans,
        accelerate=accelerate,
        single_precision=single_precision,
        on_iter=on_iter,
    )


def fit_states(
    data: BurstPhotons,
    n_states: int,
    *,
    n_restarts: int = 2,
    max_iter: int = 500,
    tol: float = 1e-7,
    seed: int = 0,
    single_precision: bool = False,
    on_iter=None,
) -> H2mmModel:
    """Fit an ``n_states`` model from random restarts, routed to the backend.

    The plain-EM half of :func:`fit_one`, for callers that want a fit rather
    than an engine choice.

    Parameters
    ----------
    data : BurstPhotons
        Photon data in engine layout.
    n_states : int
        State count to fit.
    n_restarts, max_iter, tol, seed
        EM parameters.
    single_precision : bool
        Run the float32 kernel.
    on_iter : callable, optional
        Progress callback ``on_iter(done, total)``.

    Returns
    -------
    H2mmModel
        The best model over the restarts.
    """
    return fit_one(
        data,
        n_states,
        engine="em-float32" if single_precision else "em",
        n_restarts=n_restarts,
        max_iter=max_iter,
        tol=tol,
        seed=seed,
        on_iter=on_iter,
    )
