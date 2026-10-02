"""A parameter plane with editable regions: the phasor plot with its cursors, the N&B plane with its gates, the colocalization scatter with its gate.

``PlanePanel`` draws a 2-D histogram on measured axes (an image texture inside an implot plot) with the regions of a
:class:`~chisurf.core.roi.RegionCollection` over it: a rectangle is dragged by its corners, an ellipse by its centre and axis handles, a
polygon by its vertices, every edit is reported through ``on_change``. ``PlaneRegions`` is the region list beside it: the shared
:class:`chisurf.emtk.regions.RegionControls` (add rectangle / ellipse / polygon, combine rule, enabled / invert / rename / geometry /
duplicate / remove, save / load) with new shapes placed in the plane's units.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np
from emtk import im, implot

from chisurf.core.roi import EllipseROI, PolygonROI, RectangleROI
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.emtk.regions import RegionControls

from .views import muted


class PlaneRegions(RegionControls):
    """The shared region list, with new geometry in the units of the plane the regions live on."""

    def __init__(self, collection: Callable[[], Any], extent: Callable[[], tuple], choose: Callable[[str], None],
                 on_change: Callable[[], None]) -> None:
        self._collection, self._extent = collection, extent
        super().__init__(SimpleNamespace(regions=collection()), choose, on_change=on_change, get_image=lambda: None)

    @property
    def regions(self) -> Any:
        self.model.regions = self._collection()
        return self.model.regions

    def add_shape(self, kind: str) -> str:
        x0, x1, y0, y1 = self._extent()
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 4, (y1 - y0) / 4
        if kind == "ellipse":
            roi = EllipseROI(cx, cy, rx, ry, name="Ellipse")
        elif kind == "polygon":
            roi = PolygonROI(np.array([[cx - rx, cy + ry], [cx, cy - ry], [cx + rx, cy + ry]]), name="Polygon")
        else:
            roi = RectangleROI(cx - rx, cy - ry, cx + rx, cy + ry, name="Rectangle")
        self.model.regions = self._collection()
        self.selected = self.model.regions.add(roi)
        self.changed()
        return self.selected

    def draw(self) -> None:  # noqa: D102 - the shared list
        self.model.regions = self._collection()
        super().draw()

    def duplicate(self) -> None:
        self.model.regions = self._collection()
        super().duplicate()


class PlanePanel:
    """A histogram on measured axes with draggable regions over it."""

    def __init__(self, key: str, *, collection: Callable[[], Any], image: Callable[[], Any], extent: Callable[[], tuple],
                 x_label: str, y_label: str, on_change: Callable[[], None], overlay: Callable[[], list] | None = None,
                 empty: str = "Nothing to show yet.", tooltip: str = "") -> None:
        self.key = key
        self.collection, self.image, self.extent = collection, image, extent
        self.x_label, self.y_label, self.on_change = x_label, y_label, on_change  # str or callable returning str
        self.overlay, self.empty, self.tooltip = overlay, empty, tooltip
        self.canvas = ImageCanvas(key)
        self.rect: tuple = (0.0, 0.0, 0.0, 0.0)
        self.hover = ""
        self._fit = ""

    def draw(self, colormap: str | None = None) -> None:
        array = self.image()
        if array is None:
            muted(self.empty)
            return
        maps = ["magma", "inferno", "viridis", "gray"]
        if colormap in maps:
            self.canvas.colormap = colormap
        im.text_unformatted("Colormap")
        _, index = im.combo(f"##{self.key}_colormap", maps.index(self.canvas.colormap), maps)
        self.canvas.colormap = maps[index]
        im.set_item_tooltip("Color scale of the density; the counts themselves are unchanged.")
        x0, x1, y0, y1 = self.extent()
        fingerprint = (round(x0, 6), round(x1, 6), round(y0, 6), round(y1, 6))
        if fingerprint != self._fit:
            self._fit = fingerprint
            implot.set_next_axes_to_fit()
        flags = implot.FLAGS_NO_LEGEND
        height = max(160.0, im.get_content_region_avail()[1] - 6.0)
        if implot.begin_plot(f"##{self.key}", (-1.0, height), flags):
            implot.setup_axes(self.x_label() if callable(self.x_label) else self.x_label, self.y_label() if callable(self.y_label) else self.y_label)
            implot.setup_axes_limits(x0, x1, y0, y1, implot.COND_ONCE)
            implot.plot_image("##histogram", self.canvas.texture(np.asarray(array, dtype=float)), (x0, y0), (x1, y1))
            for i, line in enumerate(self.overlay() if self.overlay else []):
                implot.set_next_line_style(line.get("color", (230, 230, 230, 255)), 1.5)
                implot.plot_line(f"##overlay{i}", np.asarray(line["x"], dtype=float), np.asarray(line["y"], dtype=float))
            self._regions()
            self.rect = (*implot.get_plot_pos(), *implot.get_plot_size())
            implot.end_plot()
        if self.tooltip:
            im.set_item_tooltip(self.tooltip)

    def _regions(self) -> None:
        for i, entry in enumerate(self.collection()):
            if not entry.enabled:
                continue
            roi = entry.roi
            points = self.canvas.outline(roi)
            if points is not None:
                implot.set_next_line_style((60, 200, 255, 255), 2.0)
                implot.plot_line(f"{entry.name}##region{i}", points[:, 0], points[:, 1])
            if isinstance(roi, RectangleROI):
                result = implot.drag_rect(i * 100, roi.x0, roi.y0, roi.x1, roi.y1)
                if result.modified:
                    roi.x0, roi.y0, roi.x1, roi.y1 = result.x_min, result.y_min, result.x_max, result.y_max
                    self.on_change()
            elif isinstance(roi, EllipseROI):
                centre = implot.drag_point(i * 100, roi.cx, roi.cy)
                if centre.modified:
                    roi.cx, roi.cy = centre.x, centre.y
                    self.on_change()
                for slot, attr, angle in ((1, "rx", roi.angle), (2, "ry", roi.angle + np.pi / 2)):
                    radius = getattr(roi, attr)
                    handle = implot.drag_point(i * 100 + slot, roi.cx + radius * np.cos(angle), roi.cy + radius * np.sin(angle))
                    if handle.modified:
                        setattr(roi, attr, float(np.hypot(handle.x - roi.cx, handle.y - roi.cy)))
                        if attr == "rx":
                            roi.angle = float(np.arctan2(handle.y - roi.cy, handle.x - roi.cx))
                        self.on_change()
            elif isinstance(roi, PolygonROI):
                for vertex, (x, y) in enumerate(roi.vertices):
                    handle = implot.drag_point(i * 100 + vertex, float(x), float(y))
                    if handle.modified:
                        roi.vertices[vertex] = [handle.x, handle.y]
                        self.on_change()


def semicircle(n: int = 120) -> dict:
    """The universal semicircle of the phasor plane: ``g = 1/2 (1 + cos t)``, ``s = 1/2 sin t``."""
    t = np.linspace(0.0, np.pi, n)
    return {"x": 0.5 * (1.0 + np.cos(t)), "y": 0.5 * np.sin(t), "color": (230, 230, 120, 255)}


def copy_collection(collection: Any) -> Any:
    """A deep copy of a region collection (a snapshot worker must not share the one being edited)."""
    return copy.deepcopy(collection)
