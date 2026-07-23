"""FRET-2CDE / ALEX-2CDE GUI tool.

A compact panel to compute the 2CDE burst-dynamics feature over a burstwise
analysis folder and plot it against the per-burst FRET efficiency.  The heavy
lifting is in :mod:`chisurf.plugins.burst.burst_2cde.core.computation`; this is
a thin GUI over it, embeddable in the ``burst_analysis`` workflow shell.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pyqtgraph as pg
from qtpy import QtWidgets, QtCore

from chisurf.plugins.burst.burst_2cde.core import computation as core

try:
    from chisurf.plugins.burst.burst_selection.api.features import proximity_ratio
except Exception:  # pragma: no cover - optional dependency
    proximity_ratio = None


class BurstTwoCdeTool(QtWidgets.QMainWindow):
    """Compute and plot FRET-2CDE / ALEX-2CDE for a burstwise analysis folder."""

    name = "Spectroscopy:Single-Molecule:2CDE"

    def __init__(self, parent=None, embedded: bool = False, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("FRET-2CDE / ALEX-2CDE")
        self._embedded = embedded
        self._folder: pathlib.Path | None = None

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # --- folder row -------------------------------------------------------
        row = QtWidgets.QHBoxLayout()
        self._folder_edit = QtWidgets.QLineEdit()
        self._folder_edit.setPlaceholderText("Burstwise analysis folder …")
        browse = QtWidgets.QToolButton()
        browse.setText("📁")
        browse.clicked.connect(self._browse)
        row.addWidget(QtWidgets.QLabel("Folder"))
        row.addWidget(self._folder_edit, 1)
        row.addWidget(browse)
        layout.addLayout(row)

        # --- settings form ----------------------------------------------------
        form = QtWidgets.QFormLayout()
        self._variant = QtWidgets.QComboBox()
        self._variant.addItems(["fret", "alex"])
        self._kernel = QtWidgets.QComboBox()
        self._kernel.addItems(["laplace", "gaussian"])
        self._tau = QtWidgets.QDoubleSpinBox()
        self._tau.setDecimals(1)
        self._tau.setRange(1.0, 100000.0)
        self._tau.setValue(100.0)
        self._tau.setSuffix(" µs")
        self._donor = QtWidgets.QLineEdit("0,8")
        self._acceptor = QtWidgets.QLineEdit("1,9")
        self._file_type = QtWidgets.QLineEdit("SPC-130")
        form.addRow("Variant", self._variant)
        form.addRow("Kernel", self._kernel)
        form.addRow("τ", self._tau)
        form.addRow("Donor ch.", self._donor)
        form.addRow("Acceptor ch.", self._acceptor)
        form.addRow("File type", self._file_type)
        layout.addLayout(form)

        # --- run button -------------------------------------------------------
        self._run = QtWidgets.QToolButton()
        self._run.setText("▶ Compute 2CDE")
        self._run.clicked.connect(self.run)
        layout.addWidget(self._run)

        # --- plot -------------------------------------------------------------
        self._plot = pg.PlotWidget()
        self._plot.setLabel("bottom", "FRET efficiency (proximity ratio)")
        self._plot.setLabel("left", "2CDE")
        layout.addWidget(self._plot, 1)

        self._status = QtWidgets.QLabel("")
        layout.addWidget(self._status)

    # -- helpers --------------------------------------------------------------
    def _browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select burstwise folder")
        if d:
            self._folder_edit.setText(d)

    def _channels(self, text: str):
        return [int(x) for x in str(text).split(",") if x.strip()]

    def set_folder(self, folder) -> None:
        """Set the analysis folder (used by the workflow context)."""
        self._folder_edit.setText(str(folder))

    def run(self) -> None:
        """Read the burst folder, compute 2CDE and update the plot."""
        folder = self._folder_edit.text().strip()
        if not folder or not pathlib.Path(folder).is_dir():
            self._status.setText("Select a valid burstwise analysis folder.")
            return
        variant = self._variant.currentText()
        column = core.COLUMN_ALEX_2CDE if variant == "alex" else core.COLUMN_FRET_2CDE
        try:
            df, tttrs = core.read_burst_analysis(pathlib.Path(folder), self._file_type.text().strip())
            df = core.compute_2cde(
                df, tttrs,
                donor_channels=self._channels(self._donor.text()),
                acceptor_channels=self._channels(self._acceptor.text()),
                donor_micro_time_ranges=[], acceptor_micro_time_ranges=[],
                tau=float(self._tau.value()) * 1e-6, kernel=self._kernel.currentText(),
                variant=variant,
            )
        except Exception as exc:  # pragma: no cover - GUI error path
            self._status.setText(f"Error: {exc}")
            return
        self._draw(df, column)

    def _draw(self, df, column) -> None:
        vals = df[column].to_numpy(dtype=float)
        finite = np.isfinite(vals)
        e = proximity_ratio(df) if proximity_ratio is not None else None
        self._plot.clear()
        if e is not None:
            e = np.asarray(e, dtype=float)
            m = finite & np.isfinite(e)
            self._plot.plot(e[m], vals[m], pen=None, symbol="o", symbolSize=3,
                            symbolBrush=(31, 119, 180, 80))
            self._plot.setLabel("bottom", "FRET efficiency (proximity ratio)")
        else:
            y, x = np.histogram(vals[finite], bins=40)
            self._plot.plot(0.5 * (x[:-1] + x[1:]), y, stepMode=False)
            self._plot.setLabel("bottom", column)
        self._status.setText(
            f"{column}: {int(finite.sum())} / {len(df)} bursts valid")
