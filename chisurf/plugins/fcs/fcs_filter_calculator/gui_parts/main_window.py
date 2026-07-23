from __future__ import annotations

import hashlib
import pathlib
from typing import Dict, List

import numpy as np
import pyqtgraph as pg
from qtpy import QtCore, QtGui, QtWidgets

import chisurf as cs
from chisurf.core.fluorescence.decay import (
    afterpulse_decay_pattern,
    compute_detector_patterns_from_fit,
    lifetime_spectrum_from_model,
    optimize_synthetic_scatter_pattern,
    sample_decay_shot_noise,
    scattered_light_decay_pattern,
)
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.dock_area import DockArea

from ..api import FilterResult, compute_filters, synthetic_component_decay, unmix_decay


def _build_filter_client():
    from ..gui.client import FilterCalcClient
    return FilterCalcClient()
from .calculator_options import CalculatorOptionsViewModel
from .data_loading import load_vector
from .widgets import SpeciesListWidget

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:
    persist_plugin_state = lambda n: lambda c: c

#: Convolution/acquisition plumbing hidden from the Auto-fit parameter table.
#: These are configured by the auto-fit itself (axis, range, IRF placement,
#: acquisition times), not results the user reads or links, and showing all of
#: them would bury the handful of lifetimes and amplitudes that matter.
_AUTOFIT_HIDDEN_PARAMETERS = frozenset({
    "dt", "rep", "start", "stop", "irf_start", "irf_stop", "lb", "n0",
    "win-size", "tBg", "tMeas", "tDead", "r0", "g", "l1", "l2",
})


