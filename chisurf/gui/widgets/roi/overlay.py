"""Draw a region collection on a chiplot canvas, and let the user drag it.

The other half of the shared region GUI. :class:`RegionOverlay` binds a
:class:`~chisurf.core.roi.collection.RegionCollection` to a chiplot
:class:`~chisurf.gui.chiplot.canvas.ImageView` (or any plot exposing
``add_roi``): every region becomes a draggable handle, and every drag writes the
new geometry back into the region — so what the list says and what the picture
shows cannot drift apart.

This is where the survey's most conspicuous gap closes. ``PolygonROI`` and
``EllipseROI`` have been in the core all along with **no producer anywhere in
the GUI**: a user could load a polygon from a file but not draw one, and the
phasor cursor's ellipse existed only in the API. Both are drawable here.

Coordinates are the canvas's own — image pixels for a frame, data values for a
scatter plane or a 2-D histogram. A region carries no axes, which is exactly
what lets the same overlay serve an image and an ``E``–``S`` histogram.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import numpy as np

from chisurf.core.roi import EllipseROI, PolygonROI, RectangleROI, RegionCollection

#: Outline colours cycled over the regions, so two neighbours are told apart.
PALETTE = ("#4dd0e1", "#ffb74d", "#81c784", "#e57373", "#ba68c8", "#fff176")

#: Outline of a region that is switched off — present, not contributing.
DISABLED_PEN = "#9e9e9e"


def roi_from_handle(handle: Any, template: Any) -> Any:
    """Return the region a dragged handle now describes.

    The handle only knows a box or a vertex list; which region type to rebuild
    comes from what was there before, so dragging an ellipse does not silently
    turn it into a rectangle.

    Parameters
    ----------
    handle : chisurf.gui.chiplot.handles.Roi
        The dragged shape.
    template : ROI
        The region this handle stands for; its type and name are kept.

    Returns
    -------
    ROI
        A region of the same type with the handle's geometry.
    """
    name = getattr(template, "name", "")
    if isinstance(template, PolygonROI):
        return PolygonROI(handle.points, name=name)
    x, y = handle.pos
    w, h = handle.size
    if isinstance(template, EllipseROI):
        return EllipseROI(x + w / 2.0, y + h / 2.0, w / 2.0, h / 2.0, name=name)
    return RectangleROI(x, y, x + w, y + h, name=name)


def _handle_spec(roi: Any) -> Optional[Dict[str, Any]]:
    """Return the ``add_roi`` arguments drawing *roi*, or ``None`` if undrawable.

    A painted mask, a threshold or a composite has no handle: there is no small
    set of grips that would edit it, and faking one — a bounding box that
    silently replaced the mask on the first drag — would destroy the region the
    user painted.
    """
    if isinstance(roi, RectangleROI):
        return {
            "kind": "rect",
            "pos": (roi.x0, roi.y0),
            "size": (roi.x1 - roi.x0, roi.y1 - roi.y0),
        }
    if isinstance(roi, EllipseROI):
        return {
            "kind": "ellipse",
            "pos": (roi.cx - roi.rx, roi.cy - roi.ry),
            "size": (2.0 * roi.rx, 2.0 * roi.ry),
        }
    if isinstance(roi, PolygonROI):
        return {"kind": "polygon", "points": [tuple(v) for v in roi.vertices]}
    return None


class RegionOverlay:
    """Keep a canvas showing what a region collection contains.

    Parameters
    ----------
    canvas : chisurf.gui.chiplot.canvas.ImageView
        Anything with ``add_roi``. Held as-is; the overlay does not own it.
    collection_getter : callable
        Returns the current :class:`RegionCollection`. A callable rather than
        the collection itself because a host may swap collections (a new file, a
        different channel) without rebuilding the overlay.
    on_change : callable, optional
        Called with no arguments after a drag has been written back, so the host
        can recompute and refresh the list.
    live : bool, optional
        Write back continuously while dragging rather than on release. Off by
        default: the write-back re-measures every region, and doing that on
        every mouse-move event is what makes an interactive gate feel heavy.

    Examples
    --------
    >>> overlay = RegionOverlay(image_view, lambda: model.regions)  # doctest: +SKIP
    >>> overlay.refresh()                                           # doctest: +SKIP
    """

    def __init__(
        self,
        canvas: Any,
        collection_getter: Callable[[], RegionCollection],
        *,
        on_change: Optional[Callable[[], None]] = None,
        live: bool = False,
    ) -> None:
        """Bind the overlay to a canvas and a collection."""
        self._canvas = canvas
        self._get = collection_getter
        self._on_change = on_change
        self._live = bool(live)
        self._handles: List[Any] = []
        self._names: List[str] = []
        self._syncing = False

    @property
    def collection(self) -> RegionCollection:
        """The collection currently drawn."""
        return self._get()

    def clear(self) -> None:
        """Remove every drawn handle from the canvas."""
        for handle in self._handles:
            try:
                handle.remove()
            except Exception:  # noqa: BLE001 - a canvas may have gone already
                pass
        self._handles.clear()
        self._names.clear()

    def refresh(self) -> None:
        """Redraw every region.

        Cheap enough to call on any change: a collection holds a handful of
        regions, and rebuilding is what keeps a renamed, reordered or removed
        region from leaving a stale handle behind.
        """
        if self._syncing:
            return
        self.clear()
        for index, entry in enumerate(self.collection):
            spec = _handle_spec(entry.roi)
            if spec is None:
                continue
            pen = PALETTE[index % len(PALETTE)] if entry.enabled else DISABLED_PEN
            handle = self._canvas.add_roi(pen=pen, **spec)
            handle.on_change(
                lambda h=handle, n=entry.name: self._write_back(h, n), final=not self._live
            )
            self._handles.append(handle)
            self._names.append(entry.name)

    def _write_back(self, handle: Any, name: str) -> None:
        """Store a dragged handle's geometry back into its region.

        A no-op change is dropped rather than reported. pyqtgraph emits the
        change signal for *programmatic* moves too, so placing a handle fires it
        once per call; re-measuring every region and telling the host each time
        makes an interactive drag feel heavy for no result.
        """
        entry = self.collection.get(name)
        if entry is None:
            return
        updated = roi_from_handle(handle, entry.roi)
        if updated.to_dict() == entry.roi.to_dict():
            return
        self._syncing = True
        try:
            entry.roi = updated
        finally:
            self._syncing = False
        if self._on_change is not None:
            self._on_change()

    def select(self, name: str) -> None:
        """Emphasise one region's outline, so the list and the picture agree."""
        for handle, drawn in zip(self._handles, self._names):
            entry = self.collection.get(drawn)
            base = DISABLED_PEN if (entry is not None and not entry.enabled) else None
            index = self._names.index(drawn)
            colour = base or PALETTE[index % len(PALETTE)]
            width = 3 if drawn == name else 1
            setter = getattr(handle, "set_pen", None)
            if callable(setter):
                setter(colour, width=width)


__all__ = ["RegionOverlay", "roi_from_handle", "PALETTE"]
