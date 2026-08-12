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

**The samples are immutable, and everything derived from them is cached.** The
reference viewer keeps a ``matrix_stats`` beside every map for the same reason:
the histogram panel repaints every frame, and a range or histogram that rescans
millions of voxels per paint is a UI that fights back. ``value_range``,
``histogram``, ``default_levels``, the strided copy and the last few contours
are all computed once and remembered. The contract that makes this safe is that
``values`` is never written in place — a changed map is a new
:class:`VolumeGrid`.
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
    recommended_level: Optional[float] = None

    #: Memoised derived quantities (range, histograms, strided copies, recent
    #: contours). Safe because ``values`` is treated as immutable — a changed
    #: map is a new grid. Not part of the value of the object.
    _cache: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def _memo(self, key, compute):
        """Return the cached value for ``key``, computing and remembering it once."""
        cache = self._cache
        if key not in cache:
            cache[key] = compute()
        return cache[key]

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
        corner would otherwise make every contour level meaningless. Computed
        once; the histogram panel asks several times per paint.
        """
        return self._memo("range", self._compute_value_range)

    def _compute_value_range(self) -> Tuple[float, float]:
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

        Cached per bin count: the density panel redraws this every frame, and
        rescanning a multi-million-voxel map per paint was most of why the
        panel felt slow.

        Returns
        -------
        tuple
            ``(counts, edges)`` over the finite values, as :func:`numpy.histogram`
            returns them.
        """
        return self._memo(("histogram", int(bins)), lambda: self._compute_histogram(bins))

    def _compute_histogram(self, bins: int):
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            return np.zeros(bins, dtype=int), np.linspace(0.0, 1.0, bins + 1)
        return np.histogram(finite, bins=bins)

    def is_binary(self) -> bool:
        """Whether the map takes only two values, as a mask or an AV does."""
        return self._memo("binary", self._compute_is_binary)

    def _compute_is_binary(self) -> bool:
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            return False
        return np.unique(finite[: min(finite.size, 1_000_000)]).size <= 2

    def is_polar(self) -> bool:
        """Whether the map is signed either way, as a difference map is.

        Judged on both tails carrying real weight, not merely on a negative
        minimum: noise around zero would otherwise make every map polar.
        """
        return self._memo("polar", self._compute_is_polar)

    def _compute_is_polar(self) -> bool:
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
        levels = self._memo(
            ("default_levels", float(voxel_fraction)),
            lambda: self._compute_default_levels(voxel_fraction),
        )
        return list(levels)

    def _compute_default_levels(self, voxel_fraction: float) -> list[float]:
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            return []
        low, high = float(finite.min()), float(finite.max())
        if high <= low:
            return []

        if self.recommended_level is not None and low < self.recommended_level < high:
            return [float(self.recommended_level)]

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

        Cached per stride, and the subsample is materialised contiguously: the
        strided grid carries its own memo (range, histogram, contours), so a
        drag that re-contours the same subsample pays for the copy and the
        scans once rather than per mouse move.
        """
        stride = self.stride_for_limit(voxel_limit_m)
        if stride <= 1:
            return self
        return self._memo(
            ("strided", stride),
            lambda: VolumeGrid(
                values=np.ascontiguousarray(
                    self.values[::stride, ::stride, ::stride]
                ),
                origin=self.origin.copy(),
                step=self.step * stride,
                rotation=self.rotation.copy(),
                name=self.name,
            ),
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

        Notes
        -----
        The last few contours are memoised per ``(level, budget)``, so a colour
        or opacity change, a surface/mesh toggle, or a redraw of the scene that
        did not move the level costs nothing. The returned arrays are shared
        between callers and marked read-only for that reason.
        """
        grid = self.strided(voxel_limit_m)
        if level is None:
            level = grid.default_level()
        level = float(level)
        low, high = grid.value_range()
        if not np.isfinite(level) or level <= low or level >= high:
            return None

        memo = self._cache.setdefault("contours", {})
        key = (level, float(voxel_limit_m))
        if key in memo:
            return memo[key]

        result = self._contour(grid, level)
        # A handful of levels covers a polar pair plus a drag preview; anything
        # older is stale drag positions, and each entry can be megabytes.
        while len(memo) >= 4:
            memo.pop(next(iter(memo)))
        memo[key] = result
        return result

    @staticmethod
    def _contour(grid: VolumeGrid, level: float):
        """One triangulated contour of ``grid``, uncached."""
        values = np.ascontiguousarray(grid.values, dtype=np.float32)
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
        out = (
            verts.astype(np.float32),
            np.asarray(faces, dtype=np.int32),
            normals.astype(np.float32),
        )
        # The tuple is memoised and handed to every caller; a consumer writing
        # into it would corrupt every later draw of the same level.
        for arr in out:
            arr.setflags(write=False)
        return out


def gaussian_filtered(grid: VolumeGrid, sdev: float) -> VolumeGrid:
    """A Gaussian-smoothed copy of a map, as a new map.

    The reference viewer's ``volume gaussian``: convolve the samples with a
    Gaussian of standard deviation ``sdev`` (in the map's placement units, so
    an anisotropic step smooths by the same *physical* width along every
    axis) and hand back a **new** grid named after the operation — filtering
    is analysis, and analysis produces a new object rather than quietly
    rewriting the data it read (the memoised contours also rely on a grid's
    samples never changing).

    Computed in Fourier space — the transfer function of a Gaussian is a
    Gaussian, and three separable FFT passes beat a spatial kernel at any
    width. The implied periodic boundary is harmless on maps whose edges sit
    at the background level, which a map with sensible padding has.
    """
    sdev = float(sdev)
    if not np.isfinite(sdev) or sdev <= 0:
        raise ValueError(f"the Gaussian width must be positive, got {sdev!r}")
    values = np.asarray(grid.values, dtype=np.float32)
    spectrum = np.fft.rfftn(values.astype(np.float64))
    shape = values.shape
    for axis in range(3):
        sigma_vox = sdev / float(grid.step[axis])
        freq = (
            np.fft.rfftfreq(shape[axis]) if axis == 2
            else np.fft.fftfreq(shape[axis])
        )
        damp = np.exp(-2.0 * (np.pi * freq * sigma_vox) ** 2)
        index = [None, None, None]
        index[axis] = slice(None)
        spectrum *= damp[tuple(index)]
    smoothed = np.fft.irfftn(spectrum, s=shape).astype(np.float32)
    return VolumeGrid(
        values=smoothed,
        origin=grid.origin.copy(),
        step=grid.step.copy(),
        rotation=grid.rotation.copy(),
        name=f"{grid.name} gaussian",
    )


__all__ = [
    "DEFAULT_LEVEL_VOXEL_FRACTION",
    "DEFAULT_VOXEL_LIMIT_M",
    "VolumeGrid",
    "gaussian_filtered",
]
