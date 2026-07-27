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

#: Fraction of voxels the default contour encloses. The reference tool's
#: ``initial_surface_levels`` uses ``vfrac = 0.01`` -- the level at which 1% of
#: the voxels are above it -- and that is the rule followed here.
#:
#: A rank is the right basis rather than a mean and a standard deviation: it is
#: free of both the *scale* and the *shape* of the distribution. An accessible
#: volume runs 0 to 1, a photon-count stack to hundreds, a cryo-EM map to
#: whatever the reconstruction produced, and none of their histograms look alike
#: -- but "the densest one per cent" means the same thing in all of them.
DEFAULT_LEVEL_VOXEL_FRACTION = 0.01


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

    def is_binary(self) -> bool:
        """Whether the map takes only two values, as a mask or an AV does."""
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            return False
        return np.unique(finite[: min(finite.size, 1_000_000)]).size <= 2

    def is_polar(self) -> bool:
        """Whether the map is signed either way, as a difference map is.

        Judged on both tails carrying real weight, not merely on a negative
        minimum: noise around zero would otherwise make every map polar.
        """
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            return False
        extreme = max(abs(float(finite.min())), abs(float(finite.max())))
        if extreme <= 0.0:
            return False
        cut = 0.2 * extreme
        return bool((finite < -cut).any() and (finite > cut).any())

    def default_levels(
        self, voxel_fraction: float = DEFAULT_LEVEL_VOXEL_FRACTION
    ) -> list[float]:
        """Opening contour level(s), by the reference tool's rule.

        The level at which ``voxel_fraction`` of the voxels lie above it, with
        two special cases taken from ``initial_surface_levels``:

        * a **binary** map contours at ``0.5``. This matters here more than
          anywhere: an accessible volume *is* a binary mask, and a rank-based
          level would sit inside the occupied region and draw a surface within
          the volume rather than around it.
        * a **polar** map -- one signed both ways, such as a difference map --
          gets a symmetric pair ``[-v, +v]``, since the negative lobe is half of
          what such a map is for and a single positive level hides it.

        Returns
        -------
        list of float
            One level, or two for a polar map. Empty when the map is flat and
            has no contour to give.
        """
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            return []
        low, high = float(finite.min()), float(finite.max())
        if high <= low:
            return []

        if self.is_binary():
            return [0.5] if low <= 0.5 <= high else [low + 0.5 * (high - low)]

        fraction = min(max(float(voxel_fraction), 0.0), 1.0)
        level = float(np.quantile(finite, 1.0 - fraction))
        if not np.isfinite(level) or level <= low or level >= high:
            level = low + 0.5 * (high - low)

        if self.is_polar() and level > 0.0:
            # The reference tool mirrors the *signed* level rather than ranking
            # the magnitudes: `initial_surface_levels` computes one value and
            # returns `[-v, v]`. So the positive lobe still encloses exactly the
            # requested fraction, and the negative one encloses whatever the map
            # happens to put below -v -- which is the asymmetry a difference map
            # is being examined for in the first place.
            return [-level, level]
        return [level]

    def default_level(
        self, voxel_fraction: float = DEFAULT_LEVEL_VOXEL_FRACTION
    ) -> float:
        """The first of :meth:`default_levels`, for callers that want just one."""
        levels = self.default_levels(voxel_fraction)
        if not levels:
            low, high = self.value_range()
            return low + 0.5 * (high - low)
        return levels[-1]

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
    "DEFAULT_LEVEL_VOXEL_FRACTION",
    "DEFAULT_VOXEL_LIMIT_M",
    "VolumeGrid",
]
