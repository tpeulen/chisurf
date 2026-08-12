"""H2MM analysis tool: toolbar, tabbed settings, and pyqtgraph result plots."""

from __future__ import annotations

import pathlib
import threading
import time
from typing import Any

import numpy as np
import pyqtgraph as pg
from qtpy import QtCore
from qtpy.QtCore import (
    QCoreApplication,
    QObject,
    QSettings,
    QSize,
    Qt,
    Signal,
)
from qtpy.QtGui import QDragEnterEvent, QDropEvent, QFont
from qtpy.QtWidgets import (
    QApplication,
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
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from chisurf import logging
from chisurf.core.datastore import row_count
from chisurf.gui.misc_helpers import get_plugin_settings_path, persist_plugin_state
from chisurf.gui.widgets.dock_area.dock_area import DockArea
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.event_pump import pump_ui
from chisurf.gui.widgets.messages import MessagesMixin, Msg
from chisurf.gui.widgets.wizard import DetectorWizardPage
from chisurf.core import analysis_cache
from chisurf.core.fio.fluorescence.burst_manifest import source_inputs
from chisurf.gui.widgets.tool_buttons import flag_attention
from chisurf.gui.widgets.tools.help_guide import attach_help_and_guide

from ..api.models import H2mmSettings, StreamSettings
from ..backend.services import run_analysis, write_result_tables
from ..core.engines import DECODER_LABELS, ENGINE_LABELS
from ..core.engines import DECODERS as H2mmDecoders
from ..core.engines import ENGINES as H2mmEngines
from chisurf.gui import dialogs
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

#: Bump in the same change that alters what this tool computes, so results
#: written by the previous version stop reading as current.
ALGORITHM_VERSION = 1


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


# The tool used to carry its own ``HelpDialog`` — a hard-coded HTML summary plus
# the CLI ``--help`` output. It is gone: the shared ``?`` modal renders
# ``gui/help.md`` instead, so the help is prose in a file rather than a string
# literal in a widget, its links are live, and it sits beside the ``guide.json``
# that answers the other question. See
# :mod:`chisurf.gui.widgets.tools.help_guide`.


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
class H2mmTool(ChisurfDockTool):
    """H2MM analysis widget with toolbar, tabbed settings, and result plots."""

    class Error(MessagesMixin.Error):
        """Conditions that stop a run, or that a run ended in."""

        no_folder = Msg("Select a folder of .bur files first.")
        fit_failed = Msg("The H2MM fit failed: {}")
        uncertainty_failed = Msg("The bootstrap failed: {}")
        llscan_failed = Msg("The likelihood scan failed: {}")

    def __init__(self, parent=None, *, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("smFRET H2MM Analysis")
        self.data_folder: pathlib.Path | None = None
        self.file_type = "SPC-130"
        self._result = None
        self._bundle = None
        # What the displayed fit was computed from, so an identical request
        # (another Next, a revisit of this step) does not refit.
        self._result_cache = analysis_cache.ResultCache()
        self._running_fingerprint: str | None = None
        self._fit_task = None
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
        # A fit whose bursts and settings are unchanged is skipped; this is how
        # the user asks for it anyway (a rebuilt engine, a suspect scan).
        self.btn_restart = action_button(
            "restart", tooltip="Refit H2MM from scratch, even if nothing changed"
        )
        # The fit starts on its own when this step is opened, and a state scan
        # with restarts runs for minutes: stopping it has to be one click away,
        # not buried in a progress bar the shell may render as a status line.
        self.btn_stop = action_button("stop", tooltip="Stop the running H2MM fit")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
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
        # The dwell grain had no way out of this window: `h2mm_dwells.csv` was
        # written and then opened by hand. One row per dwell is a table ndX is
        # made for — gate on state, duration, E/S, and drop the censored
        # burst-edge dwells with the flag that is already in it.
        self.btn_dwells_ndx = styled_tool_button("\U0001f52c", kind="toggle", tooltip=(
            "Dwells in ndX — open the per-dwell table (one row per Viterbi dwell: "
            "state, photons, duration, E/S, Is Edge) in an ndX window. Run a fit "
            "first."
        ))
        self.btn_dwells_ndx.clicked.connect(self.open_dwells_in_ndx)

        self.toolbar.addWidget(self.btn_folder)
        self.toolbar.addWidget(self.btn_run)
        self.toolbar.addWidget(self.btn_restart)
        self.toolbar.addWidget(self.btn_stop)
        self.toolbar.addWidget(self.btn_uncert)
        self.toolbar.addWidget(self.btn_llscan)
        self.toolbar.addWidget(self.btn_save)
        self.toolbar.addWidget(self.btn_dwells_ndx)
        self.toolbar.addWidget(self._folder_field)
        _spacer = QWidget()
        _spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(_spacer)
        # Adjacent stretches share the slack rather than adding to it, so the
        # helper must not add a second one and strand the pair mid-bar.
        self.toolbar.setProperty("_chisurf_right_spacer", True)
        self.toolbar.addSeparator()
        # The shared **Guide** / ``?`` pair, replacing a hand-rolled dialog that
        # carried this tool's help as an HTML literal. This window is a plain
        # ``QMainWindow``, so the free function attaches them rather than a mixin.
        attach_help_and_guide(
            self, self.toolbar, title="Photon-by-photon HMM — help"
        )

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
        self.sb_seed = QSpinBox()
        self.sb_seed.setRange(0, 2**31 - 2)
        self.sb_seed.setValue(0)
        self.sb_seed.setToolTip(
            "Random seed for the restarts. The same seed refits to the same "
            "answer, so a scan can be reported and reproduced; change it to draw "
            "an independent sample of starting points."
        )
        self.sb_divisors.setSpecialValueText("off (E only)")
        self.sb_divisors.setToolTip(
            "Nanotime divisors: split each stream into this many micro-time "
            "(fluorescence-lifetime) bins so H2MM can separate states that share "
            "an apparent FRET E but differ in lifetime. 1 = off."
        )
        # What the run leaves on disk. Two independent formats, not a fallback:
        # the per-photon state assignment is what every later step reads, so it
        # is worth being explicit about where it ends up.
        self.cb_photon_hdf5 = QCheckBox("HDF5")
        self.cb_photon_hdf5.setChecked(True)
        self.cb_photon_hdf5.setToolTip(
            "Write h2mm_photons.h5 — compact and fast to reload."
        )
        self.cb_photon_csv = QCheckBox("CSV")
        self.cb_photon_csv.setChecked(True)
        self.cb_photon_csv.setToolTip(
            "Write h2mm_photons.csv — what every other tool can open."
        )
        photon_row = QWidget()
        photon_h = QHBoxLayout(photon_row)
        photon_h.setContentsMargins(0, 0, 0, 0)
        photon_h.addWidget(self.cb_photon_hdf5)
        photon_h.addWidget(self.cb_photon_csv)
        photon_h.addStretch(1)

        # How each photon gets its state. A separate choice from how the model
        # is fitted, and one that changes what a per-state decay is made of.
        self.cb_decoder = QComboBox()
        for _d in H2mmDecoders:
            self.cb_decoder.addItem(DECODER_LABELS.get(_d, _d), _d)
        self.cb_decoder.setToolTip(
            "How each photon is assigned a state. Viterbi takes the single most "
            "likely path, which reports the photon distribution "
            "winner-takes-all: well-separated states come out inflated and "
            "ambiguous ones erased. Jitter and FFBS draw from the posterior "
            "instead, so the distribution is faithful; FFBS also keeps the dwell "
            "structure that jitter's independent draws destroy. The unbiased "
            "occupancy is reported either way."
        )
        self.sb_decoder_seed = QSpinBox()
        self.sb_decoder_seed.setRange(0, 2**31 - 2)
        self.sb_decoder_seed.setValue(0)
        self.sb_decoder_seed.setToolTip(
            "Seed for the sampling decoders. Reproducible and independent of the "
            "thread count; change it to draw an independent assignment."
        )
        decoder_row = QWidget()
        decoder_h = QHBoxLayout(decoder_row)
        decoder_h.setContentsMargins(0, 0, 0, 0)
        decoder_h.addWidget(self.cb_decoder, 1)
        self.lb_decoder_seed = QLabel("seed")
        self.lb_decoder_seed.setToolTip(self.sb_decoder_seed.toolTip())
        decoder_h.addWidget(self.lb_decoder_seed)
        decoder_h.addWidget(self.sb_decoder_seed)
        self.cb_decoder.currentIndexChanged.connect(self._update_decoder_enabled)

        # Write the assignment back into the photons, so every other tool can
        # select a state without knowing anything about H2MM.
        self.cb_state_tttr = QCheckBox("PTU")
        self.cb_state_tttr.setToolTip(
            "Write <file>_h2mm_states.ptu beside each measurement, with the "
            "routing channels encoding (stream, state). A per-state decay or FCS "
            "is then an ordinary channel selection in any tool."
        )
        self.cb_state_sidecar = QCheckBox("sidecar")
        self.cb_state_sidecar.setToolTip(
            "Write <file>_h2mm_states.msgpack — the per-photon state array plus "
            "the model, decoder, seed and channel map. Leaves the source file "
            "untouched and has no channel-id budget."
        )
        self.cb_state_write = QCheckBox("write")
        self.cb_state_write.setToolTip(
            "Write the decoded state assignment back into the photon stream."
        )
        self.cb_state_write.toggled.connect(self._update_decoder_enabled)
        state_row = QWidget()
        state_h = QHBoxLayout(state_row)
        state_h.setContentsMargins(0, 0, 0, 0)
        state_h.addWidget(self.cb_state_write)
        state_h.addWidget(self.cb_state_tttr)
        state_h.addWidget(self.cb_state_sidecar)
        state_h.addStretch(1)

        of.addRow("Restarts:", self.sb_restarts)
        of.addRow("Seed:", self.sb_seed)
        of.addRow("Photon table:", photon_row)
        of.addRow("Max iterations:", self.sb_max_iter)
        of.addRow("Min photons/burst:", self.sb_min_photons)
        of.addRow("Macro-time scale:", self.sb_time_scale)
        of.addRow("Nanotime divisors:", self.sb_divisors)
        of.addRow("Decoder:", decoder_row)
        of.addRow("State photons:", state_row)
        # Object names so the guided tour can point at individual controls: this
        # panel is hand-built rather than an AutoForm view, so there is no view
        # spec for a step to name. Prefixed because ``{"name": …}`` matches by
        # *suffix* — a bare "seed" would also find the decoder's own seed box.
        for widget, object_name in (
            (self.sb_restarts, "h2mm_restarts"),
            (self.sb_seed, "h2mm_seed"),
            (self.cb_decoder, "h2mm_decoder"),
            (self.cb_engine, "h2mm_engine"),
        ):
            widget.setObjectName(object_name)
        self.cb_state_tttr.setChecked(True)
        self.cb_state_sidecar.setChecked(True)
        self._update_decoder_enabled()
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
        # The legend names the detection colours only — one entry each, laid out
        # in a single row. Naming all colour×state curves put a block of text
        # across the middle of a small plot; the state is carried by the line
        # style and spelled out in the title instead.
        self._nano_legend = self._p_nano.addLegend(offset=(-5, 5), labelTextSize="7pt")

        # states × colours curves is more than a small plot can carry, so the
        # dock owns a filter bar: which colours, which states. Built empty and
        # populated from the fit, because neither set is known until then.
        nano_page = QWidget()
        nano_v = QVBoxLayout(nano_page)
        nano_v.setContentsMargins(0, 0, 0, 0)
        nano_v.setSpacing(2)
        nano_v.addWidget(w_nano, 1)
        # A flow layout, not a row: with three colours and up to five states the
        # bar is wider than this dock at its default width, and a control that
        # has fallen off the edge cannot be ticked. Wrapping keeps every one
        # reachable however narrow the dock is dragged.
        from chisurf.gui.widgets.dock_area.dock_stacked_tab_bar import FlowLayout

        self._nano_filter_bar = QWidget()
        # Compact type, like the other in-plot toggles: the bar is chrome around
        # a small plot, and every pixel it takes comes off the decay.
        self._nano_filter_bar.setStyleSheet(
            "QCheckBox, QLabel { color: #aaa; font-size: 11px; }"
        )
        self._nano_filter_layout = FlowLayout(
            self._nano_filter_bar, margin=1, h_spacing=5, v_spacing=1
        )
        nano_v.addWidget(self._nano_filter_bar)
        self._nano_colour_boxes: dict[str, QCheckBox] = {}
        self._nano_state_boxes: dict[int, QCheckBox] = {}
        self._nano_decays = None

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
            self._DOCK_NANO: nano_page,
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
        self.btn_run.clicked.connect(self._on_run_clicked)
        self.btn_restart.clicked.connect(self._on_restart_clicked)
        self.btn_uncert.clicked.connect(self._run_uncertainty)
        self.btn_llscan.clicked.connect(self._run_llscan)
        self.btn_save.clicked.connect(self._save_plot)

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
            seed=self.sb_seed.value(),
            photon_hdf5=self.cb_photon_hdf5.isChecked(),
            photon_csv=self.cb_photon_csv.isChecked(),
            max_iter=self.sb_max_iter.value(),
            min_photons=self.sb_min_photons.value(),
            time_scale=self.sb_time_scale.value(),
            divisors=self.sb_divisors.value(),
            file_type=self.file_type,
            engine=self.cb_engine.currentData() or "em",
            decoder=self.cb_decoder.currentData() or "viterbi",
            decoder_seed=self.sb_decoder_seed.value(),
            write_state_tttr=self.cb_state_write.isChecked(),
            state_tttr_ptu=self.cb_state_tttr.isChecked(),
            state_tttr_sidecar=self.cb_state_sidecar.isChecked(),
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

        Thin alias for :class:`~chisurf.gui.progress.ChiSurfProgress`, which
        decides where the bar appears (shell status bar when embedded, modal
        dialog when standalone, the log when headless) and delivers Cancel to
        *cancel_cb* — the fit runs in a thread, so the stop has to be pushed to
        it rather than polled.
        """
        return ChiSurfProgress(self, label, maxv, title=title, cancel=cancel_cb)

    def input_files(self) -> list:
        """Everything this fit reads: the burst tables and the photons.

        H2MM is a photon-by-photon fit, so the raw measurements named in the
        folder's manifest are inputs as much as the `.bur` tables are.
        """
        if not self.data_folder:
            return []
        tables = sorted(pathlib.Path(self.data_folder).glob("**/*.bur"))
        return tables + list(source_inputs(self.data_folder))

    def analysis_fingerprint(self, settings) -> str:
        """Fingerprint of the inputs, the settings, the read context and the code."""
        return analysis_cache.fingerprint(
            self.input_files(),
            {
                "settings": settings,
                "_read_context": analysis_cache.photon_read_context(),
            },
            extra=analysis_cache.algorithm_tag("h2mm", ALGORITHM_VERSION, "tttrlib"),
        )

    def _run_analysis(self, *, force: bool = False):
        """Fit H2MM models off the GUI thread, streaming the scan into the plots.

        A fit whose burst files and settings are identical to the one already
        displayed is skipped — the workflow asks for a run on every *Next*, and
        scanning state counts with restarts is minutes of work on real data.
        ``force=True`` refits regardless — which, because the restarts are
        seeded, reproduces the same answer rather than resampling. To draw a
        genuinely different sample, change the seed.
        """
        if not self.data_folder:
            self.Error.no_folder()
            return
        self.Error.no_folder.clear()
        self.Error.fit_failed.clear()
        settings = self._gather_settings()
        fingerprint = self.analysis_fingerprint(settings)
        if (
            not force
            and self._result is not None
            and self._result_cache.matches(fingerprint)
        ):
            self._status(
                "Unchanged — kept the previous H2MM fit (🔁 Restart refits it)"
            )
            flag_attention(self.btn_restart, True)
            return
        flag_attention(self.btn_restart, False)
        self._running_fingerprint = fingerprint
        self._fit_t0 = time.perf_counter()
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._status("Fitting H2MM models \u2026")
        self._fit_task = ChiSurfProgress.run(
            self, "Loading bursts \u2026", self._fit_worker, args=(settings,),
            maximum=100, title="H2MM", owner=self.btn_run,
            on_partial=self._plot_scan_live,
            on_result=self._on_fit_result,
            on_error=self.Error.fit_failed,
            on_done=self._on_fit_done,
        )

    def _on_fit_done(self) -> None:
        """Whatever the outcome, the fit is over: Run is available, Stop is not."""
        self._fit_task = None
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def stop(self) -> None:
        """Stop the running fit.

        The worker checks for this between state counts and between iterations
        (``task.raise_if_cancelled``), so a stop lands within one iteration
        rather than at the end of the scan. A stopped fit leaves no result to
        reuse — the next run starts over rather than reporting the partial scan
        as finished.
        """
        task = self._fit_task
        if task is None:
            return
        task.cancel()
        # Abandoned rather than merely invalidated: revisiting this step must not
        # start the same minutes-long scan the user just stopped.
        self._result_cache.abandon(self._running_fingerprint)
        self._status("Stopping the H2MM fit \u2026")

    def showEvent(self, event) -> None:
        """Start fitting for the folder this panel was given, once it is shown.

        Landing on the H2MM step should start the fit the upstream steps set it
        up for. Deferred by one event-loop turn so the panel paints first and so
        it sees the burst folder — the shell shows a panel and then applies the
        workflow context to it, in that order. Arriving again does not refit: the
        run is gated on the fingerprint (see :meth:`_run_analysis`), and Stop is
        there for the fit you did not want.
        """
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._auto_run)

    def _auto_run(self) -> None:
        """Fit for the current folder, quietly doing nothing when there is none.

        A fit the user stopped does not start itself again when the step is
        revisited — otherwise Stop would only postpone minutes of work until the
        next *Next*. Changing a burst file or a setting gives a different
        fingerprint, which was never abandoned, so the suppression is exactly as
        narrow as the stop was.
        """
        if not self.data_folder or self._fit_is_running():
            return
        if self._result_cache.was_abandoned(
            self.analysis_fingerprint(self._gather_settings())
        ):
            self._status("Stopped earlier — press Run to fit H2MM")
            return
        self._run_analysis()

    def _on_run_clicked(self) -> None:
        """Fit because the user asked, clearing any earlier stop."""
        self._result_cache.allow()
        self._run_analysis()

    def _on_restart_clicked(self) -> None:
        """Refit even though nothing changed."""
        self._result_cache.allow()
        self._run_analysis(force=True)

    def _fit_is_running(self) -> bool:
        """Whether a fit started by this panel is still going."""
        task = self._fit_task
        # ``is_running`` is a property of the task handle, not a method.
        return task is not None and task.is_running

    def _fit_worker(self, settings, task):
        """Worker: fit every state count, reporting through *task*. No GUI here.

        The progress value carries the bar and its ETA; the *partial* carries the
        snapshot of finished fits the live plots draw. Splitting them that way is
        what removes the hand-rolled 10 Hz throttle: the task layer drops a
        repeated progress value, and a snapshot is only produced when a
        state-count fit actually finishes.
        """
        t0 = self._fit_t0

        def _progress(done, total_, fits):
            task.raise_if_cancelled()
            pct = int(90 * done / max(total_, 1))  # last 10% for finalisation
            if done > 0.05:
                eta = (time.perf_counter() - t0) * (total_ - done) / done
                task.set_progress(
                    pct,
                    f"Fitting \u2026 {int(done)}/{total_} state counts done   "
                    f"({pct}%, ETA {self._fmt_eta(eta)})",
                )
            else:
                task.set_progress(pct, "Fitting \u2026 (estimating ETA)")
            if float(done).is_integer() and fits:
                task.set_partial(list(fits))

        result, bundle = run_analysis(
            settings, analysis_folder=str(self.data_folder), progress=_progress
        )

        # Write the result tables, as the CLI and the RPC service already do.
        # Without this a GUI fit left *nothing* on disk: the per-photon state
        # assignment lived only in this panel, so the state-wise MLE step could
        # not see that H2MM had run at all, and neither could ndX. Written here,
        # in the worker, because it is one more pass over every photon.
        if getattr(settings, "write_photons", True) and self.data_folder:
            task.set_progress(95, "Writing H2MM tables …")
            try:
                write_result_tables(result, bundle, pathlib.Path(self.data_folder) / "h2mm")
            except Exception as exc:  # pragma: no cover - disk/permission path
                logging.warning("could not write the H2MM tables: %s", exc)
        return result, bundle

    @staticmethod
    def _fmt_eta(seconds: float) -> str:
        """Human-readable ETA string."""
        if seconds < 90:
            return f"{seconds:.0f} s"
        if seconds < 3600:
            return f"{seconds / 60:.1f} min"
        return f"{seconds / 3600:.1f} h"

    def _on_fit_result(self, payload):
        """Store results, finalise plots, and close the progress dialog."""
        result, bundle = payload
        self._result = result
        self._bundle = bundle
        if self._running_fingerprint is not None:
            self._result_cache.remember(self._running_fingerprint)
        self._uncertainty = None  # bootstrap CIs are stale after a new fit
        self._update_plots()
        # The seed is part of the answer: the same one refits identically, so a
        # reported state count is only reproducible if it travels with it.
        seed = (result.settings_applied or {}).get("seed")
        msg = (
            f"Selected {result.n_states} states "
            f"({result.criterion.upper()}) from {result.n_bursts} bursts / "
            f"{result.n_photons} photons"
            + (f" (seed {seed})" if seed is not None else "")
        )
        # The occupancy is what most readers take away, and the counted one is
        # biased under Viterbi — so report the posterior estimate here rather
        # than leaving it in a JSON file nobody opens.
        if result.posterior_populations:
            pops = ", ".join(f"{x:.3f}" for x in result.posterior_populations)
            msg += f" — occupancy {pops}"
            if result.decoder != "viterbi":
                msg += f" (decoder: {result.decoder})"
        if result.n_underflow:
            msg += f" — WARNING: {result.n_underflow} photons without posterior information"
        self._status(msg)

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
        self.Error.uncertainty_failed.clear()
        ChiSurfProgress.run(
            self, "Bootstrapping \u2026", self._uncertainty_worker,
            args=(data, ana, settings, n_boot),
            maximum=n_boot, title="H2MM", owner=self.btn_uncert,
            on_result=self._on_uncert_result,
            on_error=self.Error.uncertainty_failed,
            on_done=lambda: self.btn_uncert.setEnabled(True),
        )

    def dwell_table(self):
        """The per-dwell table of the current fit, or ``None``.

        The same builder the exporter writes to ``h2mm_dwells.csv``, so what a
        user explores is what a later reader gets.
        """
        if self._bundle is None:
            return None
        meta = getattr(self._bundle, "meta", None)
        if meta is None:
            return None  # loaded without per-photon metadata
        from ..core.decays import colour_groups
        from ..core.export import build_dwell_table

        ana = self._bundle.analysis
        micro_ns = getattr(self._bundle, "micro_time_ns", None)
        return build_dwell_table(
            self._bundle.data, meta, ana.dwells, ana.base_time_s,
            stream_groups=colour_groups(ana, self._bundle.settings),
            micro_time_ns=(micro_ns if micro_ns else None),
        )

    def open_dwells_in_ndx(self) -> bool:
        """Open the per-dwell table in ndX (one row per Viterbi dwell).

        The dwell is a grain this window computes and nothing consumed: the CSV
        was written for a human to open by hand. ndX is exactly the tool for it
        — gate on state, duration, E/S, and drop the censored burst-edge dwells
        with the ``Is Edge`` column that is already there.
        """
        table = self.dwell_table()
        if table is None or row_count(table) == 0:
            self._status("No dwells to explore — run a fit first.")
            return False
        try:
            from ndxplorer.core.data_source import DataSource

            try:
                from chisurf.plugins.ndxplorer.rpc_bridge import make_ndxplorer

                win = make_ndxplorer()
            except Exception:
                from ndxplorer import NDXplorer

                win = NDXplorer()
            win.setWindowTitle("ndX — H2MM dwells")
            self._ndx_dwell_window = win
            win.show()
            win.raise_()
            win.activateWindow()
            # ndX builds its plot widgets in a deferred init after the window is
            # shown; let that run first or the data lands before the UI exists.
            QApplication.processEvents()
            # from_store: the store IS the data, so nothing is copied on the
            # way into the window.
            win.data_source = DataSource.from_store(table)
            for name in ("recompute", "replot", "update_plots"):
                fn = getattr(win, name, None)
                if callable(fn):
                    fn()
        except Exception as exc:
            logging.warning("could not open the dwell table in ndX: %s", exc)
            self._status(f"ndX could not be opened: {exc}")
            return False
        self._status(f"{row_count(table)} dwells opened in ndX.")
        return True

    def _uncertainty_worker(self, data, ana, settings, n_boot, task):
        """Worker: bootstrap the selected model over bursts. No GUI here."""
        from ..core.analysis import bootstrap_uncertainty

        def _progress(done, total):
            task.raise_if_cancelled()
            task.set_progress(
                int(done), f"Bootstrapping \u2026 {int(done)}/{int(total)} resamples"
            )

        return bootstrap_uncertainty(
            data, int(ana.best.n_states),
            n_boot=n_boot, engine=getattr(settings, "engine", "em"),
            n_restarts=1, max_iter=300,
            donor_streams=getattr(ana, "donor_streams", (0,)),
            acceptor_streams=getattr(ana, "acceptor_streams", (1,)),
            aex_streams=getattr(ana, "aex_streams", None),
            progress=_progress,
        )

    def _on_uncert_result(self, unc):
        """Store bootstrap CIs and redraw the E/E–S and E–τ panels with error bars."""
        self._uncertainty = unc
        if self._bundle is not None:
            self._plot_dwell_fret(self._bundle.analysis)
        self._status(f"Uncertainty from {unc.n_boot} bootstrap resamples "
                     f"({unc.ci[0]:.0f}–{unc.ci[1]:.0f}% CI)")

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
        self.Error.llscan_failed.clear()
        ChiSurfProgress.run(
            self, "Likelihood scan \u2026", self._llscan_worker,
            args=(data, model, ana, n_points),
            maximum=100, title="H2MM", owner=self.btn_llscan,
            on_result=self._on_llscan_result,
            on_error=self.Error.llscan_failed,
            on_done=lambda: self.btn_llscan.setEnabled(True),
        )

    def _llscan_worker(self, data, model, ana, n_points, task):
        """Worker: profile the log-likelihood per state. No GUI here."""
        from ..core.analysis import profile_likelihood

        def _progress(done, total_):
            task.raise_if_cancelled()
            pct = int(100 * done / max(total_, 1))
            task.set_progress(
                pct, f"Likelihood scan \u2026 {int(done)}/{int(total_)} evaluations"
            )

        return profile_likelihood(
            data, model,
            donor_streams=getattr(ana, "donor_streams", (0,)),
            acceptor_streams=getattr(ana, "acceptor_streams", (1,)),
            aex_streams=getattr(ana, "aex_streams", None),
            n_points=n_points, progress=_progress,
        )

    def _on_llscan_result(self, scans):
        if not scans:
            self._status("Likelihood scan: nothing to profile")
            return
        LikelihoodScanDialog(scans, self._uncertainty, self._state_color, self).show()
        self._status(f"Likelihood scan: {len(scans)} parameter profiles")

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

    def _update_decoder_enabled(self, *_):
        """Grey out what the current choices make meaningless.

        The seed only matters for a decoder that draws, and the two output
        formats only matter once writing is on — a live control that changes
        nothing is a question the user has to answer for no reason.
        """
        decoder = self.cb_decoder.currentData() or "viterbi"
        draws = decoder != "viterbi"
        self.sb_decoder_seed.setEnabled(draws)
        self.lb_decoder_seed.setEnabled(draws)
        writing = self.cb_state_write.isChecked()
        self.cb_state_tttr.setEnabled(writing)
        self.cb_state_sidecar.setEnabled(writing)

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
        # The labels are drawn at a fixed point size while the cells scale with
        # the dock, so in a narrow panel neighbouring rates ran into each other
        # and the matrix became unreadable. Size them to their cell, and keep
        # doing so as the panel is resized.
        view = p.getViewBox()
        if view is not None and not getattr(self, "_rate_labels_tracked", False):
            view.sigResized.connect(self._fit_rate_labels)
            self._rate_labels_tracked = True
        self._fit_rate_labels()

    def _fit_rate_labels(self) -> None:
        """Scale the rate-matrix labels so each fits inside its own cell."""
        p = self._p_rates
        view = p.getViewBox()
        if view is None:
            return
        try:
            px_w, px_h = view.viewPixelSize()
        except Exception:
            return
        if not px_w or not px_h:
            return
        cell_w = 1.0 / px_w  # one cell spans one data unit in each direction
        cell_h = 1.0 / px_h
        for item in p.items:
            if not isinstance(item, pg.TextItem):
                continue
            chars = max(len(item.toPlainText()), 1)
            # A digit is roughly 0.6 * point size wide; leave a margin in the cell.
            size = min(cell_w * 0.8 / (0.6 * chars), cell_h * 0.5)
            # Below ~5 pt the number is unreadable anyway — hide it rather than
            # overprint the neighbouring cell.
            item.setVisible(size >= 5.0)
            font = QFont()
            font.setPointSizeF(max(5.0, min(12.0, size)))
            item.setFont(font)

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
        """Bottom-right: per-state dwell-time distributions (ms).

        Dwells that touch a burst edge are left out. They did not end — the
        burst did — so their duration is a lower bound set by the photon
        selection, and a state slower than a burst has *only* those: plotted,
        they draw the burst-duration distribution under the name "dwell time".
        A state with no complete dwell is named in the title rather than
        silently missing from the legend.
        """
        self._p_dwell.clear()
        self._dwell_legend.clear()
        base_ms = ana.base_time_s * 1e3
        arrays = ana.dwell_time_arrays()  # complete dwells only
        censored = []
        for i, (_state, arr) in enumerate(sorted(arrays.items())):
            if arr.size == 0:
                censored.append(f"S{i}")
                continue
            counts, edges = np.histogram(arr * base_ms, bins=30)
            centers = (edges[:-1] + edges[1:]) / 2
            self._p_dwell.plot(centers, counts, pen=pg.mkPen(self._state_color(i), width=2),
                               name=f"S{i}")
        title = "Dwell times (burst-edge dwells excluded)"
        if censored:
            title += f" — {', '.join(censored)}: no dwell ended within a burst"
        self._p_dwell.setTitle(title)

    #: Pen colour per detection colour. A decay is drawn in the colour of the
    #: light that produced it, so a green curve is green photons — the state is
    #: carried by the line style instead.
    _COLOUR_PENS = {
        "green": "#2ca02c", "donor": "#2ca02c",
        "red": "#d62728", "acceptor": "#d62728",
        "yellow": "#e8b400", "aex": "#e8b400",
    }
    #: Line style per state, so one plot can hold states × colours curves.
    _STATE_DASHES = [
        QtCore.Qt.SolidLine, QtCore.Qt.DashLine, QtCore.Qt.DotLine,
        QtCore.Qt.DashDotLine, QtCore.Qt.DashDotDotLine,
    ]
    #: How to say those styles in the title, since the legend names colours.
    _DASH_NAMES = ["solid", "dashed", "dotted", "dash-dot", "dash-dot-dot"]

    def _colour_pen(self, name: str, state: int):
        """A pen whose colour is the detection channel and whose dash is the state."""
        rgb = self._COLOUR_PENS.get(str(name).strip().lower(), "#999999")
        style = self._STATE_DASHES[state % len(self._STATE_DASHES)]
        return pg.mkPen(rgb, width=2, style=style)

    def _plot_nanotime(self, ana):
        """Row 2, left: per-state fluorescence decays, one curve per colour.

        A decay is only defined *within* a detection colour. Histogramming every
        photon of a state — donor and acceptor together — gives a curve whose
        shape is set by the green:red mixing ratio, i.e. by the FRET efficiency,
        and which is the decay of nothing. The photons are therefore split by
        stream (which separates colours that share a detector under PIE) and
        merged only within one colour; :mod:`..core.decays` does both, and writes
        the underlying per-detector histograms to ``h2mm_state_decays.csv``.

        Requires the per-photon micro times (``bundle.meta``); when absent (e.g. a
        result loaded without photon metadata) the panel is left empty.
        """
        from ..core.decays import colour_groups, state_decays

        p = self._p_nano
        p.clear()
        self._nano_legend.clear()
        meta = getattr(self._bundle, "meta", None)
        path = np.asarray(ana.path, dtype=np.int64)
        if meta is None or getattr(meta, "micro_time", None) is None:
            return
        micro = np.asarray(meta.micro_time)
        if micro.shape[0] != path.shape[0] or micro.size == 0 or int(micro.max()) <= 0:
            return

        self._nano_decays = state_decays(
            micro, meta.channel, self._bundle.data.streams, path,
            n_states=int(ana.fret.shape[0]),
            groups=colour_groups(ana, self._bundle.settings),
            micro_time_ns=getattr(self._bundle, "micro_time_ns", None),
        )
        self._rebuild_nano_filters(self._nano_decays)
        self._draw_nanotime()

    def _rebuild_nano_filters(self, decays) -> None:
        """Offer one checkbox per colour and per state, for *this* fit.

        Rebuilt rather than reused: a refit can change the state count, and a
        stale "S3" box would filter on a state that no longer exists. A colour or
        state already on screen keeps its tick, so a refit does not silently
        change what is being looked at.
        """
        previous_colours = {n: b.isChecked() for n, b in self._nano_colour_boxes.items()}
        previous_states = {s: b.isChecked() for s, b in self._nano_state_boxes.items()}
        while self._nano_filter_layout.count():
            item = self._nano_filter_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._nano_colour_boxes = {}
        self._nano_state_boxes = {}

        self._nano_filter_layout.addWidget(QLabel("Colour:"))
        for i, colour in enumerate(decays.colours):
            box = QCheckBox(colour)
            # Default to the donor alone: every colour at once is what made this
            # plot unreadable. The rest are one tick away, and visibly so.
            box.setChecked(previous_colours.get(colour, i == 0))
            box.setToolTip(
                f"Show the {colour} decays "
                f"(detectors {decays.colour_channels.get(colour, [])})"
            )
            box.toggled.connect(self._draw_nanotime)
            self._nano_filter_layout.addWidget(box)
            self._nano_colour_boxes[colour] = box

        self._nano_filter_layout.addWidget(QLabel("State:"))
        for s in range(decays.n_states):
            box = QCheckBox(f"S{s}")
            box.setChecked(previous_states.get(s, True))
            box.setToolTip(f"Show state {s} ({self._DASH_NAMES[s % len(self._DASH_NAMES)]})")
            box.toggled.connect(self._draw_nanotime)
            self._nano_filter_layout.addWidget(box)
            self._nano_state_boxes[s] = box

    def _draw_nanotime(self) -> None:
        """Draw the decays the filter bar selects. Cheap: nothing is recomputed."""
        decays = self._nano_decays
        p = self._p_nano
        p.clear()
        self._nano_legend.clear()
        if decays is None:
            return
        x = decays.centers_ns()
        p.setLabel("bottom", "Micro time (ns)" if decays.micro_time_ns else "Micro time")
        named: set[str] = set()
        states_drawn: set[int] = set()
        # With one colour on screen the legend only repeats what the ticked
        # checkbox already says, while sitting on top of the curve it names.
        selected = [
            c for c in decays.colours
            if (b := self._nano_colour_boxes.get(c)) is None or b.isChecked()
        ]
        label_curves = len(selected) > 1
        for k, colour in enumerate(decays.colours):
            box = self._nano_colour_boxes.get(colour)
            if box is not None and not box.isChecked():
                continue
            for s in range(decays.n_states):
                s_box = self._nano_state_boxes.get(s)
                if s_box is not None and not s_box.isChecked():
                    continue
                y = decays.colour_counts[s, k]
                keep = y > 0
                if not keep.any():
                    continue
                # Name one curve per colour: the legend answers "which colour is
                # which", the title answers "which line style is which state".
                name = colour if (label_curves and colour not in named) else None
                named.add(colour)
                states_drawn.add(s)
                p.plot(x[keep], y[keep], pen=self._colour_pen(colour, s), name=name)
        try:
            self._nano_legend.setColumnCount(max(1, len(named)))
        except Exception:  # pragma: no cover - older pyqtgraph
            pass
        key = " · ".join(
            f"{self._DASH_NAMES[s % len(self._DASH_NAMES)]} S{s}"
            for s in sorted(states_drawn)
        )
        p.setTitle(f"Per-state decay<br><span style='font-size:7pt'>{key}</span>"
                   if key else "Per-state decay")

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
        # Repaint through the shared guarded pump (see chisurf.gui.event_pump).
        pump_ui(allow_input=False)

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
