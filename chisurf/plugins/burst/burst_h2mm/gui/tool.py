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
from chisurf.gui import dialogs


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


class LikelihoodScanDialog(QDialog):
    """Show per-state log-likelihood profiles (E and S) with CI markers.

    Solid curve = deviance ``2·(logL_max − logL)`` vs the parameter; its shaded
    band is the likelihood CI (where the deviance crosses the 95 % threshold).
    When a bootstrap was run, its CI is overlaid as dotted lines so the two
    methods can be compared (they diverge on poorly-identified states).
    """

    def __init__(self, scans, uncertainty, color_fn, parent=None):
        super().__init__(parent)
        self.setWindowTitle("H2MM likelihood scan")
        self.resize(780, 480)
        layout = QVBoxLayout(self)
        glw = pg.GraphicsLayoutWidget()
        layout.addWidget(glw, 1)

        # Map each state to its E-ascending rank (index into the bootstrap arrays).
        e_scans = sorted((s for s in scans if s.param == "E"), key=lambda s: s.mle)
        rank_of = {s.state: r for r, s in enumerate(e_scans)}

        params = [p for p in ("E", "S") if any(s.param == p for s in scans)]
        for col, param in enumerate(params):
            p = glw.addPlot(row=0, col=col,
                            title=("FRET-E profile" if param == "E" else "Stoichiometry profile"))
            p.setLabels(bottom=("Apparent FRET E" if param == "E" else "Stoichiometry S"),
                        left="Δ(2·logL)")
            p.setXRange(0, 1)
            p.setYRange(-0.3, 12)
            p.addLegend(offset=(-5, 5))
            thr = 3.84
            for s in (s for s in scans if s.param == param):
                color = color_fn(s.state)
                dev = 2.0 * (np.max(s.loglik) - s.loglik)
                p.plot(s.values, dev, pen=pg.mkPen(color, width=2), name=f"S{s.state}")
                p.addItem(pg.InfiniteLine(pos=float(s.mle), angle=90,
                          pen=pg.mkPen(color, width=1, style=Qt.DashLine)))
                region = pg.LinearRegionItem(values=(float(s.ci[0]), float(s.ci[1])),
                                             brush=pg.mkBrush(color + "22"), movable=False)
                region.setZValue(-10)
                p.addItem(region)
                thr = s.threshold
                if uncertainty is not None and s.state in rank_of:
                    r = rank_of[s.state]
                    lo, hi = ((uncertainty.fret_lo[r], uncertainty.fret_hi[r]) if param == "E"
                              else (uncertainty.stoich_lo[r], uncertainty.stoich_hi[r]))
                    if np.isfinite(lo) and np.isfinite(hi):
                        for xb in (lo, hi):
                            p.addItem(pg.InfiniteLine(pos=float(xb), angle=90,
                                      pen=pg.mkPen(color, width=1, style=Qt.DotLine)))
            p.addItem(pg.InfiniteLine(pos=thr, angle=0, pen=pg.mkPen("#888888", style=Qt.DashLine)))

        cap = QLabel(
            "Solid = likelihood profile (shaded = its 95% CI); dashed vertical = MLE; "
            "horizontal dashed = χ²₁ threshold (Δ=3.84); dotted vertical = bootstrap CI "
            "(if computed). A flat curve / window-wide CI means the state is poorly identified."
        )
        cap.setWordWrap(True)
        cap.setStyleSheet("color:#888;")
        layout.addWidget(cap)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


