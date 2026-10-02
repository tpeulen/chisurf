"""Native image/stack canvas shared by bead and spot inspection tools."""

from __future__ import annotations

from typing import Callable

import numpy as np
from emtk import Texture, im, implot
from emtk.i18n import tr

from chisurf.plugins.calculator.inputs import bounded_float, bounded_int


class ImageCanvas:
    """Image pixels in x/y coordinates; row zero remains at the top."""

    def __init__(self, key="image", *, image_label="Intensity", image_unit=""):
        self.key = key
        self.image_label = str(image_label)
        self.image_unit = str(image_unit)
        self.z = 0
        self.colormap = "magma"
        self.gamma = 1.0
        self.auto_levels = True
        self.low = 0.0
        self.high = 1.0
        self.rect = None
        self._cache_key = None
        self._texture = None
        self._reset_axes = True
        self.pick_pixels = None
        self._selection_texture = None
        self._selection_key = None

    def reset(self):
        self.z = 0
        self._reset_axes = True
        self._cache_key = None

    def pick(self, x, y, shape, callback):
        """Resolve a pixel-centred click to the image's exact (z,y,x) contract."""
        if not np.isfinite([x, y]).all():
            return False
        ny, nx = shape[-2:]
        if not (-0.5 <= x < nx - 0.5 and -0.5 <= y < ny - 0.5):
            return False
        callback((self.z, int(np.clip(round(y), 0, ny - 1)), int(np.clip(round(x), 0, nx - 1))))
        return True

    def texture(self, array):
        source = np.asarray(array)
        plane = source[self.z] if source.ndim == 3 else source
        key = (
            source.__array_interface__["data"][0],
            source.shape,
            self.z,
            self.colormap,
            self.gamma,
            self.auto_levels,
            self.low,
            self.high,
        )
        if key != self._cache_key:
            finite = plane[np.isfinite(plane)]
            low, high = (
                (float(finite.min()), float(finite.max()))
                if self.auto_levels and finite.size
                else (self.low, self.high)
            )
            high = max(high, low + 1e-12)
            scaled = np.clip(
                np.nan_to_num((plane - low) / (high - low), nan=0.0, posinf=1.0, neginf=0.0),
                0.0,
                1.0,
            ) ** (1.0 / self.gamma)
            from matplotlib import colormaps

            rgba = (colormaps[self.colormap](scaled) * 255).astype(np.uint8)
            self._texture = Texture(
                plane.shape[1], plane.shape[0], rgba.tobytes(), filter="nearest"
            )
            self._cache_key = key
        return self._texture

    @staticmethod
    def outline(roi):
        from chisurf.core.roi import EllipseROI, PolygonROI, RectangleROI

        if isinstance(roi, RectangleROI):
            return np.asarray(
                [
                    (roi.x0, roi.y0),
                    (roi.x1, roi.y0),
                    (roi.x1, roi.y1),
                    (roi.x0, roi.y1),
                    (roi.x0, roi.y0),
                ]
            )
        if isinstance(roi, EllipseROI):
            phi = np.linspace(0, 2 * np.pi, 65)
            x, y = roi.rx * np.cos(phi), roi.ry * np.sin(phi)
            return np.column_stack(
                [
                    roi.cx + np.cos(roi.angle) * x - np.sin(roi.angle) * y,
                    roi.cy + np.sin(roi.angle) * x + np.cos(roi.angle) * y,
                ]
            )
        if isinstance(roi, PolygonROI):
            return np.vstack([roi.vertices, roi.vertices[:1]])
        return None

    def draw(
        self,
        array,
        *,
        markers=(),
        found=(),
        picked=(),
        analysis=None,
        on_change=None,
        on_pick: Callable | None = None,
        fit_circle=None,
        pick_enabled=True,
        analysis_editable=True,
        height=-1,
        labels=(),
        selection=None,
        selection_version=0,
        on_brush=None,
    ):
        if array is None:
            im.text_unformatted("Load an image or run Preview to inspect pixels.")
            return
        source = np.asarray(array)
        if source.ndim not in (2, 3) or not all(source.shape):
            im.text_unformatted("Expected a non-empty image or stack.")
            return
        im.push_id(self.key)
        legend_label = tr(self.image_label)
        if self.image_unit:
            legend_label = f"{legend_label} ({self.image_unit})"
        if source.ndim == 3:
            self.z = int(np.clip(self.z, 0, source.shape[0] - 1))
            _, self.z = bounded_int("Z slice", self.z, minimum=0, maximum=source.shape[0] - 1)
            im.set_item_tooltip(
                "Browse the axial stack; image picks and bead overlays refer to this slice."
            )
        maps = ["magma", "inferno", "viridis", "gray"]
        im.text_unformatted("Colormap")
        _, index = im.combo(
            "##Colormap", maps.index(self.colormap) if self.colormap in maps else 0, maps
        )
        self.colormap = maps[index]
        im.set_item_tooltip(
            "Color scale of the image; pixel values and fits remain unchanged."
        )
        im.text_unformatted("Display gamma")
        _, self.gamma = bounded_float(
            "##Display gamma", self.gamma, minimum=0.1, maximum=5.0, step=0.1
        )
        im.set_item_tooltip(
            "Lift dim structures with gamma above one; display changes do not affect detection or fitting."
        )
        _, self.auto_levels = im.checkbox("Automatic levels", self.auto_levels)
        im.set_item_tooltip("Map the minimum and maximum finite image values to the color range.")
        if not self.auto_levels:
            _, self.low = im.input_float("Display minimum", self.low, step=1.0)
            im.set_item_tooltip("Set the lower display level without changing stored pixel values.")
            _, self.high = im.input_float("Display maximum", self.high, step=1.0)
            im.set_item_tooltip("Set the upper display level without changing stored pixel values.")
        if im.button("Reset view"):
            self._reset_axes = True
        im.set_item_tooltip("Restore the full-image view after zooming or panning.")
        texture = self.texture(source)
        ny, nx = source.shape[-2:]
        available = im.get_content_region_avail()
        plot_width = max(100.0, available[0] - 80.0)
        plot_height = max(100.0, (available[1] if height < 0 else height) - 60.0)
        span_x = 1.08 * max(nx, ny * plot_width / plot_height)
        span_y = span_x * plot_height / plot_width
        center_x, center_y = (nx - 1.0) / 2.0, (ny - 1.0) / 2.0
        input_map = implot.get_input_map()
        previous_pan, previous_fit = input_map.pan, input_map.fit
        if on_brush is not None:
            input_map.pan, input_map.fit = 2, 2
        plot_flags = implot.FLAGS_EQUAL | (implot.FLAGS_NO_LEGEND if labels else 0)
        try:
            if implot.begin_plot("##" + self.key, (-1, height), plot_flags):
                implot.setup_axes(tr("x [px]"), tr("y [px]"), y_flags=implot.AXIS_FLAGS_INVERT)
                limits = (
                    center_x - span_x / 2.0,
                    center_x + span_x / 2.0,
                    center_y - span_y / 2.0,
                    center_y + span_y / 2.0,
                )
                if self._reset_axes:
                    implot.setup_axes_limits(*limits, implot.COND_ALWAYS)
                # Release forced range locks before equal-aspect setup adjusts the
                # exact pixel scale for the measured label/axis margins.
                implot.setup_axes_limits(*limits, implot.COND_ONCE)
                self._reset_axes = False
                # An inverted y axis swaps PlotImage's vertical corners. Invert UVs
                # explicitly so row zero is still the top, matching click coordinates.
                implot.plot_image(
                    legend_label, texture, (-0.5, -0.5), (nx - 0.5, ny - 0.5), uv0=(0, 1), uv1=(1, 0)
                )
                if selection is not None:
                    mask = np.asarray(selection) > 0
                    key = (id(selection), mask.shape, selection_version)
                    if key != self._selection_key:
                        rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
                        rgba[mask] = [60, 200, 255, 100]
                        self._selection_texture = Texture(
                            mask.shape[1], mask.shape[0], rgba.tobytes(), filter="nearest"
                        )
                        self._selection_key = key
                    implot.plot_image(
                    tr("Selection"),
                        self._selection_texture,
                        (-0.5, -0.5),
                        (nx - 0.5, ny - 0.5),
                        uv0=(0, 1),
                        uv1=(1, 0),
                    )
                for label in labels:
                    text = str(label["text"])
                    implot.plot_text(
                        text,
                        float(label["x"]),
                        float(label["y"]),
                        pix_offset=(im.calc_text_size(text)[0] / 2, 0),
                    )
                origin = implot.plot_to_pixels(0.0, 0.0)
                unit = implot.plot_to_pixels(1.0, 1.0)
                self.pick_pixels = lambda x, y: (
                    origin[0] + float(x) * (unit[0] - origin[0]),
                    origin[1] + float(y) * (unit[1] - origin[1]),
                )
                points = [(x, y) for z, y, x in markers if source.ndim == 2 or int(z) == self.z]
                if points:
                    implot.set_next_marker_style(implot.MARKER_SQUARE, 5.0, (50, 230, 90, 255))
                    implot.plot_scatter(
                        tr("Detected/selected"), *[np.asarray(points)[:, i] for i in (0, 1)]
                    )
                for label, collection, color in [
                    ("Found", found, (60, 220, 100, 255)),
                    ("Picked", picked, (255, 130, 50, 255)),
                ]:
                    for i, entry in enumerate(collection):
                        roi = getattr(entry, "roi", entry)
                        points = self.outline(roi)
                        if points is not None:
                            implot.set_next_line_style(color, 1.5)
                            implot.plot_line(f"{tr(label)} {i + 1}", points[:, 0], points[:, 1])
                if fit_circle and int(fit_circle["z"]) == self.z:
                    phi = np.linspace(0, 2 * np.pi, 65)
                    implot.set_next_line_style((255, 225, 50, 255), 2.0)
                    implot.plot_line(
                        tr("Fitted FWHM"),
                        fit_circle["x"] + fit_circle["r"] * np.cos(phi),
                        fit_circle["y"] + fit_circle["r"] * np.sin(phi),
                    )
                used_roi_handle = False
                if analysis is not None:
                    from chisurf.core.roi import EllipseROI, PolygonROI, RectangleROI

                    for i, entry in enumerate(analysis):
                        if not entry.enabled:
                            continue
                        roi = entry.roi
                        points = self.outline(roi)
                        if points is not None:
                            implot.set_next_line_style((90, 180, 255, 255), 2.0)
                            implot.plot_line(f"{tr('Analysis')} {entry.name}", points[:, 0], points[:, 1])
                        if not analysis_editable:
                            continue
                        if isinstance(roi, RectangleROI):
                            result = implot.drag_rect(
                                1000 + i, roi.x0, roi.y0, roi.x1, roi.y1, (90, 180, 255, 255)
                            )
                            used_roi_handle |= bool(result.clicked or result.held)
                            if result.hovered:
                                im.set_tooltip(
                                    "Drag the region center, corner or edge to move/resize its pixel bounds."
                                )
                            if result.modified:
                                entry.roi = RectangleROI(
                                    result.x_min,
                                    result.y_min,
                                    result.x_max,
                                    result.y_max,
                                    name=roi.name,
                                )
                                if callable(on_change):
                                    on_change()
                        elif isinstance(roi, EllipseROI):
                            result = implot.drag_point(
                                1000 + i, roi.cx, roi.cy, (90, 180, 255, 255), 5
                            )
                            used_roi_handle |= bool(result.clicked or result.held)
                            if result.hovered:
                                im.set_tooltip("Drag to move the ellipse center in image pixels.")
                            if result.modified:
                                roi.cx, roi.cy = result.x, result.y
                                if callable(on_change):
                                    on_change()
                            cos, sin = np.cos(roi.angle), np.sin(roi.angle)
                            for axis, (x, y) in enumerate(
                                [
                                    (roi.cx + roi.rx * cos, roi.cy + roi.rx * sin),
                                    (roi.cx - roi.ry * sin, roi.cy + roi.ry * cos),
                                ]
                            ):
                                result = implot.drag_point(
                                    20000 + i * 10 + axis,
                                    float(x),
                                    float(y),
                                    (90, 180, 255, 255),
                                    4,
                                )
                                used_roi_handle |= bool(result.clicked or result.held)
                                if result.hovered:
                                    im.set_tooltip(
                                        "Drag to resize this ellipse radius; the angle and other radius remain unchanged."
                                    )
                                if result.modified:
                                    dx, dy = result.x - roi.cx, result.y - roi.cy
                                    if axis == 0:
                                        roi.rx = max(0.01, abs(dx * cos + dy * sin))
                                    else:
                                        roi.ry = max(0.01, abs(-dx * sin + dy * cos))
                                    if callable(on_change):
                                        on_change()
                            radius = max(roi.rx, roi.ry) * 1.4
                            result = implot.drag_point(
                                20000 + i * 10 + 2,
                                roi.cx + radius * cos,
                                roi.cy + radius * sin,
                                (180, 220, 255, 255),
                                4,
                            )
                            used_roi_handle |= bool(result.clicked or result.held)
                            if result.hovered:
                                im.set_tooltip(
                                    "Drag the outer handle to rotate the analysis ellipse."
                                )
                            if result.modified:
                                roi.angle = float(np.arctan2(result.y - roi.cy, result.x - roi.cx))
                                if callable(on_change):
                                    on_change()
                        elif isinstance(roi, PolygonROI):
                            for j, (x, y) in enumerate(roi.vertices):
                                result = implot.drag_point(
                                    100000 + i * 1000 + j,
                                    float(x),
                                    float(y),
                                    (90, 180, 255, 255),
                                    4,
                                )
                                used_roi_handle |= bool(result.clicked or result.held)
                                if result.hovered:
                                    im.set_tooltip(
                                        "Drag to reshape this polygon vertex in image coordinates."
                                    )
                                if result.modified:
                                    roi.vertices[j] = [result.x, result.y]
                                    if callable(on_change):
                                        on_change()
                if (
                    on_brush is not None
                    and not used_roi_handle
                    and pick_enabled
                    and implot.is_plot_hovered()
                    and im.is_mouse_down(0)
                ):
                    position = implot.get_plot_mouse_pos()
                    self.pick(position.x, position.y, source.shape, on_brush)
                if (
                    on_pick is not None
                    and pick_enabled
                    and not used_roi_handle
                    and implot.is_plot_hovered()
                    and im.is_mouse_clicked(0)
                ):
                    position = implot.get_plot_mouse_pos()
                    self.pick(position.x, position.y, source.shape, on_pick)
                pos, size = implot.get_plot_pos(), implot.get_plot_size()
                self.rect = (*pos, *size)
                implot.end_plot()
                im.set_item_tooltip(
                    "Click a bead/spot to fit it. Drag to pan, scroll to zoom; blue handles edit analysis regions. Found and picked outlines are measured results."
                )
        finally:
            input_map.pan, input_map.fit = previous_pan, previous_fit
            im.pop_id()
