"""Burst Variance Analysis (BVA) tool with toolbar, tabbed settings, and pyqtgraph plot."""

from __future__ import annotations

import json
import pathlib
from typing import Dict, Tuple

import numpy as np
import pandas as pd
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
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from chisurf import logging
from chisurf.gui import chiplot as cp
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
from chisurf.gui import dialogs
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.event_pump import pump_ui
from chisurf.gui.widgets.messages import MessagesMixin, Msg


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
)
from chisurf.gui.widgets.tool_buttons import (
    action_button,
)

from chisurf.core import analysis_cache  # noqa: E402


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


@persist_plugin_state("burst_bva")
class BVATool(MessagesMixin, QMainWindow):
    """BVA analysis widget with toolbar, tabbed settings, and pyqtgraph plot."""

    class Error(MessagesMixin.Error):
        """Conditions that stop a BVA run, or that a run ended in."""

        no_folder = Msg("Select a data folder first.")
        bad_settings = Msg("BVA settings: {}")
        failed = Msg("BVA failed: {}")

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
        # What the displayed result was computed from, so an identical request
        # (a panel revisit, another Next) does not recompute it.
        self._result_cache = analysis_cache.ResultCache()
        self._running_fingerprint: str | None = None
        self._static_line_item: cp.handles.Curve | None = None
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
        self._start_analysis(write_output=False)

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
        self.plot_widget = cp.Grid()
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
        plot = self.plot_widget.add_plot()
        plot.set_labels(bottom="Mean Proximity Ratio", left="Std Proximity Ratio")
        plot.set_range(x=(-0.05, 1.05), y=(-0.01, 0.44))
        plot.grid(x=True, y=True, alpha=0.3)

        self._image_item = plot.image(np.zeros((1, 1)), axis_order='col-major')

        self._static_line_item = plot.line([], [], pen=cp.to_pen("#ff6b6b", width=2))

        self._profile_mean_item = plot.line(
            [], [], pen=cp.to_pen("cyan", width=2),
            symbol='o', symbol_size=4, symbol_brush=(0, 255, 255, 150),
        )
        # Asymmetric extents from the start: the profile is updated with
        # top/bottom, and a handle created with `height` would keep that mode.
        self._profile_error_item = plot.errorbars(
            np.array([]), np.array([]),
            top=np.array([]), bottom=np.array([]), beam=0.01,
        )

        self._hist_lut = self.plot_widget.add_colorbar(self._image_item, colormap="CET-L4")
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
        self._image_item.set_image(clipped)
        self._image_item.set_rect(
            range_x[0], range_y[0],
            range_x[1] - range_x[0], range_y[1] - range_y[0],
        )
        mean, sd = self._average_histogram(hist, x_edges, y_edges)
        x_centers = (x_edges[:-1] + x_edges[1:]) / 2
        self._profile_mean_item.set_data(x_centers, mean)
        self._profile_error_item.set_data(
            x_centers, mean, top=sd, bottom=sd,
        )

    def _plot_static_line(self, n_photons: int = 10):
        x_axis = np.linspace(0, 1, 131)
        mean_sim, std_sim = core.compute_static_bva_line(
            x_axis, number_of_photons_per_slice=n_photons,
        )
        self._static_line_item.set_data(mean_sim, std_sim)

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

    def _notify_error(self, title: str, msg: str) -> None:
        """Log the error (shown in the shell status bar when embedded); box if standalone."""
        logging.getLogger(__name__).error("%s: %s", title, msg)
        if not self._embedded:
            dialogs.error(self, title, msg)

    def _run_analysis(self):
        """Run the full analysis and write the BV4 output."""
        self._start_analysis(write_output=True)

    # ── reuse instead of recompute ───────────────────────────────────

    def input_files(self) -> list[pathlib.Path]:
        """The burst files this analysis reads (``bi4_bur/*``).

        These are what identifies the input: they are themselves the product of
        the raw TTTR files, so raw data that changed under them means step 2 has
        to run again anyway, and stat-ing a burst folder is far cheaper than
        stat-ing gigabytes of photon data.
        """
        folder = self.analysis_folder
        if folder is None:
            return []
        return [
            f
            for d in sorted(pathlib.Path(folder).glob("bi4_bur"))
            for f in sorted(d.glob("*"))
            if f.is_file()
        ]

    def _stamp_path(self) -> pathlib.Path | None:
        """Where the BV4 outputs record what produced them."""
        if self.analysis_folder is None:
            return None
        return pathlib.Path(self.analysis_folder) / "bv4" / "bva.stamp.json"

    def analysis_fingerprint(self, settings: dict) -> str:
        """Fingerprint of the burst files plus *settings* (see analysis_cache)."""
        return analysis_cache.fingerprint(self.input_files(), settings, extra="bva")

    def _start_analysis(self, *, write_output: bool, force: bool = False) -> None:
        """Read, compute and (optionally) write BVA off the GUI thread.

        Reading a folder of burst files and correlating every burst are both
        long; running them here froze the window for the whole batch behind a
        modal bar. Only the plotting stays on the GUI thread, in
        :meth:`_analysis_done`.

        A run whose inputs and settings are identical to the result already on
        screen is skipped: the workflow shell re-applies the burst folder on
        every visit to this step and clicks Run on every *Next*, so without this
        the same correlation was computed again each time the user looked at the
        plot. Pass ``force=True`` to recompute regardless.
        """
        if not self.data_folder:
            self.Error.no_folder()
            return
        self.Error.no_folder.clear()
        try:
            self.bva_settings = self._get_bva_settings()
        except Exception as exc:
            self.Error.bad_settings(exc)
            return
        self.Error.bad_settings.clear()

        fingerprint = self.analysis_fingerprint(self.bva_settings)
        stamp = self._stamp_path()
        # Writing is a second obligation: a preview run (write_output=False) can
        # satisfy a later preview but not a later Run, unless the BV4 files on
        # disk were written for exactly this fingerprint.
        outputs_current = bool(stamp) and analysis_cache.is_current(stamp, fingerprint)
        if (
            not force
            and self._df is not None
            and self._result_cache.matches(fingerprint)
            and (not write_output or outputs_current)
        ):
            self._status("Unchanged — kept the previous BVA result")
            return

        self._running_fingerprint = fingerprint
        ChiSurfProgress.run(
            self, "Reading burst data...", self._analysis_worker,
            args=(dict(self.bva_settings), bool(write_output), fingerprint),
            maximum=0, title="BVA Analysis", owner=self,
            on_result=self._analysis_done,
            on_error=self._analysis_failed,
        )

    def _analysis_failed(self, exc) -> None:
        """A failed run leaves no result to reuse."""
        self._result_cache.invalidate()
        self.Error.failed(exc)

    def _analysis_worker(self, settings, write_output, fingerprint, task):
        """Worker: read (if needed), compute, write. No GUI here.

        Each phase announces its own length through ``task.set_range`` rather
        than sharing one invented scale, and the core keeps its
        ``progress_window`` argument — the adapter also turns every ``set_value``
        into a cancellation check, which this analysis never had.
        """
        burst_df, tttrs = self._burst_df, self._tttrs
        if burst_df is None or tttrs is None:
            task.set_range(0, 0)          # reading has no incremental hook
            task.set_text("Reading burst data...")
            burst_df, tttrs = core.read_burst_analysis(
                self.analysis_folder, self.file_type, pattern="bi4_bur",
            )

        task.set_range(0, len(burst_df))
        task.set_text("Computing BVA...")
        df_v = core.compute_bva(
            burst_df, tttrs,
            progress_window=task.progress_window("Computing BVA..."),
            **settings,
        )

        if write_output:
            task.set_range(0, len(df_v.groupby("First File")))
            task.set_text("Writing BV4 files...")
            try:
                core.write_bv4_analysis(
                    df_v, str(self.analysis_folder),
                    progress_window=task.progress_window("Writing BV4 files..."),
                )
            except Exception as e:
                logging.error(f"BV4 write failed: {e}")
            bv4_folder = self.analysis_folder / "bv4"
            bv4_folder.mkdir(parents=True, exist_ok=True)
            with open(bv4_folder / "bva_settings.json", "w") as f:
                json.dump(settings, f, indent=4)
            # Record what these BV4 files are the result of, so a later run with
            # the same burst files and settings can leave them alone.
            analysis_cache.write_stamp(
                bv4_folder / "bva.stamp.json", fingerprint,
                params=settings, inputs=self.input_files(),
                outputs=sorted(bv4_folder.glob("*.bv4")), tool="bva",
            )
        return burst_df, tttrs, df_v

    def _analysis_done(self, payload) -> None:
        """Back on the GUI thread with the BVA table: draw it."""
        self._burst_df, self._tttrs, df_v = payload
        self._df = df_v
        if self._running_fingerprint is not None:
            self._result_cache.remember(self._running_fingerprint)

        df_selected = df_v[df_v["Proximity Ratio Std"] > 0.0]
        n_photons = self.bva_settings.get("number_of_photons_per_slice", 10)
        if n_photons < 0:
            n_photons = 100
        self._plot_2d_histogram(
            df_selected["Proximity Ratio Mean"].values,
            df_selected["Proximity Ratio Std"].values,
            bins_x=self.sb_bins_x.value(),
            bins_y=self.sb_bins_y.value(),
        )
        self._plot_static_line(n_photons)
        self._tb_info.setText(f"{len(df_selected)} / {len(df_v)} bursts")
        self._status(
            f"Done \u2013 {len(df_selected)} bursts with Std > 0 on {len(df_v)} total"
        )

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
            self._static_line_item.visible = visible

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
        self._result_cache.invalidate()
        self._tb_info.setText("No data loaded")
        self._status("Plot cleared")

    def _status(self, msg: str):
        self._status_label.setText(msg)
        # Report via normal logging; the shell's status bar shows it when embedded.
        logging.getLogger(__name__).info(msg)
        # Repaint through the shared guarded pump: a bare processEvents here
        # delivers the queued log signal back into another status update and
        # nests the two (see chisurf.gui.event_pump).
        pump_ui(allow_input=False)

    def _show_help(self):
        """Show the help dialog."""
        dialog = HelpDialog(self)
        dialog.exec_()

    def closeEvent(self, event):
        self._save_dock_layout()
        super().closeEvent(event)

    def _bias_plot_width(self) -> None:
        """Force the Plot dock to keep most of the width.

        A ``QSplitter`` redistributes a window resize by stretch factor and the
        settings form's minimum width fights any seeded sizes, so the plot kept
        drifting narrow. Identify the non-plot (settings) child of each horizontal
        split and hard-cap its width; the plot child then absorbs everything else
        (stretch=1, no cap). This holds regardless of layout timing.
        """
        try:
            from qtpy.QtWidgets import QSplitter

            SETTINGS_MAX = 440
            for sp in self.dock_area.findChildren(QSplitter):
                if sp.orientation() != Qt.Horizontal or sp.count() < 2:
                    continue
                for i in range(sp.count()):
                    child = sp.widget(i)
                    holds_plot = child is self.plot_widget or child.isAncestorOf(self.plot_widget)
                    if holds_plot:
                        sp.setStretchFactor(i, 1)
                        child.setMaximumWidth(16777215)
                    else:
                        sp.setStretchFactor(i, 0)
                        child.setMaximumWidth(SETTINGS_MAX)
                total = sp.width() or 1200
                sp.setSizes([SETTINGS_MAX, max(1, total - SETTINGS_MAX)])
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
