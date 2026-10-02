"""Native named ROI controls retaining shared geometry and persistence contracts."""

from __future__ import annotations

import copy

import numpy as np
from emtk import im

from chisurf.core.roi import (
    COMBINE_OPS,
    EllipseROI,
    PolygonROI,
    RectangleROI,
    RegionCollection,
    regionprops,
)
from chisurf.plugins.calculator.inputs import bounded_float


class RegionControls:
    def __init__(self, model, choose, on_change=None, get_image=None):
        self.model = model
        self.on_change = on_change
        self.get_image = get_image
        self.choose = choose
        self.selected = ""
        self.error = ""

    def image(self):
        if self.get_image is not None:
            return self.get_image()
        method = getattr(self.model, "detection_image", None)
        return method() if callable(method) else getattr(self.model, "current_image", None)

    def changed(self):
        if self.on_change is not None:
            self.on_change()
        else:
            self.model.apply_regions()

    def add_shape(self, kind):
        image = self.image()
        ny, nx = image.shape[-2:] if image is not None else (64, 64)
        cx, cy = nx / 2.0, ny / 2.0
        rx, ry = nx / 4.0, ny / 4.0
        if kind == "ellipse":
            roi = EllipseROI(cx, cy, rx, ry, name="Ellipse")
        elif kind == "polygon":
            roi = PolygonROI(
                np.array([[cx - rx, cy + ry], [cx, cy - ry], [cx + rx, cy + ry]]), name="Polygon"
            )
        else:
            roi = RectangleROI(cx - rx, cy - ry, cx + rx, cy + ry, name="Rectangle")
        self.selected = self.model.regions.add(roi)
        self.changed()
        return self.selected

    def duplicate(self):
        entry = self.model.regions.get(self.selected)
        if entry:
            self.selected = self.model.regions.add(copy.deepcopy(entry), name=entry.name + " copy")
            self.changed()

    def save(self, path):
        from pathlib import Path

        path = Path(path)
        if path.suffix.lower() not in (".json", ".tif", ".tiff", ".npy"):
            path = path.with_suffix(".json")
        if path.suffix.lower() == ".json":
            self.model.regions.save(str(path))
        else:
            from chisurf.core.roi.io import save_label_image

            image = self.image()
            if image is None:
                raise ValueError("Display an image before exporting a raster mask.")
            save_label_image(
                [entry.roi for entry in self.model.regions],
                image.shape[-2:],
                str(path),
                image=image,
            )

    def load(self, path):
        loaded = RegionCollection.load(str(path))
        for entry in loaded:
            self.model.regions.add(entry.roi, enabled=entry.enabled, invert=entry.invert)
        self.changed()

    def draw(self):
        m = self.model
        expanded = im.collapsing_header("Analysis regions", 0)
        im.set_item_tooltip(
            "Restrict detection to named regions; empty or disabled regions use the entire frame."
        )
        if not expanded:
            return
        for kind in ("rectangle", "ellipse", "polygon"):
            if im.button("Add " + kind):
                self.add_shape(kind)
            im.set_item_tooltip(f"Add an editable {kind} in the center of the displayed image.")
        collection = m.regions
        changed, index = im.combo(
            "Combine regions", COMBINE_OPS.index(collection.combine), list(COMBINE_OPS)
        )
        im.set_item_tooltip(
            "AND intersects, OR unions and XOR keeps pixels included by an odd number of enabled regions."
        )
        if changed:
            collection.combine = COMBINE_OPS[index]
            self.changed()
        for entry in list(collection):
            name = entry.name
            im.push_id(name)
            if im.selectable(name, self.selected == name):
                self.selected = name
            im.set_item_tooltip(
                "Select this analysis region for renaming, geometry edits, duplication or removal."
            )
            changed, value = im.checkbox("Enabled", entry.enabled)
            im.set_item_tooltip(
                "Include this region in detection; disabled entries remain available for later use."
            )
            if changed:
                entry.enabled = value
                self.changed()
            im.same_line()
            changed, value = im.checkbox("Invert", entry.invert)
            im.set_item_tooltip("Use pixels outside this region instead of inside it.")
            if changed:
                entry.invert = value
                self.changed()
            im.pop_id()
        entry = collection.get(self.selected)
        if entry:
            changed, value = im.input_text("Region name", entry.name)
            im.set_item_tooltip(
                "Name the selected region; names are kept unique when saved and restored."
            )
            if changed and value.strip():
                self.selected = collection.rename(self.selected, value)
                self.changed()
            roi = entry.roi
            parameters = []
            if isinstance(roi, RectangleROI):
                parameters = [("x0", "Left"), ("y0", "Top"), ("x1", "Right"), ("y1", "Bottom")]
            elif isinstance(roi, EllipseROI):
                parameters = [
                    ("cx", "Center x"),
                    ("cy", "Center y"),
                    ("rx", "Radius x"),
                    ("ry", "Radius y"),
                    ("angle", "Angle [rad]"),
                ]
            for attr, label in parameters:
                changed, value = bounded_float(
                    label,
                    float(getattr(roi, attr)),
                    minimum=0.01 if attr in ("rx", "ry") else -1e6,
                    maximum=1e6,
                    step=0.5,
                )
                im.set_item_tooltip(
                    "Geometric coordinate in image pixels; ellipse rotation is in radians."
                )
                if changed:
                    setattr(roi, attr, value)
                    self.changed()
            if isinstance(roi, PolygonROI):
                for i, (x, y) in enumerate(roi.vertices):
                    im.push_id(i)
                    changed, newx = im.input_float("Vertex x", float(x), step=0.5)
                    im.set_item_tooltip("Horizontal image coordinate of this polygon vertex.")
                    changed_y, newy = im.input_float("Vertex y", float(y), step=0.5)
                    im.set_item_tooltip("Vertical image coordinate of this polygon vertex.")
                    if changed or changed_y:
                        roi.vertices[i] = [newx, newy]
                        self.changed()
                    im.pop_id()
            image = self.image()
            if image is not None:
                props = regionprops(roi.to_mask(image.shape[-2:], image=image), image)
                if props:
                    im.text_unformatted(
                        f"{props[0].area} px; mean intensity {props[0].intensity_mean:.3g}"
                    )
            if im.button("Duplicate region"):
                self.duplicate()
            im.set_item_tooltip("Copy the selected region including its enabled/inverted state.")
            if im.button("Remove region"):
                collection.remove(self.selected)
                self.selected = ""
                self.changed()
            im.set_item_tooltip("Delete the selected analysis region from the collection.")
        if im.button("Save regions"):
            self.choose("save_regions")
        im.set_item_tooltip(
            "Save all regions as JSON with flags, or export their raster labels as TIFF/NumPy."
        )
        if im.button("Load regions"):
            self.choose("load_regions")
        im.set_item_tooltip(
            "Append regions from JSON, masks, label images or Cellpose segmentation files."
        )
