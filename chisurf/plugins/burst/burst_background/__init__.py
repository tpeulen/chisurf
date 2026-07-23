"""Burst Background Estimation Plugin

This plugin estimates background count rates from TTTR data by fitting the
exponential tail of the interphoton time distribution, analogous to
PAM's `Estimate_Background_From_Burst.m`.

It uses the detector and PIE-window definitions from the
:class:`chisurf.gui.widgets.wizard.tttr_channel_definition.DetectorWizardPage`
so that the same setups can be shared with other TTTR tools.
"""

# Plugin brand icon (unified emoji set)
icon = "🌑"

name = "Spectroscopy:Single-Molecule:Burst Background Estimation"

# Expose the plugin CLI through chisurf.core.cli
cli_entrypoint = "burst-background=chisurf.plugins.burst.burst_background.cli:cli"

import os
import sys
from typing import Dict

import numpy as np
import pyqtgraph as pg
import tttrlib
from qtpy.QtCore import Qt
from qtpy.QtGui import QDragEnterEvent, QDropEvent
from qtpy.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# A small, stable colour palette keyed by detector name for the plots.
_DET_COLORS = [
    (31, 119, 180), (214, 39, 40), (44, 160, 44), (255, 127, 14),
    (148, 103, 189), (140, 86, 75), (23, 190, 207), (188, 189, 34),
]
# Semantic colours for common detector names (identity-stable, matching the
# convention used elsewhere in ChiSurf); other names fall back to the palette.
_SEMANTIC_COLORS = {
    "green": (44, 160, 44), "donor": (44, 160, 44), "g": (44, 160, 44),
    "red": (214, 39, 40), "acceptor": (214, 39, 40), "r": (214, 39, 40),
    "yellow": (188, 189, 34), "y": (188, 189, 34),
    "blue": (31, 119, 180), "b": (31, 119, 180),
}


def _det_color(name: str):
    """Colour for a detector name: semantic for common names, else a stable palette."""
    key = str(name).strip().lower()
    if key in _SEMANTIC_COLORS:
        return _SEMANTIC_COLORS[key]
    return _DET_COLORS[abs(hash(key)) % len(_DET_COLORS)]

import chisurf.core.fluorescence.burst
from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizardPage

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:
    persist_plugin_state = lambda n: lambda c: c



