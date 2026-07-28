"""The shared region editor — one list of regions, used by every tool.

Before this widget, every tool that let a user work with more than one region
grew its own list, and they disagreed about what a list of regions even is: the
CLSM tool had names, save/load and measurements but no way to combine two
regions; ndX had per-row *enabled* and *invert* and combined by implicit
AND, but lost every non-rectangle selection when reloading; the MLE tools took
several regions from a file and silently unioned them, with nothing on screen to
say so. Most tools had no list at all — one anonymous region, or a file picker.

:class:`RegionEditor` is that list. It edits a
:class:`~chisurf.core.roi.collection.RegionCollection`, which is Qt-free, so the
same object drives a headless script, an RPC payload and this widget.

Two halves, deliberately separable:

* **the list** — this widget: name, shape, measurement, on/off, invert, the
  combining rule, save/load. It needs no canvas and is useful on its own (a
  region loaded from a file still wants naming and measuring);
* **the overlay** — :class:`~chisurf.gui.widgets.roi.overlay.RegionOverlay`:
  draws the collection on a chiplot canvas and lets the user drag the shapes.

A host that has a canvas attaches both and they stay in step through the
collection they share.

The list is a ``QTreeWidget`` rather than a ``ChiTable``: it is a handful of
rows of *widget state* with checkboxes and in-place renaming, not a view over a
dataset, and the table framework's source adapters buy nothing here.
"""

from __future__ import annotations

import pathlib
from typing import Any, Callable, Optional

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf.core.roi import COMBINE_OPS, RegionCollection

#: Item role carrying a row's region name, so the visible text can also show the
#: shape and the measurement without the name having to be parsed back out.
_NAME_ROLE = QtCore.Qt.UserRole

#: Column layout of the list.
_COL_NAME, _COL_SHAPE, _COL_INFO, _COL_INVERT = range(4)

#: How each combining rule reads to a user. The key is the core's operation.
_COMBINE_LABELS = {
    "and": "∩  all of them",
    "or": "∪  any of them",
    "xor": "⊕  exactly one",
}

#: The shapes a user can create, and the glyph each gets on its button.
SHAPES = (
    ("rect", "▭", "Rectangle"),
    ("ellipse", "◯", "Ellipse"),
    ("polygon", "⬠", "Polygon"),
)


def _tool_button(text: str, tooltip: str, slot: Callable) -> QtWidgets.QToolButton:
    """Build a configured ``QToolButton`` in one call."""
    button = QtWidgets.QToolButton()
    button.setText(text)
    button.setToolTip(tooltip)
    button.clicked.connect(slot)
    return button