@persist_plugin_state("fcs_filter_calculator")
class FcsFilterCalculatorWidget(QtWidgets.QWidget):
    """A modular implementation of the Filtered FCS: Lifetime Filter Calculator."""

    _PLOT_COLORS = (
        "#38bdf8", "#fb7185", "#4ade80", "#facc15",
        "#c084fc", "#fb923c", "#2dd4bf", "#f472b6",
    )
    _NAMED_COLORS = {
        "green": "#4ade80",
        "red": "#fb4d4d",
        "yellow": "#facc15",
        "blue": "#38bdf8",
        "cyan": "#22d3ee",
        "magenta": "#f472b6",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Filtered FCS: Lifetime Filter Calculator")
        self.resize(1000, 600)

        self._total_paths: List[pathlib.Path] = []
        self._total_vector: np.ndarray | None = None
        self._total_vectors_by_detector: dict[str, np.ndarray] = {}
        # Micro-time axis taken from the loaded data / setup: the TAC bin width
        # (ns) captured from the TTTR header, and an optional coarsening factor.
        self._data_dt_ns: float = 0.0
        self._micro_time_binning: int = 1
        self._suspend_compute: bool = False
        #: Whether the mixed decay was adopted from the Correlator (re-synced on show).
        self._total_from_correlator: bool = False
        #: Optional per-detector fit-range overrides {detector: (start, stop)} in TAC
        #: bins; a detector without an entry uses the global draggable region.
        self._detector_fit_ranges: dict[str, tuple[int, int]] = {}
        #: Persistent auto-fit settings, mirrored from the Auto-fit dock by
        #: `_sync_autofit_settings` (which rebuilds this dict wholesale, so every
        #: key here must have a dock control behind it). Periodic-convolution
        #: settings deliberately live in the Instrument dock instead and reach the
        #: fit through `_fit_period_ns`.
        self._auto_fit_settings: dict = {
            "kind": "lifetime", "n_components": 2, "tau_min": 0.2, "tau_max": 8.0,
        }
        #: Result of the last auto-fit, including the live `Fit`/`LifetimeModel`
        #: whose parameters the Auto-fit dock's table exposes for linking.
        self._auto_fit_result: dict | None = None
        self._result: FilterResult | None = None
        self._result_anisotropy = None  # For single-detector Anisotropy results
        self._result_multi_anisotropy = None  # For multi-detector Anisotropy results (list)
        self._result_multi_detector = None  # For multi-detector stacked results
        self._unmix_result = None
        # IRF / scatter pattern used per detector in the last computation, kept so
        # the reconstruction/decay plot can overlay the instrument response.
        self._irf_by_detector: dict[str, np.ndarray] = {}
        # Coarse scatter fits, only populated for detectors that have neither a
        # measured nor a usable synthetic IRF (the fallback branch of
        # `_nuisance_patterns`).
        self._synthetic_scatter_fits: dict[str, object] = {}

        # Detector Wizard Support
        from .data_loading import HAS_DETECTOR_WIZARD, load_detector_setups
        self._has_detector_wizard = HAS_DETECTOR_WIZARD
        self._load_detector_setups = load_detector_setups
        self._detector_settings = None
        
        # Cache for loaded decay data to avoid redundant file loading
        self._decay_cache = {}  # Key: (tuple(paths), tuple(chs)), Value: loaded_vectors
        self._routing_cache = {}  # Key: file_path, Value: dict of {routing_ch: histogram}
        self._cache_state = None  # Track state for cache invalidation

        self._setup_ui()
        self._refresh_detector_checkboxes()
        self._populate_example_project()

    def _setup_ui(self) -> None:
        main_vbox = QtWidgets.QVBoxLayout(self)
        main_vbox.setContentsMargins(2, 2, 2, 2)
        main_vbox.setSpacing(2)

        self.toolbar = QtWidgets.QToolBar("Filter calculator")
        self.toolbar.setObjectName("fcsFilterCalculatorToolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        main_vbox.addWidget(self.toolbar)
        self._build_toolbar()

        self.dock_area = DockArea(self)
        self.dock_area.setObjectName("fcsFilterCalculatorDockArea")
        self.dock_area.setNewTabButtonVisible(False)
        self.dock_area.setContextMenuEnabled(True)
        self.dock_area.setContextMenuMode("basic")
        main_vbox.addWidget(self.dock_area, 1)

        # Detector setup is a consumer of the authoritative Detector Def tool.
        self.setup_tab = QtWidgets.QWidget()
        setup_layout = QtWidgets.QVBoxLayout(self.setup_tab)
        self.detector_wizard_page = None
        self._build_detector_setup_selector(setup_layout)

        sidebar = QtWidgets.QWidget()
        sidebar_layout = QtWidgets.QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(2, 2, 2, 2)
        sidebar_layout.setSpacing(2)
        sidebar.setMinimumWidth(280)

        # Data loading group
        data_group = QtWidgets.QGroupBox("Inputs")
        data_layout = QtWidgets.QVBoxLayout(data_group)
        data_layout.setContentsMargins(3, 3, 3, 3)
        data_layout.setSpacing(2)
        
        from chisurf.gui.autoform import AutoForm
        from chisurf.gui.autoform.sections.builtin import ToggleWidget

        self.options_model = CalculatorOptionsViewModel(
            on_polarized=lambda _value: self._on_anisotropy_mode_changed(),
            on_background=lambda _value: self._on_data_changed(),
        )
        self.options_form = AutoForm(self.options_model, self)
        self.options_model.set_refresh_callback(self.options_form.sync_fields)
        data_layout.addWidget(self.options_form)
        option_toggles = self.options_form.findChildren(ToggleWidget)
        self.anisotropy_mode_cb = option_toggles[0].checkbox
        self.fit_background_cb = option_toggles[1].checkbox
        
        # Detector selection + per-detector IRF editor (unified table).
        from .widgets import DetectorIrfTableWidget
        self.detector_selection = DetectorIrfTableWidget()
        self.detector_selection.selectionChanged.connect(self._on_detector_selection_changed)
        data_layout.addWidget(self.detector_selection)

        # Multi-detector filter mode. Unchecked → independent per-detector filters.
        # Checked → one global filter set over the detectors stacked onto a single
        # axis, so a species' relative brightness across detectors (fixed by the
        # FRET model / crosstalk) constrains the unmix.
        self.stacked_mode_cb = QtWidgets.QCheckBox("Global (stacked) multi-detector filters")
        self.stacked_mode_cb.setToolTip(
            "Compute ONE filter set over all selected detectors concatenated onto a\n"
            "single axis, so the FRET-constrained inter-detector amplitude ratios\n"
            "enter the unmix. Unchecked computes independent per-detector filters."
        )
        self.stacked_mode_cb.toggled.connect(lambda _=False: self._on_data_changed())
        data_layout.addWidget(self.stacked_mode_cb)

        # Total Decay Group
        total_group = QtWidgets.QGroupBox("Mixed decay")
        total_vbox = QtWidgets.QVBoxLayout(total_group)
        total_vbox.setContentsMargins(3, 3, 3, 3)
        total_vbox.setSpacing(2)
        total_row = QtWidgets.QHBoxLayout()
        total_row.setContentsMargins(0, 0, 0, 0)
        total_row.setSpacing(4)
        self.le_total = QtWidgets.QLineEdit()
        self.le_total.setReadOnly(True)
        self.le_total.setPlaceholderText("Drop the measured mixed decay here…")
        self.le_total.setToolTip("The measured mixed (total) decay histogram to unmix.")
        total_row.addWidget(self.le_total, 1)
        self.btn_load_total = QtWidgets.QToolButton()
        self.btn_load_total.setText(f"{Glyphs.OPEN} Load…")
        self.btn_load_total.setToolTip("Open a measured mixed decay histogram to replace the built-in example.")
        self.btn_load_total.clicked.connect(self._add_total_dialog)
        total_row.addWidget(self.btn_load_total)
        self.btn_total_from_correlator = QtWidgets.QToolButton()
        self.btn_total_from_correlator.setText(f"{Glyphs.ANTENNA} From correlator")
        self.btn_total_from_correlator.setToolTip(
            "Use the TTTR files already loaded in the Correlator (Files & Steps) as "
            "the mixed decay."
        )
        self.btn_total_from_correlator.clicked.connect(self._use_correlator_total)
        total_row.addWidget(self.btn_total_from_correlator)
        total_vbox.addLayout(total_row)
        # Fit / filter range (TAC bins) — kept in sync with the draggable region
        # on the reconstruction plot.
        range_row = QtWidgets.QHBoxLayout()
        range_row.setContentsMargins(0, 0, 0, 0)
        range_row.setSpacing(4)
        range_row.addWidget(QtWidgets.QLabel("Fit range:"))
        self.sb_fit_start = QtWidgets.QSpinBox()
        self.sb_fit_start.setRange(0, 1_000_000)
        self.sb_fit_start.setToolTip("First TAC bin of the fit / filter window.")
        self.sb_fit_stop = QtWidgets.QSpinBox()
        self.sb_fit_stop.setRange(0, 1_000_000)
        self.sb_fit_stop.setToolTip("Last TAC bin of the fit / filter window.")
        range_row.addWidget(self.sb_fit_start)
        range_row.addWidget(QtWidgets.QLabel("–"))
        range_row.addWidget(self.sb_fit_stop, 1)
        total_vbox.addLayout(range_row)
        self.sb_fit_start.valueChanged.connect(self._on_range_spin_changed)
        self.sb_fit_stop.valueChanged.connect(self._on_range_spin_changed)
        data_layout.addWidget(total_group)
        sidebar_layout.addWidget(data_group)

        # Species Patterns Group
        species_group = QtWidgets.QGroupBox("Components")
        species_vbox = QtWidgets.QVBoxLayout(species_group)
        species_vbox.setContentsMargins(3, 3, 3, 3)
        species_vbox.setSpacing(2)
        self.lw_species = SpeciesListWidget()
        self.lw_species.filesChanged.connect(self._on_files_changed)  # Files added/removed
        self.lw_species.checkStateChanged.connect(self._on_data_changed)  # Checkboxes toggled
        self.lw_species.customContextMenuRequested.connect(self._species_context_menu)
        self.lw_species.itemDoubleClicked.connect(self._edit_component_item)
        species_vbox.addWidget(self.lw_species)
        sidebar_layout.addWidget(species_group)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        sidebar_layout.addWidget(self.status_label)

        self.plot_filters = pg.PlotWidget(title="Lifetime Filters")
        self.plot_filters.setLabel("bottom", "TAC bin")
        self.plot_filters.setLabel("left", "Filter value")
        self.plot_filters.addLegend()
        self.plot_recon = pg.PlotWidget(title="Reconstruction Quality")
        self.plot_recon.setLabel("bottom", "TAC bin")
        self.plot_recon.setLabel("left", "Counts")
        self.plot_recon.setLogMode(y=True)
        self.plot_recon.addLegend()
        # Draggable fit/filter range (TAC bins of the first detector). Auto-fit and
        # the reconstruction use only this window — set past the prompt to a tail fit.
        self._fit_region = pg.LinearRegionItem(
            brush=(90, 150, 255, 55),
            hoverBrush=(120, 175, 255, 80),
            pen=pg.mkPen((150, 190, 255), width=2),
            hoverPen=pg.mkPen((190, 215, 255), width=3),
            movable=True,
        )
        self._fit_region.setZValue(10)  # above the decays so its handles are grabbable
        self._fit_region_initialized = False
        self._syncing_range = False
        self._fit_region.sigRegionChanged.connect(self._on_region_changed)
        # Re-apply the range on release: recompute (re-zero filters) + re-mask residuals.
        self._fit_region.sigRegionChangeFinished.connect(self._on_fit_range_committed)
        self.plot_recon.addItem(self._fit_region)
        self.plot_residuals = pg.PlotWidget(title="Weighted Residuals")
        self.plot_residuals.setLabel("bottom", "TAC bin")
        self.plot_residuals.setLabel("left", "Residuals (σ)")
        self._build_docks(sidebar)

        # Set up drag and drop for the whole widget
        self.setAcceptDrops(True)

    def _build_toolbar(self) -> None:
        self.action_load_total = self.toolbar.addAction(f"{Glyphs.OPEN} Mixed…")
        self.action_load_total.setToolTip(
            "Open a measured mixed decay histogram to replace the built-in example."
        )
        self.action_load_total.triggered.connect(self._add_total_dialog)

        # Add / Edit / Remove all live on the Components list context menu
        # (right-click) and double-click-to-edit — not toolbar buttons.

        self.toolbar.addSeparator()
        autofit_action = self.toolbar.addAction(f"{Glyphs.TARGET} Auto-fit")
        autofit_action.setToolTip(
            "Auto-fit the measured mixed decay to N lifetime components and add them "
            "as species — a quick starting set of filter components."
        )
        autofit_action.triggered.connect(self._auto_fit_components)
        self.btn_autofit = self.toolbar.widgetForAction(autofit_action)

        unmix_action = self.toolbar.addAction("🧩 Unmix")
        unmix_action.setToolTip(
            "Fit non-negative component intensities and compute component filters."
        )
        unmix_action.triggered.connect(self._unmix_total)
        self.btn_unmix = self.toolbar.widgetForAction(unmix_action)

        project_action = self.toolbar.addAction(f"{Glyphs.SAVE} Project")
        project_action.setToolTip("Save or load a Filter Calculator project, or export its results.")
        project_button = self.toolbar.widgetForAction(project_action)
        project_menu = QtWidgets.QMenu(project_button)
        project_menu.setToolTipsVisible(True)
        save_action = project_menu.addAction("Save project…")
        load_action = project_menu.addAction("Load project…")
        self.action_export = project_menu.addAction("Export results…")
        save_action.setToolTip("Save inputs, component definitions, filters, and the current GUI state.")
        load_action.setToolTip("Restore a saved Filter Calculator project and recompute its active inputs.")
        self.action_export.setToolTip("Export computed filters, reconstruction, residuals, and metadata.")
        save_action.triggered.connect(self._on_save_project)
        load_action.triggered.connect(self._on_load_project)
        self.action_export.triggered.connect(self._on_export)
        self.action_export.setEnabled(False)
        project_button.setMenu(project_menu)
        project_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.btn_save_project = project_button
        self.btn_load_project = project_button
        self.btn_export = self.action_export

    def _add_total_dialog(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select mixed total decay", "",
            "Decay files (*.txt *.dat *.csv *.spc *.ptu *.ht3 *.tttr);;All files (*)",
        )
        if paths:
            self._set_total_paths([pathlib.Path(path) for path in paths])

    def _register_split_dock(self, widget, name: str, target, zone: str):
        """Add one panel as a real ChiSurf dock split."""
        tab = self.dock_area._create_tab_widget()
        tab.addTab(widget, name)
        self.dock_area._all_widgets.append(widget)
        self.dock_area._tab_names[widget] = name
        self.dock_area.setTabCloseMode(widget, "hide")
        self.dock_area.split_tab_widget(target, tab, zone)
        return tab

    def _build_autofit_panel(self) -> QtWidgets.QWidget:
        """A persistent Auto-fit settings dock (type, N, lifetime bounds, Fit)."""
        s = self._auto_fit_settings
        panel = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(panel)
        form.setContentsMargins(6, 6, 6, 6)
        form.setSpacing(4)

        self.cb_autofit_kind = QtWidgets.QComboBox()
        self.cb_autofit_kind.addItem("Lifetime species", "lifetime")
        self.cb_autofit_kind.addItem("FRET species", "fret")
        self.cb_autofit_kind.setCurrentIndex(1 if s["kind"] == "fret" else 0)
        self.cb_autofit_kind.setToolTip(
            "Fit N lifetime species, or N FRET states (E from the relative donor quenching)."
        )
        form.addRow("Type:", self.cb_autofit_kind)

        self.sb_autofit_n = QtWidgets.QSpinBox()
        self.sb_autofit_n.setRange(1, 12)
        self.sb_autofit_n.setValue(int(s["n_components"]))
        self.sb_autofit_n.setToolTip("Number of lifetime components / FRET states to resolve.")
        form.addRow("Components / states:", self.sb_autofit_n)

        self.sb_autofit_tmin = QtWidgets.QDoubleSpinBox()
        self.sb_autofit_tmin.setRange(0.01, 1000.0)
        self.sb_autofit_tmin.setDecimals(3)
        self.sb_autofit_tmin.setValue(float(s["tau_min"]))
        self.sb_autofit_tmax = QtWidgets.QDoubleSpinBox()
        self.sb_autofit_tmax.setRange(0.02, 1000.0)
        self.sb_autofit_tmax.setDecimals(3)
        self.sb_autofit_tmax.setValue(float(s["tau_max"]))
        form.addRow("Lifetime min (ns):", self.sb_autofit_tmin)
        form.addRow("Lifetime max (ns):", self.sb_autofit_tmax)

        self.lbl_autofit_range = QtWidgets.QLabel("Fit range: —")
        self.lbl_autofit_range.setStyleSheet("color: palette(mid);")
        form.addRow(self.lbl_autofit_range)

        for w in (self.cb_autofit_kind, self.sb_autofit_n,
                  self.sb_autofit_tmin, self.sb_autofit_tmax):
            sig = w.currentIndexChanged if isinstance(w, QtWidgets.QComboBox) else w.valueChanged
            sig.connect(self._sync_autofit_settings)

        self.btn_autofit_run = QtWidgets.QPushButton(f"{Glyphs.TARGET} Fit + generate filters")
        self.btn_autofit_run.setToolTip("Run the auto-fit over the selected range and add the species.")
        self.btn_autofit_run.clicked.connect(lambda: self._auto_fit_components())
        form.addRow(self.btn_autofit_run)
        self.lbl_autofit_status = QtWidgets.QLabel()
        self.lbl_autofit_status.setWordWrap(True)
        form.addRow(self.lbl_autofit_status)

        # The fitted model's parameters, shown once a fit has run. These are real
        # `FittingParameter`s from a real `LifetimeModel`, so the table's own
        # context menu offers the standard Link… targets — that is the point of
        # fitting through the model stack rather than a standalone optimiser.
        self.autofit_parameters_host = QtWidgets.QWidget()
        host_layout = QtWidgets.QVBoxLayout(self.autofit_parameters_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)
        self.autofit_parameters_host.setVisible(False)
        form.addRow(self.autofit_parameters_host)
        self.autofit_parameter_table = None
        return panel

    def _refresh_autofit_parameters(self, fit) -> None:
        """Show the fitted model's parameters in the Auto-fit dock.

        Rebuilt rather than updated in place: each auto-fit constructs a new
        ``Fit``, so the previous table's parameters belong to a model that is no
        longer the one on screen.
        """
        host = getattr(self, "autofit_parameters_host", None)
        if host is None:
            return
        layout = host.layout()
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.autofit_parameter_table = None

        model = getattr(fit, "model", None)
        params = []
        if model is not None:
            try:
                params = [p for p in model.parameters_all
                          if getattr(p, "name", "") not in _AUTOFIT_HIDDEN_PARAMETERS]
            except Exception as error:
                cs.logging.warning(f"Auto-fit parameter table unavailable: {error}")
                params = []
        if not params:
            host.setVisible(False)
            return

        from chisurf.gui.autoform.sections.parameter_table import (
            ParameterGroupTableWidget,
        )

        self.autofit_parameter_table = ParameterGroupTableWidget(params=params)
        layout.addWidget(self.autofit_parameter_table)
        host.setVisible(True)

    def _sync_autofit_settings(self) -> None:
        """Mirror the Auto-fit dock's controls into the settings dict."""
        self._auto_fit_settings = {
            "kind": self.cb_autofit_kind.currentData(),
            "n_components": int(self.sb_autofit_n.value()),
            "tau_min": float(self.sb_autofit_tmin.value()),
            "tau_max": float(max(self.sb_autofit_tmax.value(), self.sb_autofit_tmin.value() + 0.01)),
        }

    def _build_instrument_panel(self) -> QtWidgets.QWidget:
        """AutoForm dock for instrument/calibration parameters, seeded from the setup."""
        from chisurf.gui.autoform import AutoForm

        from .instrument_options import InstrumentViewModel

        self.instrument_model = InstrumentViewModel(on_change=self._on_instrument_changed)
        self.instrument_form = AutoForm(self.instrument_model, self)
        self.instrument_model.set_refresh_callback(self.instrument_form.sync_fields)
        self._prepopulate_instrument_from_setup()
        return self.instrument_form

    def _on_instrument_changed(self) -> None:
        """An instrument parameter changed → recompute (period/crosstalk affect patterns)."""
        self._on_data_changed()

    def _prepopulate_instrument_from_setup(self) -> None:
        """Fill the instrument parameters from the selected setup's calibration."""
        if not hasattr(self, "instrument_model"):
            return
        settings = self._detector_settings or {}
        cal = dict(settings.get("calibration") or settings.get("crosstalk") or {})
        # Default the laser period to the full micro-time window when the setup
        # does not specify one.
        if not cal.get("period_ns"):
            n_bins = self._current_n_bins() if self._has_total_decay() else 0
            if n_bins:
                cal.setdefault("period_ns", n_bins * self._pattern_bin_width_ns())
        self.instrument_model.update_from(cal)

    def _instrument(self) -> dict:
        """Current instrument parameters as a plain dict (defaults if not built)."""
        if hasattr(self, "instrument_model"):
            return self.instrument_model.to_dict()
        from .instrument_options import DEFAULTS
        return dict(DEFAULTS)

    def _fit_period_ns(self, n_bins: int, dt: float) -> float | None:
        """Laser period (ns) for periodic convolution, or None when disabled.

        Uses the Instrument dock's period; 0 ⇒ the full micro-time window.
        """
        instr = self._instrument()
        if not instr.get("periodic"):
            return None
        period = float(instr.get("period_ns", 0.0) or 0.0)
        return period if period > 0.0 else float(n_bins) * float(dt)

    def _build_info_panel(self) -> QtWidgets.QWidget:
        """A read-only info panel that gathers all the relevant state + results,
        plus an editable per-detector fit-range table."""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        layout.addWidget(QtWidgets.QLabel("<b>Per-detector fit range</b> (TAC bins)"))
        self.info_range_table = QtWidgets.QTableWidget(0, 3)
        self.info_range_table.setHorizontalHeaderLabels(["Detector", "Start", "Stop"])
        self.info_range_table.verticalHeader().setVisible(False)
        self.info_range_table.verticalHeader().setDefaultSectionSize(22)
        self.info_range_table.horizontalHeader().setStretchLastSection(True)
        self.info_range_table.setToolTip(
            "Fit/filter range per detector. Blank ⇒ use the global region. Filters "
            "outside a detector's range are zeroed."
        )
        # Hug the content (header + rows) instead of stretching vertically, so the
        # Information text below gets the remaining space.
        self.info_range_table.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.info_range_table.itemChanged.connect(self._on_info_range_edited)
        layout.addWidget(self.info_range_table)

        layout.addWidget(QtWidgets.QLabel("<b>Information</b>"))
        self.info_text = QtWidgets.QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        from chisurf.gui.widgets.general import table_font
        self.info_text.setFont(table_font())
        layout.addWidget(self.info_text, 1)
        return panel

    def _on_info_range_edited(self, item) -> None:
        """Apply an edited per-detector fit range and recompute."""
        if getattr(self, "_syncing_info", False):
            return
        row = item.row()
        det_item = self.info_range_table.item(row, 0)
        if det_item is None:
            return
        det = det_item.text()
        n_bins = self._current_n_bins()

        def _cell_int(col, default):
            it = self.info_range_table.item(row, col)
            try:
                return int(float(it.text()))
            except (TypeError, ValueError):
                return default

        g_start, g_stop = self._fit_range(n_bins)
        start = max(0, min(_cell_int(1, g_start), n_bins - 1))
        stop = max(start + 1, min(_cell_int(2, g_stop), n_bins))
        self._detector_fit_ranges[det] = (start, stop)
        # Re-zero to the new per-detector range and replot (no refit needed).
        self._on_fit_range_committed()

    def _refresh_info(self) -> None:
        """Rebuild the info panel's per-detector range table and text summary."""
        if not hasattr(self, "info_text"):
            return
        self._syncing_info = True
        try:
            n_bins = self._current_n_bins() if self._has_total_decay() else 0
            dets = self.detector_selection.get_selected() or ["default"]
            # Per-detector range table.
            self.info_range_table.setRowCount(len(dets))
            for r, det in enumerate(dets):
                start, stop = self._detector_fit_range(det, n_bins or 1)
                cells = [det, str(int(start)), str(int(stop))]
                for c, text in enumerate(cells):
                    it = QtWidgets.QTableWidgetItem(text)
                    if c == 0:
                        it.setFlags(QtCore.Qt.ItemIsEnabled)
                    self.info_range_table.setItem(r, c, it)
            self._size_range_table()
            self.info_text.setPlainText(self._gather_info_text())
        finally:
            self._syncing_info = False

    def _size_range_table(self) -> None:
        """Fix the range table's height to its content (header + rows), capped."""
        t = self.info_range_table
        height = t.horizontalHeader().height() + 2 * t.frameWidth()
        for r in range(t.rowCount()):
            height += t.rowHeight(r)
        t.setFixedHeight(int(min(max(height, 48), 220)))

    def _gather_info_text(self) -> str:
        """Assemble a plain-text summary of inputs, settings and last results."""
        lines: list[str] = []
        n_bins = self._current_n_bins() if self._has_total_decay() else 0
        dt = self._pattern_bin_width_ns()
        # Inputs
        lines.append("== Mixed decay ==")
        if self._total_paths:
            src = "correlator" if self._total_from_correlator else "loaded"
            lines.append(f"  source: {src}, {len(self._total_paths)} file(s)")
            for p in self._total_paths[:8]:
                lines.append(f"    {p.name}")
        elif self._total_vector is not None:
            lines.append("  source: example / in-memory")
        else:
            lines.append("  (none)")
        lines.append(f"  bins: {n_bins}   bin width: {dt:.4g} ns"
                     f"   micro-time binning: ×{self._micro_time_binning}")
        g0, g1 = self._fit_range(n_bins or 1)
        lines.append(f"  global fit range: {g0}–{g1} bins")
        # Detectors
        lines.append("")
        lines.append("== Detectors (IRF) ==")
        for det in (self.detector_selection.get_selected() or ["default"]):
            has_irf = bool(self.detector_selection.irf_path(det, ""))
            lines.append(
                f"  {det}: width {self.detector_selection.width(det, ''):.3f} ns, "
                f"skew {self.detector_selection.skew(det, ''):+.2f}, "
                f"shift {self.detector_selection.shift(det, ''):+.3f} ns, "
                f"IRF {'measured' if has_irf else 'synthetic'}"
            )
        # Components
        lines.append("")
        lines.append(f"== Components ({self.lw_species.count()}) ==")
        for i in range(self.lw_species.count()):
            lines.append(f"  {self.lw_species.item(i).text()}")
        # Last auto-fit
        if getattr(self, "lbl_autofit_status", None) and self.lbl_autofit_status.text():
            lines.append("")
            lines.append("== Last auto-fit ==")
            lines.append(f"  {self.lbl_autofit_status.text()}")
        # Filters
        results = self._result_multi_detector or ([self._result] if self._result else [])
        if results:
            lines.append("")
            lines.append("== Filters ==")
            for entry in results:
                res = entry["result"] if isinstance(entry, dict) else entry
                det = entry["detector"] if isinstance(entry, dict) else "single"
                mode = (res.metadata or {}).get("filter_mode", "independent")
                lines.append(
                    f"  {det}: {res.n_species} species + {res.nuisance_count} nuisance "
                    f"({res.n_filters} filters × {res.n_bins} bins) [{mode}]"
                )
        return "\n".join(lines)

    def _build_docks(self, sources_panel) -> None:
        self.dock_area.addTab(sources_panel, "Decay sources")
        sources_dock = self.dock_area.find_main_tab_widget()
        detector_dock = self._register_split_dock(
            self.setup_tab, "Setup", sources_dock, "bottom"
        )
        self._register_split_dock(
            self._build_autofit_panel(), "Auto-fit", sources_dock, "bottom"
        )
        self._register_split_dock(
            self._build_instrument_panel(), "Instrument", sources_dock, "bottom"
        )
        self._register_split_dock(
            self._build_info_panel(), "Info", sources_dock, "bottom"
        )
        filters_dock = self._register_split_dock(
            self.plot_filters, "Lifetime filters", sources_dock, "right"
        )
        residuals_dock = self._register_split_dock(
            self.plot_residuals, "Weighted residuals", filters_dock, "bottom"
        )
        self._register_split_dock(
            self.plot_recon, "Reconstruction / decay", residuals_dock, "bottom"
        )
        try:
            self.dock_area.enable_persistence("fcs_filter_calculator_wres_above_decay")
        except Exception:
            pass

    @classmethod
    def _stable_plot_color(cls, key: str) -> str:
        """Return a semantic or digest-stable color independent of list order."""
        normalized = str(key).strip().lower()
        for name, color in cls._NAMED_COLORS.items():
            if name in normalized:
                return color
        digest = hashlib.blake2b(normalized.encode("utf-8"), digest_size=2).digest()
        return cls._PLOT_COLORS[int.from_bytes(digest, "big") % len(cls._PLOT_COLORS)]

    def _active_component_names(self) -> list[str]:
        names = []
        for index in range(self.lw_species.count()):
            item = self.lw_species.item(index)
            if item.checkState() == QtCore.Qt.Checked:
                names.append(item.text().split("  [", 1)[0])
        return names

    def _component_color(self, index: int) -> str:
        names = self._active_component_names()
        key = names[index] if index < len(names) else f"component-{index + 1}"
        return self._stable_plot_color(key)

    def _filter_label(self, result, index: int) -> str:
        signal_count = int(result.metadata.get("n_species", result.n_filters))
        if index < signal_count:
            names = self._active_component_names()
            return names[index] if index < len(names) else f"Species {index + 1}"
        nuisance = list(getattr(result, "nuisance_labels", None) or [])
        nuisance_index = index - signal_count
        return nuisance[nuisance_index] if nuisance_index < len(nuisance) else "Nuisance"

    def _filter_color(self, result, index: int) -> str:
        label = self._filter_label(result, index)
        if "afterpulse" in label.lower():
            return "#a3a3a3"
        if "scatter" in label.lower() or "irf" in label.lower():
            return "#22d3ee"
        return self._stable_plot_color(label)

    def _filter_is_rejected(self, result, index: int) -> bool:
        """True when filter row ``index`` is a nuisance row excluded from output.

        Nuisance rejection keeps the row's filter (it still absorbs nuisance
        photons) but drops it from the correlation-facing set; those rows are the
        ones past ``n_species``. When rejection is off, ``n_species == n_filters``
        and nothing is rejected.
        """
        n_species = int(getattr(result, "n_species", result.n_filters))
        return index >= n_species

    def _filter_pen_name(self, result, index: int, prefix: str = "") -> tuple:
        """Return the (pen, legend-name) for a filter curve.

        Rejected nuisance rows are drawn dotted and tagged ``(rejected)`` so the
        Nuisance toggle visibly changes the Lifetime-filters plot.
        """
        color = self._filter_color(result, index)
        name = f"{prefix}{self._filter_label(result, index)}"
        if self._filter_is_rejected(result, index):
            return pg.mkPen(color, style=QtCore.Qt.DotLine), f"{name} (rejected)"
        return pg.mkPen(color), name

    def _plot_irf_overlay(self, plot, x, det_name, ref_peak) -> None:
        """Overlay a detector's IRF/scatter pattern on ``plot``, scaled to the decay peak.

        The stored IRF is shape-normalised; it is rescaled so its maximum matches
        the total-decay peak, so its position and width are visible on the same
        (log) counts axis as the decay it convolves.
        """
        irf = self._irf_by_detector.get(str(det_name))
        if irf is None:
            return
        irf = np.asarray(irf, dtype=float)
        top = float(np.nanmax(irf)) if irf.size else 0.0
        if top <= 0.0:
            return
        scale = float(ref_peak) / top if ref_peak else 1.0
        disp = irf * scale
        # The scatter/IRF pattern is a sharp spike that is ~zero in its tail;
        # on a log-counts axis those zeros would blow the y-range down to 1e-200.
        # Mask everything below a small fraction of the decay peak so only the
        # visible instrument-response spike is drawn.
        floor = max(float(ref_peak) * 1e-4, 1e-9) if ref_peak else 1e-9
        disp = np.where(disp >= floor, disp, np.nan)
        plot.plot(
            x, disp,
            pen=pg.mkPen("#22d3ee", style=QtCore.Qt.DotLine),
            name=f"{det_name}: IRF" if det_name else "IRF",
        )

    @staticmethod
    def _decay_peak(decay) -> float:
        arr = np.asarray(decay, dtype=float)
        return float(np.nanmax(arr)) if arr.size else 0.0

    def _pattern_bin_width_ns(self) -> float:
        # Prefer the micro-time bin width captured from the loaded data / setup.
        if getattr(self, "_data_dt_ns", 0.0) > 0.0:
            return float(self._data_dt_ns)
        for index in range(self.lw_species.count()):
            source = self.lw_species.item(index).data(QtCore.Qt.UserRole)
            if isinstance(source, dict) and source.get("bin_width"):
                return float(source["bin_width"])
        return 0.05

    def _micro_time_axis(self, header, microtimes: np.ndarray, n_tac: int):
        """Apply the optional micro-time binning and capture the TAC bin width.

        Reads the micro-time resolution from the TTTR ``header`` (seconds → ns),
        multiplies it by the coarsening factor, and stores it in ``_data_dt_ns``
        so the lifetime filters use the same micro-time axis as the data / the
        correlator. Returns ``(microtimes, n_tac)`` after coarsening.
        """
        try:
            resolution_s = float(getattr(header, "micro_time_resolution", 0.0) or 0.0)
        except Exception:
            resolution_s = 0.0
        b = max(1, int(getattr(self, "_micro_time_binning", 1)))
        if b > 1:
            microtimes = microtimes // b
            n_tac = (int(n_tac) + b - 1) // b
        if resolution_s > 0.0:
            self._data_dt_ns = resolution_s * 1.0e9 * b
        return microtimes, int(n_tac)

    def _nuisance_patterns(
        self,
        total_decay: np.ndarray,
        component_decays: List[np.ndarray] | None = None,
        detector_name: str | None = None,
        role: str = "",
    ) -> tuple[list[np.ndarray], list[str]]:
        total = np.asarray(total_decay, dtype=float).ravel()
        n_bins = total.size
        patterns: list[np.ndarray] = []
        labels: list[str] = []
        if self.fit_background_cb.isChecked():
            patterns.append(afterpulse_decay_pattern(n_bins))
            labels.append("Afterpulse / constant")
        if self.options_model.scatter_irf:
            detector = detector_name or (self.detector_selection.get_selected()[:1] or ["default"])[0]
            configured_path = self.detector_selection.irf_path(detector, role)
            if configured_path:
                irf_path = pathlib.Path(configured_path)
                if not irf_path.is_file():
                    raise ValueError(f"Scatter IRF for {detector} does not exist: {irf_path}")
                shift = float(self.detector_selection.shift(detector, role) or 0.0)
                measured = self._shift_irf(
                    load_vector(irf_path), shift, self._pattern_bin_width_ns()
                )
                scatter = scattered_light_decay_pattern(measured, n_bins)
                source = "measured"
            else:
                # Use the detector's synthetic IRF (the width/skew/shift set in the
                # Detectors table — written back by the auto-fit) as the scatter
                # shape, so the scatter prompt in the FILTER reconstruction is
                # CONSISTENT with the auto-fit's IRF and the component convolution.
                # Otherwise an independent coarse re-fit would misalign the prompt
                # and leave the tell-tale antisymmetric residual at the rising edge.
                det_irf = self._detector_irf(detector, role, n_bins=n_bins)
                if det_irf is not None and np.any(np.asarray(det_irf) > 0.0):
                    scatter = scattered_light_decay_pattern(det_irf, n_bins)
                    source = "detector-IRF"
                else:
                    # Fallback (no usable synthetic IRF, e.g. width 0): the coarse
                    # amplitude/position fit against the species basis.
                    basis = [
                        np.asarray(d, dtype=float).ravel()
                        for d in (component_decays or [])
                    ]
                    basis = [
                        d for d in basis
                        if d.size == total.size
                        and np.all(np.isfinite(d))
                        and np.all(d >= 0.0)
                        and d.sum() > 0.0
                    ]
                    scatter, fit = optimize_synthetic_scatter_pattern(
                        total,
                        basis,
                        bin_width_ns=self._pattern_bin_width_ns(),
                        initial_fwhm_ns=self.detector_selection.width(detector, role),
                        shape=self.detector_selection.skew(detector, role),
                        include_constant=self.fit_background_cb.isChecked(),
                    )
                    key = f"{detector}:{role}" if role else detector
                    self._synthetic_scatter_fits[key] = fit
                    source = "fitted"
            patterns.append(scatter)
            labels.append(f"Scatter / IRF ({detector}, {source})")
            # Remember the IRF/scatter shape so the decay plot can overlay it.
            self._irf_by_detector[str(detector)] = np.asarray(scatter, dtype=float)
        return patterns, labels

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        
        paths = [pathlib.Path(url.toLocalFile()) for url in urls]
        
        # If dropping on total decay group area
        if self.le_total.geometry().translated(self.le_total.parentWidget().mapTo(self, QtCore.QPoint(0,0))).contains(event.pos()):
            self._set_total_paths(paths)
        else:
            # Default to adding as species
            self.lw_species.add_pattern(paths)

    def _set_total_paths(self, paths: List[pathlib.Path], from_correlator: bool = False) -> None:
        self._total_paths = paths
        # Remember whether the mixed decay came from the Correlator (so a later
        # visit can re-sync it) or was manually loaded (leave it alone).
        self._total_from_correlator = bool(from_correlator)
        self._total_vector = None
        self._total_vectors_by_detector = {}
        # Recapture the micro-time bin width from the new data (TTTR headers set
        # it; text totals leave it 0 so the species/default bin width is used).
        self._data_dt_ns = 0.0
        # Re-default the fit/filter range for the new data's micro-time axis.
        self._fit_region_initialized = False
        if not paths:
            self.le_total.setText("")
            self.le_total.setToolTip("")
        else:
            name = paths[0].name
            if len(paths) > 1:
                name += f" (+{len(paths)-1} files)"
            self.le_total.setText(name)
            self.le_total.setToolTip("\n".join([str(p.absolute()) for p in paths]))
            # Real data replaces the built-in example → drop the eye-candy species.
            self._clear_example_components()
        # Invalidate cache when total paths change
        self._invalidate_cache()
        self._on_data_changed()

    def _correlator_context(self):
        """The FCS toolbox's shared workflow context, if this panel is hosted in it."""
        widget = self.parent()
        while widget is not None:
            ctx = getattr(widget, "workflow_context", None)
            if ctx is not None:
                return ctx
            widget = widget.parent()
        return None

    def _correlator_file_paths(self) -> List[pathlib.Path]:
        """TTTR files loaded in the sibling Correlator (Files & Steps), if any."""
        ctx = self._correlator_context()
        if ctx is None:
            return []
        # Prefer the fully-expanded list; fall back to the checked paths.
        paths = list(getattr(ctx, "expanded_files", []) or []) or \
            list(getattr(ctx, "file_paths", []) or [])
        return [pathlib.Path(p) for p in paths]

    def _use_correlator_total(self) -> None:
        """Set the mixed decay from the Correlator's already-loaded TTTR files."""
        ctx = self._correlator_context()
        if ctx is not None:
            # Adopt the correlator's micro-time binning so the lifetime filters
            # share its micro-time axis (the resolution comes from the data).
            self._micro_time_binning = max(1, int(getattr(ctx, "microtime_binning", 1) or 1))
        paths = [p for p in self._correlator_file_paths() if pathlib.Path(p).is_file()]
        if not paths:
            QtWidgets.QMessageBox.information(
                self, "No correlator data",
                "No files are loaded in the Correlator (Files & Steps) step yet.",
            )
            return
        self._set_total_paths(paths, from_correlator=True)
        self._update_status(f"Mixed decay from correlator ({len(paths)} file(s)).")

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        # Every time this panel is shown (e.g. navigating here from the Correlator),
        # re-sync the mixed decay with the Correlator's CURRENT files and refresh
        # the plots — but only when the total is correlator-sourced (or unset), so a
        # manually-loaded measured decay is never overwritten.
        corr = [pathlib.Path(p) for p in self._correlator_file_paths()
                if pathlib.Path(p).is_file()]
        first_show = not getattr(self, "_correlator_autoload_done", False)
        self._correlator_autoload_done = True
        adopt = getattr(self, "_total_from_correlator", False) or not self._total_paths
        if corr and adopt:
            current = [str(p) for p in (self._total_paths or [])]
            if [str(p) for p in corr] != current:
                self._use_correlator_total()  # re-loads + recomputes + replots
            elif not first_show:
                self._update_plots()
        elif not first_show:
            # Manually-loaded total: just make sure the plots reflect current state.
            self._update_plots()

    def _has_total_decay(self) -> bool:
        return bool(self._total_paths) or self._total_vector is not None

    def _total_decay(self, chs: List[str] | None = None) -> np.ndarray:
        if self._total_paths:
            return self._load_and_sum_vectors(self._total_paths, chs)
        if self._total_vectors_by_detector and chs:
            selected = [
                self._total_vectors_by_detector[name]
                for name in chs if name in self._total_vectors_by_detector
            ]
            if selected:
                return np.sum(selected, axis=0)
        if self._total_vector is not None:
            return np.asarray(self._total_vector, dtype=float).copy()
        raise ValueError("No mixed total decay is available.")

    def _populate_example_project(self) -> None:
        """Seed detector-convolved components plus scatter and afterpulsing."""
        from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

        n_bins = 256
        bin_width = 0.05
        detector_names = self.detector_selection.get_selected() or ["default"]
        time = np.arange(n_bins, dtype=float) * bin_width
        fast_patterns: dict[str, list[float]] = {}
        slow_patterns: dict[str, list[float]] = {}
        totals: dict[str, np.ndarray] = {}
        for index, detector in enumerate(detector_names):
            irf = synthetic_irf(
                time,
                center_ns=0.35 + 0.06 * index,
                fwhm_ns=0.16 + 0.035 * index,
                shape=0.35 * index,
            )
            fast = synthetic_component_decay(n_bins, {
                "model": "lifetime", "lifetime": 1.2, "bin_width": bin_width,
            }, irf=irf)
            slow = synthetic_component_decay(n_bins, {
                "model": "lifetime", "lifetime": 4.0, "bin_width": bin_width,
            }, irf=irf)
            fast_patterns[detector] = fast.tolist()
            slow_patterns[detector] = slow.tolist()
            expected = (
                0.665 * fast
                + 0.285 * slow
                + 0.03 * scattered_light_decay_pattern(irf, n_bins)
                + 0.02 * afterpulse_decay_pattern(n_bins)
            )
            totals[detector] = sample_decay_shot_noise(
                expected, photon_count=100_000, seed=20260716 + index
            )
        fast_patterns["__default__"] = next(iter(fast_patterns.values()))
        slow_patterns["__default__"] = next(iter(slow_patterns.values()))
        self._total_vectors_by_detector = totals
        self._total_vector = next(iter(totals.values())).copy()
        self.le_total.setText("Convolved example (70/30 + scatter + afterpulse)")
        self.le_total.setCursorPosition(0)
        self.le_total.setToolTip(
            "Built-in example. Use ‘Open mixed decay…’ to replace it with measured data."
        )
        self.lw_species.add_synthetic_source({
            "type": "synthetic", "model": "lifetime", "name": "Fast example",
            "lifetime": 1.2, "bin_width": bin_width, "example": True,
            "patterns_by_detector": fast_patterns,
        })
        self.lw_species.add_synthetic_source({
            "type": "synthetic", "model": "lifetime", "name": "Slow example",
            "lifetime": 4.0, "bin_width": bin_width, "example": True,
            "patterns_by_detector": slow_patterns,
        })
        self._compute_filters()

    def _clear_example_components(self) -> None:
        """Remove the built-in eye-candy example species (kept only until real data).

        The example mixture seeds two placeholder components so the workflow is
        visible on an empty panel; once measured data is loaded they are just
        decoration, so drop them. User-added components are left untouched.
        """
        for i in range(self.lw_species.count() - 1, -1, -1):
            source = self.lw_species.item(i).data(QtCore.Qt.UserRole)
            if isinstance(source, dict) and source.get("example"):
                self.lw_species.takeItem(i)

    def _add_species_dialog(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select species decay histograms", "", 
            "All Decay Files (*.txt *.dat *.csv *.bst *.tttr);;Text Files (*.txt *.dat *.csv);;Burst Files (*.bst);;TTTR Files (*.tttr);;All files (*)"
        )
        if paths:
            self.lw_species.add_pattern([pathlib.Path(p) for p in paths])

    def _choose_fit_spectrum(self, parent):
        """Prompt for an open ChiSurf fit and return ``(spectrum, label, fit)``."""
        fits = list(getattr(cs, "fits", []) or [])
        current = getattr(getattr(cs, "cs", None), "current_fit", None)
        if current is None:
            current = getattr(cs, "current_fit", None)
        if current is not None and all(current is not fit for fit in fits):
            fits.append(current)
        if not fits:
            QtWidgets.QMessageBox.information(parent, "No Fits", "No ChiSurf fits are open.")
            return None
        labels = [str(getattr(fit, "name", None) or fit) for fit in fits]
        default = fits.index(current) if current in fits else 0
        label, accepted = QtWidgets.QInputDialog.getItem(
            parent, "Read Lifetime Spectrum", "Fit:", labels, default, False
        )
        if not accepted:
            return None
        fit = fits[labels.index(label)]
        model = getattr(getattr(fit, "selected_fit", fit), "model", None)
        try:
            spectrum = lifetime_spectrum_from_model(model)
        except Exception as error:
            QtWidgets.QMessageBox.warning(parent, "Unsupported Fit", str(error))
            return None
        return spectrum, label, fit

    def _build_component_editor(self, kind: str, existing=None):
        """Build (editor_model, AutoForm) for a component ``kind`` (lifetime/fret)."""
        from chisurf.gui.autoform import AutoForm

        if kind == "fret":
            from chisurf.gui.widgets.fret_species_editor import FretSpeciesEditorModel

            editor_model = FretSpeciesEditorModel()
            editor_model.set_calibration_seed(self._calibration_seed)
        else:
            from chisurf.gui.widgets.synthetic_decay_editor import SyntheticDecayEditorModel

            editor_model = SyntheticDecayEditorModel(
                read_fit=lambda: self._choose_fit_spectrum(self)
            )
        if isinstance(existing, dict):
            editor_model.load_component(existing)
        editor = AutoForm(editor_model)
        editor_model.set_changed_callback(editor.refresh_plots)
        return editor_model, editor

    def _add_component_dialog(self, edit_item=None) -> None:
        """One dialog to add/edit a decay component — a **Type** selector switches
        between a plain lifetime spectrum and a coupled FRET species."""
        existing = edit_item.data(QtCore.Qt.UserRole) if edit_item is not None else None
        init_kind = "fret" if isinstance(existing, dict) and existing.get("model") == "fret_species" else "lifetime"

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Edit Component" if edit_item is not None else "Add Component")
        dialog.resize(660, 720)
        layout = QtWidgets.QVBoxLayout(dialog)

        type_row = QtWidgets.QHBoxLayout()
        type_row.addWidget(QtWidgets.QLabel("Type:"))
        combo = QtWidgets.QComboBox()
        combo.addItem("Lifetime spectrum", "lifetime")
        combo.addItem("FRET species", "fret")
        combo.setCurrentIndex(1 if init_kind == "fret" else 0)
        combo.setEnabled(edit_item is None)  # type is fixed when editing
        combo.setToolTip("Plain lifetime decay (same in all detectors) or a coupled "
                         "smFRET species (different green/red/yellow decays).")
        type_row.addWidget(combo)
        type_row.addStretch(1)
        layout.addLayout(type_row)

        container = QtWidgets.QWidget()
        c_layout = QtWidgets.QVBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(container, 1)
        state: dict = {}

        def build(kind: str):
            while c_layout.count():
                w = c_layout.takeAt(0).widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
            editor_model, editor = self._build_component_editor(kind, existing)
            c_layout.addWidget(editor)
            state["kind"] = kind
            state["model"] = editor_model

        build(init_kind)
        combo.currentIndexChanged.connect(lambda: build(combo.currentData()))

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        if state["kind"] == "fret":
            self._commit_fret_component(state["model"], edit_item, dialog)
        else:
            self._commit_synthetic_component(state["model"], edit_item, dialog)

    def _commit_synthetic_component(self, editor_model, edit_item, parent) -> None:
        try:
            spectrum = editor_model.lifetime_spectrum
            irf = pathlib.Path(editor_model.irf_path) if editor_model.irf_path.strip() else None
            if irf is not None and not irf.is_file():
                raise ValueError("The selected IRF file does not exist.")
        except ValueError as error:
            QtWidgets.QMessageBox.warning(self, "Invalid Synthetic Decay", str(error))
            return

        source = editor_model.component()
        if editor_model.selected_fit is not None:
            detector_names = self.detector_selection.get_selected()
            try:
                patterns = compute_detector_patterns_from_fit(
                    editor_model.selected_fit, spectrum, detector_names=detector_names
                )
                # A grouped polarization fit often has one member per routing
                # channel. Preserve routing aliases when the detector setup
                # provides the same number of channels.
                routing_names = []
                for detector_name in detector_names:
                    config = (self._detector_settings or {}).get("detectors", {}).get(detector_name, {})
                    routing_names.extend(f"routing_{channel}" for channel in config.get("chs", []))
                ordered = [patterns[key] for key in sorted(
                    (key for key in patterns if key.startswith("detector_")),
                    key=lambda key: int(key.split("_")[-1]),
                )]
                if len(routing_names) == len(ordered):
                    patterns.update(dict(zip(routing_names, ordered)))
                source["patterns_by_detector"] = {}
                noisy_by_pattern: dict[int, np.ndarray] = {}
                for detector_index, (key, pattern) in enumerate(patterns.items()):
                    identity = id(pattern)
                    detector_source = dict(source)
                    detector_source["noise_seed"] = int(source["noise_seed"]) + detector_index
                    if identity not in noisy_by_pattern:
                        noisy_by_pattern[identity] = self._apply_pattern_shot_noise(
                            pattern, detector_source
                        )
                    source["patterns_by_detector"][key] = noisy_by_pattern[identity].tolist()
                source["source_fit"] = editor_model.selected_fit_label
            except Exception as error:
                QtWidgets.QMessageBox.warning(self, "Fit Pattern Error", str(error))
                return
        if edit_item is not None:
            self.lw_species.replace_synthetic_source(edit_item, source)
        else:
            self.lw_species.add_synthetic_source(source)

    def _shift_irf(self, irf, shift_ns: float, dt: float):
        """Shift an IRF vector by ``shift_ns`` (sub-bin, linear interp, zero edges).

        A positive shift moves the IRF to later times. Applied uniformly to both
        measured and synthetic IRFs so a detector's timing offset is corrected the
        same way regardless of how the IRF was obtained.
        """
        if irf is None or not shift_ns or dt <= 0.0:
            return irf
        v = np.asarray(irf, dtype=float).ravel()
        idx = np.arange(v.size, dtype=float) - float(shift_ns) / float(dt)
        return np.interp(idx, np.arange(v.size, dtype=float), v, left=0.0, right=0.0)

    def _current_n_bins(self) -> int:
        """Bin count of the active total decay (data-derived, not a fixed 256).

        For file-/correlator-backed totals ``_total_vector`` is ``None``, so the
        length must come from the loaded decay — otherwise a synthetic IRF built at
        the default 256 bins is far shorter than the real micro-time axis and a
        fitted shift can push its prompt off the end.
        """
        if self._total_vector is not None:
            return int(self._total_vector.size)
        try:
            chs = (self.detector_selection.get_selected() or None
                   if self.detector_selection.checkboxes else None)
            return int(np.asarray(self._total_decay(chs)).size)
        except Exception:
            return 256

    def _detector_irf(self, detector_name: str, role: str = "", n_bins: int | None = None):
        """Return a detector's IRF (measured file or synthetic Gaussian) for FRET decays.

        The per-detector time shift from the Detectors table is applied to the
        returned IRF (measured or synthetic) so the modelled prompt lines up with
        the measurement. ``n_bins`` defaults to the active total's length.
        """
        import numpy as np

        from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

        n = int(n_bins) if n_bins else self._current_n_bins()
        dt = float(self._pattern_bin_width_ns())
        shift = float(self.detector_selection.shift(detector_name, role) or 0.0)
        configured = self.detector_selection.irf_path(detector_name, role)
        if configured and pathlib.Path(configured).is_file():
            return self._shift_irf(load_vector(pathlib.Path(configured)), shift, dt)
        fwhm = float(self.detector_selection.width(detector_name, role) or 0.0)
        if fwhm <= 0.0:
            return None
        time = np.arange(n, dtype=float) * dt
        irf = synthetic_irf(time, 2.0 * fwhm, fwhm,
                            shape=float(self.detector_selection.skew(detector_name, role) or 0.0))
        shifted = self._shift_irf(irf, shift, dt)
        # A large shift/skew can leave the prompt outside the window (all-zero);
        # fall back to the unshifted IRF so downstream convolution stays valid.
        if shifted is None or not np.any(np.asarray(shifted) > 0.0):
            return irf if np.any(irf > 0.0) else None
        return shifted

    def _calibration_seed(self) -> dict:
        """Crosstalk factors seeded from the selected detector setup, if any."""
        settings = self._detector_settings or {}
        cal = settings.get("calibration") or settings.get("crosstalk") or {}
        seed = {}
        for key in ("alpha", "beta", "gamma", "delta", "forster_radius"):
            if key in cal:
                seed[key] = float(cal[key])
        return seed

    def _commit_fret_component(self, editor_model, edit_item, parent) -> None:
        from chisurf.core.fluorescence.fret.species_decay import fret_species_detector_patterns

        source = editor_model.component()
        detector_names = self.detector_selection.get_selected() or ["green", "red", "yellow"]
        n_bins = self._current_n_bins()
        try:
            patterns = fret_species_detector_patterns(
                source, detector_names, n_bins, irf_for_detector=self._detector_irf,
            )
        except Exception as error:
            QtWidgets.QMessageBox.warning(self, "FRET Species Error", str(error))
            return
        source["patterns_by_detector"] = {k: np.asarray(v, dtype=float).tolist()
                                          for k, v in patterns.items()}
        if edit_item is not None:
            self.lw_species.replace_synthetic_source(edit_item, source)
        else:
            self.lw_species.add_synthetic_source(source)

    @staticmethod
    def _resize_pattern(pattern: np.ndarray, n_bins: int) -> np.ndarray:
        pattern = np.asarray(pattern, dtype=float).ravel()
        if pattern.size >= n_bins:
            return pattern[:n_bins]
        resized = np.zeros(n_bins, dtype=float)
        resized[:pattern.size] = pattern
        return resized

    @staticmethod
    def _apply_pattern_shot_noise(pattern: np.ndarray, source: dict) -> np.ndarray:
        pattern = np.asarray(pattern, dtype=float).ravel()
        if not source.get("shot_noise", False):
            return pattern
        sampled = sample_decay_shot_noise(
            pattern,
            photon_count=float(source.get("photon_count", 100_000)),
            seed=int(source.get("noise_seed", 0)),
        )
        total = sampled.sum()
        if total <= 0.0:
            raise ValueError("shot-noise sampling produced an empty decay")
        return sampled / total

    def _species_item_pattern(self, item, n_bins: int, chs: List[str] | None):
        """Resolve a file-backed or synthetic list item to one decay pattern."""
        source = item.data(QtCore.Qt.UserRole)
        if isinstance(source, dict) and source.get("type") == "synthetic":
            detector_patterns = source.get("patterns_by_detector") or {}
            if detector_patterns:
                selected = [
                    np.asarray(detector_patterns[channel], dtype=float)
                    for channel in (chs or []) if channel in detector_patterns
                ]
                if selected:
                    pattern = np.sum([self._resize_pattern(value, n_bins) for value in selected], axis=0)
                else:
                    pattern = np.asarray(
                        detector_patterns.get("__default__", next(iter(detector_patterns.values()))),
                        dtype=float,
                    )
                return self._resize_pattern(pattern, n_bins), dict(source)
            irf = None
            if source.get("irf_path"):
                irf = load_vector(pathlib.Path(source["irf_path"]))
            source = dict(source)
            source["start_bin"] = min(int(source.get("start_bin", 0)), n_bins - 1)
            pattern = synthetic_component_decay(n_bins, source, irf=irf)
            return pattern, dict(source)

        paths = [pathlib.Path(path) for path in source]
        pattern = self._load_and_sum_vectors(paths, chs)
        return self._resize_pattern(pattern, n_bins), [str(path.absolute()) for path in paths]

    def _clear_recon_plot(self) -> None:
        """Clear the reconstruction plot but keep the draggable fit-range region.

        ``PlotWidget.clear()`` removes *all* items, including the
        :class:`~pyqtgraph.LinearRegionItem` selector — so every recompute would
        otherwise wipe the region and it would never reappear. Re-add it after the
        clear so the range selector survives replots.
        """
        self.plot_recon.clear()
        region = getattr(self, "_fit_region", None)
        if region is not None:
            self.plot_recon.addItem(region)

    def _init_fit_region(self, decay) -> None:
        """Set a sensible default fit range (just past the prompt → near the end)."""
        if self._fit_region_initialized:
            return
        d = np.asarray(decay, dtype=float).ravel()
        if d.size < 8:
            return
        peak = int(np.argmax(d))
        start = min(peak + max(2, d.size // 100), d.size - 4)
        stop = d.size - max(1, d.size // 100)
        self._fit_region_initialized = True
        self._set_fit_range(start, stop, source="init")

    def _set_fit_range(self, start: int, stop: int, source: str = "") -> None:
        """Set both the plot region and the spinboxes without signal feedback loops."""
        if self._syncing_range:
            return
        self._syncing_range = True
        try:
            if source != "region":
                self._fit_region.setRegion((float(start), float(stop)))
            if source != "spin":
                self.sb_fit_start.setValue(int(start))
                self.sb_fit_stop.setValue(int(stop))
            if hasattr(self, "lbl_autofit_range"):
                self.lbl_autofit_range.setText(f"Fit range: {int(start)}–{int(stop)} TAC bins")
        finally:
            self._syncing_range = False

    def _on_region_changed(self) -> None:
        lo, hi = self._fit_region.getRegion()
        self._set_fit_range(int(round(min(lo, hi))), int(round(max(lo, hi))), source="region")

    def _on_fit_range_committed(self, *_args) -> None:
        """Region drag / spin edit finished → recompute over the new window.

        The fFCS filters are now computed **over the fit-range slice** (so the
        reconstruction/residuals are not biased by the excluded pre-prompt and
        far-tail bins), which means a range change genuinely re-fits.
        """
        self._on_data_changed()

    def _on_range_spin_changed(self) -> None:
        self._fit_region_initialized = True
        self._set_fit_range(self.sb_fit_start.value(), self.sb_fit_stop.value(), source="spin")
        self._on_fit_range_committed()

    def _fit_range(self, n_bins: int) -> tuple[int, int]:
        """The selected fit/filter range (TAC bins), clamped to ``[0, n_bins]``."""
        lo, hi = self._fit_region.getRegion()
        start = max(0, int(round(min(lo, hi))))
        stop = min(int(n_bins), int(round(max(lo, hi))))
        if stop - start < 4:
            return 0, int(n_bins)
        return start, stop

    def _mask_to_fit_range(self, values, detector: str | None = None) -> np.ndarray:
        """Blank residuals outside the fit range (NaN → not drawn).

        Residuals are only meaningful inside the fit window, so bins outside
        ``[start, stop]`` are set to NaN and the residual traces are drawn with
        ``connect="finite"`` so the excluded region is simply not shown. When a
        ``detector`` is given its per-detector range override (if any) is used.
        """
        v = np.asarray(values, dtype=float).copy()
        start, stop = self._detector_fit_range(detector, v.size)
        if start > 0 or stop < v.size:
            v[:start] = np.nan
            v[stop:] = np.nan
        return v

    def _detector_fit_range(self, detector: str | None, n_bins: int) -> tuple[int, int]:
        """Per-detector fit range (override or the global region), clamped to n_bins."""
        rng = self._detector_fit_ranges.get(detector) if detector else None
        start, stop = rng if rng is not None else self._fit_range(n_bins)
        start = max(0, min(int(start), int(n_bins) - 1))
        stop = max(start + 1, min(int(stop), int(n_bins)))
        return start, stop

    def _zero_filters_outside(self, filters, start: int, stop: int) -> np.ndarray:
        """Zero every filter column outside ``[start, stop]``.

        Photons outside the fit range carry no fitted model, so their filter
        weights are set to zero — the filters are only defined where the decay was
        fitted (requested behaviour: "filters outside the fitting range are zeroed").
        """
        f = np.array(filters, dtype=float, copy=True)
        if f.ndim == 2:
            f[:, :max(0, int(start))] = 0.0
            f[:, int(stop):] = 0.0
        return f

    def _apply_range_to_result(self, result, detector: str | None) -> None:
        """Zero a result's filters outside that detector's fit range, in place.

        Handles both single/multi/stacked :class:`FilterResult` (``.filters``) and
        the anisotropy :class:`FilterResultMFD` (``.filters_par``/``.filters_perp``).
        The *un-zeroed* filters are cached on the result the first time, so a later
        range change can re-zero (even widen) without a refit.
        """
        if result is None:
            return
        for attr in ("filters", "filters_par", "filters_perp"):
            f = getattr(result, attr, None)
            if f is None:
                continue
            cache_attr = f"_{attr}_full"
            base = getattr(result, cache_attr, None)
            if base is None:
                base = np.array(f, dtype=float, copy=True)
                try:
                    setattr(result, cache_attr, base)
                except Exception:
                    pass
            n_bins = int(np.asarray(base).shape[1])
            start, stop = self._detector_fit_range(detector, n_bins)
            setattr(result, attr, self._zero_filters_outside(base, start, stop))

    def _single_detector(self) -> str | None:
        """The detector to attribute a single-channel result to (or None → global)."""
        chs = self.detector_selection.get_selected() if self.detector_selection.checkboxes else None
        return chs[0] if chs and len(chs) == 1 else None

    def _ranged_filters(self, total_data, species_data, *, detector, total_path,
                        species_patterns, nuisance_decays, nuisance_labels):
        """Compute fFCS filters **over the detector's fit range** and embed back.

        The filters/g-matrix are solved on the ``[start, stop]`` slice only, so the
        reconstruction and residuals are not biased by the excluded pre-prompt and
        far-tail bins (the cause of a systematic tail offset). The full-length
        result has the in-range columns filled and zeros/original outside.
        """
        total = np.asarray(total_data, dtype=float).ravel()
        n_bins = int(total.size)
        start, stop = self._detector_fit_range(detector, n_bins)
        species = [self._resize_pattern(np.asarray(s, dtype=float), n_bins)
                   for s in species_data]
        nuis = [self._resize_pattern(np.asarray(d, dtype=float), n_bins)
                for d in (nuisance_decays or [])]
        ranged = compute_filters(
            total[start:stop],
            [s[start:stop] for s in species],
            total_path=total_path,
            species_patterns=species_patterns,
            nuisance_decays=[d[start:stop] for d in nuis] or None,
            nuisance_labels=nuisance_labels,
            reject_nuisance=True,
        )
        n_filt = int(np.asarray(ranged.filters).shape[0])
        filters = np.zeros((n_filt, n_bins), dtype=float)
        filters[:, start:stop] = np.asarray(ranged.filters)
        recon = total.copy()  # outside the window recon == total (residual 0)
        recon[start:stop] = np.asarray(ranged.reconstruction)
        wres = np.zeros(n_bins, dtype=float)
        wres[start:stop] = np.asarray(ranged.weighted_residuals)
        return FilterResult(
            filters=filters, reconstruction=recon, weighted_residuals=wres,
            total_decay=total, species_decays=species,
            metadata=ranged.metadata, total_path=total_path,
            species_patterns=species_patterns,
            nuisance_count=int(ranged.nuisance_count),
            nuisance_labels=list(ranged.nuisance_labels or []),
        )

    def _reapply_fit_ranges(self) -> None:
        """Re-zero every stored result to the current ranges (from cached filters)."""
        if self._result is not None:
            self._apply_range_to_result(self._result, self._single_detector())
        if self._result_anisotropy is not None:
            self._apply_range_to_result(self._result_anisotropy, self._single_detector())
        for entry in (self._result_multi_detector or []):
            self._apply_range_to_result(entry["result"], entry["detector"])
        for entry in (self._result_multi_anisotropy or []):
            self._apply_range_to_result(entry["result"], entry["detector"])

    def _measured_irf_vector(self, detector: str | None, role: str = ""):
        """Return a detector's *measured* IRF vector, or ``None`` if none is loaded."""
        if not detector:
            return None
        configured = self.detector_selection.irf_path(detector, role)
        if configured and pathlib.Path(configured).is_file():
            return np.asarray(load_vector(pathlib.Path(configured)), dtype=float).ravel()
        return None

    def _auto_fit_components(self, n_components: int | None = None) -> None:
        """Auto-fit the mixed decay to N lifetime components and add them as species.

        The draggable fit region on the reconstruction plot sets the fit window.
        When the primary detector carries a **measured IRF** it is used directly and
        a tail fit (range start past the prompt) resolves the lifetimes. When **no
        IRF is loaded** the synthetic Gaussian IRF is *fitted jointly* — its width is
        a free parameter — so the fit window is extended down to the prompt
        (``fit_lo = 0``) to make the IRF identifiable, and the fitted FWHM is written
        back to every selected detector that lacks a measured IRF. Each resolved
        lifetime is appended as one synthetic species, its per-detector pattern
        convolved with that detector's IRF.
        """
        from chisurf.core.fluorescence.decay_fit_model import fit_lifetime_model
        from chisurf.core.fluorescence.tcspc.irf import FWHM_TO_SIGMA

        if not self._has_total_decay():
            QtWidgets.QMessageBox.warning(
                self, "Missing Total Decay", "Load a mixed total decay first."
            )
            return
        # Settings come from the persistent Auto-fit dock (no modal popup).
        settings = dict(self._auto_fit_settings)
        kind = settings["kind"]
        if n_components is None:
            n_components = int(settings["n_components"])

        chs = self.detector_selection.get_selected() if self.detector_selection.checkboxes else None
        total = np.asarray(self._total_decay(chs[:1] if chs else None), dtype=float).ravel()
        dt = self._pattern_bin_width_ns()
        n_bins = int(total.size)
        self._init_fit_region(total)
        start, stop = self._fit_range(n_bins)

        # Fit the IRF jointly when the primary detector has no measured IRF.
        primary = (chs[0] if chs else None)
        measured = self._measured_irf_vector(primary)
        fit_irf = measured is None
        # The model masks the fit window itself, so it is handed the FULL decay
        # (and the full IRF) plus the range — unlike the sliced-window call this
        # replaced, which made every fitted time relative to the window start.
        fit_lo = int(start)

        # Fit the fraction of scatter (IRF-shaped prompt) and background/afterpulse
        # jointly with the lifetimes, driven by the AP / IRF toggles, so the
        # lifetimes are not biased by having to absorb the prompt/baseline.
        include_background = bool(self.fit_background_cb.isChecked())
        include_scatter = bool(self.options_model.scatter_irf)
        # Periodic (laser-period) convolution comes from the Instrument dock.
        period = self._fit_period_ns(n_bins, dt)

        fwhm0 = (max(dt, float(self.detector_selection.width(primary, "") or 0.2))
                 if primary else 0.2)
        skew0 = float(self.detector_selection.skew(primary, "") or 0.0) if primary else 0.0
        shared = dict(
            bin_width=dt, irf=measured, start_bin=fit_lo, stop_bin=stop,
            fit_irf=fit_irf,
            irf_width=fwhm0 * FWHM_TO_SIGMA,   # the model parameterises sigma
            irf_skew=skew0,
            fit_background=include_background,
            fit_scatter=include_scatter,
            period=period,
        )
        try:
            if kind == "fret":
                # A real FRET fit: the distances (and hence the efficiencies) are
                # fitted against R0, rather than lifetimes converted afterwards.
                from chisurf.core.fluorescence.decay_fit_model import fit_fret_model

                instrument = self._instrument()
                result = fit_fret_model(
                    total, n_states=int(n_components),
                    donor_lifetime=float(settings["tau_max"]),
                    forster_radius=float(instrument.get("forster_radius") or 52.0),
                    **shared,
                )
                taus = np.asarray([], dtype=float)
            else:
                result = fit_lifetime_model(
                    total, n_components=int(n_components),
                    tau_bounds=(float(settings["tau_min"]), float(settings["tau_max"])),
                    **shared,
                )
                taus = result["lifetimes"]
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Auto-fit Error", str(error))
            return
        if kind == "fret":
            # The FRET fit reports species fractions directly.
            amps = np.asarray(result["fractions"], dtype=float)
        else:
            # `fit_lifetime_model` reports PRE-EXPONENTIAL amplitudes, whereas the
            # scipy fitter this replaced reported photon fractions. Everything
            # downstream (species labels, relative species weights) means
            # fractions, so convert: f_i = a_i·tau_i / sum(a_j·tau_j).
            amps = np.asarray(result["amplitudes"], dtype=float) * taus
        scale = float(amps.sum()) or 1.0
        self._auto_fit_result = result
        self._refresh_autofit_parameters(result.get("fit"))
        detector_names = list(chs or [])
        # Write the fitted IRF back to detectors lacking a measured one. The model
        # parameterises the prompt as a generalized normal with sigma `iw` and
        # shape `ik`; `synthetic_irf` takes a FWHM and the *same* shape, so the
        # width converts exactly and the skew transfers unchanged. The shift is
        # read off the model's own processed IRF (whose peak carries the absolute
        # position) against `_detector_irf`'s nominal 2·FWHM centre, which avoids
        # depending on the units of the model's internal timeshift.
        fitted_fwhm = float(result.get("irf_width") or 0.0) / FWHM_TO_SIGMA
        fitted_skew = result.get("irf_skew")
        if fit_irf and fitted_fwhm > 0:
            try:
                irf_y = np.asarray(result["model"].convolve.irf.y, dtype=float)
                peak_ns = float(int(np.argmax(irf_y))) * dt
            except Exception:
                peak_ns = 2.0 * fitted_fwhm
            shift = peak_ns - 2.0 * fitted_fwhm
            for det in (detector_names or ([primary] if primary else [])):
                if self._measured_irf_vector(det) is None:
                    self.detector_selection.set_width(det, float(fitted_fwhm), "")
                    if fitted_skew is not None:
                        self.detector_selection.set_skew(det, float(fitted_skew), "")
                    self.detector_selection.set_shift(det, float(shift), "")

        # The IRF (measured or fitted) carries the absolute prompt position, so
        # components are convolved from t=0 over the full axis in both cases.
        comp_start = 0
        # Replace the current components with the freshly-fitted set (clear first),
        # adding all species without recomputing per add; compute once at the end.
        self._suspend_compute = True
        try:
            self.lw_species.clear()
            if kind == "fret":
                self._add_fret_autofit_species(
                    amps, taus, scale, dt, comp_start, n_bins, detector_names,
                    period=period,
                    efficiencies=result["efficiencies"],
                    tau_d0=result["donor_lifetime"],
                    donor_only_fraction=result["donor_only_fraction"],
                )
            else:
                self._add_autofit_species(kind, amps, taus, scale, dt, comp_start,
                                          n_bins, detector_names, apply_irf=True,
                                          period=period)
        finally:
            self._suspend_compute = False
        self._on_data_changed()
        if kind == "fret":
            parts = ", ".join(
                f"{float(a) / scale:.0%}·E={float(e):.2f}"
                for a, e in zip(amps, result["efficiencies"])
            )
            n_species = len(result["efficiencies"])
        else:
            parts = ", ".join(
                f"{float(a) / scale:.0%}·{float(t):.2f}ns" for a, t in zip(amps, taus)
            )
            n_species = len(taus)
        label = "FRET states" if kind == "fret" else "components"
        if fit_irf and fitted_fwhm > 0:
            irf_note = (f", IRF FWHM {fitted_fwhm:.3f} ns / shift {shift:+.3f} ns"
                        f" / skew {float(fitted_skew or 0.0):+.2f}")
        else:
            irf_note = ""
        # Report the fitted nuisance terms. The model reports them as absolute
        # per-bin amplitudes rather than as fractions of the total.
        nuis = []
        if include_scatter and result.get("scatter"):
            nuis.append(f"scatter {result['scatter']:.3g}")
        if include_background and result.get("background"):
            nuis.append(f"bkg {result['background']:.3g}")
        nuis_note = (" [" + ", ".join(nuis) + "]") if nuis else ""
        msg = (f"Auto-fit [{fit_lo}–{stop}]: {n_species} {label} "
               f"(χ²ᵣ={result['chi2_reduced']:.3g}{irf_note}) — {parts}{nuis_note}.")
        self._update_status(msg)
        if hasattr(self, "lbl_autofit_status"):
            self.lbl_autofit_status.setText(msg)
        # Persist the full breakdown to the log/console so the fitted fractions
        # (including the scatter/background nuisance) are recorded, not just shown.
        cs.logging.info(msg)

    def _add_autofit_species(self, kind, amps, taus, scale, dt, start, n_bins,
                             detector_names, apply_irf: bool = False, period=None):
        from chisurf.core.fluorescence.decay import synthetic_decay

        if kind == "fret":
            self._add_fret_autofit_species(amps, taus, scale, dt, start, n_bins,
                                           detector_names, period=period)
        else:
            for amp, tau in zip(amps, taus):
                frac = float(amp) / scale
                source = {
                    "type": "synthetic", "model": "lifetime_spectrum",
                    # Fitted fraction is kept in the component name so it stays
                    # visible in the Components list (not just the transient status).
                    "name": f"τ={float(tau):.2f} ns ({frac:.0%})",
                    "amplitudes": [frac], "lifetimes": [float(tau)],
                    "bin_width": float(dt), "start_bin": int(start), "irf_path": None,
                    "period_ns": float(period) if period else 0.0,
                }
                # When the IRF was fitted, convolve each detector's pattern with that
                # detector's IRF (the fitted synthetic width, written back above);
                # otherwise keep the tail alignment (no IRF, start_bin=range start).
                patterns = {}
                for name in detector_names:
                    irf = self._detector_irf(name, n_bins=int(n_bins)) if apply_irf else None
                    # Guard: only convolve with a usable (positive) IRF.
                    if irf is not None and not np.any(np.asarray(irf) > 0.0):
                        irf = None
                    patterns[name] = synthetic_decay(
                        n_bins, [float(tau)], bin_width=float(dt), irf=irf,
                        start_bin=int(start), normalize=True, period=period,
                    ).tolist()
                if patterns:
                    patterns["__default__"] = patterns[detector_names[0]]
                    source["patterns_by_detector"] = patterns
                self.lw_species.add_synthetic_source(source)

    def _add_fret_autofit_species(self, amps, taus, scale, dt, start, n_bins,
                                  detector_names, period=None, efficiencies=None,
                                  tau_d0=None, donor_only_fraction=0.0):
        """Add FRET species from fitted efficiencies, or derive them from lifetimes.

        With ``efficiencies`` (from a real ``FRETModel`` fit) each value is used
        directly, together with the fitted ``tau_d0`` and, when non-zero, an extra
        donor-only species carrying ``donor_only_fraction``.

        Without them the efficiencies are *derived*: the longest fitted lifetime is
        taken as the unquenched donor τ_D0 and each τᵢ becomes Eᵢ = 1 − τᵢ/τ_D0.
        That is the weaker inference — it assumes the slowest component is
        unquenched donor — and is kept for callers that only have lifetimes.

        Each species is expanded to per-detector coupled decays and added — a
        starting FRET set the user refines in the editor.
        """
        from chisurf.core.fluorescence.fret.species_decay import fret_species_detector_patterns

        if efficiencies is not None:
            tau_d0 = float(tau_d0 or 1.0)
            pairs = [(float(a), float(e)) for a, e in zip(amps, efficiencies)]
            if float(donor_only_fraction) > 1e-3:
                # The fitted donor-only population is its own species; its
                # fraction is a share of the whole sample, so it is expressed on
                # the same scale as the FRET states.
                pairs.append((float(donor_only_fraction) * scale, 0.0))
        else:
            tau_d0 = float(max(taus)) if len(taus) else 1.0
            pairs = [(float(a), float(np.clip(1.0 - float(t) / tau_d0, 0.0, 0.999)))
                     for a, t in zip(amps, taus)]

        dets = detector_names or ["green", "red", "yellow"]
        for amp, efficiency in pairs:
            frac = float(amp) / scale
            tau = tau_d0 * (1.0 - efficiency)
            state = "d_only" if efficiency < 1e-3 else "da"
            source = {
                "type": "synthetic", "model": "fret_species",
                # Keep the fitted fraction visible in the Components list.
                "name": (f"donor-only τ={tau_d0:.2f} ({frac:.0%})" if state == "d_only"
                         else f"DA E={efficiency:.2f} ({frac:.0%})"),
                "state": state,
                "donor_spectrum": [1.0, tau_d0],
                "acceptor_spectrum": [1.0, 2.0],
                "fret_mode": "efficiency", "transfer_efficiency": efficiency,
                "bin_width": float(dt),
                "period_ns": float(period) if period else 0.0,
                # Seed crosstalk from the Instrument dock (α/β/γ/δ, R0).
                "crosstalk": {k: self._instrument().get(k)
                              for k in ("alpha", "beta", "gamma", "delta")},
                "forster_radius": self._instrument().get("forster_radius"),
            }
            try:
                patterns = fret_species_detector_patterns(
                    source, dets, n_bins, irf_for_detector=self._detector_irf
                )
                source["patterns_by_detector"] = {
                    k: np.asarray(v, dtype=float).tolist() for k, v in patterns.items()
                }
            except Exception as error:
                cs.logging.warning(f"FRET auto-fit species build failed: {error}")
            self.lw_species.add_synthetic_source(source)

    def _unmix_total(self) -> None:
        if not self._has_total_decay():
            QtWidgets.QMessageBox.warning(self, "Missing Total Decay", "Load a mixed total decay first.")
            return
        try:
            chs = self.detector_selection.get_selected() if self.detector_selection.checkboxes else None
            total = self._total_decay(chs)
            patterns = []
            names = []
            for index in range(self.lw_species.count()):
                item = self.lw_species.item(index)
                if item.checkState() == QtCore.Qt.Checked:
                    pattern, _ = self._species_item_pattern(item, total.size, chs)
                    patterns.append(pattern)
                    names.append(item.text().split("  [", 1)[0])
            selected_detectors = self.detector_selection.get_selected()
            nuisance, nuisance_labels = self._nuisance_patterns(
                total,
                patterns,
                selected_detectors[0] if len(selected_detectors) == 1 else None,
            )
            self._unmix_result = unmix_decay(
                total,
                patterns,
                nuisance_decays=nuisance,
                nuisance_labels=nuisance_labels,
            )
            self._compute_filters()
            diagnostics = self._unmix_result.to_dict()
            if self._result is not None:
                self._result.reconstruction = self._unmix_result.reconstruction
                self._result.weighted_residuals = self._unmix_result.weighted_residuals
                self._result.metadata["unmixing"] = diagnostics
                self._result.metadata["component_names"] = names
                self._update_plots()
            elif self._result_multi_detector:
                for detector_result in self._result_multi_detector:
                    detector_result["result"].metadata["unmixing"] = diagnostics
                    detector_result["result"].metadata["component_names"] = names
            elif self._result_anisotropy is not None:
                self._result_anisotropy.metadata["unmixing"] = diagnostics
                self._result_anisotropy.metadata["component_names"] = names
            elif self._result_multi_anisotropy:
                for detector_result in self._result_multi_anisotropy:
                    detector_result["result"].metadata["unmixing"] = diagnostics
                    detector_result["result"].metadata["component_names"] = names
            fractions = ", ".join(
                f"{name}: {fraction:.1%}"
                for name, fraction in zip(names, self._unmix_result.fractions)
            )
            nuisance_summary = ", ".join(
                f"{label}: {count:.0f} counts"
                for label, count in zip(
                    self._unmix_result.nuisance_labels or [],
                    self._unmix_result.nuisance_counts
                    if self._unmix_result.nuisance_counts is not None else [],
                )
            )
            suffix = f"; {nuisance_summary}" if nuisance_summary else ""
            self._update_status(f"Unmixed total — {fractions}{suffix}")
        except Exception as error:
            cs.logging.error(f"Decay unmixing error: {error}")
            QtWidgets.QMessageBox.critical(self, "Unmixing Error", str(error))
            self._update_status(f"Unmixing error: {error}")

    def _remove_selected_species(self) -> None:
        for item in self.lw_species.selectedItems():
            self.lw_species.takeItem(self.lw_species.row(item))
        # Removing species files requires cache invalidation
        self._invalidate_cache()
        self._on_data_changed()

    @staticmethod
    def _editable_model(item) -> str:
        """Return the editable model kind of a component, or '' if not editable."""
        source = item.data(QtCore.Qt.UserRole) if item is not None else None
        if isinstance(source, dict) and source.get("type") == "synthetic":
            model = source.get("model")
            if model in ("lifetime_spectrum", "fret_species"):
                return str(model)
        return ""

    @classmethod
    def _is_editable_component(cls, item) -> bool:
        """A synthetic lifetime-spectrum or FRET-species component can be reopened."""
        return bool(cls._editable_model(item))

    def _edit_component_item(self, item) -> None:
        """Reopen the unified component editor for an editable component."""
        if self._is_editable_component(item):
            self._add_component_dialog(edit_item=item)

    def _species_context_menu(self, pos) -> None:
        """Right-click menu on the Components list: add / edit / remove."""
        item = self.lw_species.itemAt(pos)
        menu = QtWidgets.QMenu(self.lw_species)
        act_add = menu.addAction(f"{Glyphs.ADD} Add component…")
        act_add.setToolTip("Add a synthetic decay component (plain lifetime spectrum or FRET species).")
        act_add.triggered.connect(lambda: self._add_component_dialog())
        act_add_file = menu.addAction(f"{Glyphs.CHART_UP} Add measured pattern…")
        act_add_file.triggered.connect(self._add_species_dialog)
        act_edit = menu.addAction(f"{Glyphs.EDIT} Edit…")
        act_edit.setEnabled(self._is_editable_component(item))
        act_edit.triggered.connect(lambda: self._edit_component_item(item))
        menu.addSeparator()
        act_remove = menu.addAction(f"{Glyphs.REMOVE} Remove")
        act_remove.setEnabled(bool(self.lw_species.selectedItems()) or item is not None)

        def _remove():
            if item is not None and item not in self.lw_species.selectedItems():
                self.lw_species.takeItem(self.lw_species.row(item))
                self._invalidate_cache()
                self._on_data_changed()
            else:
                self._remove_selected_species()

        act_remove.triggered.connect(_remove)
        menu.exec_(self.lw_species.viewport().mapToGlobal(pos))

    def _on_files_changed(self) -> None:
        """Called when species files are added/removed (not just checkbox toggled)."""
        # Invalidate cache when files change
        self._invalidate_cache()
        self._on_data_changed()

    def _on_anisotropy_mode_changed(self) -> None:
        """Called when Anisotropy mode checkbox is toggled."""
        # Clear all results when switching modes
        self._result = None
        self._result_anisotropy = None
        self._result_multi_anisotropy = None
        self._result_multi_detector = None
        # Polarized mode splits each detector into parallel/perpendicular IRF rows.
        try:
            self.detector_selection.set_polarized(self.anisotropy_mode_cb.isChecked())
        except Exception:
            pass
        # Don't invalidate cache - just recompute filters from cached decays
        self._on_data_changed()

    def _on_detector_selection_changed(self) -> None:
        """Called when detector selection checkboxes are toggled."""
        # Don't invalidate cache - just recompute filters from cached decays
        self._on_data_changed()

    def _on_data_changed(self) -> None:
        self._result = None
        self.btn_export.setEnabled(False)
        self._update_status()
        # Note: Do NOT invalidate cache here - species checkbox changes don't require reloading files
        # Cache is only invalidated when files or detector selection actually change
        # Trigger auto-compute
        try:
            self._compute_filters()
        except Exception as e:
            import traceback
            cs.logging.error(f"Error in auto-compute: {e}\n{traceback.format_exc()}")
            self._update_status(f"Error: {e}")

    def _update_status(self, msg: str | None = None) -> None:
        if msg is None:
            n_species = self.lw_species.count()
            if not self._has_total_decay():
                msg = "Missing total decay histogram."
            elif n_species == 0:
                msg = "Add species decay patterns."
            else:
                msg = f"Ready to compute ({n_species} species)."
        self.status_label.setText(msg)

    @property
    def _filter_client(self):
        """Lazily-created backend RPC client (in-process)."""
        client = getattr(self, "_filter_client_obj", None)
        if client is None:
            client = _build_filter_client()
            self._filter_client_obj = client
        return client

    def _compute_filters_rpc(self, total_data, species_data, *, total_path=None,
                             species_patterns=None, nuisance_decays=None,
                             nuisance_labels=None, reject_nuisance=True) -> "FilterResult":
        """Compute single-channel filters through the backend RPC client.

        Falls back to the direct API on any transport/serialization issue so the
        GUI stays robust.
        """
        if nuisance_decays:
            return compute_filters(
                total_data,
                species_data,
                total_path=total_path,
                species_patterns=species_patterns,
                nuisance_decays=nuisance_decays,
                nuisance_labels=nuisance_labels,
                reject_nuisance=reject_nuisance,
            )
        try:
            r = self._filter_client.compute(total_data, species_data)
            if r.get("ok"):
                result = FilterResult.from_dict(r["result"])
                result.total_path = total_path
                result.species_patterns = species_patterns
                return result
        except Exception:
            pass
        return compute_filters(total_data, species_data, total_path=total_path,
                               species_patterns=species_patterns,
                               nuisance_decays=nuisance_decays,
                               nuisance_labels=nuisance_labels,
                               reject_nuisance=reject_nuisance)

    def _compute_filters(self) -> None:
        # Bulk operations (auto-fit adding many species) suspend the per-change
        # recompute and trigger one compute at the end.
        if getattr(self, "_suspend_compute", False):
            return
        if not self._has_total_decay() or self.lw_species.count() == 0:
            return

        # Rebuilt per computation by _nuisance_patterns (stale detectors dropped).
        self._irf_by_detector = {}
        try:
            # Detector filtering logic
            chs = None
            if self.detector_selection.checkboxes:
                chs = self.detector_selection.get_selected()
            
            # Check if Anisotropy mode is enabled (takes priority over multi-detector)
            anisotropy_mode = self.anisotropy_mode_cb.isChecked()
            if anisotropy_mode and chs and len(chs) >= 1:
                self._compute_filters_anisotropy(chs)
                return
            
            # Check if multiple detectors are selected (multi-detector stacking mode)
            # Only if NOT in anisotropy mode
            if chs and len(chs) > 1:
                if self.stacked_mode_cb.isChecked():
                    self._compute_filters_stacked(chs)
                else:
                    self._compute_filters_multi_detector(chs)
                return
            
            # Standard single-channel mode
            # Load and sum total decay files (with caching)
            total_data = self._total_decay(chs)

            species_data = []
            species_names = []
            species_patterns = []
            for i in range(self.lw_species.count()):
                item = self.lw_species.item(i)
                if item.checkState() != QtCore.Qt.Checked:
                    continue
                
                pattern_sum, source = self._species_item_pattern(item, total_data.size, chs)
                species_patterns.append(source)
                
                species_data.append(pattern_sum)
                species_names.append(item.text())

            # Validation against total - use the total size as the master size
            total_size = total_data.size
            for i in range(len(species_data)):
                sd = species_data[i]
                if sd.size != total_size:
                    # Adjust species pattern to match total size (truncate or pad)
                    if sd.size > total_size:
                        species_data[i] = sd[:total_size]
                    else:
                        padded = np.zeros(total_size, dtype=np.float64)
                        padded[:sd.size] = sd
                        species_data[i] = padded

            nuisance_decays, nuisance_labels = self._nuisance_patterns(
                total_data,
                species_data,
                chs[0] if chs and len(chs) == 1 else None,
            )
            self._result = self._ranged_filters(
                total_data,
                species_data,
                detector=chs[0] if chs and len(chs) == 1 else None,
                total_path=(
                    [str(p.absolute()) for p in self._total_paths]
                    if self._total_paths else ["synthetic:example-mixture"]
                ),
                species_patterns=species_patterns,
                nuisance_decays=nuisance_decays,
                nuisance_labels=nuisance_labels,
            )
            self._result_anisotropy = None  # Clear Anisotropy result
            self._result_multi_detector = None  # Clear multi-detector result
            self._update_plots()
            self.btn_export.setEnabled(True)
            self._update_status("Filters computed successfully.")

        except Exception as e:
            import traceback
            cs.logging.error(f"Computation error: {e}\n{traceback.format_exc()}")
            QtWidgets.QMessageBox.critical(self, "Computation Error", str(e))
            self._update_status(f"Error: {e}")

    def _invalidate_cache(self) -> None:
        """Invalidate decay cache when inputs change."""
        self._decay_cache.clear()
        self._routing_cache.clear()
        self._cache_state = None

    def _get_cache_key(self, paths: List[pathlib.Path], chs: List[str] | None) -> tuple:
        """Generate cache key from file paths and detector channels."""
        path_tuple = tuple(str(p.absolute()) for p in paths)
        ch_tuple = tuple(sorted(chs)) if chs else ()
        return (path_tuple, ch_tuple)

    def _load_routing_channels(self, path: pathlib.Path) -> Dict[int, np.ndarray]:
        """Load and cache all routing channel histograms for a TTTR file.
        
        Returns dict mapping routing_channel_number -> histogram.
        """
        path_str = str(path.absolute())
        
        if path_str in self._routing_cache:
            return self._routing_cache[path_str]
        
        # Load file and extract all routing channels
        ext = path.suffix.lower()
        routing_histograms = {}
        
        if ext in ('.spc', '.ptu', '.ht3', '.tttr'):
            import tttrlib
            try:
                # Load TTTR data once
                if ext == '.spc':
                    try:
                        data = tttrlib.TTTR(str(path), 'SPC-130')
                    except:
                        data = tttrlib.TTTR(str(path))
                else:
                    data = tttrlib.TTTR(str(path))
                
                header = data.get_header()
                try:
                    n_tac = header.number_of_micro_time_channels
                except AttributeError:
                    try:
                        n_tac = header['number_of_micro_time_channels']
                    except (KeyError, TypeError):
                        n_tac = 4096
                
                microtimes = data.micro_times
                routing = data.routing_channels
                # Micro-time axis (bin width + optional binning) from the data.
                microtimes, n_tac = self._micro_time_axis(header, microtimes, n_tac)

                # Extract histogram for each routing channel
                unique_routing = np.unique(routing)
                for rch in unique_routing:
                    mask = (routing == rch) & (microtimes >= 0) & (microtimes < n_tac)
                    hist = np.zeros(n_tac, dtype=np.float64)
                    np.add.at(hist, microtimes[mask], 1)
                    routing_histograms[int(rch)] = hist

            except Exception as e:
                cs.logging.warning(f"Error loading routing channels from {path.name}: {e}")
        
        elif ext == '.bst':
            # For BST files, load the underlying TTTR and extract bursts
            from .data_loading import parse_bst_file
            tttr_path, ranges = parse_bst_file(path)
            
            if tttr_path and ranges:
                import tttrlib
                try:
                    data = tttrlib.TTTR(str(tttr_path))
                    header = data.get_header()
                    try:
                        n_tac = header.number_of_micro_time_channels
                    except AttributeError:
                        try:
                            n_tac = header['number_of_micro_time_channels']
                        except (KeyError, TypeError):
                            n_tac = 4096
                    
                    microtimes = data.micro_times
                    routing = data.routing_channels
                    # Micro-time axis (bin width + optional binning) from the data.
                    microtimes, n_tac = self._micro_time_axis(header, microtimes, n_tac)

                    # Extract histograms for each routing channel from burst regions
                    unique_routing = np.unique(routing)
                    for rch in unique_routing:
                        hist = np.zeros(n_tac, dtype=np.float64)
                        for start, end in ranges:
                            if start < len(microtimes) and end <= len(microtimes):
                                burst_mt = microtimes[start:end]
                                burst_rt = routing[start:end]
                                mask = (burst_rt == rch) & (burst_mt >= 0) & (burst_mt < n_tac)
                                np.add.at(hist, burst_mt[mask], 1)
                        routing_histograms[int(rch)] = hist
                        
                except Exception as e:
                    cs.logging.warning(f"Error loading BST routing channels from {path.name}: {e}")
        
        # Cache the routing histograms
        self._routing_cache[path_str] = routing_histograms
        return routing_histograms

    def _load_and_sum_vectors(self, paths: List[pathlib.Path], chs: List[str] | None) -> np.ndarray:
        """Load and sum vectors with routing channel caching."""
        cache_key = self._get_cache_key(paths, chs)
        
        if cache_key in self._decay_cache:
            return self._decay_cache[cache_key].copy()
        
        # Determine which routing channels to use
        routing_channels = set()
        if chs:
            for ch_name in chs:
                if ch_name.startswith("routing_"):
                    try:
                        routing_channels.add(int(ch_name.split("_")[1]))
                    except:
                        pass
                elif self._detector_settings:
                    # Map detector name to routing channels
                    det_config = self._detector_settings.get("detectors", {}).get(ch_name, {})
                    det_chs = det_config.get("chs", [])
                    routing_channels.update(det_chs)
        
        # Load and combine from routing channel cache
        max_size = 0
        all_histograms = []
        
        for path in paths:
            ext = path.suffix.lower()
            
            if ext in ('.spc', '.ptu', '.ht3', '.tttr', '.bst'):
                # Use routing channel cache
                routing_hists = self._load_routing_channels(path)
                
                if routing_channels:
                    # Combine specified routing channels
                    combined = None
                    for rch in routing_channels:
                        if rch in routing_hists:
                            if combined is None:
                                combined = routing_hists[rch].copy()
                            else:
                                combined += routing_hists[rch]
                    if combined is not None:
                        all_histograms.append(combined)
                        max_size = max(max_size, combined.size)
                else:
                    # Use all routing channels
                    combined = None
                    for hist in routing_hists.values():
                        if combined is None:
                            combined = hist.copy()
                        else:
                            combined += hist
                    if combined is not None:
                        all_histograms.append(combined)
                        max_size = max(max_size, combined.size)
            else:
                # For text files, use old method
                vec = load_vector(path, chs=chs, detector_settings=self._detector_settings)
                all_histograms.append(vec)
                max_size = max(max_size, vec.size)
        
        # Sum all histograms
        if max_size == 0 or not all_histograms:
            # No valid data - return empty array
            cs.logging.warning(f"No valid histogram data loaded for paths: {[p.name for p in paths]}")
            return np.zeros(4096, dtype=np.float64)
        
        summed = np.zeros(max_size, dtype=np.float64)
        for hist in all_histograms:
            if hist.size < max_size:
                padded = np.zeros(max_size, dtype=np.float64)
                padded[:hist.size] = hist
                summed += padded
            else:
                summed += hist
        
        # Cache the result
        self._decay_cache[cache_key] = summed.copy()
        return summed

    def _compute_filters_anisotropy(self, chs: List[str]) -> None:
        """Compute Anisotropy filters for parallel and perpendicular channels.
        
        Uses detector wizard routing channel logic: channels alternate as par, perp, par, perp.
        For a detector with routing channels [8, 0], ch 8 = parallel, ch 0 = perpendicular.
        With multiple detectors - computes separate par/perp for each detector and stacks them.
        """
        from ..api import compute_filters_mfd
        
        try:
            # Check if multiple detectors selected - compute separately for each
            if len(chs) > 1:
                self._compute_filters_multi_anisotropy(chs)
                return
            
            # Single detector anisotropy mode
            # Extract routing channels from the selected detector
            routing_par = []
            routing_perp = []
            
            if self._detector_settings and chs:
                det_name = chs[0]
                det_config = self._detector_settings.get("detectors", {}).get(det_name, {})
                routing_chs = det_config.get("chs", [])
                
                if len(routing_chs) >= 2:
                    # Alternating pattern: index 0, 2, 4... = parallel; index 1, 3, 5... = perpendicular
                    for i, ch in enumerate(routing_chs):
                        if i % 2 == 0:
                            routing_par.append(ch)
                        else:
                            routing_perp.append(ch)
                else:
                    raise ValueError(f"Detector '{det_name}' must have at least 2 routing channels for Anisotropy mode")
            else:
                raise ValueError("Anisotropy mode requires detector settings with routing channels")
            
            # Create routing channel names for load_vector
            ch_par = [f"routing_{ch}" for ch in routing_par]
            ch_perp = [f"routing_{ch}" for ch in routing_perp]
            
            # Load total decay for each channel separately (with caching)
            total_par = self._total_decay(ch_par)
            total_perp = self._total_decay(ch_perp)
            
            # Ensure both have same size
            max_size = max(total_par.size, total_perp.size)
            if total_par.size < max_size:
                padded = np.zeros(max_size, dtype=np.float64)
                padded[:total_par.size] = total_par
                total_par = padded
            if total_perp.size < max_size:
                padded = np.zeros(max_size, dtype=np.float64)
                padded[:total_perp.size] = total_perp
                total_perp = padded
            
            # Load species patterns for each channel
            species_par = []
            species_perp = []
            species_patterns = []
            
            for i in range(self.lw_species.count()):
                item = self.lw_species.item(i)
                if item.checkState() != QtCore.Qt.Checked:
                    continue
                
                pattern_par, source = self._species_item_pattern(item, max_size, ch_par)
                species_patterns.append(source)
                species_par.append(pattern_par)
                
                # Load for perpendicular channel (with caching)
                pattern_perp, _ = self._species_item_pattern(item, max_size, ch_perp)
                species_perp.append(pattern_perp)
            
            # Compute Anisotropy filters
            metadata = {
                "detector": chs[0],
                "routing_par": routing_par,
                "routing_perp": routing_perp,
            }
            nuisance_par, nuisance_labels = self._nuisance_patterns(
                total_par, species_par, chs[0], "parallel"
            )
            nuisance_perp, _ = self._nuisance_patterns(
                total_perp, species_perp, chs[0], "perpendicular"
            )
            self._result_anisotropy = compute_filters_mfd(
                total_par, total_perp,
                species_par, species_perp,
                metadata=metadata,
                nuisance_decays_par=nuisance_par,
                nuisance_decays_perp=nuisance_perp,
                nuisance_labels=nuisance_labels,
                reject_nuisance=True,
            )
            self._apply_range_to_result(self._result_anisotropy, chs[0] if chs else None)
            self._result = None  # Clear single-channel result
            self._result_multi_detector = None  # Clear multi-detector result
            self._result_multi_anisotropy = None  # Clear multi-anisotropy result
            self._update_plots()
            self.btn_export.setEnabled(True)
            self._update_status(f"Anisotropy filters computed successfully ({chs[0]}: ch {routing_par} || ch {routing_perp}).")
            
        except Exception as e:
            import traceback
            cs.logging.error(f"Anisotropy computation error: {e}\n{traceback.format_exc()}")
            QtWidgets.QMessageBox.critical(self, "Anisotropy Computation Error", str(e))
            self._update_status(f"Anisotropy Error: {e}")

    def _compute_filters_multi_anisotropy(self, chs: List[str]) -> None:
        """Compute Anisotropy filters separately for each detector and stack them.
        
        Each detector gets its own par/perp computation.
        """
        from ..api import compute_filters_mfd
        
        try:
            anisotropy_results = []
            
            for det_name in chs:
                # Extract routing channels for this detector
                if not self._detector_settings:
                    raise ValueError("Anisotropy mode requires detector settings")
                
                det_config = self._detector_settings.get("detectors", {}).get(det_name, {})
                routing_chs = det_config.get("chs", [])
                
                if len(routing_chs) < 2:
                    cs.logging.warning(f"Detector '{det_name}' has <2 routing channels, skipping")
                    continue
                
                # Split into par/perp
                routing_par = []
                routing_perp = []
                for i, ch in enumerate(routing_chs):
                    if i % 2 == 0:
                        routing_par.append(ch)
                    else:
                        routing_perp.append(ch)
                
                ch_par = [f"routing_{ch}" for ch in routing_par]
                ch_perp = [f"routing_{ch}" for ch in routing_perp]
                
                # Load total decay for this detector's par/perp
                total_par = self._total_decay(ch_par)
                total_perp = self._total_decay(ch_perp)
                
                # Ensure same size
                max_size = max(total_par.size, total_perp.size)
                if total_par.size < max_size:
                    padded = np.zeros(max_size, dtype=np.float64)
                    padded[:total_par.size] = total_par
                    total_par = padded
                if total_perp.size < max_size:
                    padded = np.zeros(max_size, dtype=np.float64)
                    padded[:total_perp.size] = total_perp
                    total_perp = padded
                
                # Load species patterns
                species_par = []
                species_perp = []
                species_patterns = []
                
                for i in range(self.lw_species.count()):
                    item = self.lw_species.item(i)
                    if item.checkState() != QtCore.Qt.Checked:
                        continue
                    
                    pattern_par, source = self._species_item_pattern(item, max_size, ch_par)
                    species_patterns.append(source)
                    species_par.append(pattern_par)
                    
                    pattern_perp, _ = self._species_item_pattern(item, max_size, ch_perp)
                    species_perp.append(pattern_perp)
                
                # Compute anisotropy for this detector
                metadata = {
                    "detector": det_name,
                    "routing_par": routing_par,
                    "routing_perp": routing_perp,
                }
                nuisance_par, nuisance_labels = self._nuisance_patterns(
                    total_par, species_par, det_name, "parallel"
                )
                nuisance_perp, _ = self._nuisance_patterns(
                    total_perp, species_perp, det_name, "perpendicular"
                )
                result = compute_filters_mfd(
                    total_par, total_perp,
                    species_par, species_perp,
                    metadata=metadata,
                    nuisance_decays_par=nuisance_par,
                    nuisance_decays_perp=nuisance_perp,
                    nuisance_labels=nuisance_labels,
                    reject_nuisance=True,
                )
                self._apply_range_to_result(result, det_name)
                anisotropy_results.append({
                    'detector': det_name,
                    'result': result
                })
            
            if not anisotropy_results:
                raise ValueError("No valid detectors for Anisotropy mode")
            
            # Store multi-anisotropy results
            self._result_multi_anisotropy = anisotropy_results
            self._result = None
            self._result_anisotropy = None
            self._result_multi_detector = None
            self._update_plots()
            self.btn_export.setEnabled(True)
            detector_names = ", ".join([ar['detector'] for ar in anisotropy_results])
            self._update_status(f"Multi-detector Anisotropy filters computed successfully ({detector_names}).")
            
        except Exception as e:
            import traceback
            cs.logging.error(f"Multi-Anisotropy computation error: {e}\n{traceback.format_exc()}")
            QtWidgets.QMessageBox.critical(self, "Multi-Anisotropy Computation Error", str(e))
            self._update_status(f"Multi-Anisotropy Error: {e}")

    def _compute_filters_multi_detector(self, chs: List[str]) -> None:
        """Compute filters for multiple detectors separately and stack them.
        
        Each detector's photons are isolated - red photons don't contribute to green decay.
        """
        try:
            # Store results for each detector
            detector_results = []
            
            for det_name in chs:
                # Load total decay for this detector only (with caching)
                ch_list = [det_name]
                total_data = self._total_decay(ch_list)
                
                # Load species patterns for this detector only
                species_data = []
                species_names = []
                species_patterns = []
                for i in range(self.lw_species.count()):
                    item = self.lw_species.item(i)
                    if item.checkState() != QtCore.Qt.Checked:
                        continue
                    
                    pattern_sum, source = self._species_item_pattern(item, total_data.size, ch_list)
                    species_patterns.append(source)
                    
                    species_data.append(pattern_sum)
                    species_names.append(item.text())
                
                # Validation against total
                total_size = total_data.size
                for i in range(len(species_data)):
                    sd = species_data[i]
                    if sd.size != total_size:
                        if sd.size > total_size:
                            species_data[i] = sd[:total_size]
                        else:
                            padded = np.zeros(total_size, dtype=np.float64)
                            padded[:sd.size] = sd
                            species_data[i] = padded
                
                # Compute filters for this detector over its fit range.
                nuisance, nuisance_labels = self._nuisance_patterns(
                    total_data, species_data, det_name
                )
                result = self._ranged_filters(
                    total_data,
                    species_data,
                    detector=det_name,
                    total_path=[str(p.absolute()) for p in self._total_paths],
                    species_patterns=species_patterns,
                    nuisance_decays=nuisance,
                    nuisance_labels=nuisance_labels,
                )
                detector_results.append({
                    'detector': det_name,
                    'result': result
                })

            # Store multi-detector results
            self._result_multi_detector = detector_results
            self._result = None  # Clear single-channel result
            self._result_anisotropy = None  # Clear anisotropy result
            self._update_plots()
            self.btn_export.setEnabled(True)
            detector_names = ", ".join(chs)
            self._update_status(f"Multi-detector filters computed successfully ({detector_names}).")
            
        except Exception as e:
            import traceback
            cs.logging.error(f"Multi-detector computation error: {e}\n{traceback.format_exc()}")
            QtWidgets.QMessageBox.critical(self, "Multi-Detector Computation Error", str(e))
            self._update_status(f"Multi-Detector Error: {e}")

    def _compute_filters_stacked(self, chs: List[str]) -> None:
        """Compute ONE global filter set over the detectors stacked on a single axis.

        Each detector's total decay and per-species patterns are concatenated
        (``[green | red | yellow]``) into a single long vector, and one filter set
        is solved jointly. Because the per-detector species patterns keep their
        joint (FRET-constrained) normalization — a species' relative brightness
        across detectors — that ratio constrains the unmix, unlike the independent
        per-detector mode where each detector is normalized on its own.

        The global result is split back into per-detector :class:`FilterResult`
        slices stored in ``_result_multi_detector`` so the existing multi-detector
        plotting/export path renders each detector's segment unchanged; each
        detector's ``to_channel_filters()`` returns its slice of the global filters.
        """
        try:
            # Per-detector totals and species patterns (joint scaling preserved).
            totals = {det: np.asarray(self._total_decay([det]), dtype=float).ravel()
                      for det in chs}
            n_bins = int(min(t.size for t in totals.values()))
            totals = {det: self._resize_pattern(t, n_bins) for det, t in totals.items()}

            checked = [self.lw_species.item(i) for i in range(self.lw_species.count())
                       if self.lw_species.item(i).checkState() == QtCore.Qt.Checked]
            if not checked:
                return
            per_det_species: dict[str, list[np.ndarray]] = {det: [] for det in chs}
            species_patterns = []
            for item in checked:
                source = None
                for det in chs:
                    pat, source = self._species_item_pattern(item, n_bins, [det])
                    per_det_species[det].append(self._resize_pattern(pat, n_bins))
                species_patterns.append(source)

            # Per-detector nuisance, aligned by index (AP / scatter) across detectors.
            nuis_by_det, labels0 = {}, None
            for det in chs:
                nd, nl = self._nuisance_patterns(totals[det], per_det_species[det], det)
                nuis_by_det[det] = [self._resize_pattern(np.asarray(p, dtype=float), n_bins)
                                    for p in nd]
                if labels0 is None:
                    labels0 = nl
            n_nuis = min((len(v) for v in nuis_by_det.values()), default=0)

            # Concatenate onto the stacked axis.
            total_stacked = np.concatenate([totals[det] for det in chs])
            species_stacked = [
                np.concatenate([per_det_species[det][k] for det in chs])
                for k in range(len(checked))
            ]
            nuisance_stacked = [
                np.concatenate([nuis_by_det[det][k] for det in chs])
                for k in range(n_nuis)
            ]

            stacked = compute_filters(
                total_stacked, species_stacked,
                total_path=[str(p.absolute()) for p in self._total_paths],
                species_patterns=species_patterns,
                nuisance_decays=nuisance_stacked or None,
                nuisance_labels=(labels0[:n_nuis] if labels0 else None),
                reject_nuisance=True,
            )

            # Split the global result back into per-detector FilterResult slices.
            from copy import deepcopy
            detector_results = []
            for idx, det in enumerate(chs):
                seg = slice(idx * n_bins, (idx + 1) * n_bins)
                meta = deepcopy(stacked.metadata) if stacked.metadata else {}
                meta["filter_mode"] = "stacked"
                meta["stacked_detectors"] = list(chs)
                fr = FilterResult(
                    filters=np.asarray(stacked.filters)[:, seg].copy(),
                    reconstruction=np.asarray(stacked.reconstruction)[seg].copy(),
                    weighted_residuals=np.asarray(stacked.weighted_residuals)[seg].copy(),
                    total_decay=np.asarray(stacked.total_decay)[seg].copy(),
                    species_decays=[np.asarray(s)[seg].copy() for s in stacked.species_decays],
                    metadata=meta,
                    total_path=stacked.total_path,
                    species_patterns=species_patterns,
                    nuisance_count=int(stacked.nuisance_count),
                    nuisance_labels=list(stacked.nuisance_labels or []),
                )
                self._apply_range_to_result(fr, det)
                detector_results.append({"detector": det, "result": fr})

            self._result_multi_detector = detector_results
            self._result = None
            self._result_anisotropy = None
            self._result_multi_anisotropy = None
            self._update_plots()
            self.btn_export.setEnabled(True)
            self._update_status(
                f"Global (stacked) filters computed over {', '.join(chs)} "
                f"({stacked.n_species} species, {n_bins} bins × {len(chs)} detectors)."
            )
        except Exception as e:
            import traceback
            cs.logging.error(f"Stacked computation error: {e}\n{traceback.format_exc()}")
            QtWidgets.QMessageBox.critical(self, "Stacked Filter Computation Error", str(e))
            self._update_status(f"Stacked Filter Error: {e}")

    def _build_detector_setup_selector(self, layout) -> None:
        """Compact picker of saved detector setups.

        Detector setups are edited in the toolbox's authoritative "Detector Def"
        tool; here the user only picks one, whose detectors populate the filter
        channel checkboxes. Uses the shared :class:`SetupSelector`.
        """
        from chisurf.gui.widgets.setup_selector import SetupSelector

        self.setup_selector = SetupSelector(
            loader=self._load_detector_setups or None
        )
        self.setup_selector.setupChanged.connect(self._on_detector_setup_selected)
        layout.addWidget(self.setup_selector)
        layout.addStretch(1)
        # Apply the initial selection now that the handler is connected.
        self._on_detector_setup_selected(self.setup_selector.current_setup())

    def _on_detector_setup_selected(self, name: str) -> None:
        setup = None
        if hasattr(self, "setup_selector"):
            setup = self.setup_selector.current_setup_dict()
        self._detector_settings = setup if isinstance(setup, dict) else None
        self._refresh_detector_checkboxes()
        # Pre-populate the Instrument dock (α/β/γ/δ, G, l1/l2, R0, period) from it.
        self._prepopulate_instrument_from_setup()

    def _connect_setup_signals(self):
        if not hasattr(self, 'detector_wizard_page') or not self.detector_wizard_page: return
        for widget in self.detector_wizard_page.findChildren(QtWidgets.QWidget):
            for signal_name in ['textChanged', 'currentIndexChanged', 'stateChanged', 'valueChanged', 'editingFinished']:
                if hasattr(widget, signal_name):
                    try:
                        getattr(widget, signal_name).connect(self._schedule_setup_refresh)
                    except Exception: pass

    def _schedule_setup_refresh(self):
        # Refresh checkboxes when wizard settings change
        self._detector_settings = self.detector_wizard_page.get_settings()
        self._refresh_detector_checkboxes()

    def _refresh_detector_checkboxes(self):
        # The Detector Setup tab is built before the Filter tab's selector
        # widget; skip until it exists (a later refresh covers it).
        if not hasattr(self, "detector_selection"):
            return
        detector_names = []
        if self._detector_settings:
            detector_names = list(self._detector_settings.get("detectors", {}).keys())
        elif self._has_detector_wizard:
            try:
                setups_data = self._load_detector_setups()
                if setups_data:
                    last_used = setups_data.get('last_used')
                    if last_used and last_used in setups_data.get('setups', {}):
                        self._detector_settings = setups_data['setups'][last_used]
                        detector_names = list(self._detector_settings.get("detectors", {}).keys())
            except Exception: pass
        
        self.detector_selection.set_bin_width_ns(self._pattern_bin_width_ns())
        self.detector_selection.refresh(detector_names)

    def _on_save_project(self) -> None:
        if self._result is None:
            # We can still save the UI state if paths are present
            if not self._total_paths and self.lw_species.count() == 0:
                QtWidgets.QMessageBox.warning(self, "Empty Project", "No data loaded to save.")
                return
            
            # Filters are automatically computed, so we can proceed with saving
            # The computation will happen automatically when data is loaded

        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save fFCS Project", "fcs_filter.json", "JSON (*.json)"
        )
        if path:
            import json
            
            if self._result is not None:
                # Save result with additional UI state
                self._result.to_json(path, indent=2)
                
                # Also save detector selection state and anisotropy mode
                with open(path, 'r') as f:
                    project_data = json.load(f)
                
                # Add UI state
                project_data['ui_state'] = {
                    'selected_detectors': self.detector_selection.get_selected(),
                    'anisotropy_mode': self.anisotropy_mode_cb.isChecked(),
                    'stacked_mode': self.stacked_mode_cb.isChecked(),
                    'afterpulse_filter': self.fit_background_cb.isChecked(),
                    'scatter_filter': self.options_model.scatter_irf,
                    'detector_irf': self.detector_selection.export_state(),
                }
                if self._total_vector is not None:
                    project_data['total_decay'] = self._total_vector.tolist()
                    project_data['total_label'] = self.le_total.text()
                if self._total_vectors_by_detector:
                    project_data['total_decays_by_detector'] = {
                        name: decay.tolist()
                        for name, decay in self._total_vectors_by_detector.items()
                    }
                
                with open(path, 'w') as f:
                    json.dump(project_data, f, indent=2)
            else:
                # Save only UI state when no computation results exist
                project_data = {
                    'total_path': [str(p.absolute()) for p in self._total_paths],
                    'total_decay': (
                        self._total_vector.tolist() if self._total_vector is not None else None
                    ),
                    'total_label': self.le_total.text(),
                    'species_patterns': [],
                    'ui_state': {
                        'selected_detectors': self.detector_selection.get_selected(),
                        'anisotropy_mode': self.anisotropy_mode_cb.isChecked(),
                        'stacked_mode': self.stacked_mode_cb.isChecked(),
                        'afterpulse_filter': self.fit_background_cb.isChecked(),
                        'scatter_filter': self.options_model.scatter_irf,
                        'detector_irf': self.detector_selection.export_state(),
                    }
                }
                if self._total_vectors_by_detector:
                    project_data['total_decays_by_detector'] = {
                        name: decay.tolist()
                        for name, decay in self._total_vectors_by_detector.items()
                    }
                
                # Add species patterns
                for i in range(self.lw_species.count()):
                    item = self.lw_species.item(i)
                    if item.checkState() == QtCore.Qt.Checked:
                        source = item.data(QtCore.Qt.UserRole)
                        if isinstance(source, dict):
                            project_data['species_patterns'].append(dict(source))
                        else:
                            project_data['species_patterns'].append(
                                [str(pathlib.Path(p).absolute()) for p in source]
                            )
                
                with open(path, 'w') as f:
                    json.dump(project_data, f, indent=2)
            
            self._update_status(f"Project saved to {pathlib.Path(path).name}")

    def _on_load_project(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load fFCS Project", "", "JSON (*.json)"
        )
        if not path:
            return

        try:
            import json
            with open(path, 'r') as f:
                project_data = json.load(f)
            res = FilterResult.from_dict(project_data) if 'filters' in project_data else None
            self._result = res
            
            # Restore UI state
            total_path = res.total_path if res is not None else project_data.get('total_path')
            inline_total = project_data.get('total_decay')
            inline_by_detector = project_data.get('total_decays_by_detector') or {}
            if inline_total is not None:
                self._total_paths = []
                self._total_vector = np.asarray(inline_total, dtype=float)
                self._total_vectors_by_detector = {
                    str(name): np.asarray(decay, dtype=float)
                    for name, decay in inline_by_detector.items()
                }
                self.le_total.setText(project_data.get('total_label') or "Project mixture")
                self.le_total.setCursorPosition(0)
            elif total_path:
                # If it's an old single-string path, wrap in list
                t_paths = total_path if isinstance(total_path, list) else [total_path]
                path_objs = [pathlib.Path(p) for p in t_paths]
                
                # Check for existence
                valid_paths = []
                for p in path_objs:
                    if p.exists():
                        valid_paths.append(p)
                    else:
                        cs.logging.warning(f"Total decay file not found: {p}")
                
                self._set_total_paths(valid_paths)
            
            self.lw_species.clear()
            species_patterns = (
                res.species_patterns if res is not None
                else project_data.get('species_patterns', [])
            )
            if species_patterns:
                for source in species_patterns:
                    if isinstance(source, dict) and source.get('type') == 'synthetic':
                        self.lw_species.add_synthetic_source(source)
                        continue
                    pattern_files = source.get('paths', []) if isinstance(source, dict) else source
                    paths = [pathlib.Path(p) for p in pattern_files]
                    # Check if all files in pattern exist
                    missing = [p for p in paths if not p.exists()]
                    if missing:
                        cs.logging.warning(f"Some files missing for pattern: {missing}")
                    self.lw_species.add_pattern(paths)
            
            ui_state = project_data.get('ui_state', {})
            
            # Restore detector selection
            selected_detectors = ui_state.get('selected_detectors', [])
            if selected_detectors and self.detector_selection.checkboxes:
                # First uncheck all
                for cb in self.detector_selection.checkboxes.values():
                    cb.setChecked(False)
                # Then check the saved ones
                for det_name in selected_detectors:
                    if det_name in self.detector_selection.checkboxes:
                        self.detector_selection.checkboxes[det_name].setChecked(True)
            
            # Restore anisotropy mode
            anisotropy_mode = ui_state.get('anisotropy_mode', False)
            self.anisotropy_mode_cb.setChecked(anisotropy_mode)
            self.stacked_mode_cb.setChecked(bool(ui_state.get('stacked_mode', False)))
            self.options_model.fit_background = ui_state.get('afterpulse_filter', True)
            self.options_model.scatter_irf = ui_state.get('scatter_filter', True)
            # Per-detector IRF / width / skew live on the detector table now.
            self.detector_selection.set_polarized(anisotropy_mode)
            self.detector_selection.import_state(ui_state.get('detector_irf', {}))
            self.options_form.sync_fields()
            
            self._update_plots()
            self.btn_export.setEnabled(True)
            self._update_status("Project loaded successfully.")
            
        except Exception as e:
            import traceback
            cs.logging.error(f"Error loading project: {e}\n{traceback.format_exc()}")
            QtWidgets.QMessageBox.critical(self, "Load Error", str(e))

    def _update_plots(self) -> None:
        # Keep the Info dock in sync with every recompute / data change.
        self._refresh_info()
        # Seed the draggable fit/filter range from the first available total decay
        # — including a file-backed total loaded with no species yet (the example
        # components are cleared on load, so there may be no computed result).
        def _loaded_total():
            if self._total_vector is not None:
                return self._total_vector
            if self._has_total_decay():
                try:
                    return self._total_decay(
                        self.detector_selection.get_selected() or None
                        if self.detector_selection.checkboxes else None
                    )
                except Exception:
                    return None
            return None

        for candidate in (
            getattr(self._result, "total_decay", None) if self._result else None,
            (self._result_multi_detector[0]["result"].total_decay
             if self._result_multi_detector else None),
            _loaded_total(),
        ):
            if candidate is not None and np.asarray(candidate).size > 8:
                self._init_fit_region(candidate)
                break

        # Handle multi-anisotropy mode - stack each detector's par/perp horizontally
        if self._result_multi_anisotropy:
            anisotropy_results = self._result_multi_anisotropy
            
            # Find maximum bin size
            max_bins = max(ar['result'].n_bins for ar in anisotropy_results)
            offset = max_bins * 1.1  # 10% gap between par/perp pairs
            
            # 1. Filters - stack each detector's par/perp horizontally
            self.plot_filters.clear()
            for det_idx, ar in enumerate(anisotropy_results):
                res = ar['result']
                det_name = ar['detector']
                base_x = det_idx * 2 * offset  # Each detector gets 2 slots (par + perp)
                x = np.arange(res.n_bins)
                
                for i in range(res.n_filters):
                    filter_label = self._filter_label(res, i)
                    # Parallel filters
                    self.plot_filters.plot(x + base_x, res.filters_par[i], pen=self._filter_color(res, i),
                                          name=f"{det_name}: {filter_label} (||)")
                    # Perpendicular filters
                    self.plot_filters.plot(x + base_x + offset, res.filters_perp[i], pen=self._filter_color(res, i),
                                          name=f"{det_name}: {filter_label} (⊥)")
                # Zero lines
                self.plot_filters.plot(x + base_x, np.zeros(res.n_bins), pen=pg.mkPen('w', style=QtCore.Qt.DashLine))
                self.plot_filters.plot(x + base_x + offset, np.zeros(res.n_bins), pen=pg.mkPen('w', style=QtCore.Qt.DashLine))
            
            # 2. Reconstruction - stack each detector's par/perp
            self._clear_recon_plot()
            for det_idx, ar in enumerate(anisotropy_results):
                res = ar['result']
                det_name = ar['detector']
                base_x = det_idx * 2 * offset
                x = np.arange(res.n_bins)
                
                # Parallel
                detector_color = self._stable_plot_color(det_name)
                self.plot_recon.plot(x + base_x, res.total_decay_par, pen=detector_color,
                                    name=f"{det_name}: Total (||)")
                self.plot_recon.plot(x + base_x, res.reconstruction_par, pen=pg.mkPen(detector_color, style=QtCore.Qt.DashLine),
                                    name=f"{det_name}: Recon (||)", style=QtCore.Qt.DashLine)
                # Perpendicular
                self.plot_recon.plot(x + base_x + offset, res.total_decay_perp, pen=detector_color,
                                    name=f"{det_name}: Total (⊥)")
                self.plot_recon.plot(x + base_x + offset, res.reconstruction_perp, pen=pg.mkPen(detector_color, style=QtCore.Qt.DashLine),
                                    name=f"{det_name}: Recon (⊥)", style=QtCore.Qt.DashLine)
            
            # 3. Residuals - stack each detector's par/perp
            self.plot_residuals.clear()
            for det_idx, ar in enumerate(anisotropy_results):
                res = ar['result']
                det_name = ar['detector']
                base_x = det_idx * 2 * offset
                x = np.arange(res.n_bins)
                
                # Parallel
                detector_color = self._stable_plot_color(det_name)
                self.plot_residuals.plot(x + base_x, self._mask_to_fit_range(res.weighted_residuals_par, det_name), pen=detector_color, connect="finite",
                                        name=f"{det_name} (||)")
                # Perpendicular
                self.plot_residuals.plot(x + base_x + offset, self._mask_to_fit_range(res.weighted_residuals_perp, det_name), pen=detector_color, connect="finite",
                                        name=f"{det_name} (⊥)")
                # Reference lines
                for val in [-3, 0, 3]:
                    pen = pg.mkPen('r' if val != 0 else 'w', style=QtCore.Qt.DashLine)
                    self.plot_residuals.plot(x + base_x, np.full(res.n_bins, val), pen=pen)
                    self.plot_residuals.plot(x + base_x + offset, np.full(res.n_bins, val), pen=pen)
            return
        
        # Handle multi-detector mode - stack detectors horizontally
        if self._result_multi_detector:
            detector_results = self._result_multi_detector
            
            # Find maximum bin size across all detectors
            max_bins = max(dr['result'].n_bins for dr in detector_results)
            offset = max_bins * 1.1  # 10% gap between detectors
            
            # 1. Filters - stack each detector horizontally
            self.plot_filters.clear()
            for det_idx, dr in enumerate(detector_results):
                res = dr['result']
                det_name = dr['detector']
                x = np.arange(res.n_bins) + (det_idx * offset)
                
                for i in range(res.n_filters):
                    pen, name = self._filter_pen_name(res, i, f"{det_name}: ")
                    self.plot_filters.plot(x, res.filters[i], pen=pen, name=name)
                # Zero line for this detector
                self.plot_filters.plot(x, np.zeros(res.n_bins), pen=pg.mkPen('w', style=QtCore.Qt.DashLine))
            
            # 2. Reconstruction - stack each detector horizontally
            self._clear_recon_plot()
            for det_idx, dr in enumerate(detector_results):
                res = dr['result']
                det_name = dr['detector']
                x = np.arange(res.n_bins) + (det_idx * offset)
                
                detector_color = self._stable_plot_color(det_name)
                self.plot_recon.plot(x, res.total_decay, pen=detector_color,
                                    name=f"{det_name}: Total")
                self.plot_recon.plot(x, res.reconstruction, pen=pg.mkPen(detector_color, style=QtCore.Qt.DashLine),
                                    name=f"{det_name}: Recon", style=QtCore.Qt.DashLine)
                self._plot_irf_overlay(self.plot_recon, x, det_name, self._decay_peak(res.total_decay))

            # 3. Residuals - stack each detector horizontally
            self.plot_residuals.clear()
            for det_idx, dr in enumerate(detector_results):
                res = dr['result']
                det_name = dr['detector']
                x = np.arange(res.n_bins) + (det_idx * offset)
                
                self.plot_residuals.plot(x, self._mask_to_fit_range(res.weighted_residuals, det_name), pen=self._stable_plot_color(det_name), connect="finite",
                                        name=f"{det_name}")
                # Reference lines for this detector
                for val in [-3, 0, 3]:
                    pen = pg.mkPen('r' if val != 0 else 'w', style=QtCore.Qt.DashLine)
                    self.plot_residuals.plot(x, np.full(res.n_bins, val), pen=pen)
            return
        
        # Handle Anisotropy mode - stack decays horizontally
        if self._result_anisotropy:
            res = self._result_anisotropy
            x = np.arange(res.n_bins)
            
            # Offset for horizontal stacking
            offset = res.n_bins * 1.1  # 10% gap between channels

            # 1. Filters - stack parallel and perpendicular horizontally
            self.plot_filters.clear()
            for i in range(res.n_filters):
                filter_label = self._filter_label(res, i)
                # Parallel filters (left side)
                self.plot_filters.plot(x, res.filters_par[i], pen=self._filter_color(res, i),
                                      name=f"{filter_label} (||)")
                # Perpendicular filters (right side, offset)
                self.plot_filters.plot(x + offset, res.filters_perp[i], pen=self._filter_color(res, i),
                                      name=f"{filter_label} (⊥)")
            # Zero lines for both channels
            self.plot_filters.plot(x, np.zeros_like(x), pen=pg.mkPen('w', style=QtCore.Qt.DashLine))
            self.plot_filters.plot(x + offset, np.zeros_like(x), pen=pg.mkPen('w', style=QtCore.Qt.DashLine))

            # 2. Reconstruction - stack horizontally
            self._clear_recon_plot()
            # Parallel (left)
            self.plot_recon.plot(x, res.total_decay_par, pen='w', name="Total (||)")
            self.plot_recon.plot(x, res.reconstruction_par, pen='r', name="Recon (||)")
            # Perpendicular (right)
            self.plot_recon.plot(x + offset, res.total_decay_perp, pen='w', name="Total (⊥)")
            self.plot_recon.plot(x + offset, res.reconstruction_perp, pen='r', name="Recon (⊥)")

            # 3. Residuals - stack horizontally
            self.plot_residuals.clear()
            # Parallel (left)
            self.plot_residuals.plot(x, self._mask_to_fit_range(res.weighted_residuals_par), pen='g', connect="finite", name="Residuals (||)")
            # Perpendicular (right)
            self.plot_residuals.plot(x + offset, self._mask_to_fit_range(res.weighted_residuals_perp), pen='y', connect="finite", name="Residuals (⊥)")
            # Reference lines for both channels
            for val in [-3, 0, 3]:
                pen = pg.mkPen('r' if val != 0 else 'w', style=QtCore.Qt.DashLine)
                self.plot_residuals.plot(x, np.full_like(x, val), pen=pen)
                self.plot_residuals.plot(x + offset, np.full_like(x, val), pen=pen)
            return
        
        # Standard single-channel mode
        if not self._result:
            return

        res = self._result
        x = np.arange(res.n_bins)

        # 1. Filters
        self.plot_filters.clear()
        for i in range(res.n_filters):
            pen, name = self._filter_pen_name(res, i)
            self.plot_filters.plot(x, res.filters[i], pen=pen, name=name)
        self.plot_filters.plot(x, np.zeros_like(x), pen=pg.mkPen('w', style=QtCore.Qt.DashLine))

        # 2. Reconstruction
        self._clear_recon_plot()
        self.plot_recon.plot(x, res.total_decay, pen='w', name="Total")
        self.plot_recon.plot(x, res.reconstruction, pen='r', name="Recon", style=QtCore.Qt.DashLine)
        # Overlay the IRF/scatter pattern (single detector → one stored entry).
        peak = self._decay_peak(res.total_decay)
        for det_name in list(self._irf_by_detector.keys()):
            self._plot_irf_overlay(self.plot_recon, x, det_name, peak)

        # 3. Residuals
        self.plot_residuals.clear()
        self.plot_residuals.plot(x, self._mask_to_fit_range(res.weighted_residuals), pen='g', connect="finite")
        for val in [-3, 0, 3]:
            self.plot_residuals.plot(x, np.full_like(x, val), pen=pg.mkPen('r' if val != 0 else 'w', style=QtCore.Qt.DashLine))

    def _on_export(self) -> None:
        if not self._result and not self._result_anisotropy and not self._result_multi_detector and not self._result_multi_anisotropy:
            return
        
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export Filters", "fcs_filters.json", "JSON (*.json)")
        if path:
            if self._result_multi_anisotropy:
                # Export multi-anisotropy results
                import json
                export_data = {
                    'mode': 'multi_anisotropy',
                    'detectors': [
                        {
                            'detector': ar['detector'],
                            'result': ar['result'].to_dict()
                        }
                        for ar in self._result_multi_anisotropy
                    ]
                }
                with open(path, 'w') as f:
                    json.dump(export_data, f, indent=2)
            elif self._result_anisotropy:
                self._result_anisotropy.to_json(path)
            elif self._result_multi_detector:
                # Export multi-detector results as a list
                import json
                export_data = {
                    'mode': 'multi_detector',
                    'detectors': [
                        {
                            'detector': dr['detector'],
                            'result': dr['result'].to_dict()
                        }
                        for dr in self._result_multi_detector
                    ]
                }
                with open(path, 'w') as f:
                    json.dump(export_data, f, indent=2)
            else:
                self._result.to_json(path)
            self._update_status(f"Exported to {pathlib.Path(path).name}")
