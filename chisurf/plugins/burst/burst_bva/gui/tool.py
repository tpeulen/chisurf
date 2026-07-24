"""Burst Variance Analysis (BVA) tool with toolbar, tabbed settings, and pyqtgraph plot."""

from __future__ import annotations

import json
import pathlib
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import pyqtgraph as pg
from qtpy.QtCore import QCoreApplication, QSettings, QSize, Qt, QTimer, Signal
from qtpy.QtGui import QDragEnterEvent, QDropEvent
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from chisurf import logging
from chisurf.gui.misc_helpers import (
    get_plugin_settings_path,
    persist_plugin_state,
)
from chisurf.gui.widgets.dock_area.dock_area import DockArea
from chisurf.gui.widgets.wizard import DetectorWizardPage
from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups import (
    load_detector_setups,
)
from chisurf.plugins.burst.burst_bva.core import computation as core


class HelpDialog(QDialog):
    """Help dialog with description and CLI reference."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About Burst Variance Analysis (BVA)")
        self.resize(640, 520)
        layout = QVBoxLayout(self)

        text = QTextEdit(self)
        text.setReadOnly(True)

        cli_text = ""
        try:
            from click.testing import CliRunner

            from ..cli.main import cli

            runner = CliRunner()
            result = runner.invoke(cli, ["--help"])
            cli_text = "<pre>\n" + result.output + "</pre>"
        except Exception as exc:
            cli_text = f"<p>CLI help unavailable: {exc}</p>"

        text.setHtml(
            """
            <h2>Burst Variance Analysis (BVA)</h2>
            <p>This plugin implements Burst Variance Analysis for single-molecule FRET experiments.
            BVA is a technique that analyzes the variance of FRET efficiency within individual
            bursts to distinguish between static and dynamic heterogeneity in the sample.</p>

            <h3>How it works</h3>
            <ol>
              <li>Select data folder containing TTTR files</li>
              <li>Configure analysis parameters (window length, photons per slice)</li>
              <li>Set up FRET pair assignment (donor/acceptor channels)</li>
              <li>Click <b>Run</b> to process all files and generate BVA results</li>
            </ol>

            <h3>Output</h3>
            <p>Results include burst statistics, FRET efficiency distributions, variance analysis,
            and heterogeneity metrics.</p>

            <hr>
            <h3>CLI Reference</h3>
            """
            + cli_text
        )
        layout.addWidget(text, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


# Shared, app-wide tool-button language (this colour scheme is its canonical
# source). BVA keeps its exact look while every other tool can adopt the same.
from chisurf.gui.widgets.tool_buttons import (  # noqa: E402
    TOOLBAR_STYLE as _TOOLBAR_STYLE,
    action_button,
)


class _FolderLineEdit(QLineEdit):
    """QLineEdit that accepts folder drops from the file manager."""
    folderDropped = Signal(str)

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setReadOnly(True)
        self.setAcceptDrops(True)
        self.setStyleSheet("color: #aaa; padding: 0 4px; background: transparent; border: none;")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.setText(path)
                self.folderDropped.emit(path)


class _ProgressDialog(QDialog):
    def __init__(self, title="Progress", message="Processing...", max_value=100, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowModality(Qt.WindowModal)
        layout = QVBoxLayout()
        self.label = QLabel(message)
        self.progress = QProgressBar()
        self.progress.setRange(0, max_value)
        layout.addWidget(self.label)
        layout.addWidget(self.progress)
        self.setLayout(layout)

    def set_value(self, value: int):
        self.progress.setValue(value)
        QCoreApplication.processEvents()

    def set_maximum(self, value: int):
        self.progress.setMaximum(value)


@persist_plugin_state("burst_bva")
class BVATool(QMainWindow):
    """BVA analysis widget with toolbar, tabbed settings, and pyqtgraph plot."""

    def __init__(self, parent=None, *, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("smFRET BVA Analysis")
        self.data_folder: pathlib.Path | None = None
        self.analysis_folder: pathlib.Path | None = None
        self.file_type = "SPC-130"
        self.bva_settings = {}
        self._df: pd.DataFrame | None = None
        self._burst_df: pd.DataFrame | None = None
        self._tttrs: list | None = None
        self._static_line_item: pg.PlotDataItem | None = None
        # Coalesce parameter-change bursts (e.g. applying workflow context loads the
        # detector table, refreshes the donor/acceptor combos and sets the folder in
        # one turn, each of which fires ``_on_param_changed``) into a single recompute
        # via a zero-delay single-shot timer, and let callers suspend auto-recompute
        # entirely while applying a batch of settings.
        self._recompute_pending = False
        self._suspend_recompute = 0
        self._recompute_timer = QTimer(self)
        self._recompute_timer.setSingleShot(True)
        self._recompute_timer.setInterval(0)
        self._recompute_timer.timeout.connect(self._flush_recompute)
        self._build_ui()

    # ── recompute coalescing ──────────────────────────────────────────

    def suspend_recompute(self):
        """Context manager suppressing auto-recompute while applying settings.

        Rapid programmatic changes (workflow-context application) would otherwise
        each trigger a full read/compute/plot pass. Wrap them in this manager; a
        single coalesced recompute is scheduled on exit if any change requested one.
        """
        tool = self

        class _Suspend:
            def __enter__(self_inner):
                tool._suspend_recompute += 1

            def __exit__(self_inner, *exc):
                tool._suspend_recompute -= 1
                if tool._suspend_recompute == 0 and tool._recompute_pending:
                    tool._recompute_timer.start()
                return False

        return _Suspend()

    def _flush_recompute(self):
        """Run the single coalesced recompute scheduled by ``_on_param_changed``."""
        if not self._recompute_pending:
            return
        self._recompute_pending = False
        if self._burst_df is not None:
            self._compute_and_plot(write_output=False)
        elif self.data_folder is not None:
            # Read + compute share one progress dialog (no per-phase flashing).
            progress = self._begin_progress("Reading burst data...", 0)
            try:
                if self._read_burst_data(progress=progress):
                    self._compute_and_plot(write_output=False, progress=progress)
            finally:
                progress.close()

    # ── UI Build ──────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._setup_toolbar()
        main_layout.addWidget(self.toolbar)

        self.dock_area = DockArea()
        self.dock_area.addTab(self._build_settings_tab(), "BVA Settings", close_mode="hide")
        self.dock_area.addTab(self._build_channels_tab(), "Channel Definitions", close_mode="hide")
        self.plot_widget = pg.GraphicsLayoutWidget()
        self.dock_area.addTab(self.plot_widget, "Plot", close_mode="hide")
        self.dock_area.setContextMenuEnabled(True)
        self.dock_area.setContextMenuMode("basic")
        self._restore_dock_layout()
        self.dock_area.layoutChanged.connect(self._save_dock_layout)
        main_layout.addWidget(self.dock_area, 1)
        # Make the Plot dock absorb extra horizontal space (a QSplitter otherwise
        # redistributes a window resize ~50/50, drifting off the plot-dominant
        # default). Deferred so it runs after the splitter is laid out.
        QTimer.singleShot(0, self._bias_plot_width)

        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("color: #888; font-style: italic; padding: 0 8px;")
        self._status_label.setFixedHeight(22)
        main_layout.addWidget(self._status_label)
        # Embedded in the Burst Analysis shell the shared status bar carries all
        # messages, so the panel's own status line is redundant — hide it.
        if self._embedded:
            self._status_label.setVisible(False)

        self._connect_signals()
        self._setup_plot()
        self._load_settings()

    def _setup_toolbar(self):
        self.toolbar = QToolBar("Main")
        self.toolbar.setObjectName("bvaMainToolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setContentsMargins(4, 2, 4, 2)
        self.toolbar.layout().setSpacing(6)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toolbar.setStyleSheet(_TOOLBAR_STYLE)

        # Canonical shared actions (same icon / colour / order as every other
        # plugin toolbar). Detail lives in the tooltip; captions are icon-only.
        self.btn_folder = action_button("folder", tooltip="Select the burst analysis folder")
        self._folder_field = _FolderLineEdit(placeholder="No folder selected")
        self._folder_field.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_run = action_button("run", tooltip="Run BVA on all loaded data")
        self.btn_clear = action_button("clear", tooltip="Clear loaded data")
        self.btn_save = action_button("save", tooltip="Save BVA results")
        self.btn_save_settings = action_button("settings", tooltip="Save current settings as default")
        self.btn_help = action_button("help", tooltip="Show help")

        self.cb_toggle_static = QCheckBox("Show static line")
        self.cb_toggle_static.setChecked(True)
        self.cb_toggle_static.setStyleSheet("color: #aaa; font-size: 11px;")

        self._auto_update_cb = QCheckBox("Auto update")
        self._auto_update_cb.setChecked(True)
        self._auto_update_cb.setStyleSheet("color: #aaa; font-size: 11px;")

        # Left cluster: source, then the primary action group in canonical order.
        self.toolbar.addWidget(self.btn_folder)
        self.toolbar.addWidget(self.btn_run)
        self.toolbar.addWidget(self.btn_clear)
        self.toolbar.addWidget(self.btn_save)
        self.toolbar.addWidget(self._folder_field)
        # Middle: tool-specific view toggles + info, pushed to the right.
        self.toolbar.addWidget(self.cb_toggle_static)
        self.toolbar.addWidget(self._auto_update_cb)
        self._tb_info = QLabel("")
        self._tb_info.setStyleSheet("color: #aaa;")
        self.toolbar.addWidget(self._tb_info)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)
        # Right cluster: settings + help (canonical trailing position).
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.btn_save_settings)
        self.toolbar.addWidget(self.btn_help)
        self.btn_help.clicked.connect(self._show_help)

    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        param_group = QGroupBox("BVA Parameters")
        pf = QFormLayout(param_group)
        self.le_window_length = QLineEdit("0.01")
        self.le_photons_per_slice = QLineEdit("10")
        pf.addRow("Min window length (s):", self.le_window_length)
        pf.addRow("Photons per slice:", self.le_photons_per_slice)
        layout.addWidget(param_group)
        layout.addWidget(self._build_fret_pair_group())

        display_group = QGroupBox("Display")
        df_layout = QFormLayout(display_group)
        self.sb_bins_x = QSpinBox()
        self.sb_bins_x.setRange(10, 500)
        self.sb_bins_x.setValue(31)
        self.sb_bins_y = QSpinBox()
        self.sb_bins_y.setRange(10, 500)
        self.sb_bins_y.setValue(31)
        df_layout.addRow("Bins X:", self.sb_bins_x)
        df_layout.addRow("Bins Y:", self.sb_bins_y)
        layout.addWidget(display_group)

        layout.addStretch()

        # Keep the input fields compact so the settings column stays narrow and the
        # Plot dock gets the width (otherwise expanding fields set a wide minimum).
        for field in w.findChildren((QLineEdit, QComboBox, QSpinBox)):
            field.setMaximumWidth(190)

        return w

    def _build_fret_pair_group(self) -> QGroupBox:
        sel_group = QGroupBox("FRET Pair Assignment")
        sel_layout = QVBoxLayout(sel_group)
        sel_layout.setSpacing(6)

        setup_row = QHBoxLayout()
        setup_row.addWidget(QLabel("Setup:"))
        self.cb_setup = QComboBox()
        setup_row.addWidget(self.cb_setup, 1)
        sel_layout.addLayout(setup_row)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Donor detector:"))
        self.cb_donor = QComboBox()
        row1.addWidget(self.cb_donor, 1)
        sel_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Acceptor detector:"))
        self.cb_acceptor = QComboBox()
        row2.addWidget(self.cb_acceptor, 1)
        sel_layout.addLayout(row2)

        return sel_group

    def _build_channels_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        self.detector_page = DetectorWizardPage(parent=self)
        layout.addWidget(self.detector_page, 1)
        self.detector_page.detectorsChanged.connect(self._refresh_detector_combos)
        self.detector_page.setup_combo.currentIndexChanged.connect(self._refresh_setup_combo)
        self._refresh_detector_combos()
        self._refresh_setup_combo()
        return w

    def _refresh_detector_combos(self):
        settings = self.detector_page.get_settings()
        names = list(settings.get("detectors", {}).keys())
        # Preserve current selections
        donor_cur = self.cb_donor.currentText()
        acceptor_cur = self.cb_acceptor.currentText()
        self.cb_donor.clear()
        self.cb_acceptor.clear()
        self.cb_donor.addItems(names)
        self.cb_acceptor.addItems(names)
        # Restore if available
        if donor_cur in names:
            self.cb_donor.setCurrentText(donor_cur)
        elif names:
            self.cb_donor.setCurrentIndex(0)
        if acceptor_cur in names:
            self.cb_acceptor.setCurrentText(acceptor_cur)
        elif len(names) > 1:
            self.cb_acceptor.setCurrentIndex(1)
        elif names:
            self.cb_acceptor.setCurrentIndex(0)

    def _refresh_setup_combo(self):
        self.cb_setup.blockSignals(True)
        self.cb_setup.clear()
        self.cb_setup.addItem("")
        setups = load_detector_setups()
        for name in setups.get("setups", {}).keys():
            self.cb_setup.addItem(name)
        cur = self.detector_page.current_setup_name
        if cur:
            idx = self.cb_setup.findText(cur)
            if idx >= 0:
                self.cb_setup.setCurrentIndex(idx)
        self.cb_setup.blockSignals(False)

    def _on_setup_selected(self, index: int):
        if index <= 0:
            return
        name = self.cb_setup.currentText()
        if not name:
            return
        self.detector_page.setup_combo.setCurrentText(name)

    def _connect_signals(self):
        self.btn_folder.clicked.connect(self._select_folder)
        self._folder_field.folderDropped.connect(self._on_folder_dropped)
        self.cb_setup.currentIndexChanged.connect(self._on_setup_selected)
        self.btn_run.clicked.connect(self._run_analysis)
        self.cb_toggle_static.toggled.connect(self._toggle_static_line)
        self.btn_save.clicked.connect(self._save_plot)
        self.btn_clear.clicked.connect(self._clear_plot)
        self.btn_save_settings.clicked.connect(self._save_settings)
        self.le_window_length.editingFinished.connect(self._on_param_changed)
        self.le_photons_per_slice.editingFinished.connect(self._on_param_changed)
        self.cb_donor.currentIndexChanged.connect(self._on_param_changed)
        self.cb_acceptor.currentIndexChanged.connect(self._on_param_changed)
        self.detector_page.detectorsChanged.connect(self._on_param_changed)
        self.sb_bins_x.valueChanged.connect(self._on_bin_changed)
        self.sb_bins_y.valueChanged.connect(self._on_bin_changed)

    # ── Plot helpers ────────────────────────────────────────────────

    def _setup_plot(self):
        plot = self.plot_widget.addPlot()
        plot.setLabels(bottom="Mean Proximity Ratio", left="Std Proximity Ratio")
        plot.setRange(xRange=(-0.05, 1.05), yRange=(-0.01, 0.44))
        plot.showGrid(x=True, y=True, alpha=0.3)

        self._image_item = pg.ImageItem(axisOrder='col-major')
        plot.addItem(self._image_item)

        self._static_line_item = pg.PlotDataItem(
            pen=pg.mkPen(color="#ff6b6b", width=2),
        )
        plot.addItem(self._static_line_item)

        self._profile_mean_item = pg.PlotDataItem(
            pen=pg.mkPen(color="cyan", width=2),
            symbol='o', symbolSize=4, symbolBrush=(0, 255, 255, 150),
        )
        plot.addItem(self._profile_mean_item)
        self._profile_error_item = pg.ErrorBarItem(beam=0.01)
        plot.addItem(self._profile_error_item)

        self._hist_lut = pg.HistogramLUTItem()
        self._hist_lut.setImageItem(self._image_item)
        cm = pg.colormap.get("CET-L4")
        self._hist_lut.gradient.setColorMap(cm)
        self.plot_widget.addItem(self._hist_lut)
        self._plot_ref = plot

    @staticmethod
    def _average_histogram(
            counts: np.ndarray,
            x_edges: np.ndarray,
            y_edges: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        y = y_edges[:-1] + np.diff(y_edges) / 2
        y2 = y * y
        mean = np.full(counts.shape[0], np.nan)
        sd = np.full(counts.shape[0], np.nan)
        for i in range(counts.shape[0]):
            c = counts[i]
            s = c.sum()
            if s == 0:
                continue
            m1 = c @ y / s
            m2 = c @ y2 / s
            mean[i] = m1
            sd[i] = np.sqrt(max(m2 - m1 * m1, 0.0)) / np.sqrt(s)
        return mean, sd

    def _plot_2d_histogram(
        self, x, y,
        range_x=(-0.05, 1.05), range_y=(-0.01, 0.44),
        bins_x=51, bins_y=51, vmin=0.1, vmax=None,
    ):
        hist, x_edges, y_edges = np.histogram2d(
            x, y, bins=(bins_x, bins_y), range=[range_x, range_y],
        )
        if vmax is None:
            vmax = hist.max()
        if vmin is None:
            vmin = hist.min()
        clipped = np.clip(hist, vmin, vmax)
        self._image_item.setImage(clipped)
        self._image_item.setRect(
            range_x[0], range_y[0],
            range_x[1] - range_x[0], range_y[1] - range_y[0],
        )
        mean, sd = self._average_histogram(hist, x_edges, y_edges)
        x_centers = (x_edges[:-1] + x_edges[1:]) / 2
        self._profile_mean_item.setData(x_centers, mean)
        self._profile_error_item.setData(
            x=x_centers, y=mean, top=sd, bottom=sd,
        )

    def _plot_static_line(self, n_photons: int = 10):
        x_axis = np.linspace(0, 1, 131)
        mean_sim, std_sim = core.compute_static_bva_line(
            x_axis, number_of_photons_per_slice=n_photons,
        )
        self._static_line_item.setData(mean_sim, std_sim)

    # ── Settings helper ──────────────────────────────────────────────

    def _get_bva_settings(self) -> Dict:
        settings = self.detector_page.get_settings()
        detectors = settings.get("detectors", {})
        donor_name = self.cb_donor.currentText()
        acceptor_name = self.cb_acceptor.currentText()

        def _det(name):
            d = detectors.get(name, {})
            return {
                "chs": d.get("chs", [0, 8]),
                "micro_time_ranges": d.get("micro_time_ranges", [(0, 32768)]),
            }

        donor = _det(donor_name)
        acceptor = _det(acceptor_name)
        self.file_type = settings.get("tttr_reading", {}).get("file_type", "SPC-130")

        try:
            window_length = float(self.le_window_length.text())
        except ValueError:
            raise ValueError("Invalid minimum window length")
        try:
            photons_slice = int(self.le_photons_per_slice.text())
        except ValueError:
            raise ValueError("Invalid photons per slice")

        return {
            "donor_channels": donor["chs"],
            "donor_micro_time_ranges": donor["micro_time_ranges"],
            "acceptor_channels": acceptor["chs"],
            "acceptor_micro_time_ranges": acceptor["micro_time_ranges"],
            "minimum_window_length": window_length,
            "number_of_photons_per_slice": photons_slice,
        }

    # ── Slots ────────────────────────────────────────────────────────

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Data Folder")
        if folder:
            self._set_folder(folder)

    def _set_folder(self, path: str):
        p = pathlib.Path(path)
        if p.is_dir():
            self.data_folder = p
            self.analysis_folder = p
            self._folder_field.setText(str(p))
            self._status(f"Data folder: {p}")
            self._on_param_changed()

    def _on_folder_dropped(self, path: str):
        self._set_folder(path)

    def _reporter(self):
        """Return the hosting shell's status bar when embedded, else ``None``."""
        from chisurf.gui.widgets.navigation import find_status_reporter

        return find_status_reporter(self)

    def _notify_error(self, title: str, msg: str) -> None:
        """Log the error (shown in the shell status bar when embedded); box if standalone."""
        logging.getLogger(__name__).error("%s: %s", title, msg)
        if not self._embedded:
            QMessageBox.critical(self, title, msg)

    def _begin_progress(self, message: str, max_value: int):
        """Return a single progress handle for a fresh phase.

        When embedded in the Burst Analysis shell this is a status-bar-backed
        handle (no popup); standalone it is a modal ``_ProgressDialog``. Either way
        it duck-types ``label`` / ``progress`` / ``set_value`` / ``close`` so all
        phases of one run share **one** progress surface instead of flashing per
        phase.
        """
        reporter = self._reporter()
        if reporter is not None:
            return reporter.begin_task(message, max_value)
        progress = _ProgressDialog(
            title="BVA Analysis", message=message, max_value=max_value, parent=self,
        )
        progress.show()
        QCoreApplication.processEvents()
        return progress

    @staticmethod
    def _phase(progress, message: str, max_value: int):
        """Retarget an existing progress dialog to the next phase (label + range)."""
        progress.label.setText(message)
        progress.progress.setRange(0, max_value)
        progress.progress.setValue(0)
        QCoreApplication.processEvents()

    def _read_burst_data(self, progress=None) -> bool:
        """Read burst data from the analysis folder and store it.

        When *progress* is given the phase reuses that shared dialog; otherwise a
        transient one is created and closed here.
        """
        if not self.data_folder:
            return False
        own = progress is None
        # Reading has no incremental hook, so show a busy (indeterminate) bar.
        if own:
            progress = self._begin_progress("Reading burst data...", 0)
        else:
            self._phase(progress, "Reading burst data...", 0)
        try:
            self._burst_df, self._tttrs = core.read_burst_analysis(
                self.analysis_folder, self.file_type, pattern="bi4_bur",
            )
            if own:
                progress.close()
            return True
        except Exception as e:
            if own:
                progress.close()
            self._notify_error("Read Error", f"Could not read burst data: {e}")
            return False

    def _compute_and_plot(self, write_output: bool = False, progress=None):
        """Compute BVA from stored burst data and update the plot.

        When *progress* is given the compute/write phases reuse that shared dialog;
        otherwise a transient one is created and closed here.
        """
        if self._burst_df is None or self._tttrs is None:
            return
        try:
            self.bva_settings = self._get_bva_settings()
        except Exception as e:
            self._notify_error("BVA Settings Error", str(e))
            return

        own = progress is None
        if own:
            progress = self._begin_progress("Computing BVA...", len(self._burst_df))
        else:
            self._phase(progress, "Computing BVA...", len(self._burst_df))

        try:
            df_v = core.compute_bva(
                self._burst_df, self._tttrs, progress_window=progress, **self.bva_settings,
            )
        except Exception as e:
            if own:
                progress.close()
            self._notify_error("BVA Error", str(e))
            return

        self._df = df_v

        df_selected = df_v[df_v["Proximity Ratio Std"] > 0.0]
        x = df_selected["Proximity Ratio Mean"].values
        y = df_selected["Proximity Ratio Std"].values

        n_photons = self.bva_settings.get("number_of_photons_per_slice", 10)
        if n_photons < 0:
            n_photons = 100

        self._plot_2d_histogram(
            x, y,
            bins_x=self.sb_bins_x.value(),
            bins_y=self.sb_bins_y.value(),
        )
        self._plot_static_line(n_photons)

        if write_output:
            # Reuse the same progress dialog for the write phase so a single run
            # shows one window through compute → write.
            self._phase(
                progress, "Writing BV4 files...", len(df_v.groupby("First File"))
            )
            try:
                core.write_bv4_analysis(
                    df_v, str(self.analysis_folder), progress_window=progress,
                )
            except Exception as e:
                logging.error(f"BV4 write failed: {e}")

            bv4_folder = self.analysis_folder / "bv4"
            bv4_folder.mkdir(parents=True, exist_ok=True)
            settings_path = bv4_folder / "bva_settings.json"
            with open(settings_path, "w") as f:
                json.dump(self.bva_settings, f, indent=4)
            logging.info(f"BVA settings saved to {settings_path}")

        if own:
            progress.close()

        self._tb_info.setText(f"{len(df_selected)} / {len(df_v)} bursts")
        self._status(
            f"Done \u2013 {len(df_selected)} bursts with Std > 0 on {len(df_v)} total"
        )

    def _run_analysis(self):
        if not self.data_folder:
            self._notify_error("Error", "Please select a data folder first.")
            return
        # One shared progress dialog spans read \u2192 compute \u2192 write.
        progress = self._begin_progress("Reading burst data...", 0)
        try:
            if not self._read_burst_data(progress=progress):
                return
            self._compute_and_plot(write_output=True, progress=progress)
        finally:
            progress.close()

    def _on_param_changed(self):
        if not self._auto_update_cb.isChecked():
            return
        # Coalesce this change into one recompute. While a batch of settings is
        # being applied (suspend_recompute) just remember that a recompute is due;
        # otherwise schedule the single-shot flush, which collapses several changes
        # fired in the same event-loop turn into a single read/compute/plot pass.
        self._recompute_pending = True
        if self._suspend_recompute == 0:
            self._recompute_timer.start()

    def _on_bin_changed(self):
        if not self._auto_update_cb.isChecked():
            return
        if self._df is not None:
            df_selected = self._df[self._df["Proximity Ratio Std"] > 0.0]
            x = df_selected["Proximity Ratio Mean"].values
            y = df_selected["Proximity Ratio Std"].values
            self._plot_2d_histogram(
                x, y,
                bins_x=self.sb_bins_x.value(),
                bins_y=self.sb_bins_y.value(),
            )

    def _save_settings(self):
        ini = QSettings(str(get_plugin_settings_path("burst_bva")), QSettings.IniFormat)
        ini.setValue("window_length", self.le_window_length.text())
        ini.setValue("photons_per_slice", self.le_photons_per_slice.text())
        ini.setValue("bins_x", self.sb_bins_x.value())
        ini.setValue("bins_y", self.sb_bins_y.value())
        if self.data_folder is not None:
            ini.setValue("last_folder", str(self.data_folder))
        self._status("Settings saved")

    def _load_settings(self):
        ini = QSettings(str(get_plugin_settings_path("burst_bva")), QSettings.IniFormat)
        wl = ini.value("window_length")
        if wl is not None:
            self.le_window_length.setText(str(wl))
        pps = ini.value("photons_per_slice")
        if pps is not None:
            self.le_photons_per_slice.setText(str(pps))
        bx = ini.value("bins_x")
        if bx is not None:
            self.sb_bins_x.setValue(int(bx))
        by = ini.value("bins_y")
        if by is not None:
            self.sb_bins_y.setValue(int(by))
        lf = ini.value("last_folder")
        if lf is not None:
            p = pathlib.Path(str(lf))
            if p.is_dir():
                self._set_folder(str(p))

    def _toggle_static_line(self, visible: bool):
        if self._static_line_item:
            self._static_line_item.setVisible(visible)

    def _save_plot(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Plot", "bva_plot.png", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)",
        )
        if path:
            self.plot_widget.grab().save(path)

    def _clear_plot(self):
        self._image_item.clear()
        self._static_line_item.clear()
        self._df = None
        self._tb_info.setText("No data loaded")
        self._status("Plot cleared")

    def _status(self, msg: str):
        self._status_label.setText(msg)
        # Report via normal logging; the shell's status bar shows it when embedded.
        logging.getLogger(__name__).info(msg)
        QCoreApplication.processEvents()

    def _show_help(self):
        """Show the help dialog."""
        dialog = HelpDialog(self)
        dialog.exec_()

    def closeEvent(self, event):
        self._save_dock_layout()
        super().closeEvent(event)

    def _bias_plot_width(self) -> None:
        """Bias the horizontal split so the Plot dock keeps most of the width.

        A ``QSplitter`` redistributes a window resize by stretch factor; without
        this the compact settings and the plot drift back toward 50/50 and the
        plot looks cramped. Give every child but the last (the Plot, per the
        default layout) zero stretch and seed a ~1/3 : 2/3 split.
        """
        try:
            from qtpy.QtWidgets import QSplitter

            for sp in self.dock_area.findChildren(QSplitter):
                if sp.orientation() != Qt.Horizontal or sp.count() < 2:
                    continue
                for i in range(sp.count()):
                    sp.setStretchFactor(i, 0)
                sp.setStretchFactor(sp.count() - 1, 1)
                total = sp.width() or 1200
                left = max(360, int(total * 0.32))
                sp.setSizes([left, max(1, total - left)])
        except Exception:
            pass

    @staticmethod
    def _default_dock_layout() -> dict:
        """Plot-dominant default: settings/channels on the left, a wide Plot right.

        The settings need little width, so give the Plot ~2/3 of the horizontal
        space (it otherwise inherited a stale 50/50 saved split and looked
        cramped). Users can still drag/re-tab; their arrangement is saved.
        """
        def _tab(*names):
            return {
                "type": "tab",
                "current_index": 0,
                "tabs": [{"widget_key": n, "tab_name": n, "tab_text": n} for n in names],
            }

        return {
            "version": 1,
            "root": {
                "type": "splitter",
                "orientation": "horizontal",
                "sizes": [430, 900],
                "children": [_tab("BVA Settings", "Channel Definitions"), _tab("Plot")],
            },
            "active_tab_widget": [],
            "current_index": 0,
        }

    def _save_dock_layout(self):
        try:
            settings = QSettings("chisurf", "BVATool")
            layout_state = self.dock_area.get_layout_state()
            # v2: dropped the old (often stale 50/50) "dock_layout" key so the new
            # plot-dominant default applies once.
            settings.setValue("dock_layout_v2", json.dumps(layout_state, sort_keys=True))
            if not self._embedded:
                settings.setValue("window_geometry", self.saveGeometry())
                settings.setValue("window_state", self.saveState())
            settings.sync()
        except Exception as exc:
            pass

    def _restore_dock_layout(self):
        try:
            settings = QSettings("chisurf", "BVATool")
            value = settings.value("dock_layout_v2")
            if isinstance(value, str):
                layout_state = json.loads(value)
            elif isinstance(value, dict):
                layout_state = value
            else:
                # No saved arrangement yet — apply the plot-dominant default.
                self.dock_area.set_layout_state(self._default_dock_layout(), emit_change=False)
                return
            if not self._embedded:
                geometry = settings.value("window_geometry")
                if geometry is not None:
                    self.restoreGeometry(geometry)
                state = settings.value("window_state")
                if state is not None:
                    self.restoreState(state)
            self.dock_area.set_layout_state(layout_state, emit_change=False)
        except Exception as exc:
            pass