@persist_plugin_state("burst_h2mm")
class H2mmTool(QMainWindow):
    """H2MM analysis widget with toolbar, tabbed settings, and result plots."""

    def __init__(self, parent=None, *, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("smFRET H2MM Analysis")
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
        # Each result plot is its own dock (drag to split / rearrange / resize),
        # not a single cramped grid. A default 2-column arrangement mirrors the
        # familiar dashboard while every plot stays independently resizable.
        self._build_plot_docks()
        # Full chisurf-dock behaviour (same as BVA): right-click context menu to
        # split/move/close docks, not just a plain tab bar.
        self.dock_area.setContextMenuEnabled(True)
        self.dock_area.setContextMenuMode("basic")
        layout.addWidget(self.dock_area, 1)

        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("color: #888; font-style: italic; padding: 0 8px;")
        self._status_label.setFixedHeight(22)
        layout.addWidget(self._status_label)
        # Embedded, the shared status bar carries messages — hide the local line.
        if self._embedded:
            self._status_label.setVisible(False)

        self._connect_signals()
        # Restore a saved dock arrangement, else apply the default two-column grid
        # (both synchronous here, matching BVA — no showEvent-time restore, which
        # interacts badly with the embedded navigation lifecycle).
        self._restore_dock_layout()
        self.dock_area.layoutChanged.connect(self._save_dock_layout)
        self._load_settings()

    def _setup_toolbar(self):
        from chisurf.gui.widgets.tool_buttons import (
            TOOLBAR_STYLE,
            action_button,
            styled_tool_button,
        )

        self.toolbar = QToolBar("Main")
        self.toolbar.setObjectName("h2mmMainToolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toolbar.setStyleSheet(TOOLBAR_STYLE)

        # Canonical shared actions (same icon / colour / order as every plugin).
        self.btn_folder = action_button("folder", tooltip="Select the burst analysis folder")
        self._folder_field = _FolderLineEdit(placeholder="No folder selected")
        self._folder_field.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_run = action_button("run", tooltip="Fit H2MM on all loaded bursts")
        # Tool-specific follow-ups (styled consistently, distinct from Run).
        self.btn_uncert = styled_tool_button("±", kind="toggle", tooltip=(
            "Uncertainty — bootstrap the selected model over bursts to put "
            "confidence intervals on the per-state E/S (overlaid as error bars). "
            "Compute-heavy — run after a fit."
        ))
        self.btn_llscan = styled_tool_button("\U0001f4c8", kind="toggle", tooltip=(
            "LL scan — profile the log-likelihood in each state's E/S (holding the "
            "rest fixed) → likelihood-based confidence intervals. A flat profile "
            "flags an unidentifiable state. Run after a fit."
        ))
        self.btn_save = action_button("save", tooltip="Save the active plot")
        self.btn_help = action_button("help", tooltip="Show help")

        self.toolbar.addWidget(self.btn_folder)
        self.toolbar.addWidget(self.btn_run)
        self.toolbar.addWidget(self.btn_uncert)
        self.toolbar.addWidget(self.btn_llscan)
        self.toolbar.addWidget(self.btn_save)
        self.toolbar.addWidget(self._folder_field)
        _spacer = QWidget()
        _spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(_spacer)
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

    #: dock tab titles for each result plot (stable — used by the default layout).
    _DOCK_FRET = "Dwell FRET states"
    _DOCK_TDP = "Transition density"
    _DOCK_SEL = "Model selection"
    _DOCK_DWELL = "Dwell times"
    _DOCK_NANO = "Per-state decay"
    _DOCK_RATES = "Transition rates"
    _DOCK_PATH = "State path"

    @staticmethod
    def _new_plot(title: str) -> pg.PlotWidget:
        """Create a single-plot dock page whose PlotItem is returned by the caller."""
        return pg.PlotWidget(title=title)

    def _build_plot_docks(self) -> None:
        """Add each burstH2MM-style result plot as its own dock in the dock area.

        Previously all seven plots were packed into one ``GraphicsLayoutWidget`` in a
        single "Results" dock, so each was tiny. They are now independent docks the
        user can resize, tab, maximize or drag into any split arrangement; a default
        two-column layout is applied in :meth:`_apply_default_plot_layout`.
        """
        # Row-0 plots — dwell FRET (E histogram or E–S scatter) + transition density.
        w_fret = self._new_plot(self._DOCK_FRET)
        self._p_fret = w_fret.getPlotItem()
        self._p_fret.setLabels(bottom="Apparent FRET E", left="Dwells")
        self._p_fret.setXRange(0, 1)
        self._fret_legend = self._p_fret.addLegend(offset=(-5, 5))

        w_tdp = self._new_plot(self._DOCK_TDP)
        self._p_tdp = w_tdp.getPlotItem()
        self._p_tdp.setLabels(bottom="E before", left="E after")
        self._p_tdp.setRange(xRange=(0, 1), yRange=(0, 1))
        self._tdp_img = pg.ImageItem(axisOrder="col-major")
        self._p_tdp.addItem(self._tdp_img)

        # Row-1 plots — model selection + dwell-time distributions.
        w_sel = self._new_plot(self._DOCK_SEL)
        self._p_sel = w_sel.getPlotItem()
        self._p_sel.setLabels(bottom="Number of states", left="Criterion")
        self._p_sel.addLegend()

        w_dwell = self._new_plot(self._DOCK_DWELL)
        self._p_dwell = w_dwell.getPlotItem()
        self._p_dwell.setLabels(bottom="Dwell time (ms)", left="Counts")
        self._dwell_legend = self._p_dwell.addLegend(offset=(-5, 5))

        # Row-2 plots — per-state fluorescence decay + transition-rate matrix.
        w_nano = self._new_plot(self._DOCK_NANO)
        self._p_nano = w_nano.getPlotItem()
        self._p_nano.setLabels(bottom="Micro time (channel)", left="Counts")
        self._p_nano.setLogMode(y=True)
        self._nano_legend = self._p_nano.addLegend(offset=(-5, 5))

        w_rates = self._new_plot(self._DOCK_RATES)
        self._p_rates = w_rates.getPlotItem()
        self._p_rates.setLabels(bottom="to state", left="from state")
        self._p_rates.invertY(True)
        self._p_rates.setAspectLocked(True)
        self._rates_img = pg.ImageItem(axisOrder="row-major")
        self._p_rates.addItem(self._rates_img)

        # Burst state path — plot plus its navigation bar, in one dock.
        path_page = QWidget()
        v = QVBoxLayout(path_page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        w_path = self._new_plot(self._DOCK_PATH)
        self._p_path = w_path.getPlotItem()
        self._p_path.setLabels(bottom="Time in burst (ms)", left="FRET E")
        self._p_path.setYRange(-0.05, 1.05)
        v.addWidget(w_path, 1)

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

        # Keep an ordered handle on the plot dock pages (for Save-plot / grabbing).
        self._plot_pages = {
            self._DOCK_FRET: w_fret,
            self._DOCK_TDP: w_tdp,
            self._DOCK_SEL: w_sel,
            self._DOCK_DWELL: w_dwell,
            self._DOCK_NANO: w_nano,
            self._DOCK_RATES: w_rates,
            self._DOCK_PATH: path_page,
        }
        for title, page in self._plot_pages.items():
            self.dock_area.addTab(page, title, close_mode="hide")

    def _apply_default_plot_layout(self) -> None:
        """Arrange the plot docks as a default two-column grid beside the controls.

        Mirrors the original dashboard (two columns of plots, the state path along
        the bottom) but as independent, resizable docks. Falls back silently to the
        flat tab order if the layout cannot be applied. Only used when there is no
        saved arrangement (see :meth:`_restore_dock_layout`).
        """
        def _tab(name: str) -> dict:
            return {"type": "tab", "current_index": 0, "tabs": [{"tab_name": name}]}

        def _row(left: str, right: str) -> dict:
            return {
                "type": "splitter",
                "orientation": "horizontal",
                "sizes": [600, 600],
                "children": [_tab(left), _tab(right)],
            }

        state = {
            "version": 1,
            "root": {
                "type": "splitter",
                "orientation": "horizontal",
                "sizes": [300, 1200],
                "children": [
                    {
                        "type": "tab",
                        "current_index": 0,
                        "tabs": [
                            {"tab_name": "H2MM Settings"},
                            {"tab_name": "Channel Definitions"},
                        ],
                    },
                    {
                        "type": "splitter",
                        "orientation": "vertical",
                        "sizes": [320, 320, 320, 220],
                        "children": [
                            _row(self._DOCK_FRET, self._DOCK_TDP),
                            _row(self._DOCK_SEL, self._DOCK_DWELL),
                            _row(self._DOCK_NANO, self._DOCK_RATES),
                            _tab(self._DOCK_PATH),
                        ],
                    },
                ],
            },
        }
        try:
            self.dock_area.set_layout_state(state, emit_change=False)
        except Exception:
            pass

    def _save_dock_layout(self) -> None:
        """Persist the current dock arrangement (same INI file as the settings)."""
        try:
            import json

            ini = QSettings(str(get_plugin_settings_path("burst_h2mm")), QSettings.IniFormat)
            ini.setValue("dock_layout", json.dumps(self.dock_area.get_layout_state(), sort_keys=True))
        except Exception:
            pass

    def _restore_dock_layout(self) -> None:
        """Restore a saved dock arrangement, else apply the default grid.

        Both paths run synchronously here (BVA-style), never on ``showEvent`` — a
        showEvent-time restore fought the embedded navigation lifecycle and could
        leave a stale (deleted) plot widget registered, crashing a later show.
        Restore uses ``emit_change=False`` so rebuilding does not re-trigger a save.
        """
        try:
            import json

            ini = QSettings(str(get_plugin_settings_path("burst_h2mm")), QSettings.IniFormat)
            raw = ini.value("dock_layout")
            state = None
            if isinstance(raw, str) and raw:
                state = json.loads(raw)
            elif isinstance(raw, dict):
                state = raw
            if state and self.dock_area.set_layout_state(state, emit_change=False):
                return
        except Exception:
            pass
        self._apply_default_plot_layout()

    def _connect_signals(self):
        self.btn_folder.clicked.connect(self._select_folder)
        self._folder_field.folderDropped.connect(self._set_folder)
        self.btn_run.clicked.connect(self._run_analysis)
        self.btn_uncert.clicked.connect(self._run_uncertainty)
        self.btn_llscan.clicked.connect(self._run_llscan)
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

    def _make_progress(self, title, label, minv, maxv, cancel_cb):
        """Return a progress handle for a threaded run.

        Embedded in the Burst Analysis shell this drives the shared status bar
        (no popup), with its Cancel button wired to *cancel_cb*; standalone it is
        the modal ``EnhancedProgressDialog``. Both duck-type
        ``setValue`` / ``setLabelText`` / ``close``.
        """
        from chisurf.gui.widgets.navigation import find_status_reporter

        reporter = find_status_reporter(self)
        if reporter is not None:
            return reporter.begin_task(label, maxv, cancel=cancel_cb)
        prog = EnhancedProgressDialog(title, label, minv, maxv, self)
        prog.show()
        try:
            prog.canceled.connect(cancel_cb)
        except Exception:
            pass
        return prog

    def _run_analysis(self):
        if not self.data_folder:
            self._status("Please select a folder of .bur files first.")
            return
        settings = self._gather_settings()

        self._cancel = threading.Event()
        self._prog = self._make_progress("H2MM", "Loading bursts …", 0, 100, self._cancel.set)
        self._fit_t0 = time.perf_counter()
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
        dialogs.error(self, "H2MM error", message)
        logging.error(f"H2MM analysis failed: {tb}")

    # ── uncertainty (bootstrap) ──────────────────────────────────────

    def _run_uncertainty(self):
        """Bootstrap the selected model over bursts and overlay E/S error bars."""
        if self._bundle is None or self._result is None:
            self._status("Run a fit before estimating uncertainty.")
            return
        from ..core.analysis import bootstrap_uncertainty

        ana = self._bundle.analysis
        data = self._bundle.data
        settings = self._bundle.settings
        n_boot = 20

        self.btn_uncert.setEnabled(False)
        self._ucancel = threading.Event()
        self._uprog = self._make_progress(
            "H2MM", "Bootstrapping …", 0, n_boot, self._ucancel.set
        )
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
        dialogs.error(self, "H2MM uncertainty error", message)
        logging.error(f"H2MM bootstrap failed: {tb}")

    def _uncert_ranks(self, fret: np.ndarray) -> np.ndarray:
        """E-ascending rank of each native state (index into the Uncertainty arrays)."""
        finite = np.where(np.isfinite(fret), fret, np.inf)
        return np.argsort(np.argsort(finite))

    # ── profile-likelihood scan ──────────────────────────────────────

    def _run_llscan(self):
        """Profile the log-likelihood per state and show the scans in a dialog."""
        if self._bundle is None or self._result is None:
            self._status("Run a fit before the likelihood scan.")
            return
        from ..core.analysis import profile_likelihood

        ana = self._bundle.analysis
        data = self._bundle.data
        model = ana.best.model
        n_points = 25

        self.btn_llscan.setEnabled(False)
        self._llcancel = threading.Event()
        self._llprog = self._make_progress(
            "H2MM", "Likelihood scan …", 0, 100, self._llcancel.set
        )
        self._llscan_signals = _UncertSignals()
        self._llscan_signals.tick.connect(self._on_llscan_progress)

        def _progress(done, total_):
            if self._llcancel.is_set():
                raise _FitCancelled()
            self._llscan_signals.tick.emit(int(done), int(total_))

        worker = Worker(
            profile_likelihood, data, model,
            donor_streams=getattr(ana, "donor_streams", (0,)),
            acceptor_streams=getattr(ana, "acceptor_streams", (1,)),
            aex_streams=getattr(ana, "aex_streams", None),
            n_points=n_points, progress=_progress,
        )
        worker.signals.result.connect(self._on_llscan_result)
        worker.signals.error.connect(self._on_llscan_error)
        QThreadPool.globalInstance().start(worker)

    def _on_llscan_progress(self, done: int, total: int):
        try:
            pct = int(100 * done / max(total, 1))
            self._llprog.setValue(pct)
            self._llprog.setLabelText(f"Likelihood scan … {done}/{total} evaluations")
        except Exception:
            pass

    def _on_llscan_result(self, scans):
        try:
            self._llprog.close()
        except Exception:
            pass
        self.btn_llscan.setEnabled(True)
        if not scans:
            self._status("Likelihood scan: nothing to profile")
            return
        LikelihoodScanDialog(scans, self._uncertainty, self._state_color, self).show()
        self._status(f"Likelihood scan: {len(scans)} parameter profiles")

    def _on_llscan_error(self, tb):
        try:
            self._llprog.close()
        except Exception:
            pass
        self.btn_llscan.setEnabled(True)
        if tb and "_FitCancelled" in str(tb):
            self._status("Likelihood scan cancelled")
            return
        message = str(tb).strip().splitlines()[-1] if tb else "unknown error"
        dialogs.error(self, "H2MM likelihood scan error", message)
        logging.error(f"H2MM likelihood scan failed: {tb}")

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
        self._plot_rates(ana)
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
            self._overlay_trans_arrows(p, fret, stoich, ana)
            return

        p.setTitle("Dwell FRET states")
        p.setLabels(bottom="Apparent FRET E", left="Dwells")
        p.setXRange(0, 1)
        ymax = 1.0
        for i in range(fret.shape[0]):
            m = (st == i) & np.isfinite(e)
            color = self._state_color(i)
            if m.any():
                counts, edges = np.histogram(e[m], bins=41, range=(0, 1), weights=w[m])
                centers = (edges[:-1] + edges[1:]) / 2
                ymax = max(ymax, float(counts.max()))
                p.plot(centers, counts, pen=pg.mkPen(color, width=2), fillLevel=0,
                       brush=pg.mkBrush(color + "40"), name=f"S{i}")
            if np.isfinite(fret[i]):
                p.addItem(pg.InfiniteLine(pos=float(fret[i]), angle=90,
                          pen=pg.mkPen(color, width=1, style=Qt.DashLine)))
        self._overlay_e_ci_bands(p, fret)
        # Kinetic scheme along the E axis: state nodes at a common top baseline.
        node_y = np.full_like(fret, ymax * 1.08)
        self._overlay_trans_arrows(p, fret, node_y, ana, node_size=10)

    def _overlay_trans_arrows(self, p, xs, ys, ana, node_size=0):
        """Draw transition-rate arrows between states (burstH2MM ``trans_arrow_ES``).

        Each state ``i → j`` gets a straight arrow from node ``i`` to node ``j``,
        line width scaled by the rate and a slight perpendicular offset so the two
        directions don't overlap. ``ana.trans_rates`` supplies the 1/s rates.
        """
        rates = np.asarray(getattr(ana, "trans_rates", np.empty((0, 0))), dtype=np.float64)
        xs = np.asarray(xs, dtype=np.float64)
        ys = np.asarray(ys, dtype=np.float64)
        n = xs.shape[0]
        if rates.shape != (n, n):
            return
        pos = rates[np.isfinite(rates) & (rates > 0)]
        if pos.size == 0:
            return
        rmax = float(pos.max())
        span = float(np.nanmax(np.abs(np.diff(xs)))) if n > 1 else 1.0
        off = 0.03 * (span or 1.0)
        for i in range(n):
            for j in range(n):
                if i == j or not (np.isfinite(rates[i, j]) and rates[i, j] > 0):
                    continue
                if not (np.isfinite(xs[i]) and np.isfinite(xs[j])
                        and np.isfinite(ys[i]) and np.isfinite(ys[j])):
                    continue
                dx, dy = xs[j] - xs[i], ys[j] - ys[i]
                length = float(np.hypot(dx, dy)) or 1.0
                ox, oy = -dy / length, dx / length   # unit perpendicular
                x0, y0 = xs[i] + ox * off, ys[i] + oy * off
                x1, y1 = xs[j] + ox * off, ys[j] + oy * off
                color = self._state_color(i)
                width = 1.0 + 4.0 * (rates[i, j] / rmax)
                p.plot([x0, x1], [y0, y1], pen=pg.mkPen(color, width=width))
                ang = float(np.degrees(np.arctan2(y1 - y0, x1 - x0)))
                p.addItem(pg.ArrowItem(pos=(x1, y1), angle=180 - ang,
                                       headLen=12, brush=color, pen=None))
        if node_size:
            for i in range(n):
                if np.isfinite(xs[i]) and np.isfinite(ys[i]):
                    p.addItem(pg.ScatterPlotItem(
                        [xs[i]], [ys[i]], size=node_size, symbol="o",
                        pen=pg.mkPen("k"), brush=pg.mkBrush(self._state_color(i))))

    @staticmethod
    def _fmt_rate(v: float) -> str:
        """Human-readable 1/s rate label."""
        if v >= 1e6:
            return f"{v / 1e6:.1f}M"
        if v >= 1e3:
            return f"{v / 1e3:.1f}k"
        if v >= 1:
            return f"{v:.0f}"
        return f"{v:.2g}"

    def _plot_rates(self, ana):
        """Row 2, right: the transition-rate matrix (1/s) as an annotated heatmap."""
        p = self._p_rates
        for it in list(p.items):
            if isinstance(it, pg.TextItem):
                p.removeItem(it)
        rates = np.asarray(getattr(ana, "trans_rates", np.empty((0, 0))), dtype=np.float64)
        if rates.ndim != 2 or rates.shape[0] == 0:
            self._rates_img.clear()
            return
        n = rates.shape[0]
        self._rates_img.setImage(rates)
        self._rates_img.setRect(0, 0, n, n)
        try:
            self._rates_img.setColorMap(pg.colormap.get("CET-L4"))
        except Exception:
            pass
        ticks = [[(i + 0.5, f"S{i}") for i in range(n)]]
        p.getAxis("bottom").setTicks(ticks)
        p.getAxis("left").setTicks(ticks)
        for i in range(n):       # row i = from state, col j = to state
            for j in range(n):
                if i == j or not (np.isfinite(rates[i, j]) and rates[i, j] > 0):
                    continue
                t = pg.TextItem(self._fmt_rate(float(rates[i, j])), anchor=(0.5, 0.5), color="w")
                t.setPos(j + 0.5, i + 0.5)
                p.addItem(t)
        p.setRange(xRange=(0, n), yRange=(0, n), padding=0)

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
        # Plots are now separate docks; save the one whose dock is currently active,
        # falling back to the FRET plot if the active page isn't a plot dock.
        current = self.dock_area.currentWidget() if hasattr(self.dock_area, "currentWidget") else None
        page = current if current in getattr(self, "_plot_pages", {}).values() else None
        if page is None:
            page = self._plot_pages.get(self._DOCK_FRET)
        default_name = "h2mm.png"
        for title, candidate in self._plot_pages.items():
            if candidate is page:
                default_name = f"h2mm_{title.lower().replace(' ', '_').replace('–', '-')}.png"
                break
        path, _ = QFileDialog.getSaveFileName(self, "Save plot", default_name, "PNG (*.png)")
        if path and page is not None:
            page.grab().save(path)

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
        # Report via normal logging; the shell's status bar shows it when embedded.
        logging.getLogger(__name__).info(msg)
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
        """Persist settings and dock arrangement when the window closes."""
        self._save_settings()
        self._save_dock_layout()
        super().closeEvent(event)
