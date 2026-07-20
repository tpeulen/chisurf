from __future__ import annotations

import pathlib
import hashlib
from typing import List, Dict

import numpy as np
from qtpy import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

import chisurf as cs
from chisurf.core.fluorescence.decay import (
    afterpulse_decay_pattern,
    compute_detector_patterns_from_fit,
    lifetime_spectrum_from_model,
    optimize_synthetic_scatter_pattern,
    sample_decay_shot_noise,
    scattered_light_decay_pattern,
)
from chisurf.gui.widgets.dock_area import DockArea
from ..api import compute_filters, synthetic_component_decay, unmix_decay, FilterResult


def _build_filter_client():
    from ..gui.client import FilterCalcClient
    return FilterCalcClient()
from .widgets import SpeciesListWidget
from .calculator_options import CalculatorOptionsViewModel
from .data_loading import load_vector

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:
    persist_plugin_state = lambda n: lambda c: c

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
        #: Persistent auto-fit settings (shown/edited in the Auto-fit dialog).
        self._auto_fit_settings: dict = {
            "kind": "lifetime", "n_components": 2, "tau_min": 0.2, "tau_max": 8.0,
        }
        self._result: FilterResult | None = None
        self._result_anisotropy = None  # For single-detector Anisotropy results
        self._result_multi_anisotropy = None  # For multi-detector Anisotropy results (list)
        self._result_multi_detector = None  # For multi-detector stacked results
        self._unmix_result = None
        # IRF / scatter pattern used per detector in the last computation, kept so
        # the reconstruction/decay plot can overlay the instrument response.
        self._irf_by_detector: dict[str, np.ndarray] = {}
        
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
        self.btn_load_total.setText("📂 Load…")
        self.btn_load_total.setToolTip("Open a measured mixed decay histogram to replace the built-in example.")
        self.btn_load_total.clicked.connect(self._add_total_dialog)
        total_row.addWidget(self.btn_load_total)
        self.btn_total_from_correlator = QtWidgets.QToolButton()
        self.btn_total_from_correlator.setText("📡 From correlator")
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
        self.plot_recon.addItem(self._fit_region)
        self.plot_residuals = pg.PlotWidget(title="Weighted Residuals")
        self.plot_residuals.setLabel("bottom", "TAC bin")
        self.plot_residuals.setLabel("left", "Residuals (σ)")
        self._build_docks(sidebar)

        # Set up drag and drop for the whole widget
        self.setAcceptDrops(True)

    def _build_toolbar(self) -> None:
        self.action_load_total = self.toolbar.addAction("📂 Mixed…")
        self.action_load_total.setToolTip(
            "Open a measured mixed decay histogram to replace the built-in example."
        )
        self.action_load_total.triggered.connect(self._add_total_dialog)

        # Add / Edit / Remove all live on the Components list context menu
        # (right-click) and double-click-to-edit — not toolbar buttons.

        self.toolbar.addSeparator()
        autofit_action = self.toolbar.addAction("🎯 Auto-fit")
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

        project_action = self.toolbar.addAction("💾 Project")
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

    def _build_docks(self, sources_panel) -> None:
        self.dock_area.addTab(sources_panel, "Decay sources")
        sources_dock = self.dock_area.find_main_tab_widget()
        detector_dock = self._register_split_dock(
            self.setup_tab, "Setup", sources_dock, "bottom"
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
                scatter = scattered_light_decay_pattern(load_vector(irf_path), n_bins)
                source = "measured"
            else:
                scatter, fit = optimize_synthetic_scatter_pattern(
                    total,
                    component_decays or [],
                    bin_width_ns=self._pattern_bin_width_ns(),
                    initial_fwhm_ns=self.detector_selection.width(detector, role),
                    shape=self.detector_selection.skew(detector, role),
                    include_constant=self.fit_background_cb.isChecked(),
                )
                key = f"{detector}:{role}" if role else detector
                if not hasattr(self, "_synthetic_scatter_fits"):
                    self._synthetic_scatter_fits = {}
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

    def _set_total_paths(self, paths: List[pathlib.Path]) -> None:
        self._total_paths = paths
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
        self._set_total_paths(paths)
        self._update_status(f"Mixed decay from correlator ({len(paths)} file(s)).")

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        # On first show, if the user hasn't loaded a measured total, adopt the
        # Correlator's already-loaded files as the mixed decay automatically.
        if not getattr(self, "_correlator_autoload_done", False):
            self._correlator_autoload_done = True
            if not self._total_paths and self._correlator_file_paths():
                self._use_correlator_total()

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
            "lifetime": 1.2, "bin_width": bin_width,
            "patterns_by_detector": fast_patterns,
        })
        self.lw_species.add_synthetic_source({
            "type": "synthetic", "model": "lifetime", "name": "Slow example",
            "lifetime": 4.0, "bin_width": bin_width,
            "patterns_by_detector": slow_patterns,
        })
        self._compute_filters()

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

    def _detector_irf(self, detector_name: str, role: str = ""):
        """Return a detector's IRF (measured file or synthetic Gaussian) for FRET decays."""
        import numpy as np

        from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

        n_bins = int(self._total_vector.size) if self._total_vector is not None else 256
        dt = float(self._pattern_bin_width_ns())
        configured = self.detector_selection.irf_path(detector_name, role)
        if configured and pathlib.Path(configured).is_file():
            return load_vector(pathlib.Path(configured))
        fwhm = float(self.detector_selection.width(detector_name, role) or 0.0)
        if fwhm <= 0.0:
            return None
        time = np.arange(n_bins, dtype=float) * dt
        return synthetic_irf(time, 2.0 * fwhm, fwhm,
                             shape=float(self.detector_selection.skew(detector_name, role) or 0.0))

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
        n_bins = int(self._total_vector.size) if self._total_vector is not None else 256
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
        finally:
            self._syncing_range = False

    def _on_region_changed(self) -> None:
        lo, hi = self._fit_region.getRegion()
        self._set_fit_range(int(round(min(lo, hi))), int(round(max(lo, hi))), source="region")

    def _on_range_spin_changed(self) -> None:
        self._fit_region_initialized = True
        self._set_fit_range(self.sb_fit_start.value(), self.sb_fit_stop.value(), source="spin")

    def _fit_range(self, n_bins: int) -> tuple[int, int]:
        """The selected fit/filter range (TAC bins), clamped to ``[0, n_bins]``."""
        lo, hi = self._fit_region.getRegion()
        start = max(0, int(round(min(lo, hi))))
        stop = min(int(n_bins), int(round(max(lo, hi))))
        if stop - start < 4:
            return 0, int(n_bins)
        return start, stop

    def _show_auto_fit_settings_dialog(self) -> bool:
        """Editable auto-fit settings (type, N, lifetime range). Returns True on OK."""
        s = self._auto_fit_settings
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Auto-fit settings")
        form = QtWidgets.QFormLayout(dialog)

        cb_kind = QtWidgets.QComboBox()
        cb_kind.addItem("Lifetime species", "lifetime")
        cb_kind.addItem("FRET species", "fret")
        cb_kind.setCurrentIndex(1 if s["kind"] == "fret" else 0)
        cb_kind.setToolTip("Fit N lifetime species, or N FRET states (E from the "
                           "relative donor quenching).")
        form.addRow("Type:", cb_kind)

        sb_n = QtWidgets.QSpinBox()
        sb_n.setRange(1, 12)
        sb_n.setValue(int(s["n_components"]))
        sb_n.setToolTip("Number of lifetime components / FRET states to resolve.")
        form.addRow("Components / states:", sb_n)

        sb_tmin = QtWidgets.QDoubleSpinBox()
        sb_tmin.setRange(0.01, 1000.0)
        sb_tmin.setDecimals(3)
        sb_tmin.setValue(float(s["tau_min"]))
        sb_tmax = QtWidgets.QDoubleSpinBox()
        sb_tmax.setRange(0.02, 1000.0)
        sb_tmax.setDecimals(3)
        sb_tmax.setValue(float(s["tau_max"]))
        form.addRow("Lifetime min (ns):", sb_tmin)
        form.addRow("Lifetime max (ns):", sb_tmax)

        start, stop = self._fit_range(
            int(self._total_vector.size) if self._total_vector is not None else 256
        )
        form.addRow(QtWidgets.QLabel(
            f"Fit range: {start}–{stop} TAC bins (drag the region on the decay plot "
            "or edit the Fit range spinboxes)."
        ))

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Fit")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return False
        self._auto_fit_settings = {
            "kind": cb_kind.currentData(),
            "n_components": int(sb_n.value()),
            "tau_min": float(sb_tmin.value()),
            "tau_max": float(max(sb_tmax.value(), sb_tmin.value() + 0.01)),
        }
        return True

    def _auto_fit_components(self, n_components: int | None = None) -> None:
        """Auto-fit the mixed decay (over the selected fit range) to N lifetime
        components; add them as species.

        A **tail fit** over the draggable fit range on the reconstruction plot: the
        window is fitted as a discrete multi-exponential
        (:func:`chisurf.core.fluorescence.decay_fit.fit_lifetime_components`, no IRF
        — the range starts past the prompt) and one synthetic species per resolved
        lifetime is appended, its per-detector pattern aligned to the range start.
        """
        from chisurf.core.fluorescence.decay import synthetic_decay
        from chisurf.core.fluorescence.decay_fit import fit_lifetime_components

        if not self._has_total_decay():
            QtWidgets.QMessageBox.warning(
                self, "Missing Total Decay", "Load a mixed total decay first."
            )
            return
        settings = self._auto_fit_settings
        kind = settings["kind"]
        if n_components is None:
            if not self._show_auto_fit_settings_dialog():
                return
            settings = self._auto_fit_settings
            kind = settings["kind"]
            n_components = int(settings["n_components"])

        chs = self.detector_selection.get_selected() if self.detector_selection.checkboxes else None
        total = np.asarray(self._total_decay(chs[:1] if chs else None), dtype=float).ravel()
        dt = self._pattern_bin_width_ns()
        n_bins = int(total.size)
        self._init_fit_region(total)
        start, stop = self._fit_range(n_bins)

        try:
            result = fit_lifetime_components(
                total[start:stop], bin_width=dt, n_components=int(n_components), irf=None,
                tau_bounds=(float(settings["tau_min"]), float(settings["tau_max"])),
            )
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Auto-fit Error", str(error))
            return

        amps = result["amplitudes"]
        taus = result["lifetimes"]
        scale = float(amps.sum()) or 1.0
        detector_names = list(chs or [])
        # Add all species without recomputing per add; compute once at the end.
        self._suspend_compute = True
        try:
            self._add_autofit_species(kind, amps, taus, scale, dt, start, n_bins, detector_names)
        finally:
            self._suspend_compute = False
        self._on_data_changed()
        parts = ", ".join(
            f"{float(a) / scale:.0%}·{float(t):.2f}ns" for a, t in zip(amps, taus)
        )
        label = "FRET states" if kind == "fret" else "components"
        self._update_status(
            f"Auto-fit [{start}–{stop}]: {len(taus)} {label} "
            f"(χ²ᵣ={result['chi2_reduced']:.3g}) — {parts}."
        )

    def _add_autofit_species(self, kind, amps, taus, scale, dt, start, n_bins, detector_names):
        from chisurf.core.fluorescence.decay import synthetic_decay

        if kind == "fret":
            self._add_fret_autofit_species(amps, taus, scale, dt, start, n_bins, detector_names)
        else:
            for amp, tau in zip(amps, taus):
                source = {
                    "type": "synthetic", "model": "lifetime_spectrum",
                    "name": f"τ={float(tau):.2f} ns",
                    "amplitudes": [float(amp) / scale], "lifetimes": [float(tau)],
                    "bin_width": float(dt), "start_bin": int(start), "irf_path": None,
                }
                # Align each component's decay to the fit-range start so its tail
                # lines up with the measured decay (pre-range/prompt is nuisance).
                patterns = {
                    name: synthetic_decay(n_bins, [float(tau)], bin_width=float(dt),
                                          start_bin=int(start), normalize=True).tolist()
                    for name in detector_names
                }
                if patterns:
                    patterns["__default__"] = patterns[detector_names[0]]
                    source["patterns_by_detector"] = patterns
                self.lw_species.add_synthetic_source(source)

    def _add_fret_autofit_species(self, amps, taus, scale, dt, start, n_bins, detector_names):
        """Turn fitted donor lifetimes into FRET species.

        The longest fitted (green/donor) lifetime is taken as the unquenched donor
        τ_D0; each fitted lifetime τᵢ becomes a FRET species with transfer
        efficiency Eᵢ = 1 − τᵢ/τ_D0 (τ_D0 itself → a donor-only species). Each
        species is expanded to per-detector coupled decays and added — a starting
        FRET set the user refines in the editor.
        """
        from chisurf.core.fluorescence.fret.species_decay import fret_species_detector_patterns

        tau_d0 = float(max(taus)) if len(taus) else 1.0
        dets = detector_names or ["green", "red", "yellow"]
        for amp, tau in zip(amps, taus):
            efficiency = float(np.clip(1.0 - float(tau) / tau_d0, 0.0, 0.999))
            state = "d_only" if efficiency < 1e-3 else "da"
            source = {
                "type": "synthetic", "model": "fret_species",
                "name": (f"donor-only τ={tau_d0:.2f}" if state == "d_only"
                         else f"DA E={efficiency:.2f}"),
                "state": state,
                "donor_spectrum": [1.0, tau_d0],
                "acceptor_spectrum": [1.0, 2.0],
                "fret_mode": "efficiency", "transfer_efficiency": efficiency,
                "bin_width": float(dt),
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
        act_add = menu.addAction("➕ Add component…")
        act_add.setToolTip("Add a synthetic decay component (plain lifetime spectrum or FRET species).")
        act_add.triggered.connect(lambda: self._add_component_dialog())
        act_add_file = menu.addAction("📈 Add measured pattern…")
        act_add_file.triggered.connect(self._add_species_dialog)
        act_edit = menu.addAction("✏️ Edit…")
        act_edit.setEnabled(self._is_editable_component(item))
        act_edit.triggered.connect(lambda: self._edit_component_item(item))
        menu.addSeparator()
        act_remove = menu.addAction("➖ Remove")
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
            self._result = self._compute_filters_rpc(
                total_data,
                species_data,
                total_path=(
                    [str(p.absolute()) for p in self._total_paths]
                    if self._total_paths else ["synthetic:example-mixture"]
                ),
                species_patterns=species_patterns,
                nuisance_decays=nuisance_decays,
                nuisance_labels=nuisance_labels,
                reject_nuisance=True,
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
                
                # Compute filters for this detector
                nuisance, nuisance_labels = self._nuisance_patterns(
                    total_data, species_data, det_name
                )
                result = compute_filters(
                    total_data,
                    species_data,
                    total_path=[str(p.absolute()) for p in self._total_paths],
                    species_patterns=species_patterns,
                    nuisance_decays=nuisance,
                    nuisance_labels=nuisance_labels,
                    reject_nuisance=True,
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
        # Seed the draggable fit/filter range from the first available total decay.
        for candidate in (
            getattr(self._result, "total_decay", None) if self._result else None,
            (self._result_multi_detector[0]["result"].total_decay
             if self._result_multi_detector else None),
            self._total_vector,
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
            self.plot_recon.clear()
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
                self.plot_residuals.plot(x + base_x, res.weighted_residuals_par, pen=detector_color,
                                        name=f"{det_name} (||)")
                # Perpendicular
                self.plot_residuals.plot(x + base_x + offset, res.weighted_residuals_perp, pen=detector_color,
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
            self.plot_recon.clear()
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
                
                self.plot_residuals.plot(x, res.weighted_residuals, pen=self._stable_plot_color(det_name),
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
            self.plot_recon.clear()
            # Parallel (left)
            self.plot_recon.plot(x, res.total_decay_par, pen='w', name="Total (||)")
            self.plot_recon.plot(x, res.reconstruction_par, pen='r', name="Recon (||)")
            # Perpendicular (right)
            self.plot_recon.plot(x + offset, res.total_decay_perp, pen='w', name="Total (⊥)")
            self.plot_recon.plot(x + offset, res.reconstruction_perp, pen='r', name="Recon (⊥)")

            # 3. Residuals - stack horizontally
            self.plot_residuals.clear()
            # Parallel (left)
            self.plot_residuals.plot(x, res.weighted_residuals_par, pen='g', name="Residuals (||)")
            # Perpendicular (right)
            self.plot_residuals.plot(x + offset, res.weighted_residuals_perp, pen='y', name="Residuals (⊥)")
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
        self.plot_recon.clear()
        self.plot_recon.plot(x, res.total_decay, pen='w', name="Total")
        self.plot_recon.plot(x, res.reconstruction, pen='r', name="Recon", style=QtCore.Qt.DashLine)
        # Overlay the IRF/scatter pattern (single detector → one stored entry).
        peak = self._decay_peak(res.total_decay)
        for det_name in list(self._irf_by_detector.keys()):
            self._plot_irf_overlay(self.plot_recon, x, det_name, peak)

        # 3. Residuals
        self.plot_residuals.clear()
        self.plot_residuals.plot(x, res.weighted_residuals, pen='g')
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
