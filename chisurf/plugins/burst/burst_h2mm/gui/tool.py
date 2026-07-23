"""H2MM analysis tool: toolbar, tabbed settings, and pyqtgraph result plots."""

from __future__ import annotations

import pathlib
import threading
import time
from typing import Any

import numpy as np
import pyqtgraph as pg
from qtpy.QtCore import (
    QCoreApplication,
    QObject,
    QSettings,
    QSize,
    Qt,
    QThreadPool,
    Signal,
)
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
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from chisurf import logging
from chisurf.gui.misc_helpers import get_plugin_settings_path, persist_plugin_state
from chisurf.gui.widgets.dock_area.dock_area import DockArea
from chisurf.gui.widgets.progress import EnhancedProgressDialog, Worker
from chisurf.gui.widgets.wizard import DetectorWizardPage

from ..api.models import H2mmSettings, StreamSettings
from ..backend.services import run_analysis
from ..core.engines import ENGINE_LABELS
from ..core.engines import ENGINES as H2mmEngines


class _FitCancelled(Exception):
    """Raised inside the fit worker when the user cancels the progress dialog."""


class _FitSignals(QObject):
    """Cross-thread progress signal carrying ``(done, total, fits_or_None)``."""

    tick = Signal(float, int, object)


class _UncertSignals(QObject):
    """Cross-thread bootstrap-progress signal carrying ``(done, n_boot)``."""

    tick = Signal(int, int)

_STATE_COLORS = [
    "#4e79a7", "#f28e2b", "#59a14f", "#e15759",
    "#b07aa1", "#76b7b2", "#edc948", "#ff9da7",
]


