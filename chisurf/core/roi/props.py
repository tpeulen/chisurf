"""Region properties: what a region *is*, once you have one.

:mod:`chisurf.core.roi.roi` answers where a region is — which points and which
pixels belong to it. This module answers the other half: how big is it, where is
its centre, how elongated, how bright. Segmentation produces regions, and every
consumer of a segmentation then needs the same handful of numbers; before this
module each computed them again — the molecule-MLE plugin through
``skimage.measure.regionprops``, object colocalization through a hand-rolled
pile of :mod:`scipy.ndimage` reductions, others not at all.

Modelled on ``skimage.measure.regionprops``
-------------------------------------------
The interface is deliberately the scikit-image one: :func:`regionprops` and
:func:`regionprops_table` take the same arguments in the same order, the
properties carry the same names (``area_bbox``, ``axis_major_length``,
``centroid_weighted``, ``intensity_mean``, ...), and where an algorithm has a
choice — the border-weighted perimeter, the half-pixel-offset convex hull, the
inertia-tensor axes, the sign convention of ``orientation`` — the same choice is
made, so the numbers agree to floating-point noise. Code and habits transfer in
both directions, and a number printed here is the number the literature means.

Three things are added on top, none of which change an existing name:

* the source can be **anything the ROI system produces** — a label image, a bare
  boolean mask, a drawn :class:`~chisurf.core.roi.ROI`, or a list of them. A
  polygon gated on an image has an area and an eccentricity just as a watershed
  label does;
* :meth:`RegionProperties.to_roi` turns a measured region back into a ROI, so it
  can be gated, combined and stored like any drawn one;
* :attr:`RegionProperties.circularity` and :attr:`intensity_sum`, which the
  imaging plugins here report and scikit-image does not.

One word is overloaded as a result. ``extent`` is a *property* here (the
fraction of the bounding box a region fills, as in scikit-image) and also the
name of the *argument* that gives an array's axis span to :meth:`ROI.to_mask`.
They never appear in the same call.

Coordinates are ``(row, col)`` pixel indices throughout, as scikit-image uses;
:attr:`RegionProperties.centroid_xy` gives the ``(x, y)`` form that
:meth:`ROI.contains` speaks.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from functools import cached_property
from typing import Any

import numpy as np

from .roi import ROI, Extent, MaskROI

__all__ = [
    "RegionProperties",
    "regionprops",
    "regionprops_table",
    "PROPERTIES",
    "INTENSITY_PROPERTIES",
]

#: Geometric properties, a convenient bundle to hand to :func:`regionprops_table`.
PROPERTIES: tuple[str, ...] = (
    "label",
    "centroid",
    "area",
    "bbox",
    "extent",
    "perimeter",
    "circularity",
    "equivalent_diameter_area",
    "axis_major_length",
    "axis_minor_length",
    "eccentricity",
    "orientation",
    "solidity",
)

#: Properties that need an intensity image; append them when one is supplied.
INTENSITY_PROPERTIES: tuple[str, ...] = (
    "intensity_sum",
    "intensity_mean",
    "intensity_min",
    "intensity_max",
    "intensity_std",
    "centroid_weighted",
)

# Weights of the 3x3 border configurations used by the perimeter estimate. The
# convolution below turns each border pixel's neighbourhood into an index into
# this table (Benkrid & Crookes' estimator, as used by scikit-image).
_PERIMETER_WEIGHTS = np.zeros(50, dtype=float)
_PERIMETER_WEIGHTS[[5, 7, 15, 17, 25, 27]] = 1.0
_PERIMETER_WEIGHTS[[21, 33]] = math.sqrt(2.0)
_PERIMETER_WEIGHTS[[13, 23]] = (1.0 + math.sqrt(2.0)) / 2.0

_PERIMETER_KERNEL = np.array([[10, 2, 10], [2, 1, 2], [10, 2, 10]])

# Crofton perimeter: the same trick over 2x2 neighbourhoods, weighted for the
# four-direction estimate (scikit-image's ``perimeter_crofton``).
_CROFTON_KERNEL = np.array([[0, 0, 0], [0, 1, 4], [0, 2, 8]])
_SQRT2 = math.sqrt(2.0)
_CROFTON_WEIGHTS = np.array([
    0.0,
    math.pi / 4 * (1 + 1 / _SQRT2),
    math.pi / (4 * _SQRT2),
    math.pi / (2 * _SQRT2),
    0.0,
    math.pi / 4 * (1 + 1 / _SQRT2),
    0.0,
    math.pi / (4 * _SQRT2),
    math.pi / 4,
    math.pi / 2,
    math.pi / (4 * _SQRT2),
    math.pi / (4 * _SQRT2),
    math.pi / 4,
    math.pi / 2,
    0.0,
    0.0,
])

# Euler characteristic: the same 2x2 configuration code, with the coefficients
# of the 8-connected-foreground convention (4-connected in the second row).
_EULER_WEIGHTS_8 = np.array([0, 0, 0, 0, 0, 0, -1, 0, 1, 0, 0, 0, 0, 0, -1, 0], dtype=float)
_EULER_WEIGHTS_4 = np.array([0, 1, 0, 0, 0, 0, 0, -1, 0, 1, 0, 0, 0, 0, 0, 0], dtype=float)

# Half-pixel offsets added to every pixel centre before the convex hull is
# taken, so the hull encloses the pixels' *area* rather than their centres: a
# single pixel then has a convex area of one, not zero.
_HULL_OFFSETS = np.array([[-0.5, 0.0], [0.0, -0.5], [0.0, 0.5], [0.5, 0.0]])


def _raw_moments(image: np.ndarray, order: int = 3) -> np.ndarray:
    """Return the raw image moments ``M[p, q] = sum(image * r**p * c**q)``."""
    h, w = image.shape
    rows = np.arange(h, dtype=float)
    cols = np.arange(w, dtype=float)
    row_powers = np.stack([rows ** p for p in range(order + 1)])
    col_powers = np.stack([cols ** q for q in range(order + 1)])
    # (order+1, h) @ (h, w) @ (w, order+1)
    return row_powers @ np.asarray(image, dtype=float) @ col_powers.T


def _central_moments(image: np.ndarray, centre: tuple[float, float], order: int = 3
                     ) -> np.ndarray:
    """Return the moments of *image* about *centre*."""
    h, w = image.shape
    rows = np.arange(h, dtype=float) - centre[0]
    cols = np.arange(w, dtype=float) - centre[1]
    row_powers = np.stack([rows ** p for p in range(order + 1)])
    col_powers = np.stack([cols ** q for q in range(order + 1)])
    return row_powers @ np.asarray(image, dtype=float) @ col_powers.T


class RegionProperties:
    """The measurements of one region.

    Properties are computed on first access and cached, so measuring a few
    thousand molecules costs only what is read. Both attribute and item access
    work (``prop.area`` and ``prop['area']``), as in scikit-image.

    Parameters
    ----------
    mask : numpy.ndarray
        Boolean mask of the region, already cropped to its bounding box.
    offset : tuple of int
        ``(row, col)`` position of the mask's top-left corner in the full frame.
    label : int
        Label value the region came from; ``1`` for an unlabelled mask.
    intensity : numpy.ndarray, optional
        Intensity image cropped to the same bounding box; supplying it enables
        the intensity properties and the weighted centroid.
    name : str
        Free-form label carried through from a :class:`~chisurf.core.roi.ROI`.
    extra_properties : sequence of callable, optional
        Extra measurements, as for ``skimage.measure.regionprops``: each is
        called with the cropped mask (and the cropped intensity image when it
        takes two arguments) and exposed under the function's name.

    Attributes
    ----------
    image : numpy.ndarray
        The cropped boolean mask.
    image_intensity : numpy.ndarray or None
        The cropped intensity image.
    label : int
        The region's label value.
    name : str
        The region's free-form name, if it came from a named ROI.
    """

    def __init__(
        self,
        mask: np.ndarray,
        offset: tuple[int, int] = (0, 0),
        label: int = 1,
        intensity: np.ndarray | None = None,
        name: str = "",
        extra_properties: Sequence[Callable] | None = None,
    ) -> None:
        """Initialize from a cropped mask and its offset in the full frame."""
        m = np.asarray(mask, dtype=bool)
        if m.ndim != 2:
            raise ValueError(f"region properties need a 2-D mask; got shape {m.shape}")
        self.image = m
        self.offset = (int(offset[0]), int(offset[1]))
        self.label = int(label)
        self.name = str(name)
        self.image_intensity = None if intensity is None else np.asarray(intensity, dtype=float)
        if self.image_intensity is not None and self.image_intensity.shape != m.shape:
            raise ValueError(
                f"intensity image shape {self.image_intensity.shape} does not match the "
                f"region mask {m.shape}"
            )
        self._extra = tuple(extra_properties or ())
        for func in self._extra:
            setattr(self, func.__name__, self._call_extra(func))

    def _call_extra(self, func: Callable) -> Any:
        """Evaluate one user-supplied extra property."""
        try:
            return func(self.image, self.image_intensity)
        except TypeError:
            return func(self.image)

    # --- size and position -------------------------------------------------
    @cached_property
    def area(self) -> int:
        """Number of pixels in the region."""
        return int(self.image.sum())

    @property
    def num_pixels(self) -> int:
        """Number of pixels in the region (scikit-image's alias for :attr:`area`)."""
        return self.area

    @cached_property
    def coords(self) -> np.ndarray:
        """``(N, 2)`` array of the ``(row, col)`` index of every pixel."""
        rr, cc = np.nonzero(self.image)
        return np.column_stack([rr + self.offset[0], cc + self.offset[1]])

    @cached_property
    def bbox(self) -> tuple[int, int, int, int]:
        """Bounding box ``(row0, col0, row1, col1)``, upper bounds exclusive."""
        r0, c0 = self.offset
        h, w = self.image.shape
        return (r0, c0, r0 + h, c0 + w)

    @property
    def slice(self) -> tuple[slice, slice]:
        """The bounding box as slices, ready to index the full frame."""
        r0, c0, r1, c1 = self.bbox
        return (slice(r0, r1), slice(c0, c1))

    @cached_property
    def area_bbox(self) -> int:
        """Number of pixels in the bounding box."""
        return int(self.image.size)

    @cached_property
    def extent(self) -> float:
        """Fraction of its bounding box the region fills.

        Note the collision of names: this is scikit-image's ``extent``, not the
        ``extent`` argument of :meth:`ROI.to_mask`, which is an axis span.
        """
        return float(self.area / self.area_bbox) if self.area_bbox else 0.0

    @cached_property
    def centroid_local(self) -> tuple[float, float]:
        """Centre of mass in bounding-box coordinates."""
        rr, cc = np.nonzero(self.image)
        if rr.size == 0:
            return (float("nan"), float("nan"))
        return (float(rr.mean()), float(cc.mean()))

    @cached_property
    def centroid(self) -> tuple[float, float]:
        """Centre of mass of the pixels, as ``(row, col)`` in the full frame."""
        row, col = self.centroid_local
        return (row + self.offset[0], col + self.offset[1])

    @property
    def centroid_xy(self) -> tuple[float, float]:
        """The centroid as ``(x, y)``, the convention :meth:`ROI.contains` uses."""
        row, col = self.centroid
        return (col, row)

    # --- moments and the equivalent ellipse --------------------------------
    @cached_property
    def moments(self) -> np.ndarray:
        """Raw spatial moments of the mask, up to order 3."""
        return _raw_moments(self.image.astype(float))

    @cached_property
    def moments_central(self) -> np.ndarray:
        """Central moments of the mask, up to order 3."""
        return _central_moments(self.image.astype(float), self.centroid_local)

    @cached_property
    def moments_weighted(self) -> np.ndarray:
        """Raw spatial moments weighted by the intensity image."""
        return _raw_moments(self._weights)

    @cached_property
    def moments_weighted_central(self) -> np.ndarray:
        """Central moments weighted by the intensity image."""
        return _central_moments(self._weights, self.centroid_weighted_local)

    @cached_property
    def inertia_tensor(self) -> np.ndarray:
        """Inertia tensor of the region about its centroid."""
        mu = self.moments_central
        mu0 = mu[0, 0]
        if mu0 == 0:
            return np.zeros((2, 2))
        return np.array([[mu[0, 2], -mu[1, 1]], [-mu[1, 1], mu[2, 0]]]) / mu0

    @cached_property
    def inertia_tensor_eigvals(self) -> tuple[float, float]:
        """Eigenvalues of :attr:`inertia_tensor`, largest first."""
        tensor = self.inertia_tensor
        half_trace = 0.5 * (tensor[0, 0] + tensor[1, 1])
        det = tensor[0, 0] * tensor[1, 1] - tensor[0, 1] * tensor[1, 0]
        disc = math.sqrt(max(half_trace * half_trace - det, 0.0))
        return (max(half_trace + disc, 0.0), max(half_trace - disc, 0.0))

    @cached_property
    def axis_major_length(self) -> float:
        """Major axis of the ellipse with the same second moments as the region."""
        return 4.0 * math.sqrt(self.inertia_tensor_eigvals[0])

    @cached_property
    def axis_minor_length(self) -> float:
        """Minor axis of the ellipse with the same second moments as the region."""
        return 4.0 * math.sqrt(self.inertia_tensor_eigvals[1])

    @cached_property
    def eccentricity(self) -> float:
        """Eccentricity of that ellipse: ``0`` for a disc, ``1`` for a line."""
        l1, l2 = self.inertia_tensor_eigvals
        if l1 <= 0.0:
            return 0.0
        return math.sqrt(max(1.0 - l2 / l1, 0.0))

    @cached_property
    def orientation(self) -> float:
        """Angle of the major axis, in radians within ``[-pi/2, pi/2]``.

        Measured from the row axis towards the column axis, as in scikit-image,
        so a horizontally elongated region sits near ``+-pi/2``.
        """
        tensor = self.inertia_tensor
        a, b, c = tensor[0, 0], tensor[0, 1], tensor[1, 1]
        if a - c == 0:
            # No preferred axis from the second moments (a disc, a square, a
            # single pixel); fall back on the sign of the cross moment.
            return math.pi / 4.0 if b < 0 else -math.pi / 4.0
        return 0.5 * math.atan2(-2.0 * b, c - a)

    @cached_property
    def equivalent_diameter_area(self) -> float:
        """Diameter of the disc with the same area as the region."""
        return math.sqrt(4.0 * self.area / math.pi)

    # --- boundary ----------------------------------------------------------
    def _border_codes(self) -> np.ndarray:
        """Return the 3x3 neighbourhood code of every border pixel."""
        from scipy import ndimage as ndi

        img = self.image.astype(np.uint8)
        eroded = ndi.binary_erosion(img, ndi.generate_binary_structure(2, 1), border_value=0)
        border = img - eroded.astype(np.uint8)
        return ndi.convolve(border, _PERIMETER_KERNEL, mode="constant", cval=0)

    @cached_property
    def perimeter(self) -> float:
        """Length of the region's boundary.

        Border pixels are weighted by their 4-neighbourhood configuration
        (``1`` for a straight step, ``sqrt(2)`` for a diagonal one) rather than
        simply counted, which would underestimate a 45-degree edge by 29 %.

        On regions only a few pixels across the discretisation bias is large in
        either direction — a 7x7 square measures 24 rather than 28 — so treat
        :attr:`circularity` on small objects as a sorting key, not a
        measurement.
        """
        codes = self._border_codes()
        histogram = np.bincount(codes.ravel(), minlength=len(_PERIMETER_WEIGHTS))
        return float(histogram @ _PERIMETER_WEIGHTS)

    @cached_property
    def perimeter_crofton(self) -> float:
        """Boundary length from the Crofton formula over four directions.

        Less biased than :attr:`perimeter` for large convex regions, more
        sensitive to noise on the boundary of small ones.
        """
        from scipy import ndimage as ndi

        padded = np.pad(self.image.astype(np.uint8), 1, mode="constant")
        codes = ndi.convolve(padded, _CROFTON_KERNEL, mode="constant", cval=0)
        histogram = np.bincount(codes.ravel(), minlength=16)
        return float(histogram @ _CROFTON_WEIGHTS)

    @cached_property
    def circularity(self) -> float:
        """``4*pi*area / perimeter**2``: ``1`` for a disc, less for anything else.

        Not a scikit-image property; the imaging plugins here report it because
        it is the cheapest discriminator between a single molecule and an
        aggregate or a scratch. See the caveat on :attr:`perimeter` for small
        regions, where the value can exceed 1.
        """
        p = self.perimeter
        return float(4.0 * math.pi * self.area / (p * p)) if p > 0 else 0.0

    # --- hull, holes and topology ------------------------------------------
    @cached_property
    def image_convex(self) -> np.ndarray:
        """Boolean mask of the region's convex hull, cropped like :attr:`image`."""
        rr, cc = np.nonzero(self.image)
        if rr.size == 0:
            return self.image.copy()
        points = np.column_stack([rr, cc]).astype(float)
        # Hull the pixels' corners, not their centres, so a single pixel or a
        # one-pixel-wide line still encloses its own area.
        points = (points[:, None, :] + _HULL_OFFSETS[None, :, :]).reshape(-1, 2)
        try:
            from scipy.spatial import ConvexHull

            hull = ConvexHull(points)
        except Exception:  # pragma: no cover - degenerate input
            return self.image.copy()
        ny, nx = self.image.shape
        grid_r, grid_c = np.mgrid[:ny, :nx]
        grid = np.column_stack([grid_r.ravel(), grid_c.ravel()]).astype(float)
        equations = hull.equations
        inside = np.all(grid @ equations[:, :2].T + equations[:, 2] < 1e-10, axis=1)
        return inside.reshape(ny, nx)

    @cached_property
    def area_convex(self) -> int:
        """Number of pixels in the convex hull."""
        return int(self.image_convex.sum())

    @cached_property
    def solidity(self) -> float:
        """``area / area_convex``: how much of its own hull the region fills."""
        hull = self.area_convex
        return float(self.area / hull) if hull else 0.0

    @cached_property
    def image_filled(self) -> np.ndarray:
        """The region with its holes filled in."""
        from scipy import ndimage as ndi

        return ndi.binary_fill_holes(self.image)

    @cached_property
    def area_filled(self) -> int:
        """Number of pixels in the region once its holes are filled."""
        return int(self.image_filled.sum())

    @cached_property
    def euler_number(self) -> int:
        """Connected components minus holes: ``1`` for a simply-connected blob.

        Diagonally-touching pixels count as connected, as scikit-image has it
        in 2-D; :meth:`euler_characteristic` takes the other convention.
        """
        return self.euler_characteristic(2)

    def euler_characteristic(self, connectivity: int = 2) -> int:
        """Return components minus holes under a chosen connectivity.

        Counted from the 2x2 pixel configurations rather than by labelling, so
        it costs one convolution however complicated the region is.

        Parameters
        ----------
        connectivity : int
            ``2`` treats diagonally-touching pixels as connected; ``1`` does not.

        Returns
        -------
        int
            The Euler characteristic of the region.
        """
        from scipy import ndimage as ndi

        padded = np.pad(self.image.astype(int), 1, mode="constant")
        codes = ndi.convolve(padded, _CROFTON_KERNEL, mode="constant", cval=0)
        histogram = np.bincount(codes.ravel(), minlength=16)
        weights = _EULER_WEIGHTS_8 if connectivity == 2 else _EULER_WEIGHTS_4
        return int(histogram @ weights)

    @cached_property
    def feret_diameter_max(self) -> float:
        """Longest distance between any two points on the region's hull."""
        rr, cc = np.nonzero(self.image_convex)
        if rr.size == 0:
            return 0.0
        points = np.column_stack([rr, cc]).astype(float)
        points = (points[:, None, :] + _HULL_OFFSETS[None, :, :]).reshape(-1, 2)
        try:
            from scipy.spatial import ConvexHull
            from scipy.spatial.distance import pdist

            vertices = points[ConvexHull(points).vertices]
        except Exception:  # pragma: no cover - degenerate input
            vertices = points
        if len(vertices) < 2:
            return 0.0
        return float(pdist(vertices).max())

    # --- intensity ---------------------------------------------------------
    @cached_property
    def _values(self) -> np.ndarray:
        """The intensity values of the region's pixels."""
        if self.image_intensity is None:
            raise ValueError(
                "this property needs an intensity image; pass intensity_image=... to "
                "regionprops()"
            )
        return self.image_intensity[self.image]

    @cached_property
    def _weights(self) -> np.ndarray:
        """The intensity image, zeroed outside the region and clipped at zero.

        Background subtraction leaves negative pixels behind; used as weights
        they would pull a centre of mass the wrong way, or cancel the
        normalisation entirely, so they are clipped.
        """
        if self.image_intensity is None:
            raise ValueError("this property needs an intensity image")
        return np.clip(np.where(self.image, self.image_intensity, 0.0), 0.0, None)

    @cached_property
    def intensity_sum(self) -> float:
        """Integrated intensity over the region. Not a scikit-image property."""
        return float(self._values.sum())

    @cached_property
    def intensity_mean(self) -> float:
        """Mean intensity over the region."""
        return float(self._values.mean()) if self._values.size else float("nan")

    @cached_property
    def intensity_min(self) -> float:
        """Smallest intensity in the region."""
        return float(self._values.min()) if self._values.size else float("nan")

    @cached_property
    def intensity_max(self) -> float:
        """Largest intensity in the region."""
        return float(self._values.max()) if self._values.size else float("nan")

    @cached_property
    def intensity_std(self) -> float:
        """Standard deviation of the intensity in the region."""
        return float(self._values.std()) if self._values.size else float("nan")

    @cached_property
    def centroid_weighted_local(self) -> tuple[float, float]:
        """Intensity-weighted centre of mass, in bounding-box coordinates."""
        weights = self._weights
        total = float(weights.sum())
        if total <= 0.0:
            return self.centroid_local
        ny, nx = self.image.shape
        rows = np.arange(ny, dtype=float)[:, None]
        cols = np.arange(nx, dtype=float)[None, :]
        return (
            float((weights * rows).sum() / total),
            float((weights * cols).sum() / total),
        )

    @cached_property
    def centroid_weighted(self) -> tuple[float, float]:
        """Intensity-weighted centre of mass, as ``(row, col)`` in the full frame."""
        row, col = self.centroid_weighted_local
        return (row + self.offset[0], col + self.offset[1])

    # --- interoperability --------------------------------------------------
    def to_roi(self) -> MaskROI:
        """Return the region as a :class:`~chisurf.core.roi.MaskROI`.

        Closes the loop: a measured region is a region again, so it can be gated
        against, combined with others, rasterised elsewhere, or stored. This is
        what scikit-image has no counterpart for.
        """
        return MaskROI(self.image, offset=self.offset, name=self.name or str(self.label))

    def __getitem__(self, key: str) -> Any:
        """Return a property by name, as scikit-image's region objects allow."""
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc

    def to_dict(
        self, properties: Sequence[str] | None = None, separator: str = "-"
    ) -> dict[str, Any]:
        """Return the properties as one flat table row.

        Parameters
        ----------
        properties : sequence of str, optional
            Property names to report. Defaults to :data:`PROPERTIES`, plus
            :data:`INTENSITY_PROPERTIES` when an intensity image is present.
        separator : str
            Joins the index onto a multi-component property, so ``centroid``
            becomes ``centroid-0`` and ``centroid-1`` — scikit-image's
            convention in ``regionprops_table``.

        Returns
        -------
        dict
            One entry per scalar, in the requested order.
        """
        if properties is None:
            names: tuple[str, ...] = PROPERTIES
            if self.image_intensity is not None:
                names = names + INTENSITY_PROPERTIES
        else:
            names = tuple(properties)

        row: dict[str, Any] = {}
        for name in names:
            try:
                value = getattr(self, name)
            except AttributeError as exc:
                raise ValueError(f"unknown region property {name!r}") from exc
            row.update(_flatten(name, value, separator))
        return row

    def __repr__(self) -> str:
        """Return a short representation with the label, area and centroid."""
        row, col = self.centroid
        return (
            f"RegionProperties(label={self.label}, area={self.area}, "
            f"centroid=({row:.2f}, {col:.2f}))"
        )


def _flatten(name: str, value: Any, separator: str) -> dict[str, Any]:
    """Split an array- or tuple-valued property into indexed scalar columns."""
    if isinstance(value, (str, bytes)) or np.isscalar(value):
        return {name: value}
    array = np.asarray(value)
    if array.ndim == 0:
        return {name: array.item()}
    out: dict[str, Any] = {}
    for index in np.ndindex(array.shape):
        key = name + separator + separator.join(str(i) for i in index)
        out[key] = array[index]
    return out


def _measure(
    mask: np.ndarray,
    intensity: np.ndarray | None,
    label: int,
    name: str,
    extra_properties: Sequence[Callable] | None,
) -> RegionProperties | None:
    """Crop a full-frame mask to its region and measure it; ``None`` if empty."""
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if rows.size == 0 or cols.size == 0:
        return None
    r0, r1 = int(rows[0]), int(rows[-1]) + 1
    c0, c1 = int(cols[0]), int(cols[-1]) + 1
    return RegionProperties(
        mask[r0:r1, c0:c1],
        offset=(r0, c0),
        label=label,
        intensity=None if intensity is None else intensity[r0:r1, c0:c1],
        name=name,
        extra_properties=extra_properties,
    )


def regionprops(
    label_image: np.ndarray | ROI | Iterable[ROI],
    intensity_image: np.ndarray | None = None,
    cache: bool = True,
    *,
    extra_properties: Sequence[Callable] | None = None,
    shape: Sequence[int] | None = None,
    extent: Extent = None,
    background: int = 0,
) -> list[RegionProperties]:
    """Measure every labelled region, as ``skimage.measure.regionprops`` does.

    Parameters
    ----------
    label_image : numpy.ndarray or ROI or iterable of ROI
        An integer label image (one region per label value) — or, extending
        scikit-image, a boolean mask (one region), a single
        :class:`~chisurf.core.roi.ROI`, or several. ROIs are rasterised first,
        so a drawn polygon is measured exactly like a watershed label.
    intensity_image : numpy.ndarray, optional
        Image the regions were found in; enables the intensity properties and
        the weighted centroid. A stack ``(n_frames, ny, nx)`` is summed over
        frames first.
    cache : bool, optional
        Accepted for signature compatibility. Properties are always cached.
    extra_properties : sequence of callable, optional
        Extra measurements; each is called with the cropped mask (and the
        cropped intensity image when it takes two arguments) and exposed under
        the function's name.
    shape : sequence of int, optional
        Frame shape ``(ny, nx)`` used to rasterise ROI input. Defaults to the
        shape of *intensity_image*.
    extent : tuple of float, optional
        Axis span of the frame when rasterising ROI input, as for
        :meth:`ROI.to_mask`. The measurements themselves are always in pixels.
    background : int, optional
        Label value treated as background in a label image.

    Returns
    -------
    list of RegionProperties
        One entry per region, in ascending label order (label images) or in the
        order given (ROIs). Regions covering no pixel are dropped.

    Raises
    ------
    ValueError
        If ROIs are given with no frame to rasterise them onto, or the input is
        not 2-D.

    Examples
    --------
    >>> labels = np.array([[1, 1, 0], [1, 1, 0], [0, 0, 2]])
    >>> [(p.label, p.area, p.centroid) for p in regionprops(labels)]
    [(1, 4, (0.5, 0.5)), (2, 1, (2.0, 2.0))]

    A drawn region measures the same way:

    >>> from chisurf.core.roi import EllipseROI
    >>> p = regionprops(EllipseROI(5, 5, 3), shape=(11, 11))[0]
    >>> p.area, round(p.eccentricity, 3)
    (29, 0.0)
    """
    intensity: np.ndarray | None = None
    if intensity_image is not None:
        intensity = np.asarray(intensity_image, dtype=float)
        if intensity.ndim == 3:
            intensity = intensity.sum(axis=0)
        if intensity.ndim != 2:
            raise ValueError(f"the intensity image must be 2-D; got shape {intensity.shape}")

    if isinstance(label_image, ROI):
        rois: list[ROI] | None = [label_image]
    elif isinstance(label_image, np.ndarray):
        rois = None
    else:
        rois = list(label_image)

    if rois is not None:
        if shape is None:
            if intensity is None:
                raise ValueError(
                    "measuring a ROI needs a frame to rasterise it onto; pass shape=... "
                    "or an intensity_image"
                )
            shape = intensity.shape
        grid = (int(shape[0]), int(shape[1]))
        out: list[RegionProperties] = []
        for i, roi in enumerate(rois, start=1):
            props = _measure(
                roi.to_mask(grid, extent, intensity), intensity, i,
                getattr(roi, "name", ""), extra_properties,
            )
            if props is not None:
                out.append(props)
        return out

    labels = np.asarray(label_image)
    if labels.ndim != 2:
        raise ValueError(f"region properties need a 2-D label image; got shape {labels.shape}")
    if intensity is not None and intensity.shape != labels.shape:
        raise ValueError(
            f"intensity image shape {intensity.shape} does not match the label image "
            f"{labels.shape}"
        )
    if labels.dtype == bool:
        props = _measure(labels, intensity, 1, "", extra_properties)
        return [props] if props is not None else []

    out = []
    for value in sorted(int(v) for v in np.unique(labels) if int(v) != int(background)):
        props = _measure(labels == value, intensity, value, str(value), extra_properties)
        if props is not None:
            out.append(props)
    return out


def regionprops_table(
    label_image: np.ndarray | ROI | Iterable[ROI] | Sequence[RegionProperties],
    intensity_image: np.ndarray | None = None,
    properties: Sequence[str] | None = None,
    *,
    cache: bool = True,
    separator: str = "-",
    extra_properties: Sequence[Callable] | None = None,
    **kwargs: Any,
) -> dict[str, np.ndarray]:
    """Measure regions and return the result as columns, ready for a DataFrame.

    The counterpart of ``skimage.measure.regionprops_table``: a dict of equal-
    length arrays, one key per scalar column, with multi-component properties
    split by *separator* (``centroid-0``, ``centroid-1``). Wrap it in
    ``pandas.DataFrame(...)`` for a table.

    Parameters
    ----------
    label_image : array_like or ROI or iterable
        Anything :func:`regionprops` accepts, or an already-measured list of
        :class:`RegionProperties`.
    intensity_image : numpy.ndarray, optional
        Passed to :func:`regionprops`.
    properties : sequence of str, optional
        Columns to report; defaults to :data:`PROPERTIES`, plus
        :data:`INTENSITY_PROPERTIES` when an intensity image is given.
    cache : bool, optional
        Accepted for signature compatibility.
    separator : str
        Joins the index onto multi-component property names.
    extra_properties : sequence of callable, optional
        Passed to :func:`regionprops`.
    **kwargs
        Further arguments for :func:`regionprops` (``shape``, ``extent``,
        ``background``).

    Returns
    -------
    dict of numpy.ndarray
        One key per column. Empty arrays, with the requested keys, when there
        are no regions.

    Examples
    --------
    >>> labels = np.array([[1, 1, 0], [1, 1, 0], [0, 0, 2]])
    >>> table = regionprops_table(labels, properties=["label", "area"])
    >>> table["area"].tolist()
    [4, 1]

    >>> import pandas as pd
    >>> pd.DataFrame(regionprops_table(labels, properties=["centroid"]))
       centroid-0  centroid-1
    0         0.5         0.5
    1         2.0         2.0
    """
    items = list(label_image) if isinstance(label_image, (list, tuple)) else None
    if items and all(isinstance(item, RegionProperties) for item in items):
        props: list[RegionProperties] = items  # type: ignore[assignment]
    else:
        props = regionprops(
            label_image, intensity_image, cache,  # type: ignore[arg-type]
            extra_properties=extra_properties, **kwargs,
        )

    if not props:
        # No regions still means a table with the right columns, so callers need
        # no special case. A one-pixel stand-in supplies the column names.
        if properties is not None:
            names: tuple[str, ...] = tuple(properties)
        else:
            names = PROPERTIES + (INTENSITY_PROPERTIES if intensity_image is not None else ())
        stand_in = RegionProperties(
            np.ones((1, 1), dtype=bool), intensity=np.zeros((1, 1)),
            extra_properties=extra_properties,
        )
        return {key: np.array([]) for key in stand_in.to_dict(names, separator)}

    rows = [p.to_dict(properties, separator) for p in props]
    return {key: np.array([row[key] for row in rows]) for key in rows[0]}
