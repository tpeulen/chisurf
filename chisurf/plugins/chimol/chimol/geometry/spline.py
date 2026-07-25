"""PyMOL's cartoon curve, which is not a Catmull-Rom spline.

chimol interpolated between guide residues with Catmull-Rom plus a tension knob.
That is a reasonable spline, but it is not the curve PyMOL draws, and no amount
of tuning the tension reaches it: PyMOL's curve is a **linear blend with a
tangent-driven throw**, from ``CartoonGenerateSample``
(``layer2/RepCartoon.cpp``)::

    f0 = smooth(b / sampling, power_a)
    f1 = 1 - f0
    f2 = smooth(f0, power_b)
    f3 = smooth(f1, power_b)
    f4 = dev * f2 * f3                       # dev = cartoon_throw * |P1 - P0|
    P  = f1*P0 + f0*P1 + f4*(f3*T0 - f2*T1)

The two ideas worth naming, because they are what make it look like PyMOL:

* **The throw scales with the segment length.** ``dev`` is
  ``cartoon_throw x dl``, so a long step bulges proportionally more than a short
  one. A spline with a fixed tension cannot do that.
* **The envelope ``f2 x f3`` vanishes at both ends**, so the curve passes exactly
  through every guide position no matter how hard the tangents throw it. The
  bulge lives strictly between two residues.

``smooth(x, p)`` is PyMOL's own easing (``layer0/Vector.cpp``): a power curve
mirrored about the midpoint, so ``power_a`` biases sampling toward the centre of
each segment and ``power_b`` shapes the throw envelope. With the defaults
(``cartoon_power`` 2, ``cartoon_power_b`` 0.52, ``cartoon_throw`` 1.35) the
result is noticeably rounder through tight turns than Catmull-Rom.
"""

from __future__ import annotations

import numpy as np

__all__ = ["smooth", "sample_cartoon_curve", "DEFAULTS"]

#: PyMOL's defaults for the curve, read from a running PyMOL.
DEFAULTS = {"power": 2.0, "power_b": 0.52, "throw": 1.35}


def smooth(x: np.ndarray | float, power: float) -> np.ndarray:
    """PyMOL's easing function, mirrored about the midpoint.

    ``layer0/Vector.cpp``::

        x <= 0   -> 0
        x <= 0.5 -> 0.5 * (2x)^power
        x >= 1   -> 1
        else     -> 1 - 0.5 * (2 * (1 - x))^power

    Parameters
    ----------
    x : numpy.ndarray or float
        Parameter, normally in ``[0, 1]``.
    power : float
        Exponent; 1 is the identity, higher values push toward the midpoint.

    Returns
    -------
    numpy.ndarray
        The eased parameter, same shape as ``x``.
    """
    t = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    lower = 0.5 * np.power(2.0 * t, power)
    upper = 1.0 - 0.5 * np.power(2.0 * (1.0 - t), power)
    return np.where(t <= 0.5, lower, upper)


def sample_cartoon_curve(
    positions: np.ndarray,
    tangents: np.ndarray,
    sampling: int,
    *,
    orientations: np.ndarray | None = None,
    throw: float = DEFAULTS["throw"],
    power: float = DEFAULTS["power"],
    power_b: float = DEFAULTS["power_b"],
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray]:
    """Sample PyMOL's cartoon curve through a run of guide residues.

    Parameters
    ----------
    positions : numpy.ndarray
        ``(n, 3)`` guide positions.
    tangents : numpy.ndarray
        ``(n, 3)`` tangent at each guide position, from the guide-frame stage.
        These are what the curve is thrown along, which is why the strand-tip
        re-aiming feeds through into the drawn shape.
    sampling : int
        Points generated per residue interval (``cartoon_sampling``).
    orientations : numpy.ndarray, optional
        ``(n, 3)`` ribbon up-vectors, blended along with the curve using PyMOL's
        own weighting and renormalised.
    throw : float, optional
        ``cartoon_throw``; 0 gives straight segments between residues.
    power : float, optional
        ``cartoon_power``, biasing where samples fall along a segment.
    power_b : float, optional
        ``cartoon_power_b``, shaping the throw envelope.

    Returns
    -------
    tuple
        ``(points, ups, weights)``. ``points`` has ``(n - 1) * sampling + 1``
        rows; ``ups`` matches it or is ``None``; ``weights`` gives each sample's
        fractional position between its two guide residues, for interpolating
        per-residue attributes such as colour.
    """
    pts = np.asarray(positions, dtype=float)
    tan = np.asarray(tangents, dtype=float)
    n = pts.shape[0]
    if n < 2 or sampling < 1:
        ups = None if orientations is None else np.asarray(orientations, float)
        return pts, ups, np.zeros(max(n, 0))

    # Parameter values *within* a segment: sampling+1 points, the last of which
    # is the next segment's first, so only the final segment keeps its end.
    u = np.arange(sampling + 1, dtype=float) / float(sampling)
    f0 = smooth(u, power)
    f1 = 1.0 - f0
    f2 = smooth(f0, power_b)
    f3 = smooth(f1, power_b)
    envelope = f2 * f3

    p0 = pts[:-1]                     # (n-1, 3)
    p1 = pts[1:]
    t0 = tan[:-1]
    t1 = tan[1:]
    dev = throw * np.linalg.norm(p1 - p0, axis=1)     # (n-1,)

    # (n-1, sampling+1, 3): every segment against every parameter value.
    points = (
        f1[None, :, None] * p0[:, None, :]
        + f0[None, :, None] * p1[:, None, :]
        + (dev[:, None] * envelope[None, :])[:, :, None]
        * (
            f3[None, :, None] * t0[:, None, :]
            - f2[None, :, None] * t1[:, None, :]
        )
    )

    ups_out = None
    if orientations is not None:
        ori = np.asarray(orientations, dtype=float)
        o0 = ori[:-1]
        o1 = ori[1:]
        # PyMOL's own weighting: f1*(O0*f2) + f0*(O1*f3), not a plain lerp.
        blended = (
            (f1 * f2)[None, :, None] * o0[:, None, :]
            + (f0 * f3)[None, :, None] * o1[:, None, :]
        )
        # That weighting **vanishes at both ends** -- at u = 0 the pair is
        # (f1*f2, f0*f3) = (1*0, 0*1) -- which is why the C++ special-cases them
        # with its two "starter..." copies rather than evaluating the formula.
        # Without this the ribbon has a zero normal at every residue.
        blended[:, 0] = o0
        blended[:, -1] = o1
        lengths = np.linalg.norm(blended, axis=2, keepdims=True)
        np.divide(blended, lengths, out=blended, where=lengths > 1e-12)
        ups_out = _flatten_segments(blended)

    return _flatten_segments(points), ups_out, _flatten_segments(
        np.broadcast_to(f0[None, :], (n - 1, sampling + 1))[..., None]
    ).reshape(-1)


def _flatten_segments(values: np.ndarray) -> np.ndarray:
    """Join per-segment samples, dropping each segment's duplicated end point.

    Every segment is sampled inclusive of both ends so that its last sample and
    the next segment's first coincide; keeping both would put a doubled vertex
    at every residue, which shows up as a seam once the profile is extruded.
    """
    n_segments = values.shape[0]
    body = values[:, :-1]
    tail = values[-1:, -1]
    return np.concatenate(
        [body.reshape(-1, *values.shape[2:]), tail.reshape(-1, *values.shape[2:])]
    ) if n_segments else values.reshape(-1, *values.shape[2:])
