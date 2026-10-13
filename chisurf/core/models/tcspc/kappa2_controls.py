"""What the FRET models' κ² controls read and write, without a toolkit.

The editor section ``kappa2_controls`` (a FRET model's *dynamic κ²* / *static κ²*
switch, *show κ²*, *compute κ²* and *calc R0*) acts on three things of the model:
the orientation regime (``orientation_parameter.mode``), the κ² distribution a
static average uses (``orientation_parameter.orientation_spectrum``, interleaved
amplitude/κ² pairs, held on the native model's ``kappa2_distribution`` port; none
is the isotropic distribution) together with the scalar ``fret_parameters.kappa2``
the dynamic average uses, and the Förster radius. Both editors -- the legacy Qt one and the emtk shell's, which
reaches the model through the server -- call these functions, so the two cannot
disagree on what a button does.
"""

from __future__ import annotations

from typing import Any

import numpy as np

#: The value ``kappa2`` has when nothing says otherwise: dynamic isotropic averaging.
DYNAMIC_KAPPA2 = 2.0 / 3.0


def orientation_mode(model: Any) -> str:
    """``"slow"`` (static κ² average) or ``"fast"`` (dynamic), as the model holds it."""
    parameter = getattr(model, "orientation_parameter", None)
    return str(getattr(parameter, "mode", "fast") or "fast") if parameter is not None else "fast"


def set_orientation_mode(model: Any, mode: str) -> None:
    """Switch the κ² regime: ``"slow"`` averages a static distribution, ``"fast"`` uses one κ².

    Raises
    ------
    ValueError
        For a mode other than ``"fast"`` / ``"slow"``.
    AttributeError
        For a model without an orientation parameter.
    """
    mode = str(mode)
    if mode not in ("fast", "slow"):
        raise ValueError(f"the κ² mode is 'fast' or 'slow', not {mode!r}")
    parameter = getattr(model, "orientation_parameter", None)
    if parameter is None:
        raise AttributeError(f"{type(model).__name__} has no orientation parameter")
    parameter.mode = mode
    model.update()


def scalar_kappa2(model: Any) -> float:
    """The model's scalar κ² (``fret_parameters.kappa2``), 2/3 when it has none."""
    try:
        return float(getattr(getattr(model, "fret_parameters", None), "kappa2"))
    except (TypeError, ValueError, AttributeError):
        return DYNAMIC_KAPPA2


def _pairs(spectrum: Any) -> list[tuple[float, float]]:
    if spectrum is None:
        return []
    values = np.asarray(spectrum, dtype=float).ravel()
    if values.size < 2 or values.size % 2:
        return []
    return list(zip(values[0::2], values[1::2]))


#: The grid the native static average samples the isotropic density on when no
#: distribution is given (``FRETSpectrumNode``: ``kappa2_points`` over [0.01, 4]).
ISOTROPIC_GRID = (0.01, 4.0, 128)


def isotropic_kappa2_pairs() -> list[tuple[float, float]]:
    """``(w, κ²)`` of the isotropic static distribution, on the grid the native kernel averages over."""
    from chisurf.core.fluorescence.anisotropy.kappa2 import p_isotropic_orientation_factor

    lo, hi, n = ISOTROPIC_GRID
    k2 = np.linspace(lo, hi, n)
    weights = np.asarray(p_isotropic_orientation_factor(k2, normalize=False), dtype=float)
    weights = weights / float(np.sum(weights))
    return list(zip(weights.tolist(), k2.tolist()))


def used_kappa2_pairs(parameter: Any, scalar: float) -> list[tuple[float, float]]:
    """``(w, κ²)`` the model averages over: a spike at *scalar* when dynamic, else the static distribution.

    Static uses the distribution held on *parameter* (*compute κ²*'s result) and the
    isotropic one when none is held -- what the native kernel does with an empty port.
    """
    if parameter is None or str(getattr(parameter, "mode", "fast") or "fast") != "slow":
        return [(1.0, float(scalar))]
    return _pairs(getattr(parameter, "orientation_spectrum", None)) or isotropic_kappa2_pairs()


def kappa2_pairs(model: Any) -> list[tuple[float, float]]:
    """``(amplitude, κ²)`` pairs the model's FRET rates are averaged over (see :func:`used_kappa2_pairs`)."""
    return used_kappa2_pairs(getattr(model, "orientation_parameter", None), scalar_kappa2(model))