@persist_plugin_state("burst_background")
class BurstBackgroundEstimator(QWidget):
    """Main widget for the Burst Background Estimation plugin."""

    def __init__(self, show_channel_definition: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("Burst Background Estimation")
        self.show_channel_definition = show_channel_definition

        # Data storage
        self.tttr_files = []  # type: ignore[var-annotated]
        self.backgrounds: Dict[str, Dict[str, float]] = {}
        # Per-file, per-detector interphoton-time histograms + tail fits.
        self.diagnostics: Dict[str, Dict[str, object]] = {}

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Build UI
        self._init_ui()

    # ------------------------------------------------------------------
    # Qt Events (drag & drop)
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        urls = event.mimeData().urls()
        file_paths = [url.toLocalFile() for url in urls]
        self._add_tttr_files(file_paths)
        event.acceptProposedAction()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _init_ui(self) -> None:
        main_layout = QVBoxLayout()

        tab_widget = QTabWidget()

        # Tab 1: detector / PIE-window definition
        self.detector_wizard_page = DetectorWizardPage(
            show_edit_json=False,
            show_save=False,
            show_setups_file=True,
            show_setup_selection=True,
            show_help=True,
            show_tttr_reading=True,
            show_tables=True,
            show_add_inputs=True,
        )
        if self.show_channel_definition:
            tab_widget.addTab(self.detector_wizard_page, "Channel Definition")

        # Tab 2: files and background estimation results
        files_tab = QWidget()
        files_layout = QVBoxLayout(files_tab)

        controls_layout = QHBoxLayout()

        self.load_button = QPushButton("Load TTTR Files")
        self.load_button.clicked.connect(self._load_tttr_files)
        controls_layout.addWidget(self.load_button)

        self.clear_button = QPushButton("Clear Files")
        self.clear_button.clicked.connect(self._clear_files)
        controls_layout.addWidget(self.clear_button)

        self.estimate_button = QPushButton("Estimate Background")
        self.estimate_button.clicked.connect(self._estimate_background)
        controls_layout.addWidget(self.estimate_button)

        files_layout.addLayout(controls_layout)

        # Table listing TTTR files and status
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(2)
        self.file_table.setHorizontalHeaderLabels(["File", "Status"])
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        files_layout.addWidget(self.file_table)

        # Results table: one row per (file, detector)
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels([
            "File",
            "Detector",
            "Background (kHz)",
        ])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        files_layout.addWidget(self.results_table)

        tab_widget.addTab(files_tab, "Files & Results")

        # Tab 3: diagnostic plots (inter-photon-time distribution + tail fit,
        # and a per-detector background-rate bar chart).
        tab_widget.addTab(self._build_diagnostics_tab(), "Diagnostics")

        main_layout.addWidget(tab_widget)
        self.setLayout(main_layout)
        self.resize(760, 560)

    # ------------------------------------------------------------------
    # Diagnostics plots
    # ------------------------------------------------------------------
    def _build_diagnostics_tab(self) -> QWidget:
        """Build the diagnostics tab with the two pyqtgraph plots."""
        pg.setConfigOptions(antialias=True)
        w = QWidget()
        layout = QVBoxLayout(w)
        splitter = QSplitter(Qt.Vertical)

        # Inter-photon-time distribution (log-log): histogram + exponential fit.
        self.iht_plot = pg.PlotWidget()
        self.iht_plot.setLogMode(x=True, y=True)
        self.iht_plot.setLabel("bottom", "inter-photon time", units="ms")
        self.iht_plot.setLabel("left", "counts")
        self.iht_plot.setTitle("Inter-photon-time distribution + background tail fit")
        self.iht_plot.addLegend(offset=(-10, 10))
        splitter.addWidget(self.iht_plot)

        # Per-detector background-rate bar chart.
        self.rate_plot = pg.PlotWidget()
        self.rate_plot.setLabel("left", "background", units="kHz")
        self.rate_plot.setTitle("Background rate per detector")
        splitter.addWidget(self.rate_plot)

        splitter.setSizes([340, 200])
        layout.addWidget(splitter)
        self._diag_hint = QLabel("Load files and press “Estimate Background”.")
        layout.addWidget(self._diag_hint)
        return w

    def _update_plots(self) -> None:
        """Redraw the inter-photon-time and rate plots from ``self.diagnostics``."""
        self.iht_plot.clear()
        self.rate_plot.clear()
        if not self.diagnostics:
            return
        legend = getattr(self.iht_plot, "legend", None)
        if legend is not None:
            legend.clear()

        multi_file = len(self.diagnostics) > 1
        seen_labels: set = set()
        for path, det_diags in self.diagnostics.items():
            stem = os.path.basename(path)
            for det_name, diag in det_diags.items():
                centers = np.asarray(diag.centers, dtype=float)
                counts = np.asarray(diag.counts, dtype=float)
                if centers.size == 0:
                    continue
                color = _det_color(det_name)
                nz = counts > 0
                label = det_name if not multi_file else f"{det_name} · {stem}"
                # histogram points (log-log needs positive values)
                self.iht_plot.plot(
                    centers[nz], counts[nz], pen=None,
                    symbol="o", symbolSize=3,
                    symbolBrush=(*color, 90), symbolPen=None,
                    name=label if label not in seen_labels else None,
                )
                seen_labels.add(label)
                # fitted background model over the fitted range
                model = np.asarray(diag.model, dtype=float)
                mask = model > 0
                if mask.any():
                    self.iht_plot.plot(centers[mask], model[mask],
                                       pen=pg.mkPen(color, width=2))

        # Rate bar chart: grouped by detector (mean over files).
        det_names, det_rates = [], []
        agg: Dict[str, list] = {}
        for det_diags in self.diagnostics.values():
            for det_name, diag in det_diags.items():
                agg.setdefault(det_name, []).append(float(diag.rate_khz))
        for det_name, rates in agg.items():
            det_names.append(det_name)
            det_rates.append(float(np.mean(rates)))
        if det_names:
            x = np.arange(len(det_names))
            bars = pg.BarGraphItem(
                x=x, height=det_rates, width=0.6,
                brushes=[_det_color(n) for n in det_names])
            self.rate_plot.addItem(bars)
            ax = self.rate_plot.getAxis("bottom")
            ax.setTicks([list(zip(x.tolist(), det_names))])
        self._diag_hint.setText(
            f"{len(self.diagnostics)} file(s), {len(agg)} detector(s). "
            "Points: measured histogram; line: fitted background tail.")

    # ------------------------------------------------------------------
    # File handling helpers
    # ------------------------------------------------------------------
    def _load_tttr_files(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Load TTTR Files",
            "",
            "All Files (*)",
        )
        if file_paths:
            self._add_tttr_files(file_paths)

    def _add_tttr_files(self, file_paths) -> None:
        new_files_added = False
        for path in file_paths:
            if path and path not in self.tttr_files:
                self.tttr_files.append(path)
                new_files_added = True

        if not new_files_added:
            return

        # Sort lexically by basename and rebuild the table
        self.tttr_files.sort(key=lambda p: os.path.basename(p).lower())
        self.file_table.setRowCount(0)
        for path in self.tttr_files:
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)
            self.file_table.setItem(row, 0, QTableWidgetItem(os.path.basename(path)))
            self.file_table.setItem(row, 1, QTableWidgetItem("Loaded"))

    def _clear_files(self) -> None:
        self.tttr_files = []
        self.backgrounds.clear()
        self.diagnostics.clear()
        self.file_table.setRowCount(0)
        self.results_table.setRowCount(0)
        self._update_plots()

    # ------------------------------------------------------------------
    # Core calculation
    # ------------------------------------------------------------------
    def _estimate_background(self) -> None:
        if not self.tttr_files:
            QMessageBox.warning(self, "No Files", "Please load TTTR files first.")
            return

        settings = self.detector_wizard_page.get_settings()
        detectors = settings.get("detectors", {})
        if not detectors:
            QMessageBox.warning(
                self,
                "No Detectors",
                "Please define at least one detector in the channel definition tab.",
            )
            return

        self.backgrounds.clear()
        self.diagnostics.clear()
        self.results_table.setRowCount(0)

        for file_idx, path in enumerate(self.tttr_files):
            # Update status
            self.file_table.setItem(file_idx, 1, QTableWidgetItem("Processing..."))
            QApplication.processEvents()

            try:
                tttr = tttrlib.TTTR(path)
            except Exception as exc:  # pragma: no cover - GUI error path
                self.file_table.setItem(file_idx, 1, QTableWidgetItem(f"Error: {exc}"))
                continue

            # One pass yields both the rates (from the diagnostics' fits) and the
            # histograms/model curves for the plots.
            diags = chisurf.core.fluorescence.burst.background_diagnostics_from_bursts(
                tttr, detectors,
            )
            self.diagnostics[path] = diags
            self.backgrounds[path] = {name: float(d.rate_khz) for name, d in diags.items()}

            self.file_table.setItem(file_idx, 1, QTableWidgetItem("Done"))

        self._update_results_table()
        self._update_plots()

    def _update_results_table(self) -> None:
        # Count rows required
        n_rows = 0
        for bg in self.backgrounds.values():
            n_rows += len(bg)

        self.results_table.setRowCount(n_rows)
        row = 0
        for path, bg in self.backgrounds.items():
            fname = os.path.basename(path)
            for det_name, rate in bg.items():
                self.results_table.setItem(row, 0, QTableWidgetItem(fname))
                self.results_table.setItem(row, 1, QTableWidgetItem(str(det_name)))
                self.results_table.setItem(row, 2, QTableWidgetItem(f"{rate:.3f}"))
                row += 1


if __name__ == "__main__":  # pragma: no cover - manual GUI entry
    app = QApplication(sys.argv)
    window = BurstBackgroundEstimator()
    window.show()
    sys.exit(app.exec())

elif __name__ == "plugin":  # pragma: no cover - used by ChiSurf plugin loader
    window = BurstBackgroundEstimator()
    window.show()
