"""Write the CSV files the old ALEX-Suite wrote, from this workflow's bursts.

Not the storage format — the analysis is stored in the `.pto` container and the
burst companions beside it, exactly as in the PIE workflow. This is the bridge
for the spreadsheets, plotting templates and scripts people already have, which
read five specific files with five specific section headers.
"""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtWidgets

logger = logging.getLogger("chisurf.plugins.burst")


class LegacyExportPanel(QtWidgets.QWidget):
    """Pick a burst file and write the ALEX-Suite five-file export."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the export panel."""
        super().__init__(parent)
        self._workflow = parent
        self._bur_files: list[pathlib.Path] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        intro = QtWidgets.QLabel(
            "The five CSV files the old ALEX-Suite wrote — for scripts built on "
            "that layout.", self)
        intro.setToolTip(
            "Writes <stem>_meta.csv, _hist_E.csv, _hist_S.csv, _hist_2D.csv and "
            "_original_bursts.csv with the same section headers the old program "
            "used, so existing scripts and spreadsheets keep working.\n\n"
            "It is a convenience export, not the storage. The analysis itself "
            "lives in the .pto container and the burst companions beside it, the "
            "same as every other ChiSurf burst workflow."
        )
        layout.addWidget(intro)

        form = QtWidgets.QFormLayout()
        self.file_combo = QtWidgets.QComboBox(self)
        self.file_combo.setToolTip("Burst file to export (from the burst search).")
        # A burst path is long, and a combo that asks for its full width pushes
        # the form's label column off the panel ("Burst fil"). Let it elide.
        self.file_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.file_combo.setMinimumContentsLength(24)
        self.file_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        form.addRow("Burst file", self.file_combo)

        self.sample_edit = QtWidgets.QLineEdit(self)
        self.sample_edit.setPlaceholderText("e.g. dsDNA 15 bp, Cy3B/ATTO647N")
        form.addRow("Sample", self.sample_edit)

        self.buffer_edit = QtWidgets.QLineEdit(self)
        self.buffer_edit.setPlaceholderText("e.g. TE + 100 mM NaCl")
        form.addRow("Buffer", self.buffer_edit)
        layout.addLayout(form)

        boxes = QtWidgets.QHBoxLayout()
        self.checks: dict[str, QtWidgets.QCheckBox] = {}
        for key, label, default in (
            ("metadata", "Metadata", True),
            ("e_histogram", "E histogram", True),
            ("s_histogram", "S histogram", True),
            ("histogram_2d", "2-D histogram", True),
            ("original_bursts", "All bursts", False),
        ):
            box = QtWidgets.QCheckBox(label, self)
            box.setChecked(default)
            boxes.addWidget(box)
            self.checks[key] = box
        boxes.addStretch(1)
        layout.addLayout(boxes)

        row = QtWidgets.QHBoxLayout()
        self.run_button = QtWidgets.QToolButton(self)
        self.run_button.setObjectName("toolAction_run")
        self.run_button.setText("💾 Write ALEX-Suite CSVs")
        self.run_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.run_button.clicked.connect(self.run)
        row.addWidget(self.run_button)
        row.addStretch(1)
        layout.addLayout(row)

        self.status_label = QtWidgets.QLabel("No bursts yet — run the burst search first.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

    # ── workflow hand-off ───────────────────────────────────────────────

    def set_burst_files(self, files) -> None:
        """Adopt the burst files the pipeline produced."""
        self._bur_files = [pathlib.Path(p) for p in files]
        current = self.file_combo.currentText()
        self.file_combo.clear()
        self.file_combo.addItems([str(p) for p in self._bur_files])
        if current:
            index = self.file_combo.findText(current)
            if index >= 0:
                self.file_combo.setCurrentIndex(index)
        if self._bur_files:
            self.status_label.setText(
                f"{len(self._bur_files)} burst file(s) available.")

    # ── the action ──────────────────────────────────────────────────────

    def run(self) -> None:
        """Write the export beside the chosen burst file."""
        source = self.file_combo.currentText()
        if not source:
            self.status_label.setText("Pick a burst file first.")
            return
        from chisurf.plugins.burst.alex_suite.api.histograms import es_histograms
        from chisurf.plugins.burst.alex_suite.api.legacy_export import (
            LegacyExport,
            Metadata,
            write_legacy_export,
        )

        path = pathlib.Path(source)
        try:
            histograms = es_histograms(path)
            burst_table = None
            if self.checks["original_bursts"].isChecked():
                from chisurf.core.fluorescence.burst.table import read_burst_table

                burst_table = read_burst_table(path)
            written = write_legacy_export(
                path.with_suffix(""),
                histograms,
                metadata=Metadata(
                    sample_name=self.sample_edit.text(),
                    buffer=self.buffer_edit.text(),
                ),
                parts=LegacyExport(**{
                    key: box.isChecked() for key, box in self.checks.items()
                }),
                burst_table=burst_table,
            )
        except Exception as exc:
            logger.warning(f"ALEX Suite: legacy export failed — {exc}")
            self.status_label.setText(f"Export failed: {exc}")
            return
        names = ", ".join(p.name for p in written)
        self.status_label.setText(f"Wrote {len(written)} file(s) in {path.parent}: {names}")
        logger.info(f"ALEX-Suite export: {len(written)} file(s) in {path.parent}")


__all__ = ["LegacyExportPanel"]
