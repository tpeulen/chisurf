"""Bridge between ndXplorer's ``DataSelection`` gates and ChiSurf regions.

ndXplorer grew its own selection hierarchy — a 1-D interval, a Mahalanobis
ellipse, a painted histogram bitmap — with per-selection ``enabled`` and
``invert`` flags, combined by an implicit AND. That is, term for term, a
:class:`~chisurf.core.roi.collection.RegionCollection`: entries carrying the
same two flags, reduced by ``combine="and"``.

Two things differ and both are mechanical:

* **The mask convention is inverted.** ``DataSelection.get_mask`` returns
  ``True`` where a point is *excluded*, shaped ``(n_parameters, n_points)``;
  a region answers where a point is *inside*. :meth:`RegionCollection.excluded`
  is the same answer in ndXplorer's direction, which is why it exists.
* **A selection names its axes by index.** A region carries no axes at all —
  that is what lets one gate an image and a parameter plane — so the axes are
  supplied here, at the moment of conversion.

The bridge lives on the ChiSurf side and is duck-typed: it reads attributes off
whatever it is handed and never imports ndXplorer, so the dependency stays
one-directional.

Round-tripping matters for a reason beyond tidiness. ndXplorer's own
``onLoad_selection`` reconstructs **only** ``RectangularDataSelection`` — a
saved ellipse or painted mask is silently dropped on reload. Stored as a
region collection they all survive, because
:meth:`RegionCollection.to_dict` keeps the type tag.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional, Sequence, Tuple

import numpy as np

from .collection import RegionCollection, RegionEntry
from .roi import ROI, EllipseROI, MaskROI, RectangleROI

#: How far a 1-D interval extends along the axis it does not constrain.
#: Infinite, because that is what "no constraint on the other parameter" means;
#: ``contains`` compares against it without trouble.
UNBOUNDED = math.inf


def interval_roi(lower: float, upper: float, axis: int = 0, name: str = "") -> ROI:
    """Return a 1-D interval as a region on a 2-D plane.

    Parameters
    ----------
    lower, upper : float
        The interval, closed at the lower end and open at the upper, as
        :class:`~chisurf.core.roi.roi.RectangleROI` is.
    axis : int
        ``0`` constrains x, ``1`` constrains y.
    name : str, optional
        Region name.

    Returns
    -------
    RectangleROI
        Unbounded along the axis it does not constrain.
    """
    lo, hi = float(lower), float(upper)
    if hi < lo:
        lo, hi = hi, lo
    if axis:
        return RectangleROI(-UNBOUNDED, lo, UNBOUNDED, hi, name=name)
    return RectangleROI(lo, -UNBOUNDED, hi, UNBOUNDED, name=name)


def ellipse_from_covariance(
    mu: Sequence[float],
    cov: Sequence[Sequence[float]],
    sigma: float = 1.0,
    name: str = "",
) -> EllipseROI:
    """Return the Mahalanobis ellipse ``d² <= sigma²`` as a region.

    The eigenvectors of the covariance are the ellipse's axes and the square
    roots of its eigenvalues are the standard deviations along them, so the
    semi-axes are ``sigma * sqrt(eigenvalue)``.

    Parameters
    ----------
    mu : sequence of float
        Centre ``(x, y)``.
    cov : 2x2 array-like
        Covariance.
    sigma : float
        Mahalanobis radius.
    name : str, optional
        Region name.

    Returns
    -------
    EllipseROI
    """
    centre = np.asarray(mu, dtype=float).reshape(2)
    matrix = np.asarray(cov, dtype=float).reshape(2, 2)
    # Symmetric by construction; eigh keeps the eigenvectors orthonormal and the
    # eigenvalues real, which np.linalg.eig does not guarantee for a matrix that
    # is only nearly symmetric.
    values, vectors = np.linalg.eigh(0.5 * (matrix + matrix.T))
    values = np.clip(values, 0.0, None)
    order = np.argsort(values)[::-1]
    values, vectors = values[order], vectors[:, order]
    rx, ry = (float(sigma) * np.sqrt(values)).tolist()
    angle = math.atan2(float(vectors[1, 0]), float(vectors[0, 0]))
    return EllipseROI(centre[0], centre[1], rx, ry, angle=angle, name=name)


def roi_from_selection(
    selection: Any, axes: Tuple[int, int] = (0, 1), name: str = ""
) -> Optional[ROI]:
    """Return an ndXplorer selection as a region, or ``None`` if it has no shape.

    Duck-typed: the selection is recognised by the attributes it carries, not by
    its class, so this never imports ndXplorer.

    Parameters
    ----------
    selection : object
        A ``RectangularDataSelection`` (1-D interval), a ``Gaussian2DSelection``
        (Mahalanobis ellipse) or a ``MaskDataSelection`` (painted histogram).
    axes : tuple of int
        The two parameter indices the plane is drawn from. A selection on a
        parameter that is not one of them cannot be expressed as a region here
        and returns ``None``.
    name : str, optional
        Overrides the selection's own name.

    Returns
    -------
    ROI or None

    Notes
    -----
    A Gaussian selection may carry per-axis ``log_x``/``log_y`` flags, meaning
    its ellipse lives in log space. The region returned is in that same space —
    it has to be, since an ellipse in log space is not an ellipse in linear
    space — so gate log-transformed coordinates with it.
    """
    label = str(name or getattr(selection, "name", "") or "selection")

    mask = getattr(selection, "mask", None)
    if mask is not None:
        # A painted selection names its axes ``idx1``/``idx2`` where the others
        # use ``parameter_idx*``; applying it to the wrong plane would gate on
        # parameters it was never drawn against.
        idx = (int(getattr(selection, "idx1", 0)), int(getattr(selection, "idx2", 1)))
        if idx != tuple(axes):
            return None
        edges1 = getattr(selection, "edges1", None)
        edges2 = getattr(selection, "edges2", None)
        if edges1 is None or edges2 is None:
            return MaskROI(np.asarray(mask) > 0, name=label)
        return MaskROI.from_histogram(
            np.asarray(mask) > 0, np.asarray(edges1), np.asarray(edges2), name=label
        )

    if hasattr(selection, "mu") and hasattr(selection, "cov"):
        idx = (int(selection.parameter_idx1), int(selection.parameter_idx2))
        if idx != tuple(axes):
            return None
        return ellipse_from_covariance(
            selection.mu, selection.cov, float(getattr(selection, "sigma", 1.0)),
            name=label,
        )

    if hasattr(selection, "parameter_idx") and hasattr(selection, "lower"):
        index = int(selection.parameter_idx)
        if index not in tuple(axes):
            return None
        return interval_roi(
            selection.lower, selection.upper,
            axis=0 if index == axes[0] else 1, name=label,
        )

    return None


def collection_from_selections(
    selections: Iterable[Any], axes: Tuple[int, int] = (0, 1), name: str = "selection"
) -> RegionCollection:
    """Return ndXplorer's selection list as a region collection.

    ``combine="and"`` because that is what ndXplorer does: a point survives only
    if no enabled selection excludes it. Selections that cannot be expressed on
    this plane — one constraining a third parameter — are skipped rather than
    approximated, since a wrong gate is worse than a missing one.

    Parameters
    ----------
    selections : iterable
        The ndXplorer selections.
    axes : tuple of int
        The parameter indices of the plane.
    name : str, optional
        Name for the combined region.

    Returns
    -------
    RegionCollection
        Carrying each selection's ``enabled`` and ``invert`` flags.
    """
    collection = RegionCollection(combine="and", name=name)
    for selection in selections or []:
        roi = roi_from_selection(selection, axes=axes)
        if roi is None:
            continue
        collection.add(
            RegionEntry(
                roi=roi,
                enabled=bool(getattr(selection, "enabled", True)),
                invert=bool(getattr(selection, "invert", False)),
            )
        )
    return collection


def excluded_mask(
    collection: RegionCollection, data: np.ndarray, axes: Tuple[int, int] = (0, 1)
) -> np.ndarray:
    """Return ndXplorer's mask shape and convention for a region collection.

    ``True`` means *excluded*, and the answer is broadcast to every parameter
    row, exactly as ``DataSelection.get_mask`` does — that shape is what
    ndXplorer's mask combiner expects.

    Parameters
    ----------
    collection : RegionCollection
        The gates.
    data : numpy.ndarray
        ``(n_parameters, n_points)``.
    axes : tuple of int
        Which two rows form the plane.

    Returns
    -------
    numpy.ndarray
        Boolean, ``(n_parameters, n_points)``.
    """
    values = np.asarray(data, dtype=float)
    n_parameters, n_points = values.shape
    out = np.zeros((n_parameters, n_points), dtype=bool)
    if max(axes) >= n_parameters:
        return out
    points = np.column_stack([values[axes[0]], values[axes[1]]])
    out[:] = collection.excluded(points)
    return out


__all__ = [
    "roi_from_selection",
    "collection_from_selections",
    "excluded_mask",
    "ellipse_from_covariance",
    "interval_roi",
    "UNBOUNDED",
]
