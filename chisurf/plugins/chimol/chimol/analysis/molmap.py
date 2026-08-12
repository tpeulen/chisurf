"""A density map simulated from atoms, at a stated resolution.

This is the other half of working with cryo-EM data. Reading a deposited map is
half; the half that makes a map *comparable* is being able to compute what a
model would look like at the same resolution -- which is what a correlation, a
difference map, or a fit is measured against.

The recipe is ChimeraX's ``molmap``, and its constants are not arbitrary:

``sigma = resolution / (pi * sqrt(2))``
    The Gaussian whose Fourier transform falls to ``1/e`` at the stated
    resolution. Quoting a "3 A map" and then splatting a 3 A-wide Gaussian
    produces something markedly blurrier than the real thing.
``step = resolution / 3``
    Three samples across the resolution. Coarser and the contour goes faceted;
    finer costs cubically for nothing, since the field has no detail there.
``pad = 3 * resolution``
    Enough box that the Gaussian tails are inside it. A tail clipped by the box
    edge is a flat face on the isosurface.
``cutoff = 5 sigma``
    Where the Gaussian is ~1e-6 of its peak. Beyond it the arithmetic is
    rounding noise, and evaluating every atom against every voxel instead of
    its own neighbourhood is what makes a naive version unusable.

Weights are **atomic numbers**, not equal per atom: the map is electron
density, and a sulphur is not a hydrogen.
"""
from __future__ import annotations

import math

import numpy as np

from ..volume import VolumeGrid

__all__ = ["DEFAULT_CUTOFF_SIGMAS", "SIGMA_PER_RESOLUTION", "simulate_map"]

#: Standard deviation per unit of stated resolution.
SIGMA_PER_RESOLUTION = 1.0 / (math.pi * math.sqrt(2.0))

#: How far out each Gaussian is evaluated, in standard deviations.
DEFAULT_CUTOFF_SIGMAS = 5.0


def simulate_map(
    coordinates,
    resolution: float,
    *,
    weights=None,
    step: float | None = None,
    pad: float | None = None,
    on_grid: VolumeGrid | None = None,
    cutoff_sigmas: float = DEFAULT_CUTOFF_SIGMAS,
    name: str = "molmap",
) -> VolumeGrid:
    """Sum a Gaussian per atom onto a grid.

    Parameters
    ----------
    coordinates : array_like
        ``(n, 3)`` atom positions, in the same units as *resolution*.
    resolution : float
        The resolution to simulate, in the same units. Must be positive.
    weights : array_like, optional
        Per-atom weight; atomic number is what makes this a density rather than
        an atom-count. Defaults to 1 per atom, which is what an equal-bead
        coarse-grained model wants.
    step : float, optional
        Grid spacing. Defaults to ``resolution / 3``.
    pad : float, optional
        Margin around the atoms' bounding box. Defaults to ``3 * resolution``.
    on_grid : VolumeGrid, optional
        Sample onto *this* map's lattice -- same shape, origin, step and
        orientation -- instead of a box around the atoms. That is what makes
        the result comparable voxel-for-voxel with an experimental map, which
        is the only way to correlate the two; *step* and *pad* are ignored.
    cutoff_sigmas : float
        Evaluation radius per atom, in standard deviations.
    name : str
        Name for the resulting map object.

    Returns
    -------
    VolumeGrid

    Raises
    ------
    ValueError
        For an empty coordinate set or a non-positive resolution -- refused
        rather than defaulted, because an empty map looks like a result.

    Notes
    -----
    Each atom is added only to the voxels within its cutoff, so the cost is
    ``n_atoms * (cutoff / step)^3`` and not ``n_atoms * n_voxels``. At the
    default step that neighbourhood is about 23 voxels across.

    The final scaling by ``(2*pi)^-3/2 * sigma^-3`` makes each unit of weight
    integrate to one over the volume, so the map's values do not change meaning
    when the resolution does.
    """
    points = np.asarray(coordinates, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(f"coordinates must be (n, 3); got {points.shape}")
    if points.shape[0] == 0:
        raise ValueError("cannot simulate a map from no atoms")
    if not np.isfinite(resolution) or resolution <= 0.0:
        raise ValueError(f"resolution must be positive; got {resolution!r}")

    if weights is None:
        mass = np.ones(points.shape[0], dtype=float)
    else:
        mass = np.asarray(weights, dtype=float).reshape(-1)
        if mass.shape[0] != points.shape[0]:
            raise ValueError(
                f"got {mass.shape[0]} weights for {points.shape[0]} atoms"
            )

    sigma = float(resolution) * SIGMA_PER_RESOLUTION
    spacing = float(resolution) / 3.0 if step is None else float(step)
    margin = 3.0 * float(resolution) if pad is None else float(pad)
    if spacing <= 0.0:
        raise ValueError(f"step must be positive; got {step!r}")

    if on_grid is not None:
        shape = np.asarray(on_grid.shape, dtype=int)
        origin = np.asarray(on_grid.origin, dtype=float)
        spacings = np.asarray(on_grid.step, dtype=float)
        rotation = np.asarray(on_grid.rotation, dtype=float)
        if not np.allclose(rotation, np.eye(3)):
            raise ValueError(
                "on_grid must be axis-aligned; simulating onto a rotated "
                "lattice is not implemented"
            )
        if not np.allclose(spacings, spacings[0]):
            raise ValueError(
                f"on_grid must have an isotropic step; got {tuple(spacings)}"
            )
        spacing = float(spacings[0])
    else:
        low = points.min(axis=0) - margin
        high = points.max(axis=0) + margin
        shape = np.maximum(np.ceil((high - low) / spacing).astype(int), 1)
        # Centre the grid on the atoms rather than anchoring it at the low
        # corner, so a map and the model it came from share a centre whatever
        # the rounding up did to the shape.
        centre = 0.5 * (points.min(axis=0) + points.max(axis=0))
        origin = centre - 0.5 * (shape - 1) * spacing

    values = np.zeros(tuple(int(n) for n in shape), dtype=np.float32)
    reach = cutoff_sigmas * sigma
    span = int(math.ceil(reach / spacing))
    inv_two_sigma_sq = 1.0 / (2.0 * sigma * sigma)

    # Index of the voxel nearest each atom. Everything below is expressed as an
    # offset from it, which keeps the inner arithmetic in a small local window.
    nearest = np.rint((points - origin) / spacing).astype(int)

    for atom in range(points.shape[0]):
        weight = mass[atom]
        if weight == 0.0:
            continue
        base = nearest[atom]
        lows = np.maximum(base - span, 0)
        highs = np.minimum(base + span + 1, shape)
        if np.any(lows >= highs):
            continue  # entirely outside the grid

        axes = []
        for axis in range(3):
            index = np.arange(lows[axis], highs[axis])
            delta = origin[axis] + index * spacing - points[atom, axis]
            axes.append(np.exp(-(delta * delta) * inv_two_sigma_sq))
        block = weight * axes[0][:, None, None] * axes[1][None, :, None] * axes[2]
        values[lows[0]:highs[0], lows[1]:highs[1], lows[2]:highs[2]] += block.astype(
            np.float32
        )

    values *= float(math.pow(2.0 * math.pi, -1.5) * math.pow(sigma, -3.0))

    grid = VolumeGrid.from_array(
        values, origin=origin, step=(spacing, spacing, spacing), name=name
    )
    return grid
