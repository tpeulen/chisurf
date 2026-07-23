"""Custom AutoForm sections for the ① Compute LUT panel.

The interactive raw/after TAC plots with the draggable linear-region and
offset/threshold lines are a bespoke pyqtgraph widget registered here; the
parameters are plain declarative ``value``/``toggle`` sections in
``lut_compute.view.json``. The widget owns only Qt concerns and drives the
Qt-free :class:`~..view_model.LutComputeViewModel`. Imported (and registered) by
``gui.tool``.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform.sections.registry import register_section


@register_section("lut_compute_plot")
def lut_compute_plot(model, target=None, **options):
    """AutoForm factory for the interactive compute plots."""
    return _ComputePlotSection(model)


class _ComputePlotSection(pg.GraphicsLayoutWidget):
    """Raw TAC histogram (draggable region) + corrected-preview histogram."""

    is_form_field = False

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        self._syncing = False
        self.setMinimumHeight(360)

        self.plt_raw = self.addPlot(row=0, col=0)
        self.plt_raw.setTitle("Raw TAC histogram — drag the orange region to pick the linear plateau")
        self.plt_raw.setLabel("left", "Counts")
        self.plt_raw.setLabel("bottom", "TAC bin")
        self.plt_after = self.addPlot(row=1, col=0)
        self.plt_after.setTitle("After linearization (corrected preview)")
        self.plt_after.setLabel("left", "Counts")
        self.plt_after.setLabel("bottom", "Equal-width NTAC bin")

        self.region = pg.LinearRegionItem(
            values=[model.linear_start, model.linear_stop],
            brush=(255, 165, 0, 60), movable=True,
        )
        self.offset_line = pg.InfiniteLine(angle=90, movable=True, pos=model.noffset,
                                           pen=pg.mkPen((200, 0, 0), width=2))
        self.thresh_line = pg.InfiniteLine(angle=0, movable=True, pos=model.threshold,
                                           pen=pg.mkPen((0, 180, 0), width=2))
        self.plt_raw.addItem(self.region)
        self.plt_raw.addItem(self.offset_line)
        self.plt_raw.addItem(self.thresh_line)

        self.region.sigRegionChangeFinished.connect(self._on_region)
        self.offset_line.sigPositionChangeFinished.connect(self._on_offset)
        self.thresh_line.sigPositionChangeFinished.connect(self._on_thresh)

        model.add_observer(self._on_model_event)
        self._redraw()

    # ── plot-item → model ───────────────────────────────────────────────
    def _on_region(self):
        if self._syncing:
            return
        start, stop = (int(v) for v in self.region.getRegion())
        self._model.linear_start = min(start, stop)
        self._model.linear_stop = max(start, stop) + (1 if start == stop else 0)
        self._model.compute()
        self._model.notify("fields")  # tool re-syncs the value fields

    def _on_offset(self):
        if self._syncing:
            return
        self._model.noffset = max(0, int(round(self.offset_line.value())))
        self._model.compute()
        self._model.notify("fields")

    def _on_thresh(self):
        if self._syncing:
            return
        self._model.threshold = float(self.thresh_line.value())
        self._model.compute()
        self._model.notify("fields")

    # ── model → plots ───────────────────────────────────────────────────
    def _on_model_event(self, event: str):
        self._redraw()

    def _redraw(self):
        model = self._model
        # Move the draggable items to match the model without re-emitting.
        self._syncing = True
        try:
            self.region.setRegion([model.linear_start, model.linear_stop])
            self.offset_line.setValue(model.noffset)
            self.thresh_line.setValue(model.threshold)
        finally:
            self._syncing = False

        # Raw histogram.
        for item in list(self.plt_raw.listDataItems()):
            self.plt_raw.removeItem(item)
        counts = model.counts_effective()
        if counts is not None:
            x = np.arange(model.n_bins)
            if model.normalize:
                region = counts[int(model.linear_start):int(model.linear_stop)]
                mean = float(region.mean()) if region.size else 1.0
                y = counts / (mean if mean > 0 else 1.0)
                self.plt_raw.setLabel("left", "Counts / ⟨region⟩")
            else:
                y = counts.astype(float)
                self.plt_raw.setLabel("left", "Counts")
            self.plt_raw.plot(x, y, pen=pg.mkPen((255, 204, 0), width=1.5))

        # Corrected preview.
        for item in list(self.plt_after.listDataItems()):
            self.plt_after.removeItem(item)
        after = model.corrected_after_hist()
        if after is not None:
            xa, ya = after
            self.plt_after.plot(xa, ya, pen=pg.mkPen((80, 200, 255), width=1.5))
            self.plt_after.setXRange(0, int(model.ntac_required), padding=0)


@register_section("lut_compute_actions")
def lut_compute_actions(model, target=None, **options):
    """AutoForm factory for the Auto-detect / Save LUT / Export buttons."""
    return _ComputeActions(model)


class _ComputeActions(QtWidgets.QWidget):
    """Auto-detect region + Save LUT + Export corrected (with file dialogs)."""

    is_form_field = False

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)

        def _btn(text, tip, slot):
            b = QtWidgets.QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            b.clicked.connect(slot)
            return b

        row.addWidget(_btn("🎯 Auto-detect region", "Auto-detect the flat linear plateau.",
                           model.autodetect))
        row.addStretch(1)
        hint = QtWidgets.QLabel("Optional:")
        hint.setStyleSheet("color: #9ba3af; font-size: 10px;")
        row.addWidget(hint)
        row.addWidget(_btn("💾 Save LUT file…",
                           "Optional: save this channel's LUT to a file. Not needed — "
                           "use ‘➡ Add to Detector setup’ for the normal workflow.",
                           self._save))
        row.addWidget(_btn("📤 Export corrected…",
                           "Optional: export the corrected micro-times of all photons.",
                           self._export))

    def _save(self):
        if self._model.current_table is None:
            QtWidgets.QMessageBox.warning(self, "No LUT", "Compute a LUT first.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save LUT", "", "NumPy (*.npy);;NPZ (*.npz);;Text (*.txt);;CSV (*.csv)")
        if not path:
            return
        try:
            self._model.save_lut(path)
            QtWidgets.QMessageBox.information(self, "Saved", f"LUT saved to {path}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(exc))

    def _export(self):
        if self._model.current_table is None:
            QtWidgets.QMessageBox.warning(self, "No LUT", "Compute a LUT first.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export corrected micro-times", "", "NumPy (*.npy);;NPZ (*.npz);;CSV (*.csv);;Text (*.txt)")
        if not path:
            return
        try:
            self._model.export_corrected(path)
            QtWidgets.QMessageBox.information(self, "Exported", f"Saved to {path}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Export failed", str(exc))


@register_section("lut_info_label")
def lut_info_label(model, target=None, **options):
    """AutoForm factory for the one-line LUT summary label."""
    label = QtWidgets.QLabel(model.info_text())
    label.setWordWrap(True)
    label.setStyleSheet("color: #9ba3af; font-size: 11px;")

    def _refresh(_event):
        label.setText(model.info_text())

    model.add_observer(_refresh)
    label.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
    return label
