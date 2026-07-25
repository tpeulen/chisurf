"""Regions of interest, shared across ChiSurf.

A region of interest answers one of two questions, and ChiSurf asks both:

* **Is this point inside?** — gating scattered data (burst parameters in a 2-D
  histogram, molecules by position). :meth:`ROI.contains`.
* **Which pixels are inside?** — restricting an image analysis to part of a
  frame. :meth:`ROI.to_mask`.

Both come from the same geometry, so they live on the same object. A rectangle
drawn on an ndX parameter histogram and a rectangle drawn on a CLSM image are
the same :class:`RectangleROI`; only the axes differ, and axes are supplied at
call time via ``extent`` rather than baked into the shape.

ROIs compose with the boolean operators (``&``, ``|``, ``~``, ``-``, ``^``) and
round-trip through :meth:`ROI.to_dict` / :func:`roi_from_dict`, so a selection
can be stored in a project, sent over RPC, or handed from one tool to another.
"""

from __future__ import annotations

from .roi import (
    ROI,
    CompositeROI,
    EllipseROI,
    MaskROI,
    PolygonROI,
    RectangleROI,
    ThresholdROI,
    labels_to_rois,
    roi_from_dict,
    rois_to_labels,
)

__all__ = [
    "ROI",
    "RectangleROI",
    "EllipseROI",
    "PolygonROI",
    "MaskROI",
    "ThresholdROI",
    "CompositeROI",
    "roi_from_dict",
    "labels_to_rois",
    "rois_to_labels",
]
