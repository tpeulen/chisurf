"""Region-of-interest geometry shared by imaging, gating and segmentation.

See :mod:`chisurf.core.roi` for the rationale. The two operations every ROI
supports are :meth:`ROI.contains` (point membership, for gating scattered data)
and :meth:`ROI.to_mask` (rasterisation onto a pixel grid, for images); the
geometric shapes implement the first and get the second for free.

Coordinates
-----------
A ROI's geometry carries no axes of its own. ``to_mask`` takes an ``extent``
``(x0, x1, y0, y1)`` describing the value span of the array being masked, in the
same convention as an image plotted with those axis limits. Omitting ``extent``
means the geometry is in **pixel-index coordinates**: ``x`` is the column index
and ``y`` the row index, with pixel centres at integer positions.

That separation is what lets one rectangle mean "these pixels" on a CLSM frame
and "these bursts" on a parameter histogram.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

#: Registry of ROI type name -> class, populated by ``__init_subclass__``.
_ROI_TYPES: Dict[str, type] = {}

Extent = Optional[Tuple[float, float, float, float]]


def pixel_centres(
    shape: Sequence[int], extent: Extent = None
) -> Tuple[np.ndarray, np.ndarray]:
    """Return the ``(x, y)`` coordinate of every pixel centre in a grid.

    Parameters
    ----------
    shape : sequence of int
        Array shape ``(ny, nx)``.
    extent : tuple of float, optional
        Value span ``(x0, x1, y0, y1)`` covered by the array. When omitted the
        coordinates are pixel indices, with centres at integers.

    Returns
    -------
    tuple of numpy.ndarray
        Two ``(ny, nx)`` arrays holding the x and y coordinate of each pixel.

    Examples
    --------
    >>> x, y = pixel_centres((2, 3))
    >>> x[0].tolist(), y[:, 0].tolist()
    ([0.0, 1.0, 2.0], [0.0, 1.0])

    With an extent the centres are inset by half a pixel, as they should be:

    >>> x, _ = pixel_centres((1, 2), extent=(0.0, 10.0, 0.0, 1.0))
    >>> x[0].tolist()
    [2.5, 7.5]
    """
    ny, nx = int(shape[0]), int(shape[1])
    if extent is None:
        xs = np.arange(nx, dtype=float)
        ys = np.arange(ny, dtype=float)
    else:
        x0, x1, y0, y1 = (float(v) for v in extent)
        xs = x0 + (np.arange(nx, dtype=float) + 0.5) * (x1 - x0) / max(nx, 1)
        ys = y0 + (np.arange(ny, dtype=float) + 0.5) * (y1 - y0) / max(ny, 1)
    return np.meshgrid(xs, ys)


def _as_points(points: np.ndarray) -> np.ndarray:
    """Return an ``(N, 2)`` float array of ``(x, y)`` points.

    Parameters
    ----------
    points : numpy.ndarray
        Either a single ``(x, y)`` pair or an ``(N, 2)`` array.

    Returns
    -------
    numpy.ndarray
        The points as ``(N, 2)`` floats.

    Raises
    ------
    ValueError
        If the array is not shaped like a list of 2-D points.
    """
    arr = np.atleast_2d(np.asarray(points, dtype=float))
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f"points must be (N, 2) with columns (x, y); got {arr.shape}")
    return arr


class ROI(abc.ABC):
    """Base class for regions of interest.

    Subclasses implement :meth:`contains` and :meth:`_params`; masking,
    composition and serialisation are provided here.

    Attributes
    ----------
    name : str
        Free-form label, carried through serialisation so a stored selection
        keeps its meaning.
    """

    #: Serialised type tag; defaults to the class name.
    type_name: str = "roi"

    def __init__(self, name: str = "") -> None:
        """Initialize the ROI with an optional label."""
        self.name = str(name)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Register concrete subclasses so :func:`roi_from_dict` can find them."""
        super().__init_subclass__(**kwargs)
        if getattr(cls, "type_name", None):
            _ROI_TYPES[cls.type_name] = cls

    # --- the two questions -------------------------------------------------
    @abc.abstractmethod
    def contains(self, points: np.ndarray) -> np.ndarray:
        """Return which points lie inside the region.

        Parameters
        ----------
        points : numpy.ndarray
            ``(N, 2)`` array of ``(x, y)`` coordinates, or a single pair.

        Returns
        -------
        numpy.ndarray
            Boolean array of length ``N``.
        """

    def to_mask(
        self,
        shape: Sequence[int],
        extent: Extent = None,
        image: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Rasterise the region onto a pixel grid.

        Parameters
        ----------
        shape : sequence of int
            Array shape ``(ny, nx)`` to mask.
        extent : tuple of float, optional
            Value span ``(x0, x1, y0, y1)``; omit for pixel-index coordinates.
        image : numpy.ndarray, optional
            The image being masked. Only intensity-dependent regions
            (:class:`ThresholdROI`) use it; geometric regions ignore it.

        Returns
        -------
        numpy.ndarray
            Boolean mask of shape ``(ny, nx)``.
        """
        gx, gy = pixel_centres(shape, extent)
        pts = np.column_stack([gx.ravel(), gy.ravel()])
        return self.contains(pts).reshape(gx.shape)

    def bounding_box(
        self,
        shape: Sequence[int],
        extent: Extent = None,
        image: Optional[np.ndarray] = None,
    ) -> Optional[Tuple[int, int, int, int]]:
        """Return the smallest box of pixels containing the region.

        Parameters
        ----------
        shape : sequence of int
            Array shape ``(ny, nx)`` the region is rasterised onto.
        extent : tuple of float, optional
            Value span ``(x0, x1, y0, y1)``; omit for pixel-index coordinates.
        image : numpy.ndarray, optional
            Image for intensity-dependent regions.

        Returns
        -------
        tuple of int or None
            ``(row0, col0, row1, col1)`` with the upper bounds exclusive, so
            ``img[row0:row1, col0:col1]`` is the crop; ``None`` when the region
            covers no pixel.
        """
        mask = self.to_mask(shape, extent, image)
        rows = np.flatnonzero(mask.any(axis=1))
        cols = np.flatnonzero(mask.any(axis=0))
        if rows.size == 0 or cols.size == 0:
            return None
        return (int(rows[0]), int(cols[0]), int(rows[-1]) + 1, int(cols[-1]) + 1)

    def properties(
        self,
        shape: Sequence[int],
        extent: Extent = None,
        image: Optional[np.ndarray] = None,
    ) -> Optional[Any]:
        """Measure the region: area, centroid, shape and intensity statistics.

        Parameters
        ----------
        shape : sequence of int
            Array shape ``(ny, nx)`` the region is rasterised onto.
        extent : tuple of float, optional
            Value span ``(x0, x1, y0, y1)``; omit for pixel-index coordinates.
        image : numpy.ndarray, optional
            Intensity image; supplying it adds the intensity properties.

        Returns
        -------
        chisurf.core.roi.props.RegionProperties or None
            The measurements, or ``None`` when the region covers no pixel.
        """
        from .props import regionprops

        found = regionprops(self, image, shape=shape, extent=extent)
        return found[0] if found else None

    # --- composition -------------------------------------------------------
    def __and__(self, other: "ROI") -> "CompositeROI":
        """Return the intersection of two regions."""
        return CompositeROI("and", [self, other])

    def __or__(self, other: "ROI") -> "CompositeROI":
        """Return the union of two regions."""
        return CompositeROI("or", [self, other])

    def __xor__(self, other: "ROI") -> "CompositeROI":
        """Return the symmetric difference of two regions."""
        return CompositeROI("xor", [self, other])

    def __sub__(self, other: "ROI") -> "CompositeROI":
        """Return this region with another removed."""
        return CompositeROI("sub", [self, other])

    def __invert__(self) -> "CompositeROI":
        """Return everything outside this region."""
        return CompositeROI("not", [self])

    # --- serialisation -----------------------------------------------------
    @abc.abstractmethod
    def _params(self) -> Dict[str, Any]:
        """Return the type-specific parameters for :meth:`to_dict`."""

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable description of the region.

        Returns
        -------
        dict
            ``{"type": ..., "name": ..., **params}``, reversible with
            :func:`roi_from_dict`.
        """
        out: Dict[str, Any] = {"type": self.type_name, "name": self.name}
        out.update(self._params())
        return out

    def __repr__(self) -> str:
        """Return a readable representation including the parameters."""
        params = ", ".join(f"{k}={v!r}" for k, v in self._params().items())
        label = f", name={self.name!r}" if self.name else ""
        return f"{type(self).__name__}({params}{label})"


class RectangleROI(ROI):
    """An axis-aligned rectangle.

    Bounds are inclusive of the lower edge and exclusive of the upper, matching
    the half-open convention used by array slicing, so abutting rectangles tile
    without overlapping.
    """

    type_name = "rectangle"

    def __init__(
        self, x0: float, y0: float, x1: float, y1: float, name: str = ""
    ) -> None:
        """Initialize from two opposite corners, in either order."""
        super().__init__(name=name)
        self.x0, self.x1 = (float(x0), float(x1)) if x0 <= x1 else (float(x1), float(x0))
        self.y0, self.y1 = (float(y0), float(y1)) if y0 <= y1 else (float(y1), float(y0))

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Return which points lie inside the rectangle."""
        p = _as_points(points)
        return (
            (p[:, 0] >= self.x0)
            & (p[:, 0] < self.x1)
            & (p[:, 1] >= self.y0)
            & (p[:, 1] < self.y1)
        )

    def _params(self) -> Dict[str, Any]:
        """Return the corner coordinates."""
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}

    @classmethod
    def from_slices(cls, y_range: Sequence[int], x_range: Sequence[int], name: str = "") -> "RectangleROI":
        """Build a rectangle from array slice bounds.

        Parameters
        ----------
        y_range, x_range : sequence of int
            ``(start, stop)`` index pairs, as used for ``img[y0:y1, x0:x1]``.
        name : str
            Optional label.

        Returns
        -------
        RectangleROI
            A rectangle covering exactly those pixels in pixel-index
            coordinates.
        """
        # Pixel centres sit at integers, so a slice [a, b) covers centres
        # a .. b-1; the half-open rectangle [a-0.5, b-0.5) selects exactly those.
        return cls(
            float(x_range[0]) - 0.5, float(y_range[0]) - 0.5,
            float(x_range[1]) - 0.5, float(y_range[1]) - 0.5,
            name=name,
        )


class EllipseROI(ROI):
    """An ellipse, optionally rotated.

    Covers the circular case (``rx == ry``) used for beads, spots and the
    2-D-Gaussian gates drawn on parameter histograms.
    """

    type_name = "ellipse"

    def __init__(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: Optional[float] = None,
        angle: float = 0.0,
        name: str = "",
    ) -> None:
        """Initialize from a centre, two radii and a rotation in radians."""
        super().__init__(name=name)
        self.cx, self.cy = float(cx), float(cy)
        self.rx = abs(float(rx))
        self.ry = self.rx if ry is None else abs(float(ry))
        self.angle = float(angle)

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Return which points lie inside the ellipse."""
        p = _as_points(points)
        dx = p[:, 0] - self.cx
        dy = p[:, 1] - self.cy
        if self.angle:
            c, s = np.cos(-self.angle), np.sin(-self.angle)
            dx, dy = dx * c - dy * s, dx * s + dy * c
        rx = self.rx if self.rx > 0 else np.inf
        ry = self.ry if self.ry > 0 else np.inf
        return (dx / rx) ** 2 + (dy / ry) ** 2 <= 1.0

    def _params(self) -> Dict[str, Any]:
        """Return the centre, radii and rotation."""
        return {
            "cx": self.cx, "cy": self.cy,
            "rx": self.rx, "ry": self.ry, "angle": self.angle,
        }


class PolygonROI(ROI):
    """An arbitrary polygon.

    This is also the freehand region: a hand-drawn outline is a polygon with
    many vertices, so no separate type is needed.
    """

    type_name = "polygon"

    def __init__(self, vertices: np.ndarray, name: str = "") -> None:
        """Initialize from an ``(N, 2)`` array of ``(x, y)`` vertices."""
        super().__init__(name=name)
        v = np.atleast_2d(np.asarray(vertices, dtype=float))
        if v.ndim != 2 or v.shape[1] != 2 or v.shape[0] < 3:
            raise ValueError(
                f"a polygon needs at least 3 (x, y) vertices; got shape {v.shape}"
            )
        self.vertices = v

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Return which points lie inside the polygon (even-odd rule)."""
        p = _as_points(points)
        px, py = p[:, 0], p[:, 1]
        vx, vy = self.vertices[:, 0], self.vertices[:, 1]
        inside = np.zeros(px.shape, dtype=bool)
        n = len(vx)
        j = n - 1
        for i in range(n):
            # Edge j->i straddles the horizontal ray through the point.
            straddles = (vy[i] > py) != (vy[j] > py)
            if not np.any(straddles):
                j = i
                continue
            dy = vy[j] - vy[i]
            # dy is non-zero wherever `straddles` holds, so the division is only
            # evaluated there; elsewhere the result is discarded.
            with np.errstate(divide="ignore", invalid="ignore"):
                x_cross = (vx[j] - vx[i]) * (py - vy[i]) / dy + vx[i]
            inside ^= straddles & (px < x_cross)
            j = i
        return inside

    def _params(self) -> Dict[str, Any]:
        """Return the vertex list."""
        return {"vertices": self.vertices.tolist()}


class MaskROI(ROI):
    """A region given directly as a boolean pixel mask.

    This is the home for anything that is not analytic geometry: a painted
    brush stroke, one label of a segmentation, an imported classification map.
    The mask lives in pixel-index coordinates, optionally offset within a
    larger image.
    """

    type_name = "mask"

    def __init__(
        self,
        mask: np.ndarray,
        offset: Tuple[int, int] = (0, 0),
        name: str = "",
    ) -> None:
        """Initialize from a 2-D boolean array and its ``(row, col)`` offset."""
        super().__init__(name=name)
        m = np.asarray(mask)
        if m.ndim != 2:
            raise ValueError(f"a mask ROI needs a 2-D array; got shape {m.shape}")
        self.mask = m.astype(bool)
        self.offset = (int(offset[0]), int(offset[1]))

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Return which points fall on a set pixel of the mask."""
        p = _as_points(points)
        col = np.rint(p[:, 0]).astype(int) - self.offset[1]
        row = np.rint(p[:, 1]).astype(int) - self.offset[0]
        ny, nx = self.mask.shape
        ok = (row >= 0) & (row < ny) & (col >= 0) & (col < nx)
        out = np.zeros(len(p), dtype=bool)
        out[ok] = self.mask[row[ok], col[ok]]
        return out

    def to_mask(
        self,
        shape: Sequence[int],
        extent: Extent = None,
        image: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Return the stored mask placed into an array of the requested shape."""
        if extent is not None:
            return super().to_mask(shape, extent, image)
        ny, nx = int(shape[0]), int(shape[1])
        out = np.zeros((ny, nx), dtype=bool)
        r0, c0 = self.offset
        mh, mw = self.mask.shape
        # Overlap of the stored mask with the target array.
        r_lo, c_lo = max(0, r0), max(0, c0)
        r_hi, c_hi = min(ny, r0 + mh), min(nx, c0 + mw)
        if r_hi > r_lo and c_hi > c_lo:
            out[r_lo:r_hi, c_lo:c_hi] = self.mask[
                r_lo - r0:r_hi - r0, c_lo - c0:c_hi - c0
            ]
        return out

    def _params(self) -> Dict[str, Any]:
        """Return the mask as nested lists plus its offset."""
        return {"mask": self.mask.astype(np.uint8).tolist(), "offset": list(self.offset)}


class ThresholdROI(ROI):
    """Pixels whose intensity falls in a range.

    Unlike the geometric regions this one depends on the image, not on
    position, so it only answers the mask question. It composes with geometric
    regions in the usual way -- "bright pixels inside this polygon" is
    ``polygon & ThresholdROI(low=...)``.
    """

    type_name = "threshold"

    def __init__(
        self,
        low: Optional[float] = None,
        high: Optional[float] = None,
        percentile: bool = False,
        name: str = "",
    ) -> None:
        """Initialize from bounds, optionally interpreted as percentiles.

        Parameters
        ----------
        low, high : float, optional
            Bounds; ``None`` leaves that side open.
        percentile : bool
            Treat the bounds as percentiles of the finite image values rather
            than absolute intensities.
        name : str
            Optional label.
        """
        super().__init__(name=name)
        self.low = None if low is None else float(low)
        self.high = None if high is None else float(high)
        self.percentile = bool(percentile)

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Raise: a threshold is defined by intensity, not by position."""
        raise TypeError(
            "ThresholdROI selects by intensity, so it has no point membership; "
            "use to_mask(shape, image=...) instead."
        )

    def to_mask(
        self,
        shape: Sequence[int],
        extent: Extent = None,
        image: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Return the pixels of *image* whose value lies within the bounds.

        Parameters
        ----------
        shape : sequence of int
            Expected mask shape ``(ny, nx)``.
        extent : tuple of float, optional
            Unused; accepted for interface compatibility.
        image : numpy.ndarray
            The image to threshold. A stack ``(n_frames, ny, nx)`` is averaged
            over frames first.

        Returns
        -------
        numpy.ndarray
            Boolean mask of shape ``(ny, nx)``.

        Raises
        ------
        ValueError
            If no image is supplied or its shape does not match.
        """
        if image is None:
            raise ValueError("ThresholdROI.to_mask needs image=...")
        img = np.asarray(image, dtype=float)
        if img.ndim == 3:
            img = img.mean(axis=0)
        if img.ndim != 2:
            raise ValueError(f"cannot threshold an array of shape {img.shape}")
        if tuple(img.shape) != (int(shape[0]), int(shape[1])):
            raise ValueError(
                f"image shape {img.shape} does not match requested mask shape "
                f"{(int(shape[0]), int(shape[1]))}"
            )

        finite = np.isfinite(img)
        low, high = self.low, self.high
        if self.percentile:
            data = img[finite]
            if data.size == 0:
                return np.zeros_like(img, dtype=bool)
            low = None if low is None else float(np.percentile(data, low))
            high = None if high is None else float(np.percentile(data, high))

        out = finite.copy()
        if low is not None:
            out &= img >= low
        if high is not None:
            out &= img <= high
        return out

    def _params(self) -> Dict[str, Any]:
        """Return the bounds and whether they are percentiles."""
        return {"low": self.low, "high": self.high, "percentile": self.percentile}


class CompositeROI(ROI):
    """A boolean combination of regions.

    Built by the operators on :class:`ROI` rather than directly:
    ``cell & ~nucleus`` is a :class:`CompositeROI`.
    """

    type_name = "composite"

    #: Supported operations and their arity (``None`` = any number).
    OPS = {"and": None, "or": None, "xor": None, "sub": 2, "not": 1}

    def __init__(self, op: str, rois: Sequence[ROI], name: str = "") -> None:
        """Initialize from an operation name and its operands."""
        super().__init__(name=name)
        if op not in self.OPS:
            raise ValueError(f"unknown ROI operation {op!r}; expected one of {sorted(self.OPS)}")
        members = list(rois)
        arity = self.OPS[op]
        if arity is not None and len(members) != arity:
            raise ValueError(f"operation {op!r} takes {arity} regions, got {len(members)}")
        if not members:
            raise ValueError(f"operation {op!r} needs at least one region")
        self.op = op
        self.rois: List[ROI] = members

    def _combine(self, parts: List[np.ndarray]) -> np.ndarray:
        """Apply the operation to already-evaluated boolean arrays."""
        if self.op == "not":
            return ~parts[0]
        if self.op == "sub":
            return parts[0] & ~parts[1]
        out = parts[0].copy()
        for part in parts[1:]:
            if self.op == "and":
                out &= part
            elif self.op == "or":
                out |= part
            else:  # xor
                out ^= part
        return out

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Return point membership of the combined region."""
        return self._combine([r.contains(points) for r in self.rois])

    def to_mask(
        self,
        shape: Sequence[int],
        extent: Extent = None,
        image: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Return the rasterised combined region.

        Delegating per operand (rather than combining point membership) is what
        lets intensity-dependent regions take part in a composite.
        """
        return self._combine([r.to_mask(shape, extent, image) for r in self.rois])

    def _params(self) -> Dict[str, Any]:
        """Return the operation and the serialised operands."""
        return {"op": self.op, "rois": [r.to_dict() for r in self.rois]}


def roi_from_dict(data: Dict[str, Any]) -> ROI:
    """Rebuild a region from its :meth:`ROI.to_dict` description.

    Parameters
    ----------
    data : dict
        A description produced by :meth:`ROI.to_dict`.

    Returns
    -------
    ROI
        The reconstructed region, including nested composites.

    Raises
    ------
    ValueError
        If the type tag is missing or unknown.

    Examples
    --------
    >>> r = RectangleROI(0, 0, 4, 4, name="cell") & ~EllipseROI(2, 2, 1)
    >>> roi_from_dict(r.to_dict()).to_mask((4, 4)).sum()
    np.int64(11)
    """
    if not isinstance(data, dict) or "type" not in data:
        raise ValueError("a ROI description needs a 'type' entry")
    tag = str(data["type"])
    cls = _ROI_TYPES.get(tag)
    if cls is None:
        raise ValueError(f"unknown ROI type {tag!r}; known: {sorted(_ROI_TYPES)}")

    params = {k: v for k, v in data.items() if k != "type"}
    if cls is CompositeROI:
        return CompositeROI(
            op=params["op"],
            rois=[roi_from_dict(d) for d in params["rois"]],
            name=params.get("name", ""),
        )
    if cls is PolygonROI:
        return PolygonROI(np.asarray(params["vertices"], dtype=float),
                          name=params.get("name", ""))
    if cls is MaskROI:
        return MaskROI(np.asarray(params["mask"], dtype=bool),
                       offset=tuple(params.get("offset", (0, 0))),
                       name=params.get("name", ""))
    return cls(**params)


def labels_to_rois(
    labels: np.ndarray, crop: bool = True, background: int = 0
) -> List[MaskROI]:
    """Split a segmentation label image into one region per label.

    The bridge between segmentation and everything else: watershed output,
    an imported classification map or a connected-component labelling becomes a
    list of regions that can be gated, masked, combined and stored like any
    other.

    Parameters
    ----------
    labels : numpy.ndarray
        Integer label image; ``background`` marks pixels belonging to no region.
    crop : bool
        Store each region cropped to its bounding box with an offset, rather
        than as a full-size mask. Much cheaper for many small objects.
    background : int
        The label value treated as background.

    Returns
    -------
    list of MaskROI
        One region per distinct label, in ascending label order, named after
        the label value.

    Examples
    --------
    >>> lab = np.array([[0, 1, 1], [2, 2, 0]])
    >>> [r.name for r in labels_to_rois(lab)]
    ['1', '2']
    >>> labels_to_rois(lab)[0].to_mask((2, 3)).tolist()
    [[False, True, True], [False, False, False]]
    """
    lab = np.asarray(labels)
    if lab.ndim != 2:
        raise ValueError(f"labels must be a 2-D image; got shape {lab.shape}")

    out: List[MaskROI] = []
    for value in sorted(int(v) for v in np.unique(lab) if int(v) != int(background)):
        hit = lab == value
        if not crop:
            out.append(MaskROI(hit, name=str(value)))
            continue
        rows = np.flatnonzero(hit.any(axis=1))
        cols = np.flatnonzero(hit.any(axis=0))
        r0, r1 = int(rows[0]), int(rows[-1]) + 1
        c0, c1 = int(cols[0]), int(cols[-1]) + 1
        out.append(MaskROI(hit[r0:r1, c0:c1], offset=(r0, c0), name=str(value)))
    return out


def rois_to_labels(
    rois: Iterable[ROI],
    shape: Sequence[int],
    extent: Extent = None,
    image: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Rasterise several regions into one integer label image.

    The inverse of :func:`labels_to_rois`. Regions are drawn in order, so a
    later region overwrites an earlier one where they overlap.

    Parameters
    ----------
    rois : iterable of ROI
        The regions to draw; the first gets label 1.
    shape : sequence of int
        Output shape ``(ny, nx)``.
    extent : tuple of float, optional
        Value span, as for :meth:`ROI.to_mask`.
    image : numpy.ndarray, optional
        Image for any intensity-dependent regions.

    Returns
    -------
    numpy.ndarray
        Integer label image, 0 where no region applies.
    """
    ny, nx = int(shape[0]), int(shape[1])
    out = np.zeros((ny, nx), dtype=np.int32)
    for i, roi in enumerate(rois, start=1):
        out[roi.to_mask((ny, nx), extent, image)] = i
    return out
