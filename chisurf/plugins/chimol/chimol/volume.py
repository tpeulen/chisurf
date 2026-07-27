"""Voxel maps as first-class objects: the grid, its placement, and its contours.

A great deal of what this group looks at is a density rather than a structure —
an accessible volume showing where a tethered dye can physically be, an
occupancy density from an ensemble, an electron-density map around a model, a
confocal image stack. This module is the object all of those become, so that one
viewer can show a model inside its data.

Three decisions shape it, and each is here for a reason:

**The grid carries its own placement.** ``origin``, ``step`` and a full 3x3
``rotation``, not an implied unit cube. A confocal stack's z step is rarely its
xy step, and a crystallographic map need not be axis-aligned at all; a grid that
assumes otherwise silently squashes or shears the picture, which looks like data
rather than like a bug.

**A map need not come from a file.** Accessible volumes and image stacks are
already arrays in this process. :meth:`VolumeGrid.from_array` is the primary
constructor and file readers are built on it, rather than the other way round.

**Display cost is bounded by a setting, not by the file.** A map can be far
larger than anything worth drawing, so :meth:`VolumeGrid.strided` subsamples
until it fits a voxel budget. This is what lets a large map open at all, and it
keeps a contour change from stalling the viewer.

See [PRD-57](../../../okf/prds/prd-57.md) for the wider requirement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

from .geometry.marching_cubes import marching_cubes

#: Default ceiling on how many voxels are handed to a contour, in millions.
#: A map above this is strided down rather than drawn in full; 16 M is roughly a
#: 250-cubed grid, past which nothing is gained that the eye can see.
DEFAULT_VOXEL_LIMIT_M = 16.0

#: Standard deviations above the mean for the default contour. One sigma is the
#: usual starting contour for a density map, and it is scale-free -- an
#: accessible volume, a cryo-EM map and a photon-count stack share no units and
#: no order of magnitude, so any fixed number would land off at least two of
#: them. It also behaves for a sparse map: a binary volume occupying 5% of its
#: box has mean 0.05 and sigma 0.22, so one sigma falls neatly between empty and
#: full.
DEFAULT_LEVEL_SIGMA = 1.0


@dataclass
class VolumeGrid:
    """A scalar field on a regular 3-D grid, placed in space.

    Attributes
    ----------
    values : numpy.ndarray
        ``(nx, ny, nz)`` scalar samples.
    origin : numpy.ndarray
        Position of index ``(0, 0, 0)``, in the same units as ``step``.
    step : numpy.ndarray
        Sample spacing along each axis. Anisotropy is expected, not exceptional.
    rotation : numpy.ndarray
        ``3x3`` orientation of the grid axes in world space. Identity for the
        usual axis-aligned map.
    name : str
        What the object is called in the viewer.
    """

    values: np.ndarray
    origin: np.ndarray = field(default_factory=lambda: np.zeros(3))
    step: np.ndarray = field(default_factory=lambda: np.ones(3))
    rotation: np.ndarray = field(default_factory=lambda: np.eye(3))
    name: str = "map"

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def from_array(
        cls,
        array,
        *,
        origin=(0.0, 0.0, 0.0),
        step=(1.0, 1.0, 1.0),
        rotation=None,
        name: str = "map",
    ) -> "VolumeGrid":
        """Build a map from an array already in memory.

        The primary constructor. An accessible volume or a confocal stack is
        handed over directly rather than written to a file and read back.

        Parameters
        ----------
        array : array-like
            Anything coercible to a 3-D float array.
        origin, step : sequence of 3 floats
            Placement of the grid. A scalar ``step`` is accepted and taken as
            isotropic.
        rotation : array-like, optional
            ``3x3`` grid orientation; identity when omitted.
        name : str
            Object name.

        Raises
        ------
        ValueError
            If the array is not 3-D, is empty, or the step is degenerate. These
            are refused rather than defaulted, because a map drawn at the wrong
            scale looks like a result.
        """
        values = np.asarray(array, dtype=np.float32)
        if values.ndim != 3:
            raise ValueError(
                f"a volume needs a 3-D array; got one with {values.ndim} "
                f"dimension(s), shape {values.shape}"
            )
        if values.size == 0:
            raise ValueError("a volume needs at least one voxel; the array is empty")

        step_arr = np.asarray(step, dtype=float).reshape(-1)
        if step_arr.size == 1:
            step_arr = np.repeat(step_arr, 3)
        if step_arr.size != 3:
            raise ValueError(f"step must be one or three numbers, got {step!r}")
        if not np.all(np.isfinite(step_arr)) or np.any(step_arr <= 0.0):
            raise ValueError(f"step must be finite and positive, got {step_arr!r}")

        origin_arr = np.asarray(origin, dtype=float).reshape(3)
        rotation_arr = (
            np.eye(3) if rotation is None
            else np.asarray(rotation, dtype=float).reshape(3, 3)
        )
        return cls(
            values=values,
            origin=origin_arr,
            step=step_arr,
            rotation=rotation_arr,
            name=name,
        )

    # ------------------------------------------------------------------ #
    # Describing it
    # ------------------------------------------------------------------ #
    @property
    def shape(self) -> Tuple[int, int, int]:
        """Voxel counts along each axis."""
        return tuple(int(n) for n in self.values.shape)  # type: ignore[return-value]

    @property
    def voxel_count(self) -> int:
        """How many samples the map holds."""
        return int(self.values.size)

    def value_range(self) -> Tuple[float, float]:
        """Smallest and largest finite value, as ``(low, high)``.

        Non-finite samples are ignored rather than propagated: a single NaN in a
        corner would otherwise make every contour level meaningless.
        """
        finite = np.isfinite(self.values)
        if not finite.any():
            return 0.0, 0.0
        usable = self.values[finite]
        return float(usable.min()), float(usable.max())

    def extent(self) -> Tuple[np.ndarray, np.ndarray]:
        """World-space bounding box of the grid, as ``(low, high)`` corners."""
        counts = np.asarray(self.shape, dtype=float) - 1.0
        corners = np.array(
            [[i, j, k] for i in (0.0, counts[0])
             for j in (0.0, counts[1]) for k in (0.0, counts[2])]
        )
        placed = self.index_to_world(corners)
        return placed.min(axis=0), placed.max(axis=0)

    def index_to_world(self, indices) -> np.ndarray:
        """Map grid indices to world coordinates.

        The one place the placement is applied, so a rotated or anisotropic grid
        cannot be handled correctly in one code path and wrongly in another.
        """
        idx = np.asarray(indices, dtype=float)
        single = idx.ndim == 1
        idx = np.atleast_2d(idx)
        placed = (idx * self.step) @ np.asarray(self.rotation, dtype=float).T
        placed = placed + self.origin
        return placed[0] if single else placed

    def histogram(self, bins: int = 256):
        """Value distribution, for choosing a contour by looking at the data.

        Returns
        -------
        tuple
            ``(counts, edges)`` over the finite values, as :func:`numpy.histogram`
            returns them.
        """
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            return np.zeros(bins, dtype=int), np.linspace(0.0, 1.0, bins + 1)
        return np.histogram(finite, bins=bins)

    def default_level(self, sigma: float = DEFAULT_LEVEL_SIGMA) -> float:
        """A contour level derived from the data rather than assumed.

        ``mean + sigma * std`` over the finite values, which is the conventional
        starting contour for a density map and carries no assumption about units.
        Clamped inside the data, so a map whose distribution puts that above its
        maximum still opens showing something rather than nothing.

        A flat map has no contour to give; ``(low + high) / 2`` is returned and
        :meth:`isosurface` will decline it, which is the honest outcome.
        """
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            return 0.0
        low, high = float(finite.min()), float(finite.max())
        if high <= low:
            return float(high)

        level = float(finite.mean()) + float(sigma) * float(finite.std())
        if not np.isfinite(level) or level <= low or level >= high:
            # A distribution that puts one sigma outside its own range -- a
            # near-binary map, usually. Fall back to a high quantile of the
            # occupied half, which such a map always has.
            occupied = finite[finite > low + 0.5 * (high - low)]
            if occupied.size == 0:
                occupied = finite
            level = float(np.quantile(occupied, 0.5))
        if not np.isfinite(level) or level <= low or level >= high:
            level = low + 0.5 * (high - low)
        return level

    # ------------------------------------------------------------------ #
    # Bounding the cost
    # ------------------------------------------------------------------ #
    def stride_for_limit(self, voxel_limit_m: float = DEFAULT_VOXEL_LIMIT_M) -> int:
        """Smallest stride that brings the map under a voxel budget.

        Returns 1 when the map already fits, so an ordinary map is untouched.
        """
        limit = max(float(voxel_limit_m), 1e-6) * 1_000_000.0
        stride = 1
        while stride < 64:
            counts = [(n + stride - 1) // stride for n in self.shape]
            if counts[0] * counts[1] * counts[2] <= limit:
                break
            stride += 1
        return stride

    def strided(self, voxel_limit_m: float = DEFAULT_VOXEL_LIMIT_M) -> "VolumeGrid":
        """This map subsampled until it fits the voxel budget.

        Returns ``self`` when no striding is needed, so the common case costs
        nothing. The step is scaled with the stride, which is what keeps the
        subsampled map in the same place and at the same size as the full one.
        """
        stride = self.stride_for_limit(voxel_limit_m)
        if stride <= 1:
            return self
        return VolumeGrid(
            values=self.values[::stride, ::stride, ::stride],
            origin=self.origin.copy(),
            step=self.step * stride,
            rotation=self.rotation.copy(),
            name=self.name,
        )

    # ------------------------------------------------------------------ #
    # Contours
    # ------------------------------------------------------------------ #
    def isosurface(
        self,
        level: Optional[float] = None,
        *,
        voxel_limit_m: float = DEFAULT_VOXEL_LIMIT_M,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """Triangulate one contour, in world coordinates.

        Parameters
        ----------
        level : float, optional
            Contour value; :meth:`default_level` when omitted.
        voxel_limit_m : float
            Voxel budget in millions, applied before contouring.

        Returns
        -------
        tuple or None
            ``(vertices, faces, normals)``, or ``None`` when the surface does not
            cross the grid -- which is a real answer, not a failure: it means the
            level is above everything, or below it.
        """
        grid = self.strided(voxel_limit_m)
        if level is None:
            level = grid.default_level()
        level = float(level)
        low, high = grid.value_range()
        if not np.isfinite(level) or level <= low or level >= high:
            return None

        values = np.ascontiguousarray(grid.values, dtype=np.float64)
        verts, faces, normals = marching_cubes(values, level, tuple(grid.step))
        if verts.shape[0] == 0:
            return None

        # `marching_cubes` returns index-space positions already scaled by the
        # step, so only the rotation and origin remain to be applied -- and they
        # go through the same seam every other placement uses.
        rotation = np.asarray(grid.rotation, dtype=float)
        verts = np.asarray(verts, dtype=np.float64) @ rotation.T + grid.origin
        normals = np.asarray(normals, dtype=np.float64) @ rotation.T
        lengths = np.sqrt(np.einsum("ij,ij->i", normals, normals))
        good = lengths > 1e-12
        normals[good] /= lengths[good][:, None]
        return (
            verts.astype(np.float32),
            np.asarray(faces, dtype=np.int32),
            normals.astype(np.float32),
        )


__all__ = [
    "DEFAULT_LEVEL_SIGMA",
    "DEFAULT_VOXEL_LIMIT_M",
    "VolumeGrid",
]
