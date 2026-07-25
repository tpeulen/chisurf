"""Putty scale factors — PyMOL's ``cartoon_putty``.

A putty cartoon is a tube whose *thickness* carries a per-residue number: the
b-factor as deposited, or anything written into it. That makes it one of the few
representations that shows a quantity rather than a shape, and for this group the
quantity is usually not a b-factor at all — a solvent accessibility from
``get_area``, a fitted lifetime, a per-residue FRET efficiency — written into the
b-factor field and then drawn.

Transcribed from ``ExtrudeComputeScaleFactors`` (``layer1/Extrude.cpp``). PyMOL
offers nine transforms, which fall into three families and differ in **what the
number is measured against**:

* *normalized* — a z-score, ``(range + (b − mean)/stdev) / range``. Scale-free, so
  it does the right thing whatever units the property is in. This is the default,
  and the only one that needs no thought before use.
* *relative* / *scaled* — measured against the data's own range, or against the
  ``range`` setting directly. Useful when two structures must share a thickness
  scale.
* *absolute* — the raw value. Only meaningful when the number is already a radius.

Each is then raised to ``scale_power`` (the *nonlinear* half of each pair; the
*linear* variants skip it) and clamped to ``[scale_min, scale_max]``.

Two details are easy to miss and both change the picture:

* the clamp is applied **after** the power, not before;
* the factors are then smoothed along the chain with a **running window average**
  that leaves the two end points alone. Without it a single outlying residue
  produces a bead on the tube rather than a bulge.
"""

from __future__ import annotations

import numpy as np

__all__ = ["PUTTY_TRANSFORMS", "putty_scale_factors", "smooth_scale_factors"]

#: Transform names to PyMOL's ``cPuttyTransform*`` codes (``layer0/Base.h``).
PUTTY_TRANSFORMS: dict[str, int] = {
    "normalized_nonlinear": 0,
    "relative_nonlinear": 1,
    "scaled_nonlinear": 2,
    "absolute_nonlinear": 3,
    "normalized_linear": 4,
    "relative_linear": 5,
    "scaled_linear": 6,
    "absolute_linear": 7,
    "implied_rms": 8,
}

#: Transforms that raise the scale to ``scale_power``.
_NONLINEAR = {0, 1, 2, 3}

#: PyMOL's ``R_SMALL8``, the guard against dividing by a degenerate spread.
_R_SMALL8 = 1e-8


def putty_scale_factors(
    values,
    *,
    transform: str | int = "normalized_nonlinear",
    scale_power: float = 1.5,
    scale_range: float = 2.0,
    scale_min: float = 0.6,
    scale_max: float = 4.0,
) -> np.ndarray:
    """Turn per-atom values into tube-radius multipliers.

    Parameters
    ----------
    values : sequence of float
        One number per point along the chain — the b-factor, or whatever was
        written into it.
    transform : str or int, optional
        A key of :data:`PUTTY_TRANSFORMS`, or PyMOL's numeric code. The default
        is PyMOL's: a z-score raised to ``scale_power``.
    scale_power : float, optional
        Exponent for the nonlinear transforms. ``cartoon_putty_scale_power``.
    scale_range : float, optional
        Width of the distribution the z-score is spread over, or the divisor for
        the relative and scaled transforms. ``cartoon_putty_range``.
    scale_min, scale_max : float, optional
        Clamp, applied **after** the power. A negative value disables that end,
        as in PyMOL.

    Returns
    -------
    numpy.ndarray
        One multiplier per value.

    Notes
    -----
    PyMOL refuses transforms whose divisor is degenerate — a zero standard
    deviation for the normalized family, a zero range, a zero data range — and
    falls back to a uniform ``0.5``, warning as it goes. A constant property is
    exactly that case, and a flat tube is the honest answer for it.
    """
    code = (
        PUTTY_TRANSFORMS[transform] if isinstance(transform, str) else int(transform)
    )
    data = np.asarray(values, dtype=float)
    if data.size == 0:
        return np.zeros(0, dtype=float)

    mean = float(data.mean())
    stdev = float(data.std())
    lowest = float(data.min())
    data_range = float(data.max() - lowest)

    if _is_degenerate(code, stdev, scale_range, data_range):
        # PyMOL's fallback for a division it cannot perform.
        return np.full(data.shape, 0.5, dtype=float)

    if code in (0, 4):        # normalized: a z-score, widened by `range`
        scale = (scale_range + (data - mean) / stdev) / scale_range
    elif code in (1, 5):      # relative: against the data's own range
        scale = (data - lowest) / (data_range * scale_range)
    elif code in (2, 6):      # scaled: against `range` directly
        scale = data / scale_range
    elif code in (3, 7):      # absolute: the value itself
        scale = data.copy()
    elif code == 8:           # implied RMS
        scale = np.sqrt(np.maximum(data, 0.0) / 8.0) / np.pi
    else:
        raise ValueError(f"unknown putty transform {transform!r}")

    scale = np.maximum(scale, 0.0)
    if code in _NONLINEAR:
        scale = np.power(scale, float(scale_power))

    # After the power, not before -- clamping first would change the shape of
    # the curve rather than only its ends.
    if scale_min >= 0.0:
        scale = np.maximum(scale, float(scale_min))
    if scale_max >= 0.0:
        scale = np.minimum(scale, float(scale_max))
    return scale


def _is_degenerate(
    code: int, stdev: float, scale_range: float, data_range: float
) -> bool:
    """Whether this transform would divide by (near) zero."""
    if code in (0, 4) and stdev < _R_SMALL8:
        return True
    if code in (0, 1, 2, 4, 5, 6) and abs(scale_range) < _R_SMALL8:
        return True
    if code in (1, 5) and abs(data_range) < _R_SMALL8:
        return True
    return False


def smooth_scale_factors(scale: np.ndarray, window: int = 1) -> np.ndarray:
    """Average the factors along the chain, leaving the ends alone.

    Without this a single outlying residue makes a bead on the tube instead of a
    bulge. PyMOL clamps the window at the ends rather than shortening it, so
    points near a terminus average their neighbour repeatedly — which is why the
    first and last points are excluded from the smoothing entirely.

    Parameters
    ----------
    scale : numpy.ndarray
        Per-point multipliers.
    window : int, optional
        Half-width; each point averages ``2 * window + 1`` of them.

    Returns
    -------
    numpy.ndarray
        Smoothed multipliers, the same length.
    """
    values = np.asarray(scale, dtype=float)
    n = values.shape[0]
    if n < 3 or window < 1:
        return values.copy()

    out = values.copy()
    offsets = np.arange(-window, window + 1)
    interior = np.arange(1, n - 1)
    # Clamped at the ends, as PyMOL does -- not wrapped, and not shortened.
    sampled = np.clip(interior[:, None] + offsets[None, :], 0, n - 1)
    out[1:-1] = values[sampled].mean(axis=1)
    return out