class RegionEditor(QtWidgets.QWidget):
    """Edit a named list of regions.

    Parameters
    ----------
    model : object
        The host view-model. It must expose the collection under *target*; when
        it also has ``add_observer`` the editor refreshes on the events named in
        the ``refresh_on`` option.
    target : str
        Attribute on *model* holding a
        :class:`~chisurf.core.roi.collection.RegionCollection`. If the attribute
        is absent or ``None`` an empty collection is created and stored back, so
        a host only has to declare the name.
    image_attr : str, optional
        Attribute (or zero-argument method) returning the image the regions are
        measured against. Without it the rows show the shape but no
        measurement — area and brightness are properties of a region *and an
        image*, and inventing a frame to measure in would be worse than saying
        nothing.
    extent_attr : str, optional
        Attribute or method returning ``(x0, x1, y0, y1)``: where a newly
        created region should be placed and how big it should start. Defaults to
        the image's shape, then to ``(0, 100, 0, 100)``.
    refresh_on : sequence of str, optional
        Observer events that should refresh the list.
    allow_shapes : bool, optional
        Whether the new-shape buttons are shown. A tool whose regions come only
        from painting or from files sets this ``False``.
    paint_source : str, optional
        Zero-argument method on *model* returning the region the user has just
        painted (or thresholded, or otherwise built outside the list), or
        ``None`` when there is nothing. Given one, the editor grows a ``+``
        button that captures it — which is how a brush-driven tool turns a
        transient selection into a named, saveable region.
    intensity_unit : str, optional
        Unit for the per-pixel mean in the measurement column, e.g. ``"ph"`` to
        read ``216 px, 41.8 ph/px``. Empty gives the bare rate.

    Attributes
    ----------
    changed : Signal
        Emitted whenever the collection is modified through the editor, so a
        host can recompute. Carries no payload: read the collection.
    selectionChanged : Signal
        Emitted with the selected region's name (empty when none).
    """

    changed = QtCore.Signal()
    selectionChanged = QtCore.Signal(str)

    #: Marker so a hosting dock panel gives this section the spare space.
    _autoform_expanding = True

    def __init__(
        self,
        model: Any,
        target: str = "regions",
        *,
        image_attr: str = "",
        extent_attr: str = "",
        refresh_on: tuple = ("roi", "region", "selection", "image"),
        allow_shapes: bool = True,
        paint_source: str = "",
        intensity_unit: str = "",
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Build the editor and bind it to the model's collection."""
        super().__init__(parent)
        self._model = model
        self._target = target
        self._image_attr = image_attr
        self._extent_attr = extent_attr
        self._paint_source = paint_source
        self._intensity_unit = str(intensity_unit)
        self._refresh_on = tuple(refresh_on)
        self._refreshing = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)

        layout.addLayout(self._build_toolbar(allow_shapes))
        layout.addWidget(self._build_tree())
        layout.addLayout(self._build_footer())

        add_observer = getattr(model, "add_observer", None)
        if callable(add_observer):
            add_observer(self._on_model_event)
        self.refresh()

    # ── construction ────────────────────────────────────────────────────────
    def _build_toolbar(self, allow_shapes: bool) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(2)
        if self._paint_source:
            self.name_edit = QtWidgets.QLineEdit()
            self.name_edit.setPlaceholderText("name")
            self.name_edit.setMaximumWidth(110)
            self.name_edit.setToolTip("Name for the region the + button captures")
            self.name_edit.returnPressed.connect(self.capture_painted)
            row.addWidget(self.name_edit)
            row.addWidget(
                _tool_button("+", "Keep the current selection as a named region",
                             self.capture_painted)
            )
            row.addSpacing(6)
        if allow_shapes:
            for kind, glyph, title in SHAPES:
                row.addWidget(
                    _tool_button(
                        glyph, f"Add a {title.lower()} region",
                        lambda _=False, k=kind: self.add_shape(k),
                    )
                )
            row.addSpacing(6)
        row.addWidget(_tool_button("🗑", "Remove the selected region", self.remove_selected))
        row.addWidget(_tool_button("⧉", "Duplicate the selected region", self.duplicate_selected))
        row.addStretch(1)
        row.addWidget(_tool_button("📂", "Load regions from a file", self.load))
        row.addWidget(_tool_button("💾", "Save all regions to a file", self.save))
        return row

    def _build_tree(self) -> QtWidgets.QTreeWidget:
        tree = QtWidgets.QTreeWidget()
        tree.setColumnCount(4)
        tree.setHeaderLabels(["Region", "Shape", "Measurement", "~"])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
        )
        tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        header = tree.header()
        header.setSectionResizeMode(_COL_NAME, QtWidgets.QHeaderView.Stretch)
        for column in (_COL_SHAPE, _COL_INFO, _COL_INVERT):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        tree.itemChanged.connect(self._on_item_changed)
        tree.currentItemChanged.connect(self._on_current_changed)
        tree.setToolTip(
            "Tick a region to include it, untick to keep it without using it. "
            "The ~ column contributes the region's complement. Double-click to rename."
        )
        self.tree = tree
        return tree

    def _build_footer(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)
        label = QtWidgets.QLabel("Combine")
        row.addWidget(label)
        combo = QtWidgets.QComboBox()
        for op in COMBINE_OPS:
            combo.addItem(_COMBINE_LABELS[op], op)
        combo.setToolTip(
            "How the ticked regions are reduced to the one selection the "
            "analysis uses: their intersection, their union, or the pixels in "
            "exactly one of them."
        )
        combo.currentIndexChanged.connect(self._on_combine_changed)
        self.combine_box = combo
        row.addWidget(combo, 1)
        self.summary_label = QtWidgets.QLabel("")
        self.summary_label.setToolTip("The combined selection these regions describe.")
        row.addWidget(self.summary_label)
        return row

    # ── the bound collection ────────────────────────────────────────────────
    @property
    def collection(self) -> RegionCollection:
        """The bound collection, created on the model if it was not there."""
        current = getattr(self._model, self._target, None)
        if not isinstance(current, RegionCollection):
            current = RegionCollection()
            setattr(self._model, self._target, current)
        return current

    def _image(self) -> Optional[np.ndarray]:
        """Return the image regions are measured against, if the host has one."""
        if not self._image_attr:
            return None
        value = getattr(self._model, self._image_attr, None)
        if callable(value):
            value = value()
        return None if value is None else np.asarray(value)

    def _extent(self) -> tuple:
        """Return ``(x0, x1, y0, y1)`` for placing a newly created region."""
        if self._extent_attr:
            value = getattr(self._model, self._extent_attr, None)
            if callable(value):
                value = value()
            if value is not None and len(value) == 4:
                return tuple(float(v) for v in value)
        image = self._image()
        if image is not None and image.ndim >= 2:
            return (0.0, float(image.shape[-1]), 0.0, float(image.shape[-2]))
        return (0.0, 100.0, 0.0, 100.0)

    # ── editing ─────────────────────────────────────────────────────────────
    def add_shape(self, kind: str) -> str:
        """Create a region of *kind*, centred in the current frame.

        A new region starts at a third of the frame so it is visible and
        grabbable straight away; dropping a zero-size shape at the origin makes
        the user hunt for a handle before they can do anything.
        """
        from chisurf.core.roi import EllipseROI, PolygonROI, RectangleROI

        x0, x1, y0, y1 = self._extent()
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        rx, ry = max((x1 - x0) / 6.0, 1.0), max((y1 - y0) / 6.0, 1.0)

        if kind == "ellipse":
            roi = EllipseROI(cx, cy, rx, ry, name="ellipse")
        elif kind == "polygon":
            roi = PolygonROI(
                [(cx - rx, cy - ry), (cx + rx, cy - ry), (cx, cy + ry)], name="polygon"
            )
        else:
            roi = RectangleROI(cx - rx, cy - ry, cx + rx, cy + ry, name="rectangle")

        name = self.collection.add(roi)
        self._emit()
        self.select(name)
        return name

    def capture_painted(self) -> str:
        """Turn the host's current transient selection into a named region.

        The brush, the threshold slider and the phasor cursor all produce a
        selection that exists only until the next stroke. This is the step that
        keeps one: it becomes a row like any other, measurable, invertible,
        combinable and saveable.
        """
        source = getattr(self._model, self._paint_source, None) if self._paint_source else None
        region = source() if callable(source) else source
        if region is None:
            self.summary_label.setText("nothing selected to keep")
            return ""
        edit = getattr(self, "name_edit", None)
        name = edit.text().strip() if edit is not None else ""
        stored = self.add_region(region, name=name or "region")
        if edit is not None:
            edit.clear()
        return stored

    def add_region(self, region: Any, name: str = "") -> str:
        """Add a region built elsewhere — a painted mask, a threshold, a fit."""
        stored = self.collection.add(region, name=name)
        self._emit()
        self.select(stored)
        return stored

    def selected_name(self) -> str:
        """Return the selected region's name, or an empty string."""
        item = self.tree.currentItem()
        return str(item.data(_COL_NAME, _NAME_ROLE)) if item else ""

    def select(self, name: str) -> None:
        """Make *name* the selected row, if it is present."""
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if str(item.data(_COL_NAME, _NAME_ROLE)) == name:
                self.tree.setCurrentItem(item)
                return

    def remove_selected(self) -> None:
        """Remove the selected region."""
        name = self.selected_name()
        if name and self.collection.remove(name):
            self._emit()

    def duplicate_selected(self) -> None:
        """Copy the selected region, so a variant can be tried without redrawing."""
        import copy

        name = self.selected_name()
        entry = self.collection.get(name) if name else None
        if entry is None:
            return
        clone = copy.deepcopy(entry.roi)
        self._emit_after(self.collection.add(clone, name=name))

    def _emit_after(self, name: str) -> None:
        self._emit()
        self.select(name)

    # ── persistence ─────────────────────────────────────────────────────────
    def _working_dir(self) -> str:
        filename = getattr(self._model, "filename", "")
        if filename:
            return str(pathlib.Path(str(filename)).parent)
        try:
            import chisurf as cs

            return str(cs.working_path)
        except Exception:
            return str(pathlib.Path.home())

    def save(self) -> None:
        """Write every region to one file, flags and combining rule included."""
        if not len(self.collection):
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save regions", self._working_dir(),
            "Regions (*.json);;Mask image (*.tif);;NumPy (*.npy)",
        )
        if not path:
            return
        if str(path).lower().endswith(".json"):
            self.collection.save(path)
            return
        # A raster export needs a frame to rasterise into; without an image
        # there is no shape to write, and silently writing an arbitrary one
        # would produce a mask that does not line up with anything.
        image = self._image()
        if image is None:
            self._report("Saving a mask image needs a displayed image; use .json instead.")
            return
        from chisurf.core.roi.io import save_label_image

        save_label_image(
            [e.roi for e in self.collection], image.shape[-2:], path, image=image
        )

    def load(self) -> None:
        """Add the regions in a file to the list.

        Adding rather than replacing: a file is one more source of regions, and
        a load that silently discarded what the user had drawn would be the
        expensive kind of surprise.
        """
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load regions", self._working_dir(),
            "Regions (*.json);;Segmentation (*_seg.npy);;Masks (*.tif *.tiff *.npy);;All files (*)",
        )
        if not path:
            return
        try:
            loaded = RegionCollection.load(path)
        except Exception as exc:  # noqa: BLE001 - shown, not swallowed
            self._report(f"Could not read regions: {exc}")
            return
        for entry in loaded:
            self.collection.add(entry.roi, enabled=entry.enabled, invert=entry.invert)
        self._emit()

    def _report(self, message: str) -> None:
        """Show a message without blocking a headless run."""
        self.summary_label.setText(message)
        from chisurf.gui.dialogs import report_warning

        report_warning(self, "Regions", message)

    # ── model / view sync ───────────────────────────────────────────────────
    def _emit(self) -> None:
        """Refresh the list and tell the host the collection changed."""
        self.refresh()
        self.changed.emit()

    def _on_model_event(self, event: str) -> None:
        if event in self._refresh_on:
            self.refresh()

    def _on_combine_changed(self, index: int) -> None:
        if self._refreshing:
            return
        self.collection.combine = self.combine_box.itemData(index)
        self._emit()

    def _on_current_changed(self, *_) -> None:
        self.selectionChanged.emit(self.selected_name())

    def _on_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """Apply a rename, an on/off tick or an invert tick back to the model."""
        if self._refreshing:
            return
        name = str(item.data(_COL_NAME, _NAME_ROLE))
        entry = self.collection.get(name)
        if entry is None:
            return
        if column == _COL_NAME:
            entry.enabled = item.checkState(_COL_NAME) == QtCore.Qt.Checked
            typed = item.text(_COL_NAME).strip()
            if typed and typed != name:
                name = self.collection.rename(name, typed)
        elif column == _COL_INVERT:
            entry.invert = item.checkState(_COL_INVERT) == QtCore.Qt.Checked
        self._emit()
        self.select(name)

    # ── rendering ───────────────────────────────────────────────────────────
    def _measurement(self, roi, image) -> str:
        """Return the one-line measurement shown beside a region."""
        if image is None or image.ndim < 2:
            return ""
        try:
            props = roi.properties(image.shape[-2:], image=image)
        except Exception:  # noqa: BLE001 - a bad region must not empty the list
            return ""
        if props is None or not props.area:
            return "empty"
        mean = props.intensity_mean
        if mean is None:
            return f"{props.area} px"
        unit = f"{self._intensity_unit}/px" if self._intensity_unit else "/px"
        return f"{props.area} px, {mean:.1f} {unit}".replace(" /px", "/px")

    def refresh(self) -> None:
        """Rebuild the rows from the collection, keeping the selection."""
        self._refreshing = True
        try:
            current = self.selected_name()
            collection = self.collection
            image = self._image()
            self.tree.clear()
            for entry in collection:
                item = QtWidgets.QTreeWidgetItem(
                    [
                        entry.name,
                        type(entry.roi).__name__.replace("ROI", "").lower(),
                        self._measurement(entry.roi, image),
                        "",
                    ]
                )
                item.setData(_COL_NAME, _NAME_ROLE, entry.name)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(
                    _COL_NAME, QtCore.Qt.Checked if entry.enabled else QtCore.Qt.Unchecked
                )
                item.setCheckState(
                    _COL_INVERT, QtCore.Qt.Checked if entry.invert else QtCore.Qt.Unchecked
                )
                item.setToolTip(_COL_INVERT, "Use everything outside this region instead")
                self.tree.addTopLevelItem(item)

            index = self.combine_box.findData(collection.combine)
            if index >= 0:
                self.combine_box.setCurrentIndex(index)
            self._refresh_summary(collection, image)
        finally:
            self._refreshing = False
        if current:
            self.select(current)

    def _refresh_summary(self, collection: RegionCollection, image) -> None:
        """Describe the combined selection in the footer."""
        active = len(collection.enabled)
        if not len(collection):
            self.summary_label.setText("no regions")
            return
        if not active:
            self.summary_label.setText("none active — whole frame")
            return
        combined = collection.combined()
        if image is None or combined is None:
            self.summary_label.setText(f"{active} of {len(collection)} active")
            return
        try:
            area = int(combined.to_mask(image.shape[-2:], image=image).sum())
        except Exception:  # noqa: BLE001
            self.summary_label.setText(f"{active} of {len(collection)} active")
            return
        self.summary_label.setText(f"{active} of {len(collection)} → {area} px")


__all__ = ["RegionEditor", "SHAPES"]
