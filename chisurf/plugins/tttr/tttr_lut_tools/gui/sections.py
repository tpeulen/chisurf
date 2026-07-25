"""Custom AutoForm sections for the ① Compute LUT panel.

The interactive raw/after TAC plots with the draggable linear-region and
offset/threshold lines are a bespoke chiplot widget registered here; the
parameters are plain declarative ``value``/``toggle`` sections in
``lut_compute.view.json``. The widget owns only Qt concerns and drives the
Qt-free :class:`~..view_model.LutComputeViewModel`. Imported (and registered) by
``gui.tool``.
"""

from __future__ import annotations

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf.gui import chiplot as cp
from chisurf.gui.autoform.sections.registry import register_section


@register_section("lut_compute_plot")
def lut_compute_plot(model, target=None, **options):
    """AutoForm factory for the interactive compute plots."""
    return _ComputePlotSection(model)


class _ComputePlotSection(cp.Grid):
    """Raw TAC histogram (draggable region) + corrected-preview histogram."""

    is_form_field = False

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        self._raw_curve = None
        self._after_curve = None
        self.setMinimumHeight(360)

        self.plt_raw = self.add_plot(
            row=0, col=0,
            title="Raw TAC histogram — drag the orange region to pick the linear plateau",
        )
        self.plt_raw.set_labels(left="Counts", bottom="TAC bin")
        self.plt_after = self.add_plot(
            row=1, col=0, title="After linearization (corrected preview)",
        )
        self.plt_after.set_labels(left="Counts", bottom="Equal-width NTAC bin")

        self.region = self.plt_raw.region(
            (model.linear_start, model.linear_stop),
            brush=(255, 165, 0, 60), movable=True,
        )
        self.offset_line = self.plt_raw.vline(
            model.noffset, movable=True, pen=cp.to_pen((200, 0, 0), width=2),
        )
        self.thresh_line = self.plt_raw.hline(
            model.threshold, movable=True, pen=cp.to_pen((0, 180, 0), width=2),
        )

        # ``set_bounds``/``set_value`` are signal-safe, so programmatic syncs in
        # ``_redraw`` do not re-enter these handlers.
        self.region.on_change(self._on_region, final=True)
        self.offset_line.on_change(self._on_offset, final=True)
        self.thresh_line.on_change(self._on_thresh, final=True)

        model.add_observer(self._on_model_event)
        self._redraw()

    # ── plot-item → model ───────────────────────────────────────────────
    def _on_region(self, lo, hi):
        start, stop = int(lo), int(hi)
        self._model.linear_start = min(start, stop)
        self._model.linear_stop = max(start, stop) + (1 if start == stop else 0)
        self._model.compute()
        self._model.notify("fields")  # tool re-syncs the value fields

    def _on_offset(self, pos):
        self._model.noffset = max(0, int(round(pos)))
        self._model.compute()
        self._model.notify("fields")

    def _on_thresh(self, pos):
        self._model.threshold = float(pos)
        self._model.compute()
        self._model.notify("fields")

    # ── model → plots ───────────────────────────────────────────────────
    def _on_model_event(self, event: str):
        self._redraw()

    def _redraw(self):
        model = self._model
        # Move the draggable items to match the model (signal-safe: no re-emit).
        self.region.set_bounds(model.linear_start, model.linear_stop)
        self.offset_line.set_value(model.noffset)
        self.thresh_line.set_value(model.threshold)

        # Raw histogram — replace only the data curve, keep the draggable items.
        if self._raw_curve is not None:
            self.plt_raw.remove(self._raw_curve)
            self._raw_curve = None
        counts = model.counts_effective()
        if counts is not None:
            x = np.arange(model.n_bins)
            if model.normalize:
                region = counts[int(model.linear_start):int(model.linear_stop)]
                mean = float(region.mean()) if region.size else 1.0
                y = counts / (mean if mean > 0 else 1.0)
                self.plt_raw.set_labels(left="Counts / ⟨region⟩")
            else:
                y = counts.astype(float)
                self.plt_raw.set_labels(left="Counts")
            self._raw_curve = self.plt_raw.line(x, y, pen=cp.to_pen((255, 204, 0), width=1.5))

        # Corrected preview.
        if self._after_curve is not None:
            self.plt_after.remove(self._after_curve)
            self._after_curve = None
        after = model.corrected_after_hist()
        if after is not None:
            xa, ya = after
            self._after_curve = self.plt_after.line(xa, ya, pen=cp.to_pen((80, 200, 255), width=1.5))
            self.plt_after.set_xlim(0, int(model.ntac_required), padding=0)


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