def kappa2_distribution(model: Any, use_fast: bool = True, n_bins: int = 256) -> dict:
    """Everything *show κ²* draws: ρ(κ²), ρ(R_app/R_DA) and, if the model has one, ρ(R_DA) and ρ(R_app).

    Parameters
    ----------
    model : object
        A FRET model.
    use_fast : bool
        The fast loop-based convolution of the distance distribution with the
        κ² ratio distribution, else the exact outer product
        (:func:`chisurf.core.fluorescence.general.convolve_distance_with_k2_ratio`).
    n_bins : int
        Bins of the ratio and apparent-distance histograms.

    Returns
    -------
    dict
        ``mode``, ``kappa2`` (the scalar), ``k2`` / ``p_k2`` (the normalised
        distribution, sorted), ``k2_mean``, ``ratio`` / ``p_ratio`` and, when the
        model holds a distance distribution, ``r_da`` / ``p_r_da`` and
        ``r_app`` / ``p_r_app`` (each scaled to a maximum of one). Lists, so the
        result travels as JSON.
    """
    from chisurf.core.fluorescence.general import (
        convolve_distance_with_k2_ratio,
        kappa2_to_distance_ratio,
    )

    pairs = [(a, k) for a, k in kappa2_pairs(model) if np.isfinite(a) and np.isfinite(k)]
    if not pairs:
        raise ValueError("no orientation factor distribution is available")
    amps = np.asarray([a for a, _ in pairs], dtype=float)
    k2 = np.asarray([k for _, k in pairs], dtype=float)
    order = np.argsort(k2)
    amps, k2 = amps[order], k2[order]
    total = float(np.sum(amps))
    p_k2 = amps / total if total > 0 else amps
    ratio, weights, k2_mean = kappa2_to_distance_ratio(amps, k2, n_bins=n_bins)
    out: dict[str, Any] = {
        "mode": orientation_mode(model),
        "kappa2": scalar_kappa2(model),
        "k2": k2.tolist(),
        "p_k2": np.asarray(p_k2, dtype=float).tolist(),
        "k2_mean": float(k2_mean),
        "ratio": np.asarray(ratio, dtype=float).tolist(),
        "p_ratio": np.asarray(weights, dtype=float).tolist(),
    }
    distribution = getattr(model, "distance_distribution", None)
    try:
        array = np.asarray(distribution, dtype=float) if distribution is not None else None
    except (TypeError, ValueError):
        array = None
    if array is not None and array.ndim == 3 and array.shape[0] > 0:
        amp_r, r_da = array[0, 0, :], array[0, 1, :]
        valid = (amp_r > 0) & np.isfinite(r_da) & (r_da > 0)
        amp_r, r_da = amp_r[valid], r_da[valid]
        if r_da.size:
            r_app, p_r_app = convolve_distance_with_k2_ratio(
                r_da, amp_r, ratio, weights, n_bins=n_bins, use_fast=bool(use_fast)
            )

            def scaled(values):
                values = np.asarray(values, dtype=float)
                peak = float(np.max(values)) if values.size else 0.0
                return (values / peak if peak > 0 else values).tolist()

            out.update(
                r_da=r_da.tolist(),
                p_r_da=scaled(amp_r),
                r_app=np.asarray(r_app, dtype=float).tolist(),
                p_r_app=scaled(p_r_app),
            )
    return out


def apply_kappa2_distribution(
    model: Any, k2: Any, p_k2: Any, k2_mean: float | None = None
) -> float:
    """Use a computed κ² distribution: its pairs for the static average, its mean as the scalar κ².

    What *compute κ²* does with the κ²-distribution calculator's result.

    Parameters
    ----------
    model : object
        A FRET model.
    k2, p_k2 : array_like
        κ² values and their weights (any normalisation; one bin edge too many
        is dropped from *k2*, as the calculator returns edges).
    k2_mean : float, optional
        The calculator's mean; the weighted mean of *k2* when not finite.

    Returns
    -------
    float
        The κ² the model now holds.

    Raises
    ------
    ValueError
        For an empty distribution, a size mismatch or zero total weight.
    """
    k2 = np.asarray(k2, dtype=float).ravel()
    weights = np.asarray(p_k2, dtype=float).ravel()
    if weights.size == 0:
        raise ValueError("no κ² distribution was computed")
    if k2.size == weights.size + 1:
        k2 = k2[1:]
    if k2.size != weights.size:
        raise ValueError("the κ² values and their weights differ in length")
    total = float(np.sum(weights))
    if not total > 0:
        raise ValueError("the κ² distribution has zero total weight")
    weights = weights / total
    interleaved = np.empty(2 * k2.size, dtype=float)
    interleaved[0::2] = weights
    interleaved[1::2] = k2
    parameter = getattr(model, "orientation_parameter", None)
    if parameter is not None:
        parameter.orientation_spectrum = interleaved
    mean = (
        float(k2_mean)
        if k2_mean is not None and np.isfinite(k2_mean)
        else float(np.sum(k2 * weights))
    )
    model.fret_parameters.kappa2 = mean
    model.update()
    return mean


def set_forster_radius(model: Any, r0: float) -> None:
    """Write a Förster radius (Å) into the model's FRET parameters (*calc R0*'s result)."""
    value = float(r0)
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"a Förster radius is a positive length, not {r0!r}")
    model.fret_parameters.forster_radius = value
    model.update()


__all__ = [
    "DYNAMIC_KAPPA2",
    "apply_kappa2_distribution",
    "kappa2_distribution",
    "isotropic_kappa2_pairs",
    "kappa2_pairs",
    "orientation_mode",
    "scalar_kappa2",
    "set_forster_radius",
    "set_orientation_mode",
    "used_kappa2_pairs",
]
