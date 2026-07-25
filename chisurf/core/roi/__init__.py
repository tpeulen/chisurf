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

A third question follows once a region exists — **what is it?** — and
:mod:`chisurf.core.roi.props` answers it. :func:`regionprops` and
:func:`regionprops_table` deliberately mirror ``skimage.measure.regionprops``:
same call signature, same property names, same algorithms and therefore the
same numbers — extended to measure a bare mask or a drawn :class:`ROI` as
readily as a label image, and to hand the measured region back as a ROI.
"""

from __future__ import annotations

from .props import (
    INTENSITY_PROPERTIES,
    PROPERTIES,
    RegionProperties,
    regionprops,
    regionprops_table,
)
from .roi import (
    ROI,
    CompositeROI,
    EllipseROI,
    MaskROI,
    PolygonROI,
    RectangleROI,
    ThresholdROI,
    as_mask,
    as_roi,
    labels_to_rois,
    roi_from_dict,
    rois_to_labels,
    union_of,
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
    "as_roi",
    "as_mask",
    "union_of",
    # measurements of a region
    "RegionProperties",
    "regionprops",
    "regionprops_table",
    "PROPERTIES",
    "INTENSITY_PROPERTIES",
]
