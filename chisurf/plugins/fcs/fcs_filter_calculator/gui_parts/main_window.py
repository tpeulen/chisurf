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
from .synthetic_editor import SyntheticSpectrumViewModel
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
        self.le_total = QtWidgets.QLineEdit()
        self.le_total.setReadOnly(True)
        self.le_total.setPlaceholderText("Drop file here...")
        self.le_total.setToolTip("Path to the total decay histogram")
        total_vbox.addWidget(self.le_total)
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

        add_action = self.toolbar.addAction("➕ Add")
        add_action.setToolTip(
            "Add a measured decay pattern, synthetic lifetime spectrum, or spectrum from an open fit."
        )
        self.btn_add_component = self.toolbar.widgetForAction(add_action)
        add_menu = QtWidgets.QMenu(self.btn_add_component)
        add_menu.setToolTipsVisible(True)
        self.action_add_species = add_menu.addAction("📈 Measured pattern…")
        self.action_add_synthetic = add_menu.addAction("🧬 Synthetic / fit…")
        self.action_add_species.setToolTip(
            "Load one or more measured component decay histograms from files."
        )
        self.action_add_synthetic.setToolTip(
            "Define a synthetic lifetime spectrum or copy a spectrum and detector model from an open fit."
        )
        self.action_add_species.triggered.connect(self._add_species_dialog)
        self.action_add_synthetic.triggered.connect(self._add_synthetic_dialog)
        add_action.triggered.connect(self._add_synthetic_dialog)
        self.btn_add_component.setMenu(add_menu)
        self.btn_add_component.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        self.btn_add_species = self.btn_add_component
        self.btn_add_synthetic = self.btn_add_component

        remove_action = self.toolbar.addAction("➖ Remove")
        remove_action.setToolTip("Remove the selected component decay patterns.")
        remove_action.triggered.connect(self._remove_selected_species)
        self.btn_remove_species = self.toolbar.widgetForAction(remove_action)

        self.toolbar.addSeparator()
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
        for index in range(self.lw_species.count()):
            source = self.lw_species.item(index).data(QtCore.Qt.UserRole)
            if isinstance(source, dict) and source.get("bin_width"):
                return float(source["bin_width"])
        return 0.05

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

    def _add_synthetic_dialog(self) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Add Synthetic Decay Component")
        dialog.resize(620, 520)
        layout = QtWidgets.QVBoxLayout(dialog)

        def choose_fit():
            fits = list(getattr(cs, "fits", []) or [])
            current = getattr(getattr(cs, "cs", None), "current_fit", None)
            if current is None:
                current = getattr(cs, "current_fit", None)
            if current is not None and all(current is not fit for fit in fits):
                fits.append(current)
            if not fits:
                QtWidgets.QMessageBox.information(dialog, "No Fits", "No ChiSurf fits are open.")
                return None
            labels = [str(getattr(fit, "name", None) or fit) for fit in fits]
            default = fits.index(current) if current in fits else 0
            label, accepted = QtWidgets.QInputDialog.getItem(
                dialog, "Read Lifetime Spectrum", "Fit:", labels, default, False
            )
            if not accepted:
                return None
            fit = fits[labels.index(label)]
            model = getattr(getattr(fit, "selected_fit", fit), "model", None)
            try:
                spectrum = lifetime_spectrum_from_model(model)
            except Exception as error:
                QtWidgets.QMessageBox.warning(dialog, "Unsupported Fit", str(error))
                return None
            return spectrum, label, fit

        from chisurf.gui.autoform import AutoForm

        editor_model = SyntheticSpectrumViewModel(read_fit=choose_fit)
        editor = AutoForm(editor_model, dialog)
        editor_model.set_changed_callback(editor.refresh_plots)
        layout.addWidget(editor, 1)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return

        try:
            spectrum = editor_model.lifetime_spectrum
            irf = pathlib.Path(editor_model.irf_path) if editor_model.irf_path.strip() else None
            if irf is not None and not irf.is_file():
                raise ValueError("The selected IRF file does not exist.")
        except ValueError as error:
            QtWidgets.QMessageBox.warning(self, "Invalid Synthetic Decay", str(error))
            return

        source = {
            "type": "synthetic",
            "model": "lifetime_spectrum",
            "name": editor_model.name.strip() or "component",
            "amplitudes": spectrum[0::2].tolist(),
            "lifetimes": spectrum[1::2].tolist(),
            "bin_width": editor_model.bin_width,
            "start_bin": editor_model.start_bin,
            "irf_path": str(irf.absolute()) if irf else None,
            "shot_noise": bool(editor_model.shot_noise),
            "photon_count": int(editor_model.photon_count),
            "noise_seed": int(editor_model.noise_seed),
        }
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