class _FolderLineEdit(QLineEdit):
    """QLineEdit that accepts a folder drop."""

    folderDropped = Signal(str)

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setReadOnly(True)
        self.setAcceptDrops(True)
        self.setStyleSheet("color: #aaa; padding: 0 4px; background: transparent; border: none;")

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accept a drag that carries file URLs."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """Emit the dropped folder path."""
        urls = event.mimeData().urls()
        if urls and urls[0].toLocalFile():
            self.setText(urls[0].toLocalFile())
            self.folderDropped.emit(urls[0].toLocalFile())


class HelpDialog(QDialog):
    """About/help dialog with a CLI reference."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About H2MM")
        self.resize(620, 520)
        layout = QVBoxLayout(self)
        text = QTextEdit(self)
        text.setReadOnly(True)
        cli_text = ""
        try:
            from click.testing import CliRunner

            from ..cli.main import cli

            cli_text = "<pre>\n" + CliRunner().invoke(cli, ["compute", "--help"]).output + "</pre>"
        except Exception as exc:  # pragma: no cover
            cli_text = f"<p>CLI help unavailable: {exc}</p>"
        text.setHtml(
            """
            <h2>Photon-by-photon HMM (H2MM)</h2>
            <p>H2MM fits a Hidden Markov Model directly to photon arrival times and
            colours within bursts, resolving sub-burst FRET-state dynamics on the
            microsecond scale (Pirchi <i>et al.</i>, J. Phys. Chem. B 2016).</p>
            <h3>Workflow</h3>
            <ol>
              <li>Select a folder of <code>.bur</code> burst files.</li>
              <li>Define donor/acceptor detector channels (and, for µsALEX/PIE
                  data, an optional acceptor-excitation stream for stoichiometry).</li>
              <li>Choose the state range and BIC/ICL selection.</li>
              <li><b>Run</b> to fit models and view the dwell FRET (E histogram or
                  E–S scatter), transition-density plot, model selection,
                  dwell-time distributions, per-state fluorescence decays, and an
                  interactive per-burst Viterbi state-path viewer.</li>
            </ol>
            <hr><h3>CLI reference</h3>
            """
            + cli_text
        )
        layout.addWidget(text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


@persist_plugin_state("burst_h2mm")
class H2mmTool(QMainWindow):
    """H2MM analysis widget with toolbar, tabbed settings, and result plots."""

    def __init__(self, parent=None, *, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("smFRET H2MM Analysis  ⚠️ experimental")
        self.data_folder: pathlib.Path | None = None
        self.file_type = "SPC-130"
        self._result = None
        self._bundle = None
        self._uncertainty = None
        self._build_ui()

    # ── UI build ─────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._setup_toolbar()
        layout.addWidget(self.toolbar)

        self.dock_area = DockArea()
        self.dock_area.addTab(self._build_settings_tab(), "H2MM Settings", close_mode="hide")
        self.dock_area.addTab(self._build_channels_tab(), "Channel Definitions", close_mode="hide")
        self.dock_area.addTab(self._build_plots(), "Results", close_mode="hide")
        layout.addWidget(self.dock_area, 1)

        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("color: #888; font-style: italic; padding: 0 8px;")
        self._status_label.setFixedHeight(22)
        layout.addWidget(self._status_label)

        self._connect_signals()
        self._load_settings()

    def _setup_toolbar(self):
        self.toolbar = QToolBar("Main")
        self.toolbar.setObjectName("h2mmMainToolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        def _tbtn(text):
            btn = QToolButton()
            btn.setText(text)
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            return btn

        self.btn_folder = _tbtn("\U0001f4c2  Data")
        self._folder_field = _FolderLineEdit(placeholder="No folder selected")
        self._folder_field.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_run = _tbtn("▶  Run")
        self.btn_uncert = _tbtn("±  Uncertainty")
        self.btn_uncert.setToolTip(
            "Bootstrap the selected model over bursts to put confidence intervals "
            "on the per-state E/S (overlaid as error bars). Compute-heavy — run "
            "after a fit."
        )
        self.btn_save = _tbtn("\U0001f4be  Save plot")
        self.btn_help = _tbtn("ℹ️  Help")

        self.toolbar.addWidget(self.btn_folder)
        self.toolbar.addWidget(self._folder_field)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.btn_run)
        self.toolbar.addWidget(self.btn_uncert)
        self.toolbar.addWidget(self.btn_save)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.btn_help)

    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        group = QGroupBox("Model Selection")
        f = QFormLayout(group)
        self.sb_min_states = QSpinBox()
        self.sb_min_states.setRange(1, 8)
        self.sb_min_states.setValue(1)
        self.sb_max_states = QSpinBox()
        self.sb_max_states.setRange(1, 8)
        self.sb_max_states.setValue(3)
        self.cb_criterion = QComboBox()
        self.cb_criterion.addItems(["bic", "icl"])
        self.sb_patience = QSpinBox()
        self.sb_patience.setRange(-1, 8)
        self.sb_patience.setValue(1)   # default: safe early-stop (~1.6× faster scan)
        self.sb_patience.setSpecialValueText("off (scan all)")
        self.sb_patience.setToolTip(
            "Early-stop the state-count scan once the criterion rises "
            "(safe ~1.6× faster). 'off' fits every state count."
        )
        f.addRow("Min states:", self.sb_min_states)
        f.addRow("Max states:", self.sb_max_states)
        f.addRow("Criterion:", self.cb_criterion)
        f.addRow("Scan patience:", self.sb_patience)
        layout.addWidget(group)

        opt = QGroupBox("Optimisation")
        of = QFormLayout(opt)
        self.cb_engine = QComboBox()
        for _e in H2mmEngines:
            self.cb_engine.addItem(ENGINE_LABELS.get(_e, _e), _e)
        # Default to the fastest always-available method (float32 EM).
        _fast = self.cb_engine.findData("em-float32")
        if _fast >= 0:
            self.cb_engine.setCurrentIndex(_fast)
        self.cb_engine.setToolTip(
            "Compute engine: exact EM, a fast float32 EM (default), or the "
            "amortised neural surrogate (fastest, approximate)."
        )
        of.addRow("Engine:", self.cb_engine)
        self.sb_restarts = QSpinBox()
        self.sb_restarts.setRange(1, 20)
        self.sb_restarts.setValue(2)
        self.sb_max_iter = QSpinBox()
        self.sb_max_iter.setRange(10, 5000)
        self.sb_max_iter.setValue(500)
        self.sb_min_photons = QSpinBox()
        self.sb_min_photons.setRange(2, 1000)
        self.sb_min_photons.setValue(5)
        self.sb_time_scale = QSpinBox()
        self.sb_time_scale.setRange(1, 100000)
        self.sb_time_scale.setValue(1)
        self.sb_divisors = QSpinBox()
        self.sb_divisors.setRange(1, 8)
        self.sb_divisors.setValue(1)
        self.sb_divisors.setSpecialValueText("off (E only)")
        self.sb_divisors.setToolTip(
            "Nanotime divisors: split each stream into this many micro-time "
            "(fluorescence-lifetime) bins so H2MM can separate states that share "
            "an apparent FRET E but differ in lifetime. 1 = off."
        )
        of.addRow("Restarts:", self.sb_restarts)
        of.addRow("Max iterations:", self.sb_max_iter)
        of.addRow("Min photons/burst:", self.sb_min_photons)
        of.addRow("Macro-time scale:", self.sb_time_scale)
        of.addRow("Nanotime divisors:", self.sb_divisors)
        layout.addWidget(opt)
        layout.addStretch()
        return w

    def _build_channels_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        sel = QGroupBox("FRET Pair Assignment")
        sl = QVBoxLayout(sel)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Donor detector:"))
        self.cb_donor = QComboBox()
        row1.addWidget(self.cb_donor, 1)
        sl.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Acceptor detector:"))
        self.cb_acceptor = QComboBox()
        row2.addWidget(self.cb_acceptor, 1)
        sl.addLayout(row2)
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Acceptor (Aex):"))
        self.cb_aex = QComboBox()
        self.cb_aex.setToolTip(
            "Optional acceptor-excitation stream for µsALEX/PIE data (e.g. the "
            "'yellow' acceptor-emission-after-acceptor-excitation window). When "
            "set, per-state stoichiometry S and a dwell E–S scatter are computed; "
            "leave as '— none —' for 2-colour FRET-only analysis."
        )
        row3.addWidget(self.cb_aex, 1)
        sl.addLayout(row3)
        layout.addWidget(sel)

        self.detector_page = DetectorWizardPage(parent=self)
        layout.addWidget(self.detector_page, 1)
        self.detector_page.detectorsChanged.connect(self._refresh_detector_combos)
        self._refresh_detector_combos()
        return w

    _AEX_NONE = "— none —"

    def _refresh_detector_combos(self):
        settings = self.detector_page.get_settings()
        names = list(settings.get("detectors", {}).keys())
        donor_cur, acc_cur = self.cb_donor.currentText(), self.cb_acceptor.currentText()
        aex_cur = self.cb_aex.currentText()
        self.cb_donor.clear()
        self.cb_acceptor.clear()
        self.cb_aex.clear()
        self.cb_donor.addItems(names)
        self.cb_acceptor.addItems(names)
        self.cb_aex.addItems([self._AEX_NONE, *names])
        if donor_cur in names:
            self.cb_donor.setCurrentText(donor_cur)
        if acc_cur in names:
            self.cb_acceptor.setCurrentText(acc_cur)
        elif len(names) > 1:
            self.cb_acceptor.setCurrentIndex(1)
        if aex_cur in names:
            self.cb_aex.setCurrentText(aex_cur)
        elif len(names) > 2:
            # A 3rd detector (e.g. PIE 'yellow') is a good Aex default.
            self.cb_aex.setCurrentIndex(3)

    def _build_plots(self) -> QWidget:
        """Build the burstH2MM-style 3×2 result grid plus a burst state-path viewer."""
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)

        self.plot_widget = pg.GraphicsLayoutWidget()
        # Row 0 — dwell FRET (E histogram or E–S scatter) + transition-density.
        self._p_fret = self.plot_widget.addPlot(row=0, col=0, title="Dwell FRET states")
        self._p_fret.setLabels(bottom="Apparent FRET E", left="Dwells")
        self._p_fret.setXRange(0, 1)
        self._fret_legend = self._p_fret.addLegend(offset=(-5, 5))
        self._p_tdp = self.plot_widget.addPlot(row=0, col=1, title="Transition-density plot")
        self._p_tdp.setLabels(bottom="E before", left="E after")
        self._p_tdp.setRange(xRange=(0, 1), yRange=(0, 1))
        self._tdp_img = pg.ImageItem(axisOrder="col-major")
        self._p_tdp.addItem(self._tdp_img)
        # Row 1 — model selection + dwell-time distributions.
        self._p_sel = self.plot_widget.addPlot(row=1, col=0, title="Model selection")
        self._p_sel.setLabels(bottom="Number of states", left="Criterion")
        self._p_sel.addLegend()
        self._p_dwell = self.plot_widget.addPlot(row=1, col=1, title="Dwell-time distributions")
        self._p_dwell.setLabels(bottom="Dwell time (ms)", left="Counts")
        self._dwell_legend = self._p_dwell.addLegend(offset=(-5, 5))
        # Row 2 — per-state fluorescence decay + burst state path (full width).
        self._p_nano = self.plot_widget.addPlot(row=2, col=0, colspan=2,
                                                title="Per-state fluorescence decay")
        self._p_nano.setLabels(bottom="Micro time (channel)", left="Counts")
        self._p_nano.setLogMode(y=True)
        self._nano_legend = self._p_nano.addLegend(offset=(-5, 5))
        # Row 3 — burst state path, full width (it is a time series).
        self._p_path = self.plot_widget.addPlot(row=3, col=0, colspan=2, title="Burst state path")
        self._p_path.setLabels(bottom="Time in burst (ms)", left="FRET E")
        self._p_path.setYRange(-0.05, 1.05)
        v.addWidget(self.plot_widget, 1)

        # Burst-path navigation bar.
        nav = QHBoxLayout()
        nav.setContentsMargins(6, 0, 6, 2)
        self.btn_prev_burst = QToolButton()
        self.btn_prev_burst.setText("◀")
        self.btn_next_burst = QToolButton()
        self.btn_next_burst.setText("▶")
        self.sb_burst = QSpinBox()
        self.sb_burst.setMinimum(0)
        self.sb_burst.setMaximum(0)
        self.sb_burst.setToolTip("Burst shown in the state-path plot")
        self.cb_dynamic_only = QCheckBox("dynamic bursts only")
        self.cb_dynamic_only.setToolTip("Navigate only bursts with ≥1 state transition")
        self._burst_label = QLabel("no fit yet")
        self._burst_label.setStyleSheet("color:#888;")
        nav.addWidget(QLabel("State path — burst:"))
        nav.addWidget(self.btn_prev_burst)
        nav.addWidget(self.sb_burst)
        nav.addWidget(self.btn_next_burst)
        nav.addWidget(self.cb_dynamic_only)
        nav.addWidget(self._burst_label)
        nav.addStretch(1)
        v.addLayout(nav)

        self.btn_prev_burst.clicked.connect(lambda: self.sb_burst.stepBy(-1))
        self.btn_next_burst.clicked.connect(lambda: self.sb_burst.stepBy(1))
        self.sb_burst.valueChanged.connect(self._update_burst_path)
        self.cb_dynamic_only.toggled.connect(self._apply_nav_filter)
        return container

    def _connect_signals(self):
        self.btn_folder.clicked.connect(self._select_folder)
        self._folder_field.folderDropped.connect(self._set_folder)
        self.btn_run.clicked.connect(self._run_analysis)
        self.btn_uncert.clicked.connect(self._run_uncertainty)
        self.btn_save.clicked.connect(self._save_plot)
        self.btn_help.clicked.connect(lambda: HelpDialog(self).exec_())

    # ── settings ─────────────────────────────────────────────────────

    def _detector_streams(self) -> list[StreamSettings]:
        settings = self.detector_page.get_settings()
        detectors = settings.get("detectors", {})
        self.file_type = settings.get("tttr_reading", {}).get("file_type", self.file_type)

        def _stream(name: str) -> StreamSettings:
            d = detectors.get(name, {})
            ranges = [(int(a), int(b)) for a, b in d.get("micro_time_ranges", [])]
            return StreamSettings(name=name or "stream", channels=list(d.get("chs", [])), micro_time_ranges=ranges)

        streams = [_stream(self.cb_donor.currentText()), _stream(self.cb_acceptor.currentText())]
        # Optional acceptor-excitation (Aex) stream → stoichiometry (µsALEX/PIE).
        aex = self.cb_aex.currentText()
        if aex and aex != self._AEX_NONE and aex in detectors:
            streams.append(_stream(aex))
        return streams

    def _gather_settings(self) -> H2mmSettings:
        patience = self.sb_patience.value()
        return H2mmSettings(
            streams=self._detector_streams(),
            min_states=self.sb_min_states.value(),
            max_states=max(self.sb_max_states.value(), self.sb_min_states.value()),
            criterion=self.cb_criterion.currentText(),
            n_restarts=self.sb_restarts.value(),
            max_iter=self.sb_max_iter.value(),
            min_photons=self.sb_min_photons.value(),
            time_scale=self.sb_time_scale.value(),
            divisors=self.sb_divisors.value(),
            file_type=self.file_type,
            engine=self.cb_engine.currentData() or "em",
            patience=None if patience < 0 else patience,
        )

    # ── run ──────────────────────────────────────────────────────────

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select burst (.bur) folder")
        if folder:
            self._set_folder(folder)

    def _set_folder(self, path: str):
        p = pathlib.Path(path)
        if p.is_dir():
            self.data_folder = p
            self._folder_field.setText(str(p))
            self._status(f"Data folder: {p}")

    def _run_analysis(self):
        if not self.data_folder:
            QMessageBox.warning(self, "No data", "Please select a folder of .bur files first.")
            return
        settings = self._gather_settings()

        self._prog = EnhancedProgressDialog(
            "H2MM", "Loading bursts …", 0, 100, self
        )
        self._prog.show()
        self._fit_t0 = time.perf_counter()
        self._cancel = threading.Event()
        try:
            self._prog.canceled.connect(self._cancel.set)
        except Exception:
            pass
        self.btn_run.setEnabled(False)
        self._status("Fitting H2MM models …")

        # Progress signal: emitted from the worker thread, handled on the UI thread.
        self._fit_signals = _FitSignals()
        self._fit_signals.tick.connect(self._on_fit_progress)
        self._last_emit = 0.0

        def _progress(done, total_, fits):
            if self._cancel.is_set():
                raise _FitCancelled()
            now = time.perf_counter()
            fit_done = float(done).is_integer()  # a state-count fit just finished
            if fit_done:
                # Emit a fits snapshot so the live plots update.
                self._fit_signals.tick.emit(float(done), total_, list(fits))
                self._last_emit = now
            elif now - self._last_emit > 0.1:    # throttle per-iteration ticks to ~10 Hz
                self._fit_signals.tick.emit(float(done), total_, None)
                self._last_emit = now

        # run_analysis(...) -> (result, bundle); Worker emits it on `result`.
        worker = Worker(
            run_analysis, settings,
            analysis_folder=str(self.data_folder),
            progress=_progress,
        )
        worker.signals.result.connect(self._on_fit_result)
        worker.signals.error.connect(self._on_fit_error)
        QThreadPool.globalInstance().start(worker)

    # ── fit worker callbacks (UI thread) ─────────────────────────────

    @staticmethod
    def _fmt_eta(seconds: float) -> str:
        """Human-readable ETA string."""
        if seconds < 90:
            return f"{seconds:.0f} s"
        if seconds < 3600:
            return f"{seconds / 60:.1f} min"
        return f"{seconds / 3600:.1f} h"

    def _on_fit_progress(self, done: float, total: int, fits: object):
        """Update the progress bar (with ETA); refresh live plots on fit completion.

        ``done`` is fractional — completed state-count fits plus the fraction of
        the current (possibly long) fit — so the bar advances smoothly even while
        a single fit runs for minutes.  ``fits`` is a snapshot when a fit finished,
        else ``None`` (progress-only tick).
        """
        pct = int(90 * done / max(total, 1))  # last 10% reserved for finalisation
        elapsed = time.perf_counter() - self._fit_t0
        try:
            self._prog.setValue(pct)
            if done > 0.05:
                eta = elapsed * (total - done) / done
                self._prog.setLabelText(
                    f"Fitting … {int(done)}/{total} state counts done   "
                    f"({pct}%, ETA {self._fmt_eta(eta)})"
                )
            else:
                self._prog.setLabelText("Fitting … (estimating ETA)")
        except Exception:
            pass
        if fits is not None:
            self._plot_scan_live(fits)

    def _on_fit_result(self, payload):
        """Store results, finalise plots, and close the progress dialog."""
        result, bundle = payload
        self._result = result
        self._bundle = bundle
        self._uncertainty = None  # bootstrap CIs are stale after a new fit
        try:
            self._prog.setValue(100)
            self._prog.close()
        except Exception:
            pass
        self.btn_run.setEnabled(True)
        self._update_plots()
        self._status(
            f"Selected {result.n_states} states "
            f"({result.criterion.upper()}) from {result.n_bursts} bursts / "
            f"{result.n_photons} photons"
        )

    def _on_fit_error(self, tb):
        """Handle a worker failure or a user cancellation."""
        try:
            self._prog.close()
        except Exception:
            pass
        self.btn_run.setEnabled(True)
        if tb and "_FitCancelled" in str(tb):
            self._status("Fit cancelled")
            return
        message = str(tb).strip().splitlines()[-1] if tb else "unknown error"
        QMessageBox.critical(self, "H2MM error", message)
        logging.error(f"H2MM analysis failed: {tb}")

    # ── uncertainty (bootstrap) ──────────────────────────────────────

    def _run_uncertainty(self):
        """Bootstrap the selected model over bursts and overlay E/S error bars."""
        if self._bundle is None or self._result is None:
            QMessageBox.information(self, "H2MM", "Run a fit before estimating uncertainty.")
            return
        from ..core.analysis import bootstrap_uncertainty

        ana = self._bundle.analysis
        data = self._bundle.data
        settings = self._bundle.settings
        n_boot = 20

        self._uprog = EnhancedProgressDialog("H2MM", "Bootstrapping …", 0, n_boot, self)
        self._uprog.show()
        self.btn_uncert.setEnabled(False)
        self._ucancel = threading.Event()
        try:
            self._uprog.canceled.connect(self._ucancel.set)
        except Exception:
            pass
        self._uncert_signals = _UncertSignals()
        self._uncert_signals.tick.connect(self._on_uncert_progress)

        def _progress(done, total):
            if self._ucancel.is_set():
                raise _FitCancelled()
            self._uncert_signals.tick.emit(int(done), int(total))

        worker = Worker(
            bootstrap_uncertainty, data, int(ana.best.n_states),
            n_boot=n_boot, engine=getattr(settings, "engine", "em"),
            n_restarts=1, max_iter=300,
            donor_streams=getattr(ana, "donor_streams", (0,)),
            acceptor_streams=getattr(ana, "acceptor_streams", (1,)),
            aex_streams=getattr(ana, "aex_streams", None),
            progress=_progress,
        )
        worker.signals.result.connect(self._on_uncert_result)
        worker.signals.error.connect(self._on_uncert_error)
        QThreadPool.globalInstance().start(worker)

    def _on_uncert_progress(self, done: int, total: int):
        try:
            self._uprog.setValue(done)
            self._uprog.setLabelText(f"Bootstrapping … {done}/{total} resamples")
        except Exception:
            pass

    def _on_uncert_result(self, unc):
        """Store bootstrap CIs and redraw the E/E–S and E–τ panels with error bars."""
        self._uncertainty = unc
        try:
            self._uprog.close()
        except Exception:
            pass
        self.btn_uncert.setEnabled(True)
        if self._bundle is not None:
            self._plot_dwell_fret(self._bundle.analysis)
        self._status(f"Uncertainty from {unc.n_boot} bootstrap resamples "
                     f"({unc.ci[0]:.0f}–{unc.ci[1]:.0f}% CI)")

    def _on_uncert_error(self, tb):
        try:
            self._uprog.close()
        except Exception:
            pass
        self.btn_uncert.setEnabled(True)
        if tb and "_FitCancelled" in str(tb):
            self._status("Uncertainty cancelled")
            return
        message = str(tb).strip().splitlines()[-1] if tb else "unknown error"
        QMessageBox.critical(self, "H2MM uncertainty error", message)
        logging.error(f"H2MM bootstrap failed: {tb}")

    def _uncert_ranks(self, fret: np.ndarray) -> np.ndarray:
        """E-ascending rank of each native state (index into the Uncertainty arrays)."""
        finite = np.where(np.isfinite(fret), fret, np.inf)
        return np.argsort(np.argsort(finite))

    def _plot_scan_live(self, fits):
        """Live-update the model-selection and FRET-state plots during the scan."""
        if not fits:
            return
        ns = [f.n_states for f in fits]
        self._p_sel.clear()
        self._p_sel.plot(ns, [f.bic for f in fits],
                         pen=pg.mkPen("#4e79a7", width=2), symbol="o", name="BIC")
        self._p_sel.plot(ns, [f.icl for f in fits],
                         pen=pg.mkPen("#e15759", width=2), symbol="s", name="ICL")

        crit = self.cb_criterion.currentText()
        key = (lambda f: f.icl) if crit == "icl" else (lambda f: f.bic)
        best = min(fits, key=key)
        from ..core.analysis import state_fret

        div = max(int(self.sb_divisors.value()), 1)
        n_base = max(best.model.n_streams // div, 1)
        donor = range(0, div)
        acc = range(div, 2 * div) if n_base > 1 else range(0, div)
        fret = state_fret(best.model, acceptor_stream=acc, donor_stream=donor)
        self._p_fret.clear()
        for i, e in enumerate(fret):
            if not np.isfinite(e):
                continue
            color = _STATE_COLORS[i % len(_STATE_COLORS)]
            self._p_fret.addItem(pg.BarGraphItem(x=[e], height=[1.0], width=0.03, brush=color))

    # ── plotting ─────────────────────────────────────────────────────

    @staticmethod
    def _state_color(i: int) -> str:
        """Return the fixed per-state colour (cycles for > 8 states)."""
        return _STATE_COLORS[i % len(_STATE_COLORS)]

    # Photon-stream marker: donor ●, acceptor (Dex) ▲, acceptor (Aex) ■.
    _STREAM_SYMBOL = ("o", "t", "s")

    def _update_plots(self):
        if self._result is None or self._bundle is None:
            return
        ana = self._bundle.analysis
        self._plot_dwell_fret(ana)
        self._plot_tdp(ana)
        self._plot_model_selection(self._result)
        self._plot_dwell_times(ana)
        self._plot_nanotime(ana)
        self._rebuild_nav_bursts(ana)

    def _plot_dwell_fret(self, ana):
        """Top-left: measured per-dwell E histogram, or an E–S scatter for ALEX/PIE.

        Mirrors burstH2MM ``dwell_E_hist`` / ``dwell_ES_scatter``: histograms of
        the *measured* dwell efficiencies per state (weighted by dwell photons),
        with the *model* per-state E marked; when an acceptor-excitation stream is
        present the panel switches to a 2-D dwell E–S scatter.
        """
        p = self._p_fret
        p.clear()
        self._fret_legend.clear()
        fret = np.asarray(ana.fret, dtype=np.float64)
        stoich = np.asarray(getattr(ana, "stoichiometry", np.full_like(fret, np.nan)))
        has_alex = np.isfinite(stoich).any()
        e = np.array([d.e for d in ana.dwells], dtype=np.float64)
        s = np.array([d.s for d in ana.dwells], dtype=np.float64)
        st = np.array([d.state for d in ana.dwells], dtype=np.int64)
        w = np.array([d.n_photons for d in ana.dwells], dtype=np.float64)

        if has_alex:
            p.setTitle("Dwell E–S scatter")
            p.setLabels(bottom="Dwell E", left="Dwell S")
            p.setRange(xRange=(0, 1), yRange=(0, 1))
            for i in range(fret.shape[0]):
                m = (st == i) & np.isfinite(e) & np.isfinite(s)
                if not m.any():
                    continue
                color = self._state_color(i)
                p.addItem(pg.ScatterPlotItem(
                    e[m], s[m], size=5, pen=None,
                    brush=pg.mkBrush(color + "80"), name=f"S{i}",
                ))
                if np.isfinite(fret[i]) and np.isfinite(stoich[i]):
                    p.addItem(pg.ScatterPlotItem(
                        [fret[i]], [stoich[i]], size=15, symbol="x",
                        pen=pg.mkPen(color, width=3), brush=None,
                    ))
            self._overlay_es_uncert(p, fret, stoich)
            return

        p.setTitle("Dwell FRET states")
        p.setLabels(bottom="Apparent FRET E", left="Dwells")
        p.setXRange(0, 1)
        for i in range(fret.shape[0]):
            m = (st == i) & np.isfinite(e)
            color = self._state_color(i)
            if m.any():
                counts, edges = np.histogram(e[m], bins=41, range=(0, 1), weights=w[m])
                centers = (edges[:-1] + edges[1:]) / 2
                p.plot(centers, counts, pen=pg.mkPen(color, width=2), fillLevel=0,
                       brush=pg.mkBrush(color + "40"), name=f"S{i}")
            if np.isfinite(fret[i]):
                p.addItem(pg.InfiniteLine(pos=float(fret[i]), angle=90,
                          pen=pg.mkPen(color, width=1, style=Qt.DashLine)))
        self._overlay_e_ci_bands(p, fret)

    def _overlay_es_uncert(self, p, fret, stoich):
        """Draw bootstrap E/S error bars on the E–S state markers, if available."""
        unc = self._uncertainty
        if unc is None:
            return
        ranks = self._uncert_ranks(fret)
        for i in range(int(fret.shape[0])):
            r = int(ranks[i])
            if not (np.isfinite(fret[i]) and np.isfinite(stoich[i])):
                continue
            left = max(fret[i] - unc.fret_lo[r], 0.0)
            right = max(unc.fret_hi[r] - fret[i], 0.0)
            top = bottom = 0.0
            if np.isfinite(unc.stoich_lo[r]) and np.isfinite(unc.stoich_hi[r]):
                bottom = max(stoich[i] - unc.stoich_lo[r], 0.0)
                top = max(unc.stoich_hi[r] - stoich[i], 0.0)
            p.addItem(pg.ErrorBarItem(
                x=np.array([fret[i]]), y=np.array([stoich[i]]),
                left=np.array([left]), right=np.array([right]),
                top=np.array([top]), bottom=np.array([bottom]),
                beam=0.02, pen=pg.mkPen(self._state_color(i), width=2)))

    def _overlay_e_ci_bands(self, p, fret):
        """Draw translucent per-state E confidence bands on the dwell-E histogram."""
        unc = self._uncertainty
        if unc is None:
            return
        ranks = self._uncert_ranks(fret)
        for i in range(int(fret.shape[0])):
            r = int(ranks[i])
            if not (np.isfinite(unc.fret_lo[r]) and np.isfinite(unc.fret_hi[r])):
                continue
            region = pg.LinearRegionItem(
                values=(float(unc.fret_lo[r]), float(unc.fret_hi[r])),
                brush=pg.mkBrush(self._state_color(i) + "22"), movable=False)
            region.setZValue(-10)
            p.addItem(region)

    def _plot_tdp(self, ana):
        """Top-right: transition-density plot (E before vs E after, 2-D histogram)."""
        if not ana.transitions:
            self._tdp_img.clear()
            return
        eb = np.array([t.e_from for t in ana.transitions])
        ea = np.array([t.e_to for t in ana.transitions])
        good = np.isfinite(eb) & np.isfinite(ea)
        hist, _, _ = np.histogram2d(eb[good], ea[good], bins=(41, 41), range=[[0, 1], [0, 1]])
        self._tdp_img.setImage(hist)
        self._tdp_img.setRect(0, 0, 1, 1)
        try:
            self._tdp_img.setColorMap(pg.colormap.get("CET-L4"))
        except Exception:
            pass

    def _plot_model_selection(self, res):
        """Bottom-left: BIC and ICL vs number of states."""
        self._p_sel.clear()
        ns = [f.n_states for f in res.scan]
        self._p_sel.plot(ns, [f.bic for f in res.scan],
                         pen=pg.mkPen("#4e79a7", width=2), symbol="o", name="BIC")
        self._p_sel.plot(ns, [f.icl for f in res.scan],
                         pen=pg.mkPen("#e15759", width=2), symbol="s", name="ICL")

    def _plot_dwell_times(self, ana):
        """Bottom-right: per-state dwell-time distributions (ms)."""
        self._p_dwell.clear()
        self._dwell_legend.clear()
        base_ms = ana.base_time_s * 1e3
        for i, (_state, arr) in enumerate(sorted(ana.dwell_times.items())):
            if arr.size == 0:
                continue
            counts, edges = np.histogram(arr * base_ms, bins=30)
            centers = (edges[:-1] + edges[1:]) / 2
            self._p_dwell.plot(centers, counts, pen=pg.mkPen(self._state_color(i), width=2),
                               name=f"S{i}")

    def _plot_nanotime(self, ana):
        """Row 2, left: per-state fluorescence decay (micro-time histogram by state).

        Requires the per-photon micro times (``bundle.meta``); when absent (e.g. a
        result loaded without photon metadata) the panel is left empty.
        """
        p = self._p_nano
        p.clear()
        self._nano_legend.clear()
        meta = getattr(self._bundle, "meta", None)
        path = np.asarray(ana.path, dtype=np.int64)
        if meta is None or getattr(meta, "micro_time", None) is None:
            return
        micro = np.asarray(meta.micro_time)
        if micro.shape[0] != path.shape[0] or micro.size == 0:
            return
        mx = int(micro.max())
        if mx <= 0:
            return
        bins = int(min(256, max(16, mx)))
        for i in range(int(ana.fret.shape[0])):
            m = micro[path == i]
            if m.size == 0:
                continue
            counts, edges = np.histogram(m, bins=bins, range=(0, mx + 1))
            centers = (edges[:-1] + edges[1:]) / 2
            keep = counts > 0
            p.plot(centers[keep], counts[keep], pen=pg.mkPen(self._state_color(i), width=2),
                   name=f"S{i}")

    # ── burst state-path viewer ──────────────────────────────────────

    def _burst_times_ms(self, b: int):
        """Return ``(start, stop, t_ms)`` for burst ``b`` (times relative to its start)."""
        data = self._bundle.data
        offsets = np.asarray(data.burst_offsets)
        s, e = int(offsets[b]), int(offsets[b + 1])
        gap = np.asarray(data.gap_slot)
        uniq = np.asarray(data.unique_dt)
        n = e - s
        t = np.zeros(n, dtype=np.float64)
        if n > 1 and uniq.size:
            slots = gap[s : s + n - 1]
            dt = np.where(slots >= 0, uniq[np.clip(slots, 0, len(uniq) - 1)], 0)
            t[1:] = np.cumsum(dt)
        return s, e, t * (self._bundle.analysis.base_time_s * 1e3)

    def _rebuild_nav_bursts(self, ana):
        """Refresh the burst-path navigation lists after a fit."""
        self._all_bursts = list(range(int(self._bundle.data.n_bursts)))
        self._dynamic_bursts = sorted({t.burst for t in ana.transitions})
        self._apply_nav_filter()

    def _apply_nav_filter(self, *_):
        """Point the burst spinbox at all bursts or only dynamic ones."""
        if self._bundle is None or not getattr(self, "_all_bursts", None):
            return
        use_dyn = self.cb_dynamic_only.isChecked() and bool(self._dynamic_bursts)
        self._nav_bursts = self._dynamic_bursts if use_dyn else self._all_bursts
        n = len(self._nav_bursts)
        self.sb_burst.blockSignals(True)
        self.sb_burst.setMaximum(max(n - 1, 0))
        if self.sb_burst.value() > n - 1:
            self.sb_burst.setValue(0)
        self.sb_burst.blockSignals(False)
        self._update_burst_path()

    def _update_burst_path(self, *_):
        """Draw the selected burst's Viterbi state path (photons coloured by state)."""
        p = self._p_path
        p.clear()
        if self._bundle is None or not getattr(self, "_nav_bursts", None):
            self._burst_label.setText("no fit yet")
            return
        idx = self.sb_burst.value()
        if idx >= len(self._nav_bursts):
            return
        b = self._nav_bursts[idx]
        ana = self._bundle.analysis
        s, e, t = self._burst_times_ms(b)
        seg = np.asarray(ana.path[s:e], dtype=np.int64)
        streams = np.asarray(self._bundle.data.streams)[s:e]
        fret = np.asarray(ana.fret, dtype=np.float64)
        ey = np.where(np.isfinite(fret[seg]), fret[seg], np.nan)

        # State-E trajectory (light connecting line) + photons coloured by state,
        # marker shape encoding the photon stream (donor/acceptor/Aex).
        p.plot(t, ey, pen=pg.mkPen("#999999", width=1))
        n_states = int(fret.shape[0])
        for i in range(n_states):
            color = self._state_color(i)
            for k in range(int(self._bundle.data.n_streams)):
                m = (seg == i) & (streams == k)
                if not m.any():
                    continue
                sym = self._STREAM_SYMBOL[k % len(self._STREAM_SYMBOL)]
                p.addItem(pg.ScatterPlotItem(
                    t[m], ey[m], size=7, symbol=sym, pen=None,
                    brush=pg.mkBrush(color),
                ))
        n_tr = int(np.count_nonzero(np.diff(seg))) if seg.size else 0
        self._burst_label.setText(f"burst {b} · {e - s} photons · {n_tr} transitions")

    def _save_plot(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save plot", "h2mm.png", "PNG (*.png)")
        if path:
            self.plot_widget.grab().save(path)

    # ── workflow integration ─────────────────────────────────────────

    def apply_workflow_context(self, context: dict[str, Any]) -> None:
        """Apply a burst-workflow context (folder + channel settings)."""
        folder = context.get("burst_folder") or context.get("analysis_folder")
        if folder:
            self._set_folder(str(folder))
        channel_settings = context.get("channel_settings") or {}
        file_type = (channel_settings.get("tttr_reading") or {}).get("file_type")
        if file_type:
            self.file_type = file_type

    # ── persistence ──────────────────────────────────────────────────

    def _status(self, msg: str):
        self._status_label.setText(msg)
        QCoreApplication.processEvents()

    def _save_settings(self):
        ini = QSettings(str(get_plugin_settings_path("burst_h2mm")), QSettings.IniFormat)
        ini.setValue("min_states", self.sb_min_states.value())
        ini.setValue("max_states", self.sb_max_states.value())
        ini.setValue("criterion", self.cb_criterion.currentText())
        if self.data_folder is not None:
            ini.setValue("last_folder", str(self.data_folder))

    def _load_settings(self):
        ini = QSettings(str(get_plugin_settings_path("burst_h2mm")), QSettings.IniFormat)
        if (v := ini.value("min_states")) is not None:
            self.sb_min_states.setValue(int(v))
        if (v := ini.value("max_states")) is not None:
            self.sb_max_states.setValue(int(v))
        if (v := ini.value("criterion")) is not None:
            idx = self.cb_criterion.findText(str(v))
            if idx >= 0:
                self.cb_criterion.setCurrentIndex(idx)
        lf = ini.value("last_folder")
        if lf and pathlib.Path(str(lf)).is_dir():
            self._set_folder(str(lf))

    def closeEvent(self, event):
        """Persist settings when the window closes."""
        self._save_settings()
        super().closeEvent(event)
