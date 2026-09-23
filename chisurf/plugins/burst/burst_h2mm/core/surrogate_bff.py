"""IMP.bff-backed surrogate estimator.

Runs the amortised (surrogate) neural estimator through the C++
:class:`IMP.bff.HmmSurrogate` while keeping the plugin's own
:class:`~.h2mm.BurstPhotons` / :class:`~.h2mm.H2mmModel` data types, so it is a
drop-in replacement for :func:`~.surrogate.estimate_model` on the surrogate
engines. Learned models live in IMP.bff; tttrlib, which runs the EM engines
(:mod:`.h2mm_tttrlib`), carries no neural networks.

``BurstPhotons`` already is the CSR layout the C++ side reads (per-photon
streams, burst offsets, gap slots, unique Δt), so it is handed over as arrays
without building a photon engine first.

The C++ feature extractor reproduces :func:`~.surrogate.extract_features`
bit for bit (verified to 1e-12), so a surrogate trained here with scikit-learn
and exported via :meth:`~.surrogate.SurrogateModel.export_json` gives identical
estimates through either path. When IMP.bff has no surrogate (built without
tttrlib) this module reports so via :data:`HAVE_BFF` and callers fall back to
the Python estimator.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .h2mm import BurstPhotons, H2mmModel

try:
    import IMP.bff as bff

    HAVE_BFF = hasattr(bff, "HmmSurrogate")
except Exception:  # pragma: no cover - IMP.bff is optional
    bff = None
    HAVE_BFF = False


def _require() -> None:
    if not HAVE_BFF:
        raise RuntimeError("IMP.bff with HmmSurrogate support (built with tttrlib) is required")


def _layout(data: BurstPhotons) -> tuple:
    """``BurstPhotons`` as the (streams, offsets, gap_slot, unique_dt, n_streams)
    arrays :meth:`IMP.bff.HmmSurrogate.predict_from_layout` reads."""
    return (
        np.asarray(data.streams, dtype=np.int64).tolist(),
        np.asarray(data.burst_offsets, dtype=np.int64).tolist(),
        np.asarray(data.gap_slot, dtype=np.int64).tolist(),
        np.asarray(data.unique_dt, dtype=np.int64).tolist(),
        int(data.n_streams),
    )


def load(path: str | Path):
    """Load an :class:`IMP.bff.HmmSurrogate` from a ``bff.hmm_surrogate`` JSON file.

    Raises
    ------
    RuntimeError
        If IMP.bff has no surrogate.
    """
    _require()
    return bff.HmmSurrogate.from_json_file(str(path))


def is_json_surrogate(obj) -> bool:
    """Whether ``obj`` names a JSON surrogate this backend can load."""
    if isinstance(obj, (str, Path)):
        return str(obj).endswith(".json")
    return HAVE_BFF and isinstance(obj, bff.HmmSurrogate)


def extract_features(data: BurstPhotons) -> np.ndarray:
    """Feature vector via the C++ extractor (matches the in-tree one to 1e-12)."""
    _require()
    return np.asarray(bff.HmmSurrogate.extract_features_from_layout(*_layout(data)), dtype=np.float64)


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
    surrogate : IMP.bff.HmmSurrogate or path
        A loaded surrogate, or a path to a ``bff.hmm_surrogate`` JSON file.
    refine_iters : int
        If > 0, run this many Baum-Welch maps from the surrogate estimate.
    tol : float
        Convergence threshold for the optional refinement.

    Returns
    -------
    H2mmModel
        The estimated model.
    """
    _require()
    if isinstance(surrogate, (str, Path)):
        surrogate = load(surrogate)
    if surrogate.get_n_states() != int(n_states):
        raise ValueError(
            f"surrogate trained for n_states={surrogate.get_n_states()}, got {n_states}"
        )

    fit = surrogate.predict_from_layout(*_layout(data))
    n, m = fit.get_n_states(), fit.get_n_streams()
    model = H2mmModel(
        prior=np.asarray(fit.get_prior(), dtype=np.float64),
        trans=np.asarray(fit.get_trans(), dtype=np.float64).reshape(n, n),
        obs=np.asarray(fit.get_obs(), dtype=np.float64).reshape(n, m),
        n_phot=data.n_photons,
    )
    if refine_iters > 0:
        # Polish with the plugin's own EM so the refined result is identical to
        # the pure-Python path (which itself dispatches to tttrlib for EM).
        from .engines import optimize

        model = optimize(model, data, max_iter=refine_iters, tol=tol)
    return model
