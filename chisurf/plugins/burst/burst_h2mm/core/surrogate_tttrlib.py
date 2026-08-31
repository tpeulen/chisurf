"""tttrlib-backed surrogate estimator.

Runs the amortised (surrogate) neural estimator through the C++
:class:`tttrlib.HmmSurrogate` while keeping the plugin's own
:class:`~.h2mm.BurstPhotons` / :class:`~.h2mm.H2mmModel` data types, so it is a
drop-in replacement for :func:`~.surrogate.estimate_model` on the surrogate
engines — the same relationship :mod:`.h2mm_tttrlib` has to the EM engines.

The C++ feature extractor reproduces :func:`~.surrogate.extract_features`
bit for bit (verified to 1e-12 against the numba kernel), so a surrogate trained
here with scikit-learn and exported via
:meth:`~.surrogate.SurrogateModel.export_json` gives identical estimates through
either path. When tttrlib is unavailable this module reports so via
:data:`HAVE_TTTRLIB` and callers fall back to the Python estimator.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .h2mm import BurstPhotons, H2mmModel
from .h2mm_tttrlib import _to_engine

try:
    import tttrlib

    HAVE_TTTRLIB = hasattr(tttrlib, "HmmSurrogate")
except Exception:  # pragma: no cover - tttrlib is optional
    tttrlib = None
    HAVE_TTTRLIB = False


def load(path: str | Path) -> "tttrlib.HmmSurrogate":
    """Load a surrogate from a ``tttrlib.hmm_surrogate`` JSON file.

    Raises
    ------
    RuntimeError
        If tttrlib is unavailable.
    """
    if not HAVE_TTTRLIB:
        raise RuntimeError("tttrlib with HmmSurrogate support is required")
    return tttrlib.HmmSurrogate.from_json_file(str(path))


def is_json_surrogate(obj) -> bool:
    """Whether ``obj`` names a JSON surrogate this backend can load."""
    if isinstance(obj, (str, Path)):
        return str(obj).endswith(".json")
    return tttrlib is not None and isinstance(obj, tttrlib.HmmSurrogate)


def extract_features(data: BurstPhotons) -> np.ndarray:
    """Feature vector via the C++ extractor (matches the numba one to 1e-12)."""
    if not HAVE_TTTRLIB:
        raise RuntimeError("tttrlib with HmmSurrogate support is required")
    return np.asarray(tttrlib.HmmSurrogate.features(_to_engine(data)), dtype=np.float64)


def estimate_model(
    data: BurstPhotons,
    n_states: int,
    surrogate,
    refine_iters: int = 0,
    tol: float = 1e-7,
) -> H2mmModel:
    """Estimate an H2MM model with the C++ surrogate, optionally polished by EM.

    Parameters
    ----------
    data : BurstPhotons
        Photon data in engine layout.
    n_states : int
        Number of hidden states; must match the surrogate.
    surrogate : tttrlib.HmmSurrogate or path
        A loaded surrogate, or a path to a ``tttrlib.hmm_surrogate`` JSON file.
    refine_iters : int
        If > 0, run this many Baum-Welch maps from the surrogate estimate.
    tol : float
        Convergence threshold for the optional refinement.

    Returns
    -------
    H2mmModel
        The estimated model.
    """
    if not HAVE_TTTRLIB:
        raise RuntimeError("tttrlib with HmmSurrogate support is required")
    if isinstance(surrogate, (str, Path)):
        surrogate = load(surrogate)
    if surrogate.get_n_states() != int(n_states):
        raise ValueError(
            f"surrogate trained for n_states={surrogate.get_n_states()}, got {n_states}")

    fit = surrogate.predict(_to_engine(data))
    model = H2mmModel(
        prior=np.asarray(fit.prior_np, dtype=np.float64),
        trans=np.asarray(fit.trans_np, dtype=np.float64),
        obs=np.asarray(fit.obs_np, dtype=np.float64),
        n_phot=data.n_photons,
    )
    if refine_iters > 0:
        # Polish with the plugin's own EM so the refined result is identical to
        # the pure-Python path (which itself dispatches to tttrlib for EM).
        # Routed, not `.h2mm.optimize`: this is the C++ surrogate, and it was
        # polishing its estimate with the fallback optimiser.
        from .engines import optimize

        model = optimize(model, data, max_iter=refine_iters, tol=tol)
    return model
