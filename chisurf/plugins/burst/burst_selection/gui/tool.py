"""Migrated PyQt Burst Selection GUI backed by the new API."""

from __future__ import annotations

import hashlib
import logging as _logging
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from chisurf.core.datastore import (
    column_names,
    concat_stores,
    new_store,
    numeric_column,
    row_count,
    rows_from_table,
    store_from_rows,
    take_columns,
    write_csv_table,
)
import pyqtgraph as pg
from qtpy import QtCore, QtGui, QtWidgets

from chisurf.core import analysis_cache
from chisurf.core.fio.decimate import per_curve_budget, thin_for_plot
from chisurf.core.fio.mmcif.pdbx_metadata import get_pdbx_metadata_keys
from mmfdb.security.base import MMFDBClientBase
from chisurf.gui.widgets.dock_area.dock_area import DockArea
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.widgets.messages import Msg
from chisurf.gui.widgets.sample_picker import show_sample_picker_dialog
from chisurf.gui.widgets.tool_buttons import action_button, flag_attention
from chisurf.gui.widgets.tools import ChisurfDockTool
from chisurf.gui.widgets.tools import PathDropListWidget as DropListWidget
from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_channel_definition import (
    DetectorWizardPage,
)
from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups import (
    load_detector_setups,
    setup_id_for_name,
)
from chisurf.gui.widgets.wizard.tttr_photonfilter.tttr_photon_filter import WizardTTTRPhotonFilter
from chisurf.server.rpc_logging import RpcLogWriter

from ..api.mmfdb import (
    acquire_mmfdb_connection as _acquire_mmfdb_connection,
)
from ..api.mmfdb import (
    file_md5 as _file_md5,
)
from ..api.mmfdb import (
    raw_artifact_id_for_path as _raw_artifact_id_for_path,
)
from ..api.mmfdb import (
    raw_file_data_format as _raw_file_data_format,
)
from ..api.mmfdb import (
    register_raw_input_for_sample as _register_raw_input_for_sample,
)
from ..api.mmfdb import (
    sample_id_for_raw_path as _sample_id_for_raw_path,
)
from ..api.models import (
    AnalysisSettings,
    BurstDetectionSettings,
    BurstFilterMode,
    CountRateFilterSettings,
    DeltaMacroTimeFilterSettings,
    PhotonFilterSettings,
)
from .adapter import (
    PROXIMITY_RATIO_COLUMN,
    UI_COLUMNS,
    burst_rows_for_display,
    make_ui_dataframe,
    proximity_ratio_from_frame,
)
from .client import BurstSelectionClient
from chisurf.core.fio.staging import TTTR_EXTENSIONS, TTTR_FILE_FILTER
from .gmm_settings_dialog import DEFAULT_GMM_SETTINGS, GMMSettingsDialog

# Curated common keys shown first; then all PDBx keys are appended.
COMMON_METADATA_KEYS = [
    "pH", "temperature", "ionic_strength", "buffer_composition",
    "solvent_phase", "labeling_efficiency", "donor_only_fraction",
    "acceptor_only_fraction", "dye_ratio", "quencher_concentration",
    "time_resolution", "excitation_wavelength", "emission_wavelength",
    "power", "temperature_control", "data_notes",
]

# Build the full key list once
try:
    _PDBX_KEYS = get_pdbx_metadata_keys()
except Exception:
    _PDBX_KEYS = []
ALL_METADATA_KEYS = COMMON_METADATA_KEYS + [k for k in _PDBX_KEYS if k not in COMMON_METADATA_KEYS]

_LOG = RpcLogWriter("chisurf.plugins.burst.burst_selection")

#: Bump in the same change that alters what this tool computes, so results
#: written by the previous version stop reading as current.
ALGORITHM_VERSION = 1

DEFAULT_CHANNELS = [0, 1, 8, 9]
DEFAULT_MIN_PHOTONS = 60
DEFAULT_PHOTON_WINDOW = 5
DEFAULT_TIME_WINDOW_MS = 1.0
DEFAULT_D_T_MIN = 0.0001
DEFAULT_D_T_MAX = 0.15
DEFAULT_MAX_GAP = 3
DEFAULT_HISTOGRAM_BINS = 61
DEFAULT_TRACE_BIN_WIDTH_MS = 0.25
DEFAULT_DECAY_BINS = 8
DEFAULT_BURST_BINS = 51
DEFAULT_PLOT_MAX = 100000
HISTOGRAM_FEATURES = [*UI_COLUMNS, PROXIMITY_RATIO_COLUMN]

#: Pen width for the "selected photons" layer of a raw per-photon diagnostic.
#:
#: One, not two, and the reason is measured rather than aesthetic. A Qt pen
#: wider than a pixel is not cosmetic — it strokes a real outline around the
#: polyline — and on the same 66k-point curve that costs **3–5x** the paint
#: time of a hairline (0.064 s vs 0.013 s undownsampled, 0.025 s vs 0.008 s
#: with the viewport decimation on). Three such curves in a panel is the
#: difference between a window that redraws in 30 ms and one that takes a third
#: of a second per repaint. The layer is already distinguished by colour (cyan
#: against yellow/orange), so the extra pixel bought nothing that was not
#: already there.
_SELECTED_PEN_WIDTH = 1


def _normalize_filetype(filetype: str | None) -> str | None:
    """Normalize the detector setup file type for ``tttrlib``."""
    if not filetype or str(filetype).strip().lower() == "auto":
        return None
    return str(filetype).strip()


def _setup_summary(setup_name: str | None, filetype: str | None) -> str:
    """Return a compact detector setup summary for the status text."""
    if not setup_name:
        return "Detector setup: custom/default"
    if filetype:
        return f"Detector setup: {setup_name} (file type: {filetype})"
    return f"Detector setup: {setup_name} (file type: auto)"


def default_analysis_settings() -> AnalysisSettings:
    """Return default analysis settings matching the legacy Burst Selection GUI."""
    return AnalysisSettings(
        photon_filter=PhotonFilterSettings(
            channels=DEFAULT_CHANNELS,
            filter_active=True,
            used_filter=BurstFilterMode.BURST,
            count_rate_filter=CountRateFilterSettings(
                n_ph_max=DEFAULT_MIN_PHOTONS,
                time_window=DEFAULT_TIME_WINDOW_MS / 1000.0,
                invert=True,
            ),
            delta_macro_time_filter=DeltaMacroTimeFilterSettings(
                dT_min=DEFAULT_D_T_MIN,
                dT_max=DEFAULT_D_T_MAX,
                dT_min_active=False,
                dT_max_active=True,
            ),
            invert_filter=True,
            max_gap=DEFAULT_MAX_GAP,
            use_gap_fill=False,
        ),
        burst_detection=BurstDetectionSettings(
            min_photons=DEFAULT_MIN_PHOTONS,
            photon_window=DEFAULT_PHOTON_WINDOW,
            time_window=DEFAULT_TIME_WINDOW_MS / 1000.0,
        ),
    )


def histogram_data_from_frame(frame, feature: str) -> np.ndarray:
    """Return numeric histogram data excluding Margarita zero separator rows."""
    if feature == PROXIMITY_RATIO_COLUMN:
        data = proximity_ratio_from_frame(burst_rows_for_display(frame))
        if data is not None:
            return data[np.isfinite(data)]
    data = numeric_column(burst_rows_for_display(frame), feature)
    return data[np.isfinite(data)]


class MetadataDialog(QtWidgets.QDialog):
    """Dialog for adding/editing metadata for burst analysis."""

    def __init__(self, metadata: dict[str, str] | None = None, parent: QtWidgets.QWidget = None) -> None:
        """Initialize the metadata dialog."""
        super().__init__(parent)
        self.setWindowTitle("Burst Analysis Metadata")
        self.resize(600, 400)
        layout = QtWidgets.QVBoxLayout(self)

        self.metadata_table = QtWidgets.QTableWidget(0, 2)
        self.metadata_table.setHorizontalHeaderLabels(["Key", "Value"])
        self.metadata_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.metadata_table)

        buttons = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("➕ Add metadata")
        add_btn.clicked.connect(self._add_metadata_row)
        delete_btn = QtWidgets.QPushButton("🗑️ Delete selected")
        delete_btn.clicked.connect(self._delete_metadata_row)
        buttons.addWidget(add_btn)
        buttons.addWidget(delete_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        dialog_buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        dialog_buttons.accepted.connect(self.accept)
        dialog_buttons.rejected.connect(self.reject)
        layout.addWidget(dialog_buttons)

        if metadata:
            for key, value in sorted(metadata.items()):
                self._add_metadata_row(str(key), str(value))

    def _add_metadata_row(self, key: str = "", value: str = "") -> None:
        """Add a metadata row to the table."""
        row = self.metadata_table.rowCount()
        self.metadata_table.insertRow(row)
        combo = QtWidgets.QComboBox()
        combo.setEditable(True)
        combo.addItems(ALL_METADATA_KEYS)
        if key:
            combo.setCurrentText(key)
        else:
            combo.setCurrentIndex(-1)
        comp = combo.completer()
        if comp is not None:
            comp.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
            comp.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self.metadata_table.setCellWidget(row, 0, combo)
        self.metadata_table.setItem(row, 1, QtWidgets.QTableWidgetItem(value))

    def _delete_metadata_row(self) -> None:
        """Delete the selected metadata row."""
        row = self.metadata_table.currentRow()
        if row >= 0:
            self.metadata_table.removeRow(row)

    def get_metadata(self) -> dict[str, str]:
        """Return the metadata from the table."""
        metadata = {}
        for row in range(self.metadata_table.rowCount()):
            widget = self.metadata_table.cellWidget(row, 0)
            if isinstance(widget, QtWidgets.QComboBox):
                key = widget.currentText().strip()
            else:
                key_item = self.metadata_table.item(row, 0)
                key = key_item.text().strip() if key_item is not None else ""
            value_item = self.metadata_table.item(row, 1)
            value = value_item.text().strip() if value_item is not None else ""
            if key:
                metadata[key] = value
        return metadata


class BatchProcessingDialog(QtWidgets.QDialog):
    """Dialog for adding folders containing TTTR files."""

    #: Straight from the reader's own list, so a folder of `.pto`
    #: containers is not silently empty here while the file dialog beside
    #: it offers `.pto` first.
    allowed_extensions = set(TTTR_EXTENSIONS)

    def __init__(self, parent: BurstSelectionTool) -> None:
        """Initialize the batch folder dialog."""
        super().__init__(parent)
        self.setWindowTitle("Batch Burst Analysis")
        self.resize(700, 500)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(
            QtWidgets.QLabel(
                "Drop folders here. Folders containing TTTR files will be added.\n"
                "Folders without TTTR files will be scanned recursively.",
                self,
            )
        )
        self.list_widget = DropListWidget(self)
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.pathsDropped.connect(self._add_folders_from_paths)
        layout.addWidget(self.list_widget, 1)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.delete_button = QtWidgets.QPushButton("🗑️ Delete Selected", self)
        self.clear_button = QtWidgets.QPushButton("🧹 Clear All", self)
        self.add_button = QtWidgets.QPushButton("➕ Add", self)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.clear_button)
        buttons.addWidget(self.add_button)
        layout.addLayout(buttons)
        self.delete_button.clicked.connect(self._delete_selected)
        self.clear_button.clicked.connect(self.list_widget.clear)
        self.add_button.clicked.connect(self.accept)

    def _folder_has_tttr_files(self, folder: Path) -> list[str]:
        """Return TTTR files directly contained in a folder."""
        files: list[str] = []
        try:
            for child in folder.iterdir():
                if child.is_file() and child.suffix.lower() in self.allowed_extensions:
                    files.append(str(child.resolve()))
        except OSError as exc:
            _logging.getLogger(__name__).warning(f"{folder}\n{exc}")
        return files

    def _add_folder_unique(self, folder: Path) -> None:
        """Add a folder path once."""
        folder_text = str(folder.resolve())
        for index in range(self.list_widget.count()):
            if self.list_widget.item(index).text() == folder_text:
                return
        self.list_widget.addItem(folder_text)

    def _add_folders_from_paths(self, paths: list[Path]) -> None:
        """Add folders containing TTTR files."""
        for path in paths:
            if not path.is_dir():
                continue
            direct_files = self._folder_has_tttr_files(path)
            if direct_files:
                self._add_folder_unique(path)
                continue
            for subfolder in path.rglob("*"):
                if subfolder.is_dir() and self._folder_has_tttr_files(subfolder):
                    self._add_folder_unique(subfolder)

    def _delete_selected(self) -> None:
        """Delete selected folder entries."""
        for item in list(self.list_widget.selectedItems()):
            self.list_widget.takeItem(self.list_widget.row(item))

    def folders(self) -> list[Path]:
        """Return selected folders."""
        return [Path(item.text()) for item_index in range(self.list_widget.count()) for item in [self.list_widget.item(item_index)]]


class BurstSelectionTool(ChisurfDockTool):
    """Migrated Burst Selection GUI with legacy-style controls and plots."""

    class Error(ChisurfDockTool.Error):
        """Conditions a burst-selection run can end in."""

        analysis_failed = Msg("Burst selection failed: {}")

    tool_settings_name = "BurstSelectionTool"

    def __init__(
        self,
        *args: object,
        show_channel_selection: bool = True,
        show_clear_button: bool = False,
        show_decay_button: bool = False,
        show_filter_button: bool = False,
        show_mcs_plot: bool = True,
        show_decay_plot: bool = True,
        show_filter_plot: bool = False,
        show_burst_plot: bool = False,
        mmfdb_client: Any = None,
        **kwargs: object,
    ) -> None:
        """Initialize the migrated GUI and its API-backed controls."""
        assert isinstance(self, QtWidgets.QMainWindow), "BurstSelectionTool must be a QMainWindow"
        self.show_channel_selection = show_channel_selection
        self.show_clear_button = show_clear_button
        self.show_decay_button = show_decay_button
        self.show_filter_button = show_filter_button
        self.show_mcs_plot = show_mcs_plot
        self.show_decay_plot = show_decay_plot
        self.show_filter_plot = show_filter_plot
        self.show_burst_plot = show_burst_plot
        self._mmfdb_client = mmfdb_client
        super().__init__(*args, **kwargs)
        self.setWindowTitle("Burst Selection")
        self._mmfdb_db: MMFDBClientBase | None = None
        self._mmfdb_session: Any = None
        self._client = BurstSelectionClient(
            mmfdb_db_provider=self._db,
            mmfdb_session_provider=self.acquire_mmfdb_session,
        )
        self._file_paths: list[Path] = []
        self._last_result: dict[str, Any] | None = None
        self._last_bur_frames: list = []
        self._last_frames_by_file: dict = {}
        self._last_frame = None
        self._last_settings: AnalysisSettings | None = None
        self._last_tttr: Any | None = None
        self._last_selected: np.ndarray | None = None
        self._last_start_stop: np.ndarray | None = None
        self._last_diagnostic_path: Path | None = None
        self._last_diagnostics: list[dict[str, Any]] = []
        self._diagnostic_plot_features: dict[str, dict[str, Any]] = {}
        self._closed_diagnostic_plots: set[str] = set()
        self._selected_setup_name: str | None = None
        self._selected_filetype: str | None = None
        self._fit_gmm_on_update = False
        self.gmm_settings = dict(DEFAULT_GMM_SETTINGS)
        self._building_ui = True
        self._metadata: dict[str, str] = {}
        self._has_processed: bool = False
        # What the displayed burst search was run with, so an identical request
        # (another Next, a revisit of this step) is not searched again.
        self._result_cache = analysis_cache.ResultCache()
        self._running_fingerprint: str | None = None
        self._create_plot_widgets()
        self._setup_statusbar()
        self._build_ui()
        self._building_ui = False
        self._setup_menu()
        self._sync_output_format_controls()
        self._apply_visibility_toggles()
        self._connect_action_bar()
        self._configure_dock_context_menu()
        self._on_setup_changed(self.wizard.comboBox.currentText())
        self.dock_area.layoutChanged.connect(self._save_dock_layout)
        self._restore_dock_layout()
        self._restore_window_geometry()
        self.setAcceptDrops(True)

    def _build_ui(self) -> None:
        """Build the migrated GUI layout."""
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(self._build_action_bar(central))

        self.dock_area = DockArea(central)
        self._build_docks()
        layout.addWidget(self.dock_area, 1)

    def _build_action_bar(self, parent: QtWidgets.QWidget) -> QtWidgets.QLayout:
        """Create the top-level action bar (empty - controls moved to toolbar)."""
        action_bar = QtWidgets.QHBoxLayout()
        action_bar.addStretch(1)
        return action_bar

    def _build_control_panel(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Create the left-side control panel (deprecated - controls now in separate docks)."""
        # This method is no longer used; controls are now in separate dock panels
        panel = QtWidgets.QWidget(parent)
        return panel

    def _build_wizard_embed(self, parent: QtWidgets.QWidget) -> QtWidgets.QGroupBox:
        """Embed WizardTTTRPhotonFilter for setup, channel, and filter controls."""
        group = QtWidgets.QGroupBox("Filter settings", parent)
        group.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        layout = QtWidgets.QVBoxLayout(group)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)
        default_windows = {"prompt": (0, 2048), "delayed": (2048, 4095)}
        default_detectors = {
            "green": {"chs": [8, 0, 3], "micro_time_ranges": [(0, 4095)], "g_factor": 1, "l1": 0, "l2": 0},
            "red": {"chs": [9, 1, 2], "micro_time_ranges": [(0, 2048)], "g_factor": 1, "l1": 0, "l2": 0},
            "yellow": {"chs": [9, 1, 2], "micro_time_ranges": [(2048, 4095)], "g_factor": 1, "l1": 0, "l2": 0},
        }
        self.wizard = WizardTTTRPhotonFilter(
            windows=default_windows,
            detectors=default_detectors,
            show_dT=True,
            show_burst=False,
            show_mcs=False,
            show_decay=False,
            show_filter=False,
        )
        # Connect wizard status messages to the main window's statusbar
        self.wizard.status_message.connect(self._status_bar.showMessage)
        # Connect wizard filter parameter changes to plot updates
        self.wizard.actionUpdate_Values.triggered.connect(self._on_filter_settings_changed)
        self._connect_filter_controls_to_selection_update()
        setup_layout = QtWidgets.QHBoxLayout()
        setup_layout.setContentsMargins(0, 0, 0, 0)
        setup_layout.setSpacing(4)
        setup_layout.addWidget(QtWidgets.QLabel("Detector setup", group))
        self.wizard.comboBox.setMaximumWidth(16_777_215)
        self.wizard.comboBox.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        setup_layout.addWidget(self.wizard.comboBox)
        setup_layout.setStretch(1, 1)
        self.wizard.comboBox.setToolTip(
            "Select a detector setup. The setup defines detectors, PIE windows, "
            "microtime binning, burst settings, and the TTTR file type."
        )
        self.wizard.comboBox.currentTextChanged.connect(self._on_setup_changed)
        # Add save button to the right of the combobox
        self.wizard.toolButton_5.setText("💾")
        self.wizard.toolButton_5.setFixedSize(28, 22)
        self.wizard.toolButton_5.setToolTip("Save burst parameters as default to setup.")
        self.wizard.toolButton_5.show()
        # Disconnect the original save_selection slot and reconnect it
        try:
            self.wizard.toolButton_5.clicked.disconnect()
        except Exception:
            pass
        # Reconnect to the save_burst_selection_parameters method (same as Macro Time interval groupbox)
        self.wizard.toolButton_5.clicked.connect(self.wizard.save_burst_selection_parameters)
        setup_layout.addWidget(self.wizard.toolButton_5)
        layout.addLayout(setup_layout)
        # Hide redundant UI elements — we use our own action bar, file list, and dock plots
        self.wizard.textEdit.hide()  # left help panel
        self.wizard.lineEdit.hide()  # file drop area
        self.wizard.lineEdit_2.hide()  # output path
        self.wizard.spinBox_4.hide()  # file index
        self.wizard.toolButton.hide()  # help toggle
        self.wizard.toolButton_2.hide()  # MCS toggle
        self.wizard.toolButton_3.hide()  # decay toggle
        self.wizard.toolButton_4.hide()  # filter toggle
        self.wizard.toolButton_6.hide()  # clear button
        self.wizard.toolButton_7.hide()  # burst toggle
        self.wizard.checkBox_6.hide()  # sl5 output
        self.wizard.checkBox_7.hide()  # bur output
        self.wizard.groupBox_4.hide()  # plot settings
        # Keep: groupBox_3 (channel selection), groupBox_2 (macro time), groupBox (filter)
        self._compact_filter_settings_widgets()
        layout.addWidget(self.wizard, 1)
        return group

    def _connect_filter_controls_to_selection_update(self) -> None:
        """Connect filter controls to selected-file result and plot updates."""
        controls = [
            self.wizard.comboBox_2,
            self.wizard.comboBox_3,
            self.wizard.comboBox_burst_filter,
            self.wizard.checkBox,
            self.wizard.checkBox_2,
            self.wizard.checkBox_3,
            self.wizard.checkBox_4,
            self.wizard.checkBox_5,
            self.wizard.spinBox,
            self.wizard.spinBox_7,
            self.wizard.spinBox_8,
            self.wizard.doubleSpinBox,
            self.wizard.doubleSpinBox_2,
            self.wizard.doubleSpinBox_3,
        ]
        # Append CUSUM/BOCPD/Kalman widgets safely if they exist
        for name in (
            "doubleSpinBox_5",
            "doubleSpinBox_6",
            "doubleSpinBox_7",
            "doubleSpinBox_8",
            "doubleSpinBox_9",
            "doubleSpinBox_10",
            "spinBox_9"
        ):
            widget = getattr(self.wizard, name, None)
            if widget is not None:
                controls.append(widget)

        # Debounced: every one of these fires a full re-search *and* a diagnostic
        # reload (~0.9 s for 1.8 M photons), and a spin box emits `valueChanged`
        # per keystroke and per drag step. Undebounced, typing a threshold ran
        # the search once per digit and the window stopped answering.
        resettle = self._debounced(self._on_filter_settings_changed, "filter")
        for control in controls:
            if isinstance(control, QtWidgets.QComboBox):
                control.currentTextChanged.connect(resettle)
            elif isinstance(control, QtWidgets.QCheckBox):
                control.stateChanged.connect(resettle)
            else:
                control.valueChanged.connect(resettle)
        region_selector = getattr(self.wizard, "region_selector", None)
        if region_selector is not None:
            # Already a "finished" signal, so it needs no coalescing of its own.
            region_selector.sigRegionChangeFinished.connect(self._on_filter_settings_changed)

        # The generated forms have no Designer widgets to connect to: their
        # controls are created and destroyed on every rebuild, so connecting them
        # individually would need re-wiring each time. Both forms instead trigger
        # `actionUpdate_Values` on edit, so listening to that one action keeps the
        # plots responsive to the built-in *and* the registry-driven parameters,
        # including searches added to tttrlib later.
        update_action = getattr(self.wizard, "actionUpdate_Values", None)
        if update_action is not None:
            update_action.triggered.connect(self._on_filter_settings_changed)

    def _allow_horizontal_expansion(self, widget: QtWidgets.QWidget | None) -> None:
        """Allow a widget to use available horizontal space."""
        if widget is None:
            return
        widget.setMaximumWidth(16_777_215)
        widget.setSizePolicy(
            QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                widget.sizePolicy().verticalPolicy(),
            )
        )

    def _compact_filter_settings_widgets(self) -> None:
        """Reduce unused space in the embedded filter-settings controls."""
        self.wizard.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        for layout_name in ("gridLayout_4", "gridLayout_8", "gridLayout_2", "gridLayout_3", "gridLayout"):
            widget_layout = getattr(self.wizard, layout_name, None)
            if widget_layout is not None:
                widget_layout.setContentsMargins(2, 2, 2, 2)
                widget_layout.setSpacing(2)

        for box in (self.wizard.groupBox_3, self.wizard.groupBox_2, self.wizard.groupBox):
            self._allow_horizontal_expansion(box)
            box.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
        # The filter groups are no longer wrapped here: the generated form
        # (filter_settings_form) renders them as foldable PanelSections, and
        # wrapping the hidden Designer boxes as well would draw a second row of
        # empty headers over it.

    def _make_filter_groups_collapsible(self) -> None:
        """Turn the filter-settings group boxes into foldable sections.

        The same treatment the light-path simulator gives its settings: each
        group becomes a :class:`CollapsibleBox`, so the parts of the panel that
        are not currently being adjusted can be folded away. This matters here
        because the page competes for vertical space with the plots below it, and
        with a registry-driven search selected the parameter form is taller than
        the built-in modes ever were.

        Each group box is moved inside a collapsible section rather than
        recreated, so every widget keeps its identity — the wizard addresses them
        by attribute (``self.wizard.groupBox_2`` and so on) and the tool wires
        signals to the individual controls, both of which would break if the
        widgets were rebuilt. The group box itself is made flat and title-less,
        since the section header now carries the title.
        """
        from chisurf.gui.widgets.collapsible_box import CollapsibleBox

        # Channel selection folds away by default: it is set once per setup,
        # whereas the filter parameters are what a user actually iterates on.
        specs = (
            (self.wizard.groupBox_3, "Channel selection", False),
            (self.wizard.groupBox_2, "Macro time interval", True),
            (self.wizard.groupBox, "Filter", True),
        )
        self._collapsible_filter_groups = {}
        for box, title, expanded in specs:
            parent_layout = box.parentWidget().layout() if box.parentWidget() else None
            if parent_layout is None:
                continue
            index = parent_layout.indexOf(box)
            if index < 0:
                continue
            item = parent_layout.itemAt(index)
            position = None
            if isinstance(parent_layout, QtWidgets.QGridLayout):
                position = parent_layout.getItemPosition(index)
            parent_layout.takeAt(index)

            section = CollapsibleBox(title, expanded=expanded)
            box.setTitle("")
            box.setFlat(True)
            section.add_widget(box)
            section.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            if position is not None:
                row, column, row_span, column_span = position
                parent_layout.addWidget(section, row, column, row_span, column_span)
            else:
                parent_layout.insertWidget(index, section)
            self._collapsible_filter_groups[title] = section
            del item

        for widget in (
            self.wizard.comboBox_2,
            self.wizard.comboBox_3,
            self.wizard.comboBox_burst_filter,
            self.wizard.lineEdit_4,
            self.wizard.lineEdit_5,
            self.wizard.doubleSpinBox_2,
            self.wizard.doubleSpinBox_3,
            self.wizard.doubleSpinBox,
            self.wizard.doubleSpinBox_5,
            self.wizard.doubleSpinBox_6,
            self.wizard.doubleSpinBox_7,
            self.wizard.doubleSpinBox_8,
            self.wizard.doubleSpinBox_9,
            self.wizard.doubleSpinBox_10,
            self.wizard.spinBox,
            self.wizard.spinBox_7,
            self.wizard.spinBox_8,
            self.wizard.spinBox_9,
        ):
            self._allow_horizontal_expansion(widget)

        for checkbox in (self.wizard.checkBox_2, self.wizard.checkBox_3, self.wizard.checkBox_5):
            checkbox.setMaximumWidth(18)

        controls_container = getattr(self.wizard, "widget", None)
        if controls_container is not None:
            controls_container.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )

        plot_layout = getattr(self.wizard, "gridLayout_6", None)
        if plot_layout is not None:
            plot_layout.setContentsMargins(0, 0, 0, 0)
            plot_layout.setSpacing(2)
            plot_layout.setRowStretch(0, 8)
            plot_layout.setRowStretch(1, 1)
            plot_layout.setRowStretch(2, 0)
            for column in range(3):
                plot_layout.setColumnStretch(column, 1)

        for plot_widget, minimum_height in (
            (getattr(self.wizard, "pw_dT", None), 180),
            (getattr(self.wizard, "pw_filter", None), 34),
        ):
            if plot_widget is None:
                continue
            plot_widget.setMinimumHeight(minimum_height)
            plot_widget.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )

    def _build_histogram_group(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Create histogram and optional GMM controls."""
        widget = QtWidgets.QWidget(parent)
        layout = QtWidgets.QFormLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self.feature_combo = QtWidgets.QComboBox(widget)
        self.feature_combo.addItems(HISTOGRAM_FEATURES)
        self.feature_combo.setCurrentText("Proximity Ratio")
        layout.addRow("Feature", self.feature_combo)
        self.hist_bins_spin = QtWidgets.QSpinBox(widget)
        self.hist_bins_spin.setRange(1, 999)
        self.hist_bins_spin.setValue(DEFAULT_HISTOGRAM_BINS)
        layout.addRow("# Bins", self.hist_bins_spin)
        self.hist_min_spin = QtWidgets.QDoubleSpinBox(widget)
        self.hist_min_spin.setRange(-9999.0, 9999.0)
        self.hist_min_spin.setDecimals(6)
        self.hist_min_spin.setValue(0.0)
        self.hist_max_spin = QtWidgets.QDoubleSpinBox(widget)
        self.hist_max_spin.setRange(-9999.0, 9999.0)
        self.hist_max_spin.setDecimals(6)
        self.hist_max_spin.setValue(1.0)
        range_layout = QtWidgets.QHBoxLayout()
        range_layout.setSpacing(2)
        range_layout.addWidget(self.hist_min_spin)
        range_layout.addWidget(QtWidgets.QLabel("to", widget))
        range_layout.addWidget(self.hist_max_spin)
        self.auto_range_button = QtWidgets.QPushButton("⚡ Auto", widget)
        range_layout.addWidget(self.auto_range_button)
        layout.addRow("Range", range_layout)
        self.hist_log_y_check = QtWidgets.QCheckBox("Log x", widget)
        layout.addRow(self.hist_log_y_check)
        self.gmm_components_spin = QtWidgets.QSpinBox(widget)
        self.gmm_components_spin.setRange(0, 10)
        self.gmm_auto_components_check = QtWidgets.QCheckBox("Auto components", widget)
        self.fit_gmm_button = QtWidgets.QPushButton("🎯 Fit GMM", widget)
        self.gmm_settings_button = QtWidgets.QPushButton("⚙️", widget)
        self.gmm_settings_button.setToolTip("Advanced GMM settings…")
        self.gmm_settings_button.setMaximumWidth(28)
        gmm_layout = QtWidgets.QHBoxLayout()
        gmm_layout.setSpacing(2)
        gmm_layout.addWidget(self.gmm_components_spin)
        gmm_layout.addWidget(self.gmm_auto_components_check)
        gmm_layout.addWidget(self.fit_gmm_button)
        gmm_layout.addWidget(self.gmm_settings_button)
        layout.addRow("GMM", gmm_layout)
        self.gmm_summary = QtWidgets.QTextEdit(widget)
        self.gmm_summary.setReadOnly(True)
        self.gmm_summary.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        layout.addRow(self.gmm_summary)
        self._connect_histogram_controls(self._update_histogram_if_available)
        self.auto_range_button.clicked.connect(self._set_histogram_range_to_data)
        self.fit_gmm_button.clicked.connect(self._fit_gmm)
        self.gmm_settings_button.clicked.connect(self._show_gmm_settings)
        return widget

    def _build_plot_group(self, parent: QtWidgets.QWidget) -> QtWidgets.QGroupBox:
        """Create burst diagnostic plot controls (deprecated - kept for compatibility)."""
        # This method is no longer used; controls are now in separate panels
        # and connected directly in _build_plot_settings_panel, _build_mcs_controls_panel, etc.
        group = QtWidgets.QGroupBox("Plot settings", parent)
        return group

    def _build_filter_settings_panel(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Create filter settings panel for separate dock."""
        panel = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_wizard_embed(panel), 1)
        # The display settings sit with the other settings, not in the toolbar.
        # They govern every diagnostic plot (dT, MCS, Decay, Burst length), so
        # they belong once, here, rather than repeated in each plot's controls.
        layout.addWidget(self._build_display_form(panel), 0)
        panel.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        return panel

    def _ensure_display_widgets(self) -> None:
        """Create the widgets that *hold* the display settings, once.

        They are the state, not the presentation: the AutoForm built from
        ``burst_display.view.json`` is what the user sees, and it reads and
        writes these through the view-model. Keeping them means every existing
        reader (``plot_min_spin``, ``show_all_photons_check``, the MCS aliases,
        the tests) and every existing signal connection keeps working while the
        control moves out of the toolbar. Hidden children of the tool: they are
        never laid out anywhere, so they render nothing on their own.
        """
        if getattr(self, "show_all_photons_check", None) is not None:
            return
        self.show_all_photons_check = QtWidgets.QCheckBox("All photons", self)
        self.show_all_photons_check.setChecked(True)
        self.show_all_photons_check.setToolTip(
            "Show diagnostic layers computed from all photons."
        )
        self.show_all_photons_check.hide()
        self.show_selected_photons_check = QtWidgets.QCheckBox("Selected photons", self)
        self.show_selected_photons_check.setChecked(True)
        self.show_selected_photons_check.setToolTip(
            "Show diagnostic layers computed from selected burst photons."
        )
        self.show_selected_photons_check.hide()
        # Backwards-compatible aliases for older code paths/tests that used
        # the original MCS-local controls.
        self.mcs_show_all_check = self.show_all_photons_check
        self.mcs_show_selected_check = self.show_selected_photons_check

        self.plot_min_spin = QtWidgets.QSpinBox(self)
        self.plot_min_spin.setRange(0, 99_999_999)
        self.plot_min_spin.setValue(0)
        self.plot_min_spin.setToolTip(
            "Minimum photon index to process (0 = start of file)"
        )
        self.plot_min_spin.hide()
        self.plot_max_spin = QtWidgets.QSpinBox(self)
        self.plot_max_spin.setRange(0, 99_999_999)
        self.plot_max_spin.setValue(DEFAULT_PLOT_MAX)
        self.plot_max_spin.setToolTip(
            "Maximum photon index to process (default = end of file)"
        )
        self.plot_max_spin.hide()

    def _build_display_form(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """The display settings, rendered by AutoForm from ``burst_display.view.json``.

        These were toolbar widgets. They are settings — which layers to draw and
        over which slice of the file — so they belong in a form, and the toolbar
        (which holds the actions) was full enough that they pushed the actions
        out of view. The form binds to a view-model that proxies to the very same
        widgets, so nothing is duplicated and every existing reader of
        ``plot_min_spin`` / ``show_all_photons_check`` is untouched.
        """
        from chisurf.gui.autoform import AutoForm

        from .display_view_model import BurstDisplayViewModel

        self._ensure_display_widgets()
        self._display_view_model = BurstDisplayViewModel(self)
        form = AutoForm(self._display_view_model, parent)
        form.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )
        # Kept so the photon range can be pushed back into the form. The form
        # reads the hidden spin boxes when it is built; the spins are then
        # re-clamped every time diagnostics load, and without this the boxes
        # went on showing the value they were built with while the plots used
        # the new one -- a displayed limit that was not the limit in force.
        self._display_form = form
        return form

    def _build_histogram_controls_panel(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Create histogram controls panel for separate dock."""
        panel = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_histogram_group(panel), 1)
        return panel

    def _build_files_controls_panel(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Create files output format controls panel for separate dock."""
        panel = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        group = QtWidgets.QGroupBox("Output Format", panel)
        group_layout = QtWidgets.QVBoxLayout(group)
        group_layout.setContentsMargins(4, 4, 4, 4)
        group_layout.setSpacing(2)
        format_layout = QtWidgets.QHBoxLayout()
        format_layout.setSpacing(2)
        # Where the results go is not a choice: it follows the input. A `.pto`
        # already holds the photons, so the bursts go in beside them; anything
        # else has nowhere to put them and gets the tab-separated companion
        # folder external tools read. Three checkboxes offering combinations of
        # the two (plus an MFD-HDF5 that had been disabled for a long time) let
        # a run be configured to write the same bursts in two places, or in
        # none, and the label is the honest thing to show instead.
        self.output_destination_label = QtWidgets.QLabel("", group)
        self.output_destination_label.setToolTip(
            "A .pto measurement keeps its bursts inside itself; a vendor file "
            "gets the bi4_bur/ companion folder beside it."
        )
        self.mmfdb_output_check = QtWidgets.QCheckBox("MMFDB", group)
        self.zip_output_check = QtWidgets.QCheckBox("Zip Output", group)
        self.remove_folder_check = QtWidgets.QCheckBox("Remove Folder", group)
        format_layout.addWidget(self.output_destination_label)
        format_layout.addWidget(self.mmfdb_output_check)
        format_layout.addWidget(self.zip_output_check)
        format_layout.addWidget(self.remove_folder_check)
        group_layout.addLayout(format_layout)
        self.mmfdb_output_check.stateChanged.connect(self._sync_output_format_controls)
        self.zip_output_check.stateChanged.connect(self._sync_output_format_controls)
        layout.addWidget(group)
        return panel

    def _build_mcs_controls_panel(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Create MCS controls panel for separate dock."""
        panel = QtWidgets.QWidget(parent)
        layout = QtWidgets.QFormLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self.mcs_bin_spin = QtWidgets.QDoubleSpinBox(panel)
        self.mcs_bin_spin.setRange(0.05, 9999.0)
        self.mcs_bin_spin.setSuffix(" ms")
        self.mcs_bin_spin.setDecimals(3)
        self.mcs_bin_spin.setSingleStep(0.05)
        self.mcs_bin_spin.setValue(DEFAULT_TRACE_BIN_WIDTH_MS)
        layout.addRow("MCS bin-width", self.mcs_bin_spin)
        self.mcs_bin_spin.valueChanged.connect(self._debounced(self.update_burst_plots, "plots"))
        return panel

    def _build_decay_controls_panel(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Create Decay controls panel for separate dock."""
        panel = QtWidgets.QWidget(parent)
        layout = QtWidgets.QFormLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self.decay_bins_spin = QtWidgets.QSpinBox(panel)
        self.decay_bins_spin.setRange(1, 9999)
        self.decay_bins_spin.setValue(DEFAULT_DECAY_BINS)
        layout.addRow("Decay bin", self.decay_bins_spin)
        self.decay_bins_spin.valueChanged.connect(self._debounced(self.update_burst_plots, "plots"))
        return panel

    def _build_burst_controls_panel(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Create Burst controls panel for separate dock."""
        panel = QtWidgets.QWidget(parent)
        layout = QtWidgets.QFormLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self.burst_bins_spin = QtWidgets.QSpinBox(panel)
        self.burst_bins_spin.setRange(3, 999)
        self.burst_bins_spin.setValue(DEFAULT_BURST_BINS)
        layout.addRow("#Burst bins", self.burst_bins_spin)
        self.burst_bins_spin.valueChanged.connect(self._debounced(self.update_burst_plots, "plots"))
        return panel

    def _plot_widget_is_docked(self, attr: str) -> bool:
        """Return whether a diagnostic plot widget is currently present in the dock area."""
        try:
            features = getattr(self, "_diagnostic_plot_features", {})
        except RuntimeError:
            features = {}
        feature = features.get(attr)
        if feature is None or not feature["initial_enabled"]:
            return False
        try:
            closed_diagnostic_plots = self._closed_diagnostic_plots
        except RuntimeError:
            closed_diagnostic_plots = set()
        if attr in closed_diagnostic_plots or not bool(feature["check"].isChecked()):
            return False
        dock_widget = feature.get("dock_widget", feature["widget"])
        return self._dock_widget_is_present(dock_widget)

    def _dock_widget_is_present(self, widget: QtWidgets.QWidget | None) -> bool:
        """Return whether a dock widget is currently shown in the dock area."""
        if widget is None:
            return False
        try:
            dock_area = getattr(self, "dock_area", None)
        except RuntimeError:
            dock_area = None
        if dock_area is None:
            return True
        index = dock_area.indexOf(widget)
        if index < 0:
            return False
        is_visible = getattr(dock_area, "isTabVisible", None)
        if callable(is_visible):
            return bool(is_visible(index))
        return True

    def _create_plot_widgets(self) -> None:
        """Create all plot widgets early to avoid hot-reload deletion issues."""
        self.summary = QtWidgets.QTextEdit(self)
        self.summary.setReadOnly(True)

        self.histogram_plot = pg.PlotWidget(self)
        self.histogram_plot.setLabel("bottom", "Value")
        self.histogram_plot.setLabel("left", "Frequency")
        self.histogram_plot.setTitle("Histogram")

        self.filter_plot = pg.PlotWidget(self)
        self.filter_plot.setLabel("bottom", "Photon Index")
        self.filter_plot.setLabel("left", "Selected")
        self.filter_plot.setTitle("Filter/selection")

        self.mcs_plot = pg.PlotWidget(self)
        self.mcs_plot.setLabel("bottom", "Time (s)")
        self.mcs_plot.setLabel("left", "Intensity")
        self.mcs_plot.setTitle("Count rate display")

        self.decay_plot = pg.PlotWidget(self)
        self.decay_plot.setLabel("bottom", "Microtime (ns)")
        self.decay_plot.setLabel("left", "Counts")
        self.decay_plot.setTitle("Microtime histogram")
        self.decay_plot.getPlotItem().setLogMode(False, True)

        self.burst_plot = pg.PlotWidget(self)
        self.burst_plot.setLabel("bottom", "Burst size")
        self.burst_plot.setLabel("left", "Counts")
        self.burst_plot.setTitle("Burst histogram")

        self.dt_plot = pg.PlotWidget(self)
        self.dt_plot.setLabel("bottom", "Photon Index")
        self.dt_plot.setLabel("left", "dT (ms)")
        self.dt_plot.setTitle("Delta macro-time")
        self.dt_plot.getPlotItem().setLogMode(False, True)

        # The three plots that hold a raw per-photon series get the *viewport's*
        # own decimation on top of the budget applied when the arrays are built.
        # The two solve different halves: `thin_for_plot` bounds what is handed
        # to Qt, and this bounds what Qt lays out for the range currently
        # visible -- so zooming into 1% of a trace stops costing what drawing
        # all of it costs. `peak` mode keeps each bin's extremes, the same
        # reason `thin_for_plot` is min/max-per-bin rather than a stride.
        for _plot in (self.dt_plot, self.filter_plot, self.mcs_plot):
            item = _plot.getPlotItem()
            item.setDownsampling(auto=True, mode="peak")
            item.setClipToView(True)

        self.table = QtWidgets.QTableWidget(self)
        self.table.setColumnCount(len(UI_COLUMNS))
        self.table.setHorizontalHeaderLabels(UI_COLUMNS)
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.table.horizontalHeader().setStretchLastSection(True)

    def _build_docks(self) -> None:
        """Create draggable result and diagnostic docks using pre-created widgets."""
        # Create file_list widget
        self.file_list = DropListWidget(self.dock_area)
        self.file_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.pathsDropped.connect(self._add_paths)
        self.file_list.itemSelectionChanged.connect(self._on_file_selected)
        self.file_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._show_file_list_context_menu)

        # Build separate control panels for each dock
        filter_settings_panel = self._build_filter_settings_panel(self.dock_area)
        self.filter_settings_panel = filter_settings_panel
        histogram_controls_panel = self._build_histogram_controls_panel(self.dock_area)
        files_controls_panel = self._build_files_controls_panel(self.dock_area)
        mcs_controls_panel = self._build_mcs_controls_panel(self.dock_area)
        decay_controls_panel = self._build_decay_controls_panel(self.dock_area)
        burst_controls_panel = self._build_burst_controls_panel(self.dock_area)

        # Add Filter Settings dock
        self.dock_area.addTab(filter_settings_panel, "Filter Settings")

        # Add Files dock with controls
        files_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self.dock_area)
        files_splitter.addWidget(files_controls_panel)

        # Add drop hint label
        drop_hint = QtWidgets.QLabel("Drop files or folders here", self.dock_area)
        drop_hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        drop_hint.setStyleSheet("color: gray; font-style: italic;")
        files_splitter.addWidget(drop_hint)

        files_splitter.addWidget(self.file_list)
        files_splitter.setStretchFactor(0, 0)
        files_splitter.setStretchFactor(1, 0)
        files_splitter.setStretchFactor(2, 1)
        self.files_dock_widget = files_splitter
        self.dock_area.addTab(files_splitter, "Files", close_mode="remove")

        self.dock_area.addTab(self.table, "Bursts")

        # Add dT plot dock
        self.dock_area.addTab(self.dt_plot, "dT")

        # Add Histogram dock with controls
        histogram_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self.dock_area)
        histogram_splitter.addWidget(histogram_controls_panel)
        histogram_splitter.addWidget(self.histogram_plot)
        histogram_splitter.setStretchFactor(0, 0)
        histogram_splitter.setStretchFactor(1, 1)
        self.dock_area.addTab(histogram_splitter, "Histogram")

        if self.show_filter_plot:
            self.dock_area.addTab(self.filter_plot, "Filter")

        # Add MCS dock with controls
        if self.show_mcs_plot:
            mcs_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self.dock_area)
            mcs_splitter.addWidget(mcs_controls_panel)
            mcs_splitter.addWidget(self.mcs_plot)
            mcs_splitter.setStretchFactor(0, 0)
            mcs_splitter.setStretchFactor(1, 1)
            self.dock_area.addTab(mcs_splitter, "MCS")

        # Add Decay dock with controls
        if self.show_decay_plot:
            decay_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self.dock_area)
            decay_splitter.addWidget(decay_controls_panel)
            decay_splitter.addWidget(self.decay_plot)
            decay_splitter.setStretchFactor(0, 0)
            decay_splitter.setStretchFactor(1, 1)
            self.dock_area.addTab(decay_splitter, "Decay")

        # Add Burst dock with controls
        if self.show_burst_plot:
            burst_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self.dock_area)
            burst_splitter.addWidget(burst_controls_panel)
            burst_splitter.addWidget(self.burst_plot)
            burst_splitter.setStretchFactor(0, 0)
            burst_splitter.setStretchFactor(1, 1)
            self.dock_area.addTab(burst_splitter, "Burst length")

        # A controls panel is built for every diagnostic plot but only *placed*
        # when that plot is shown. An unplaced one keeps the dock area as its
        # parent with no layout to size it, so Qt draws it at its default
        # 640x480 in the corner — a ghost "Burst bins" spin box over the tab
        # bar. Hide what nothing placed.
        for panel, placed in ((mcs_controls_panel, self.show_mcs_plot),
                              (decay_controls_panel, self.show_decay_plot),
                              (burst_controls_panel, self.show_burst_plot)):
            if not placed:
                panel.hide()

        self.dock_area.addTab(self.summary, "Summary")

        self.filter_dock_widget = self.filter_plot
        self.mcs_dock_widget = locals().get("mcs_splitter")
        self.decay_dock_widget = locals().get("decay_splitter")
        self.burst_dock_widget = locals().get("burst_splitter")

        # Initialize plot checkboxes (used for context menu, not displayed)
        self.plot_mcs_check = QtWidgets.QCheckBox(self)
        self.plot_mcs_check.setChecked(self.show_mcs_plot)
        self.plot_decay_check = QtWidgets.QCheckBox(self)
        self.plot_decay_check.setChecked(self.show_decay_plot)
        self.plot_filter_check = QtWidgets.QCheckBox(self)
        self.plot_filter_check.setChecked(self.show_filter_plot)
        self.plot_burst_check = QtWidgets.QCheckBox(self)
        self.plot_burst_check.setChecked(self.show_burst_plot)

    def _setup_menu(self) -> None:
        """Create menu actions."""
        file_menu = self.menuBar().addMenu("File")
        open_files_action = QtWidgets.QAction("Add TTTR files", self)
        open_files_action.triggered.connect(self.add_files)
        open_folder_action = QtWidgets.QAction("Open folder", self)
        open_folder_action.triggered.connect(self.open_batch_dialog)
        file_menu.addSeparator()
        export_submenu = file_menu.addMenu("Export")
        export_bur_action = QtWidgets.QAction("Export as .bur", self)
        export_bur_action.triggered.connect(self.export_bur)
        export_submenu.addAction(export_bur_action)
        export_cif_action = QtWidgets.QAction("Export as flrCIF", self)
        export_cif_action.triggered.connect(self.export_flr_cif)
        export_submenu.addAction(export_cif_action)
        file_menu.addSeparator()
        exit_action = QtWidgets.QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(open_files_action)
        file_menu.addAction(open_folder_action)
        file_menu.addAction(exit_action)

        settings_menu = self.menuBar().addMenu("Settings")
        channels_action = QtWidgets.QAction("Channels", self)
        channels_action.triggered.connect(self._show_channel_settings)
        settings_menu.addAction(channels_action)
        gmm_action = QtWidgets.QAction("GMM", self)
        gmm_action.triggered.connect(self._focus_gmm_controls)
        settings_menu.addAction(gmm_action)
        metadata_action = QtWidgets.QAction("Metadata", self)
        metadata_action.triggered.connect(self._show_metadata_dialog)
        settings_menu.addAction(metadata_action)

        help_menu = self.menuBar().addMenu("Help")
        about_action = QtWidgets.QAction("Help", self)
        about_action.triggered.connect(self._show_help)
        help_menu.addAction(about_action)

        self._setup_toolbar()

    def _connect_histogram_controls(self, slot: Any) -> None:
        """Connect histogram controls to a common update slot."""
        controls = [self.feature_combo, self.hist_bins_spin, self.hist_min_spin, self.hist_max_spin, self.hist_log_y_check]
        for control in controls:
            if isinstance(control, QtWidgets.QComboBox):
                control.currentTextChanged.connect(slot)
            elif isinstance(control, QtWidgets.QCheckBox):
                control.stateChanged.connect(slot)
            else:
                control.valueChanged.connect(slot)

    def _connect_plot_controls(self, slot: Any) -> None:
        """Connect diagnostic plot controls to a common update slot (deprecated)."""
        # This method is no longer used; controls are now connected directly
        # in their respective panel building methods (_build_plot_settings_panel, etc.)
        pass

    def _apply_visibility_toggles(self) -> None:
        """Apply visibility toggles passed as constructor kwargs."""
        if not self.show_channel_selection:
            self.wizard.groupBox_3.hide()

    #: Quiet period, in ms, before a settings change is acted on.
    #:
    #: Long enough that typing "150000" into a spin box is one recompute rather
    #: than six, and that dragging a spinner is one rather than one per step;
    #: short enough to still feel like a direct response. Both slots behind it
    #: are expensive on a real measurement — a full re-search is ~0.9 s and a
    #: full redraw ~0.5 s for 1.8 M photons — so the cost of *not* coalescing is
    #: not a stutter, it is a window that stops answering.
    _SETTINGS_DEBOUNCE_MS = 250

    def _debounced(self, slot: Any, key: str) -> Any:
        """Return a callable that runs *slot* once, after a quiet period.

        Parameters
        ----------
        slot : callable
            What to run. Called with no arguments, so it can be connected to
            signals that carry a value (``valueChanged``) without the value
            reaching it.
        key : str
            Names the timer, so several controls feeding the same slot share
            one pending call instead of each getting its own.

        Returns
        -------
        callable
            Connect this to the signal in place of *slot*.
        """
        timers = self.__dict__.setdefault("_debounce_timers", {})
        timer = timers.get(key)
        if timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(self._SETTINGS_DEBOUNCE_MS)
            timer.timeout.connect(slot)
            timers[key] = timer
        return lambda *_args, _t=timer: _t.start()

    def _connect_action_bar(self) -> None:
        """Connect action bar control signals."""
        replot = self._debounced(self.update_burst_plots, "plots")
        self.plot_min_spin.valueChanged.connect(replot)
        self.plot_max_spin.valueChanged.connect(replot)
        self.show_all_photons_check.stateChanged.connect(replot)
        self.show_selected_photons_check.stateChanged.connect(replot)

    def _configure_dock_context_menu(self) -> None:
        """Configure tab context menus for closing and re-enabling diagnostic plots."""
        self._diagnostic_plot_features = {
            "Filter": {
                "widget": self.filter_plot,
                "dock_widget": self.filter_dock_widget,
                "check": self.plot_filter_check,
                "initial_enabled": self.show_filter_plot,
            },
            "MCS": {
                "widget": self.mcs_plot,
                "dock_widget": self.mcs_dock_widget,
                "check": self.plot_mcs_check,
                "initial_enabled": self.show_mcs_plot,
            },
            "Decay": {
                "widget": self.decay_plot,
                "dock_widget": self.decay_dock_widget,
                "check": self.plot_decay_check,
                "initial_enabled": self.show_decay_plot,
            },
            "Burst length": {
                "widget": self.burst_plot,
                "dock_widget": self.burst_dock_widget,
                "check": self.plot_burst_check,
                "initial_enabled": self.show_burst_plot,
            },
        }
        self.dock_area.setContextMenuEnabled(True)
        self.dock_area.setContextMenuMode("basic")
        self.dock_area.setTabsClosable(True)
        self.dock_area.setCloseTabCallback(self._on_dock_tab_close_requested)
        self.dock_area.setContextMenuCallback(self._add_dock_context_menu_actions)

    def _on_dock_tab_close_requested(self, index: int) -> None:
        """Handle diagnostic plot close requests without computing hidden plots."""
        widget = self.dock_area.widget(index)
        # Find which diagnostic plot this widget corresponds to
        name = None
        for plot_name, feature in self._diagnostic_plot_features.items():
            if feature.get("dock_widget", feature["widget"]) is widget:
                name = plot_name
                break
        if name is not None and self._diagnostic_plot_features[name]["initial_enabled"]:
            self._closed_diagnostic_plots.add(name)
            self._diagnostic_plot_features[name]["check"].setChecked(False)
            self.dock_area.hideTab(index)
            self.update_burst_plots()
            return
        if widget is getattr(self, "files_dock_widget", None):
            self.dock_area.removeTab(index)
            return
        self.dock_area.hideTab(index)

    def _add_dock_context_menu_actions(self, menu: QtWidgets.QMenu, index: int) -> None:
        """Add actions to show closed or disabled diagnostic plots."""
        del index
        unchecked = self._disabled_diagnostic_plot_names()
        if unchecked:
            menu.addSeparator()
            enable_menu = menu.addMenu("Enable plots")
            for name in unchecked:
                action = enable_menu.addAction(name)
                action.triggered.connect(
                    lambda _checked=False, plot_name=name: self._enable_diagnostic_plot(plot_name)
                )

        closed = self._closed_diagnostic_plot_names()
        if closed:
            menu.addSeparator()
            show_menu = menu.addMenu("Reopen closed docks")
            for name in closed:
                action = show_menu.addAction(name)
                action.triggered.connect(
                    lambda _checked=False, plot_name=name: self._show_diagnostic_plot(plot_name)
                )

    def _disabled_diagnostic_plot_names(self) -> list[str]:
        """Return disabled diagnostic plots that still have open docks."""
        return [
            name
            for name, feature in self._diagnostic_plot_features.items()
            if feature["initial_enabled"]
            and name not in self._closed_diagnostic_plots
            and not bool(feature["check"].isChecked())
        ]

    def _closed_diagnostic_plot_names(self) -> list[str]:
        """Return diagnostic plots closed from the dock area."""
        return [
            name
            for name, feature in self._diagnostic_plot_features.items()
            if feature["initial_enabled"] and name in self._closed_diagnostic_plots
        ]

    def _enable_diagnostic_plot(self, name: str) -> None:
        """Enable a diagnostic plot that is still present as a tab."""
        if name in self._closed_diagnostic_plots:
            self._show_diagnostic_plot(name)
            return
        feature = self._diagnostic_plot_features.get(name)
        if feature is None:
            return
        feature["check"].setChecked(True)
        self._clear_burst_plots()
        self.update_burst_plots()

    def _show_diagnostic_plot(self, name: str) -> None:
        """Re-add a diagnostic plot tab that was closed from the context menu."""
        feature = self._diagnostic_plot_features.get(name)
        if feature is None or name not in self._closed_diagnostic_plots:
            return
        self._closed_diagnostic_plots.remove(name)
        dock_widget = feature.get("dock_widget", feature["widget"])
        index = self.dock_area.indexOf(dock_widget)
        if index >= 0 and hasattr(self.dock_area, "showTab"):
            self.dock_area.showTab(index)
        else:
            self.dock_area.addTab(dock_widget, name)
        feature["check"].setChecked(True)
        self._clear_burst_plots()
        self.update_burst_plots()

    def _show_channel_settings(self) -> None:
        """Open a DetectorWizardPage dialog to manage setups, then sync to wizard."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Channel Settings")
        layout = QtWidgets.QVBoxLayout(dialog)
        channel_definer = DetectorWizardPage(parent=dialog, json_file=None)
        layout.addWidget(channel_definer)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        if dialog.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            setup_name = getattr(channel_definer, "current_setup_name", None)
            if setup_name:
                self._apply_detector_setup(setup_name)
                return
            self._apply_custom_detector_settings(
                windows=channel_definer.windows,
                detectors=channel_definer.detectors,
                filetype=channel_definer.tttr_reading.get("file_type"),
            )

    def _on_setup_changed(self, setup_name: str) -> None:
        """Apply detector setup selected in the embedded photon-filter wizard."""
        if self._building_ui or not setup_name or setup_name == "No setups available":
            self._selected_setup_name = None
            self._selected_filetype = None
            self.summary.setPlainText(_setup_summary(None, None))
            return
        self._apply_detector_setup(setup_name)

    def _apply_detector_setup(self, setup_name: str) -> None:
        """Apply a named detector setup to the embedded wizard."""
        setups = load_detector_setups()
        setup_data = setups.get("setups", {}).get(setup_name)
        if not setup_data:
            self._selected_setup_name = None
            self._selected_filetype = None
            self.summary.setPlainText(_setup_summary(None, None))
            return
        reading = setup_data.get("tttr_reading", {}) or {}
        filetype = _normalize_filetype(reading.get("file_type"))
        self._selected_setup_name = setup_name
        self._selected_filetype = filetype
        self.wizard.comboBox.blockSignals(True)
        try:
            if self.wizard.comboBox.findText(setup_name) < 0:
                self.wizard.comboBox.addItem(setup_name)
            self.wizard.comboBox.setCurrentText(setup_name)
        finally:
            self.wizard.comboBox.blockSignals(False)
        self.wizard.update_channel_routing(setup_name)
        self.wizard.update_pie_windows_from_setup(setup_name)
        self.wizard.update_micro_time_binning(setup_name)
        self._apply_burst_selection_parameters(setup_data.get("burst_selection", {}) or {})
        self.summary.setPlainText(_setup_summary(setup_name, filetype))

    def _apply_burst_selection_parameters(self, burst_params: dict[str, Any]) -> None:
        """Apply burst-selection parameters from a detector setup when present."""
        if "dT_min" in burst_params and "dT_max" in burst_params:
            self.wizard._dT_min = float(burst_params["dT_min"])
            self.wizard._dT_max = float(burst_params["dT_max"])
            self.wizard.doubleSpinBox_2.setValue(float(burst_params["dT_min"]))
            self.wizard.doubleSpinBox_3.setValue(float(burst_params["dT_max"]))
        if "use_dT_min" in burst_params:
            self.wizard.checkBox_2.setChecked(bool(burst_params["use_dT_min"]))
        if "use_dT_max" in burst_params:
            self.wizard.checkBox_3.setChecked(bool(burst_params["use_dT_max"]))
        if "photon_threshold" in burst_params:
            self.wizard.spinBox.setValue(int(burst_params["photon_threshold"]))
        if "ph_window" in burst_params:
            self.wizard.ph_window = int(burst_params["ph_window"])
        if "count_rate_window_ms" in burst_params:
            self.wizard.doubleSpinBox.setValue(float(burst_params["count_rate_window_ms"]))
        if "invert_filter" in burst_params:
            self.wizard.checkBox.setChecked(bool(burst_params["invert_filter"]))
        if "filter_active" in burst_params:
            self.wizard.checkBox_4.setChecked(bool(burst_params["filter_active"]))
        if "filter_mode" in burst_params:
            mode = str(burst_params["filter_mode"]).lower()
            if mode == "count_rate":
                self.wizard.comboBox_burst_filter.setCurrentText("Count rate")
            elif mode in {"burst", "bocpd", "kalman"}:
                label = {"burst": "Burst", "bocpd": "BOCPD Burst", "kalman": "Kalman Burst"}[mode]
                self.wizard.comboBox_burst_filter.setCurrentText(label)
        if "use_gap_fill" in burst_params:
            self.wizard.checkBox_5.setChecked(bool(burst_params["use_gap_fill"]))
        if "max_gap" in burst_params:
            self.wizard.spinBox_7.setValue(int(burst_params["max_gap"]))
        if "trace_bin_width" in burst_params:
            self.wizard.doubleSpinBox_4.setValue(float(burst_params["trace_bin_width"]))
        if "number_of_burst_bins" in burst_params:
            self.wizard.spinBox_6.setValue(int(burst_params["number_of_burst_bins"]))
        if "decay_coarse" in burst_params:
            self.wizard.spinBox_5.setValue(int(burst_params["decay_coarse"]))
        self.wizard.update_parameter()

    def _sync_detector_controls(self) -> None:
        """Refresh detector and PIE-window combo boxes after custom edits."""
        self.wizard.comboBox_2.blockSignals(True)
        self.wizard.comboBox_2.clear()
        self.wizard.comboBox_2.addItem("All")
        self.wizard.comboBox_2.addItems(self.wizard.detectors.keys())
        if self.wizard.comboBox_2.count():
            self.wizard.comboBox_2.setCurrentIndex(0)
        self.wizard.comboBox_2.blockSignals(False)

        self.wizard.comboBox_3.blockSignals(True)
        self.wizard.comboBox_3.clear()
        self.wizard.comboBox_3.addItems(self.wizard.windows.keys())
        if self.wizard.comboBox_3.count():
            self.wizard.comboBox_3.setCurrentIndex(0)
        self.wizard.comboBox_3.blockSignals(False)

        if self.wizard.detectors:
            self.wizard.update_detectors()
        if self.wizard.windows:
            self.wizard.update_pie_windows()

    def _apply_custom_detector_settings(
        self,
        windows: dict[str, Any],
        detectors: dict[str, Any],
        filetype: str | None = None,
    ) -> None:
        """Apply detector settings that were not loaded from a named setup."""
        self._selected_setup_name = None
        self._selected_filetype = _normalize_filetype(filetype)
        self.wizard.detectors = detectors
        self.wizard.windows = windows
        self._sync_detector_controls()
        self.summary.setPlainText(_setup_summary(None, self._selected_filetype))

    def _settings_from_controls(self) -> AnalysisSettings:
        """Build API settings from the embedded wizard's current state."""
        from chisurf.plugins.burst.burst_selection.gui.adapter import (
            photon_filter_settings_from_wizard,
        )

        mode_text = self.wizard.comboBox_burst_filter.currentText()
        if "CUSUM" in mode_text:
            used_filter = BurstFilterMode.CUSUM
        elif "BOCPD" in mode_text:
            used_filter = BurstFilterMode.BOCPD
        elif "Kalman" in mode_text:
            used_filter = BurstFilterMode.KALMAN
        elif "Burst" in mode_text:
            used_filter = BurstFilterMode.BURST
        else:
            used_filter = BurstFilterMode.COUNT_RATE

        threshold = int(self.wizard.min_ph)
        time_window = float(self.wizard.spinBox.value() if hasattr(self.wizard, 'spinBox') else DEFAULT_TIME_WINDOW_MS) / 1000.0
        # The number in the "Min photons" box, whatever the mode. It used to be
        # honoured for the sliding-window/CUSUM/Kalman modes and replaced by the
        # constant 60 for count-rate and the tttrlib registry searches -- back
        # when it was a *search* parameter that only some searches took. It is a
        # burst-level criterion now (`drop_short_bursts`), so every mode has one,
        # and substituting a constant meant the control did nothing in the two
        # most-used modes: the Info panel previewed the user's number and the run
        # used 60, which is 2739 bursts against 1130 on the same measurement.
        burst_detection = BurstDetectionSettings(
            min_photons=threshold,
            photon_window=self.wizard.ph_window,
            time_window=time_window,
        )

        output_formats = self._output_formats_for_inputs()

        photon_filter = photon_filter_settings_from_wizard(self.wizard)

        return AnalysisSettings(
            photon_filter=photon_filter,
            burst_detection=burst_detection,
            output_formats=output_formats,
            zip_output=self.zip_output_check.isChecked(),
            remove_folder=self.remove_folder_check.isChecked(),
        )

    def _legacy_parameters(self) -> dict[str, Any]:
        """Collect legacy burst-selection metadata for RPC calls."""
        legacy_parameters: dict[str, Any] = {}
        try:
            if hasattr(self.wizard, "get_burst_selection_parameters"):
                legacy_parameters.update(self.wizard.get_burst_selection_parameters())
        except Exception as exc:
            _LOG.warning("failed to collect legacy burst-selection parameters", error=str(exc))
        if hasattr(self.wizard, "decay_coarse"):
            legacy_parameters.setdefault("decay_coarse", self.wizard.decay_coarse)
        return legacy_parameters

    def _frame_from_result(self, path: Path, dataframes: dict[str, Any]) :
        """Return the burst table for ``path`` from an analysis result."""
        keys = (str(path), str(path.resolve()), str(path.name))
        for key in keys:
            raw_frames = dataframes.get(key)
            if raw_frames:
                return store_from_rows(raw_frames)
        return new_store()

    def _frame_for_path(self, path: Path) :
        """Return a cached burst table for ``path`` when available."""
        resolved = path.resolve()
        if resolved in self._last_frames_by_file:
            return self._last_frames_by_file[resolved]
        if path in self._last_frames_by_file:
            return self._last_frames_by_file[path]
        return None

    def _selected_sample_id(self) -> str:
        """Return the selected MMFDB sample ID when the tool exposes one."""
        def safe_getattr(obj: object, name: str, default: object = None) -> object:
            """Read an attribute from Qt test doubles that may skip ``__init__``."""
            try:
                return getattr(obj, name, default)
            except RuntimeError:
                return default

        for attr_name in ("sample_picker", "sample_selector"):
            picker = safe_getattr(self, attr_name)
            if picker is None:
                continue
            for method_name in ("selected_sample_id", "current_sample_id"):
                method = safe_getattr(picker, method_name)
                if callable(method):
                    sample_id = method()
                    if sample_id:
                        return str(sample_id)
            sample_id = safe_getattr(picker, "sample_id", "")
            if sample_id:
                return str(sample_id)
        sample_id = safe_getattr(self, "sample_id", "")
        return str(sample_id) if sample_id else ""

    def _mmfdb_output_selected(self) -> bool:
        """Return whether MMFDB archival is selected as an output mode.

        Returns
        -------
        bool
            ``True`` when the MMFDB output checkbox is checked.

        """
        check = self._safe_getattr("mmfdb_output_check")
        try:
            return bool(check is not None and check.isChecked())
        except RuntimeError:
            return False

    def acquire_mmfdb_connection(self) -> MMFDBClientBase | None:
        """Return the cached/opened MMFDB connection (PRD-23 base hook)."""
        return self._db()

    def _db(self) -> MMFDBClientBase | None:
        """Return the MMFDB connection used by the output preflight.

        Returns
        -------
        MMFDBClientBase or None
            Active or newly opened MMFDB connection.

        """
        if self._mmfdb_db is not None:
            return self._mmfdb_db
        # Connection acquisition is api-layer logic (PRD-23): prefer the global
        # connection, else open the resolved default DB.
        self._mmfdb_db = _acquire_mmfdb_connection()
        return self._mmfdb_db

    def acquire_mmfdb_session(self) -> Any:
        """Return a verified session derived from the injected authenticated client."""
        if self._mmfdb_session is not None:
            return self._mmfdb_session
        token = getattr(self._mmfdb_client, "token", None)
        db = self._db()
        if db is None:
            return None
        try:
            from chisurf.core.transform.mmfdb import (
                runtime_session_for_database,
                session_from_auth,
            )

            self._mmfdb_session = (
                session_from_auth(db, {"token": token})
                if token
                else runtime_session_for_database(db)
            )
        except Exception:
            return None
        return self._mmfdb_session

    def _ensure_selected_setup_in_mmfdb(self, db: MMFDBClientBase, session: Any) -> str:
        """Return the selected setup ID, saving the current setup when missing.

        Parameters
        ----------
        db : MMFDBClientBase
            MMFDB connection used for archival preflight.

        Returns
        -------
        str
            MMFDB setup ID, or an empty string when no setup is selected.

        """
        selected_setup = self.wizard.comboBox.currentText()
        if not selected_setup:
            return ""
        user_id = session.user_id
        setup_id = setup_id_for_name(selected_setup, user_id=user_id)
        if db.get_setup(setup_id) is not None:
            return setup_id
        windows = getattr(self.wizard, "windows", {}) or {}
        detectors = getattr(self.wizard, "detectors", {}) or {}
        tttr_reading = {
            "file_type": self._selected_filetype,
        }
        setup_data = {
            "windows": windows,
            "detectors": detectors,
            "tttr_reading": tttr_reading,
        }
        db.save_setup(
            setup_id=setup_id,
            name=selected_setup,
            description="TTTR detector and PIE-window setup",
            configuration={"setup_type": "tttr_detector_setup", "setup_data": setup_data},
            detectors=detectors,
            windows=windows,
            timing_resolution=tttr_reading,
            created_by_user_id=user_id,
            is_public=False,
        )
        return setup_id

    def _prepare_mmfdb_context_for_paths(self, paths: list[Path]) -> dict[str, Any] | None:
        """Build MMFDB context and prompt for sample registration when needed.

        Parameters
        ----------
        paths : list of Path
            Raw TTTR files about to be processed.

        Returns
        -------
        dict or None
            MMFDB context for the analysis request, or ``None`` when MMFDB output
            is disabled.

        Raises
        ------
        RuntimeError
            If MMFDB output is selected but no sample is selected or created.

        """
        if not self._mmfdb_output_selected():
            return None

        db = self._db()
        if db is None:
            return {"enabled": True}
        session = self.acquire_mmfdb_session()
        if session is None:
            raise RuntimeError("MMFDB output requires an authenticated session.")

        normalized_paths = [path.resolve() for path in paths if path.is_file()]
        sample_ids = {sample_id for path in normalized_paths if (sample_id := _sample_id_for_raw_path(db, path))}
        sample_id = self._selected_sample_id()
        if not sample_id and len(sample_ids) == 1:
            sample_id = next(iter(sample_ids))
        if not sample_id or any(_sample_id_for_raw_path(db, path) is None for path in normalized_paths):
            selected = show_sample_picker_dialog(db=db, parent=self)
            if not selected:
                raise RuntimeError("MMFDB output requires a registered sample for the raw data.")
            sample_id = selected

        source_artifact_ids: dict[str, str] = {}
        selected_setup = self.wizard.comboBox.currentText()
        setup_id = self._ensure_selected_setup_in_mmfdb(db, session)
        for path in normalized_paths:
            artifact_id = _raw_artifact_id_for_path(db, path)
            if not artifact_id:
                artifact_id = _register_raw_input_for_sample(
                    db=db,
                    path=path,
                    sample_id=sample_id,
                    filetype=self._selected_filetype,
                    selected_setup=selected_setup,
                    setup_id=setup_id,
                    session=session,
                )
            if artifact_id:
                source_artifact_ids[str(path)] = artifact_id

        return {
            "enabled": True,
            "sample_id": sample_id,
            "source_artifact_ids": source_artifact_ids,
            "register_missing_inputs": True,
            "setup_id": setup_id,
        }

    def _display_frame_set(
        self,
        frames: list,
        settings: AnalysisSettings,
        file_indices: list[int] | None = None,
    ) -> bool:
        """Display stacked burst tables and histogram data for selected files."""
        if not frames:
            return False
        indexed_frames = []
        for index, frame in enumerate(frames):
            # Converted at the entry: `concat_stores` below refuses a frame, and
            # a cached result may still be one.
            from chisurf.core.fio.fluorescence.burst_container import as_table

            # `.copy()` is load-bearing: "File Idx" is added below, and
            # `as_table` hands a store straight back — so without it the
            # *cached* result would grow a column every time it is displayed.
            tagged = as_table(frame).copy()
            which = (
                file_indices[index]
                if file_indices is not None and index < len(file_indices)
                else index
            )
            tagged["File Idx"] = np.full(row_count(tagged), which, dtype=np.int64)
            indexed_frames.append(tagged)
        combined = concat_stores(indexed_frames)
        ui_frame = make_ui_dataframe(combined)
        # "File Idx" first, then the UI columns in their declared order, then
        # whatever else the table carries.
        present = column_names(ui_frame)
        order = (
            [c for c in ("File Idx",) if c in present]
            + [c for c in UI_COLUMNS if c in present and c != "File Idx"]
            + [c for c in present if c not in UI_COLUMNS and c != "File Idx"]
        )
        ui_frame = take_columns(ui_frame, order)
        self._last_frame = ui_frame
        self._last_settings = settings
        self._last_bur_frames = frames
        self._fill_table(ui_frame)
        self._populate_feature_combo(ui_frame)
        self.update_histogram()
        return True

    def _show_selected_file_result(self, path: Path, settings: AnalysisSettings) -> bool:
        """Display cached burst table and histogram data for one selected file."""
        frame = self._frame_for_path(path)
        if frame is None:
            return False
        return self._display_frame_set([frame], settings, [self._file_index_for_path(path)])

    def _analyze_file_frame(self, path: Path, settings: AnalysisSettings) -> tuple:
        """Analyze one selected file and cache its burst table."""
        settings_dict = asdict(settings) if settings else {}
        windows = getattr(self.wizard, "windows", None)
        detectors = getattr(self.wizard, "detectors", None)
        self._status_bar.showMessage(f"Analyzing {path.name}...")
        result = self._client.analyze_files(
            [path],
            settings=settings_dict,
            windows=windows,
            detectors=detectors,
            filetype=self._selected_filetype,
            legacy_output=False,
            selected_setup=self.wizard.comboBox.currentText(),
            legacy_parameters=self._legacy_parameters(),
            mmfdb=None,
        )
        frame = self._frame_from_result(path, result.get("dataframes", {}))
        self._last_frames_by_file[path.resolve()] = frame
        metadata = result.get("metadata", {})
        if result.get("warnings"):
            metadata = dict(metadata)
            metadata["warnings"] = result["warnings"]
        return frame, metadata

    def _analyze_selected_file(self, path: Path, settings: AnalysisSettings) -> None:
        """Analyze and display burst table and histogram data for one file."""
        frame, metadata = self._analyze_file_frame(path, settings)
        self._display_frame_set([frame], settings, [self._file_index_for_path(path)])
        self._last_result = {"metadata": metadata, "settings": settings}
        self.summary.setPlainText(json.dumps(metadata | {"settings": asdict(settings)}, indent=2, default=str))

    def _analyze_selected_files(self, paths: list[Path], settings: AnalysisSettings) -> None:
        """Analyze and stack burst tables for multiple selected files."""
        frames: list = []
        metadata: dict[str, Any] = {"n_files": 0, "n_bursts": 0, "n_photons": 0, "n_selected": 0}
        for path in paths:
            frame, file_metadata = self._analyze_file_frame(path, settings)
            frames.append(frame)
            metadata["n_files"] += 1
            metadata["n_bursts"] += int(file_metadata.get("n_bursts", 0))
            metadata["n_photons"] += int(file_metadata.get("n_photons", 0))
            metadata["n_selected"] += int(file_metadata.get("n_selected", 0))
        file_indices = [self._file_index_for_path(path) for path in paths]
        self._display_frame_set(frames, settings, file_indices)
        self._last_result = {"metadata": metadata, "settings": settings}
        self.summary.setPlainText(json.dumps(metadata | {"settings": asdict(settings)}, indent=2, default=str))

    def _update_selected_files(self, paths: list[Path], settings: AnalysisSettings) -> None:
        """Update cached results or analyze selected files, then load diagnostics."""
        frames: list = []
        missing: list[Path] = []
        for path in paths:
            frame = self._frame_for_path(path)
            if frame is None:
                missing.append(path)
            else:
                frames.append(frame)
        for path in missing:
            frame, _metadata = self._analyze_file_frame(path, settings)
            frames.append(frame)
        file_indices = [self._file_index_for_path(path) for path in paths]
        self._display_frame_set(frames, settings, file_indices)
        if paths:
            self._load_tttr_for_plots(paths, settings)

    def _safe_getattr(self, name: str, default: Any = None) -> Any:
        """Return an attribute value while tolerating uninitialized Qt objects."""
        try:
            return getattr(self, name)
        except RuntimeError:
            return default

    def _file_index_for_path(self, path: Path) -> int:
        """Return the queued file-list index for ``path``."""
        file_paths = self._safe_getattr("_file_paths", None)
        if not file_paths:
            return 0
        resolved = path.resolve()
        for index, queued_path in enumerate(file_paths):
            if queued_path == resolved or queued_path == path:
                return index
        return 0

    def _selected_file_paths_from_list(self) -> list[Path]:
        """Return queued paths for the currently selected file-list items."""
        selected_items = self.file_list.selectedItems()
        paths: list[Path] = []
        for item in selected_items:
            path = Path(item.text())
            if path in self._file_paths or path.resolve() in self._file_paths:
                paths.append(path)
        return paths

    def add_files(self) -> None:
        """Open a file dialog and add TTTR files to the analysis queue."""
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select TTTR files",
            "",
            TTTR_FILE_FILTER,
        )
        self._add_paths([Path(path) for path in paths])

    def _add_paths(self, paths: list[Path]) -> None:
        """Add files and TTTR-containing folders to the file list."""
        for path in paths:
            if path.is_dir():
                self._file_paths.extend(
                    sorted(
                        child.resolve()
                        for child in path.iterdir()
                        if child.is_file() and child.suffix.lower() in TTTR_EXTENSIONS
                    )
                )
            else:
                self._file_paths.append(path.resolve())
        self._refresh_file_list()

    def _on_filter_settings_changed(self) -> None:
        """Handle filter parameter changes by reloading diagnostics and updating plots."""
        try:
            if not self.file_list or self.file_list is None:
                return
            selected_paths = self._selected_file_paths_from_list()
            if not selected_paths:
                selected_paths = self._file_paths[:1]
            if not selected_paths:
                return

            settings = self._settings_from_controls()
            self._analyze_selected_files(selected_paths, settings)
            self._load_tttr_for_plots(selected_paths, settings)
        except Exception as exc:
            self._status_bar.showMessage(f"Error updating plots after filter change: {exc}")
            _LOG.error("error updating plots after filter change", error=str(exc))

    def _restart_search(self) -> None:
        """Search the bursts again even though nothing changed."""
        self.analyze_files(force=True)

    def _flag_restart(self, on: bool) -> None:
        """Draw attention to Recompute exactly when a search was skipped.

        Read from the instance dict rather than with ``getattr``: the gate is
        exercised on tools built without ``__init__`` (headless service tests),
        where any attribute miss reaches PyQt's fallback and raises.
        """
        button = self.__dict__.get("_act_restart")
        if button is not None:
            flag_attention(button, on)

    def analyze_files(self, *, force: bool = False) -> None:
        """Run the burst selection over every selected file, off the GUI thread.

        Skipped when the files and every setting are identical to the search
        whose result is already displayed; ``force=True`` searches regardless.

        The whole batch is one backend call, so the window used to freeze for its
        entire duration behind a bar that went 0 % then 100 %. Everything the
        call needs is read here, on the GUI thread; the result is turned into
        frames and plots in :meth:`_analysis_finished`.
        """
        if not self._file_paths:
            self.summary.setPlainText("No TTTR files selected.")
            return
        settings = self._settings_from_controls()
        if not settings.output_formats and not self._mmfdb_output_selected():
            self.summary.setPlainText("No output format selected.")
            return
        try:
            mmfdb_context = self._prepare_mmfdb_context_for_paths(self._file_paths)
        except RuntimeError as exc:
            self.summary.setPlainText(str(exc))
            return

        legacy_parameters = self._legacy_parameters()
        if hasattr(self.wizard, "decay_coarse"):
            legacy_parameters.setdefault("decay_coarse", self.wizard.decay_coarse)
        request = dict(
            settings=asdict(settings) if settings else {},
            windows=getattr(self.wizard, "windows", None),
            detectors=getattr(self.wizard, "detectors", None),
            filetype=self._selected_filetype,
            legacy_output=True,
            selected_setup=self.wizard.comboBox.currentText(),
            legacy_parameters=legacy_parameters,
            mmfdb=mmfdb_context,
        )
        # Searching bursts in every photon of every file is the longest single
        # operation in the workflow, and the shell asks for it on every Next.
        # A request identical to the one that produced what is on screen is
        # answered by what is on screen.
        fingerprint = analysis_cache.fingerprint(
            self._file_paths,
            {**request, "_read_context": analysis_cache.photon_read_context()},
            extra=analysis_cache.algorithm_tag(
                "burst_selection", ALGORITHM_VERSION, "tttrlib"
            ),
        )
        if (
            not force
            and self._has_processed
            and self._result_cache.matches(fingerprint)
        ):
            self.summary.setPlainText(
                "Unchanged — kept the previous burst search "
                "(same files, same settings; nothing re-searched).\n"
                "Press 🔁 Restart to search them again anyway."
            )
            self._flag_restart(True)
            return
        self._flag_restart(False)
        self._running_fingerprint = fingerprint

        self.Error.clear()
        ChiSurfProgress.run(
            self, f"Processing {len(self._file_paths)} file(s)...",
            self._analysis_worker, args=(list(self._file_paths), request),
            maximum=len(self._file_paths), title="Burst Selection", owner=self,
            on_result=lambda result: self._analysis_finished(result, settings),
            on_error=self.Error.analysis_failed,
        )

    def _analysis_worker(self, paths, request, task):
        """Worker: one backend call for the whole batch, reporting per-file progress.

        One file is the natural chunk on this path: the backend call reports
        after each file finishes rather than only at the very end, so a
        multi-file batch shows the bar actually advancing instead of a single
        busy spinner for the whole run. A single very large (e.g. merged
        multi-measurement) file still reports only once, at completion --
        the burst search itself has no internal chunking to report through.
        """

        def _on_file_done(done: int, total: int, path: str) -> None:
            task.set_progress(done, f"{Path(path).name} ({done}/{total})")

        return self._client.analyze_files(paths, progress_callback=_on_file_done, **request)

    def _analysis_finished(self, result: dict, settings: AnalysisSettings) -> None:
        """Back on the GUI thread with the batch result: build frames and plots."""
        self._last_service_result = result
        frames: list = []
        frames_by_file: dict = {}
        metadata: dict[str, Any] = {
            "n_files": len(self._file_paths), "n_bursts": 0,
            "n_photons": 0, "n_selected": 0,
        }
        dataframes = result.get("dataframes", {})
        for path in self._file_paths:
            frame = self._frame_from_result(path, dataframes)
            frames.append(frame)
            frames_by_file[path.resolve()] = frame
        metadata.update(result.get("metadata", {}))
        if result.get("warnings"):
            metadata["warnings"] = result["warnings"]
            _LOG.warning("MMFDB registration warnings", warnings=result["warnings"])
        metadata["n_files"] = len(frames)

        if frames:
            combined = concat_stores(frames)
            self._last_frames_by_file = frames_by_file
            self._last_frame = combined
            self._last_settings = settings
            self._last_bur_frames = frames
            selected_paths = self._selected_file_paths_from_list()
            if not selected_paths:
                selected_paths = self._file_paths[:1]
            selected_frames = [frame for path in selected_paths if (frame := self._frame_for_path(path)) is not None]
            selected_indices = [self._file_index_for_path(path) for path in selected_paths]
            if selected_frames:
                self._display_frame_set(selected_frames, settings, selected_indices)
            elif self._file_paths:
                self._display_frame_set([frames_by_file[self._file_paths[0]]], settings, [0])
            self._load_tttr_for_plots(selected_paths if selected_paths else self._file_paths[:1], settings)
            self.update_burst_plots()
            self._has_processed = True
            if self._running_fingerprint is not None:
                self._result_cache.remember(self._running_fingerprint)
        else:
            self.table.setRowCount(0)
            self._last_frame = None
            self._last_settings = settings
            self._last_bur_frames.clear()
            self._last_frames_by_file.clear()
            self._last_tttr = None
            self._last_selected = None
            self._last_start_stop = None
            self._last_diagnostic_path = None
            self._last_diagnostics.clear()
            self._clear_plots()
            self._has_processed = False
            self._result_cache.invalidate()

        self._last_result = {"metadata": metadata, "settings": settings}
        self.summary.setPlainText(json.dumps(metadata | {"settings": asdict(settings)}, indent=2, default=str))

    def _load_first_tttr_for_plots(self, settings: AnalysisSettings) -> None:
        """Load the first TTTR file and selected mask for diagnostic plots."""
        if not self._file_paths:
            return
        path = self._file_paths[0]
        try:
            settings_dict = asdict(settings) if settings else {}
            diag = self._client.load_diagnostics(path, settings_dict)
            if diag and "tttr" in diag:
                self._last_tttr = diag["tttr"]
                self._last_selected = diag["selected"]
                self._last_start_stop = diag["start_stop"]
                self._last_diagnostic_path = path
                self._last_diagnostics = [
                    {
                        "path": path,
                        "tttr": diag["tttr"],
                        "selected": diag["selected"],
                        "start_stop": diag["start_stop"],
                    }
                ]
            else:
                raise ValueError("diagnostics returned no data")
        except Exception as exc:
            self._last_tttr = None
            self._last_selected = None
            self._last_start_stop = None
            self._last_diagnostic_path = None
            self._last_diagnostics.clear()
            self.summary.append(f"Diagnostic plots unavailable for {path}: {exc}")

    def save_current_bur(self) -> None:
        """Save the last API result as a ChiSurf-compatible .bur file."""
        if self._last_result is None:
            self.summary.setPlainText("No analysis result to save.")
            return
        if not self._file_paths:
            self.summary.setPlainText("No TTTR files selected.")
            return
        if not self._last_bur_frames:
            self.summary.setPlainText("No burst table available to save.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save burst table",
            str(self._file_paths[0].with_suffix(".bur")),
            "Burst files (*.bur)",
        )
        if not path:
            return
        combined = concat_stores(self._last_bur_frames)
        self._client.save_bur(combined, Path(path))
        self.summary.setPlainText(f"Saved {path}")

    def clear(self) -> None:
        """Clear selected files and result views without resetting analysis controls."""
        self._file_paths.clear()
        self._last_result = None
        self._last_bur_frames.clear()
        self._last_frames_by_file.clear()
        self._last_frame = None
        self._last_settings = None
        self._last_tttr = None
        self._last_selected = None
        self._last_start_stop = None
        self._last_diagnostic_path = None
        self._last_diagnostics.clear()
        self._has_processed = False
        self._result_cache.invalidate()
        self._refresh_file_list()
        self.table.setRowCount(0)
        self._clear_plots()
        self.summary.clear()
        self.gmm_summary.clear()

    def update_histogram(self) -> None:
        """Update the histogram plot without fitting GMMs by default."""
        if self._last_frame is None:
            self.histogram_plot.clear()
            self.gmm_summary.clear()
            return
        feature = self.feature_combo.currentText()
        if feature not in column_names(self._last_frame):
            self.histogram_plot.clear()
            return
        data = histogram_data_from_frame(self._last_frame, feature)
        if data.size == 0:
            self.histogram_plot.clear()
            self.gmm_summary.clear()
            return
        min_value, max_value = self._valid_histogram_range(data)
        counts, edges = np.histogram(data, bins=int(self.hist_bins_spin.value()), range=(min_value, max_value))
        centers = (edges[:-1] + edges[1:]) / 2.0
        width = edges[1] - edges[0]
        self.histogram_plot.clear()
        self.histogram_plot.setLabel("bottom", feature)
        self.histogram_plot.setLabel("left", "Frequency")
        self.histogram_plot.getPlotItem().setLogMode(bool(self.hist_log_y_check.isChecked()), False)
        self.histogram_plot.addItem(pg.BarGraphItem(x=centers, height=counts, width=width, brush="b", pen="k", alpha=0.7))
        if self._fit_gmm_on_update:
            self._plot_gmm(data, min_value, max_value, counts)
        else:
            self.gmm_summary.clear()

    def update_burst_plots(self) -> None:
        """Update diagnostic plots by iterating over analyzed TTTR files."""
        try:
            _LOG.debug("update_burst_plots called")
            diagnostics = self._safe_getattr("_last_diagnostics", None)
            if not diagnostics and self._safe_getattr("_last_tttr", None) is not None and self._safe_getattr("_last_selected", None) is not None:
                diagnostics = [
                    {
                        "path": self._safe_getattr("_last_diagnostic_path", None),
                        "tttr": self._last_tttr,
                        "selected": self._last_selected,
                        "start_stop": self._safe_getattr("_last_start_stop", None),
                    }
                ]
            if not diagnostics:
                _LOG.debug("diagnostic plot update skipped: diagnostics are missing")
                self._clear_burst_plots()
                return
            selected_masks = [diag["selected"].astype(bool) for diag in diagnostics]
            total_photons = int(sum(len(selected) for selected in selected_masks))
            if total_photons == 0:
                _LOG.debug("diagnostic plot update skipped: selection is empty")
                self._clear_burst_plots()
                return
            self._sync_plot_range_controls(total_photons)
            start = max(0, int(self.plot_min_spin.value()))
            stop = min(total_photons, int(self.plot_max_spin.value()) + 1)
            if stop <= start:
                stop = min(total_photons, start + 1)
            show_all_photons = self._show_all_photons()
            show_selected_photons = self._show_selected_photons()
            _LOG.debug(
                "updating diagnostic plots",
                visible_photons=int(stop - start),
                total_photons=total_photons,
                show_all_photons=show_all_photons,
                show_selected_photons=show_selected_photons,
            )
            show_dt = self._dock_widget_is_present(getattr(self, "dt_plot", None))
            show_filter = self._plot_widget_is_docked("Filter")
            show_filter_settings = self._dock_widget_is_present(getattr(self, "filter_settings_panel", None))
            d_t_visible: list[np.ndarray] = []
            # The budget belongs to the *plot*, so it is split across every
            # curve drawn into it -- one per file per visible layer. Splitting
            # by file count alone (which is what this did) let a two-layer,
            # ten-file diagnostic draw twenty times the configured number while
            # each individual call still looked bounded. Only the *drawn*
            # arrays are thinned; selection, ranges and everything else below
            # still see the untouched, full-resolution data.
            plot_point_budget = per_curve_budget(
                self._max_plot_points(),
                len(diagnostics) * max(1, int(show_all_photons) + int(show_selected_photons)),
            )

            if show_dt:
                self.dt_plot.clear()
            if show_filter:
                self.filter_plot.clear()

            offsets = self._macro_time_offsets_ms(diagnostics)
            first_visible_range: tuple[int, int, np.ndarray, np.ndarray, np.ndarray, Any, Path | None] | None = None
            photon_offset = 0
            for file_index, (diag, selected) in enumerate(zip(diagnostics, selected_masks, strict=True)):
                local_start = max(0, start - photon_offset)
                local_stop = min(len(selected), stop - photon_offset)
                if local_stop <= local_start:
                    photon_offset += len(selected)
                    continue
                local_indices = np.arange(local_start, local_stop)
                global_indices = local_indices + photon_offset
                selected_slice = selected[local_start:local_stop]
                d_t = self._delta_macro_time_ms(diag["tttr"], offsets[file_index])[local_start:local_stop]
                if first_visible_range is None:
                    first_visible_range = (local_start, local_stop, local_indices, selected_slice, d_t, diag["tttr"], diag.get("path"))
                if show_dt and d_t.size:
                    d_t_visible.append(d_t)
                    if show_all_photons:
                        plot_x, plot_y = thin_for_plot(global_indices, d_t, max_points=plot_point_budget)
                        self.dt_plot.plot(plot_x, plot_y, pen=self._diagnostic_pen(len(d_t_visible)), width=1)
                    if show_selected_photons:
                        plot_x, plot_y = thin_for_plot(
                            global_indices[selected_slice], d_t[selected_slice], max_points=plot_point_budget
                        )
                        self.dt_plot.plot(
                            plot_x,
                            plot_y,
                            pen=self._diagnostic_pen(len(d_t_visible), selected=True),
                            width=_SELECTED_PEN_WIDTH,
                        )
                if show_filter:
                    if show_all_photons:
                        thinned_indices = thin_for_plot(global_indices, max_points=plot_point_budget)
                        self.filter_plot.plot(
                            thinned_indices,
                            np.zeros_like(thinned_indices, dtype=float),
                            pen=self._diagnostic_pen(len(d_t_visible)),
                            stepMode=False,
                        )
                    if show_selected_photons:
                        selected_indices = thin_for_plot(
                            global_indices[selected_slice], max_points=plot_point_budget
                        )
                        self.filter_plot.plot(
                            selected_indices,
                            np.ones_like(selected_indices, dtype=float),
                            pen=self._diagnostic_pen(len(d_t_visible), selected=True),
                            width=_SELECTED_PEN_WIDTH,
                        )
                photon_offset += len(selected)

            if show_dt and d_t_visible:
                self._set_log_dt_range(self.dt_plot, np.concatenate(d_t_visible))
                _LOG.debug("dT plot updated")

            if show_filter:
                self.filter_plot.setYRange(-0.1, 1.1)
                _LOG.debug("filter plot updated")

            if show_filter_settings and first_visible_range is not None:
                local_start, local_stop, local_indices, selected_slice, d_t, tttr, path = first_visible_range
                self._update_filter_settings_diagnostics(local_start, local_stop, local_indices, selected_slice, d_t, tttr, path)

            if self._plot_widget_is_docked("MCS"):
                self._update_mcs_plot(start, stop)
                _LOG.debug("MCS plot updated")

            if self._plot_widget_is_docked("Decay"):
                self._update_decay_plot()
                _LOG.debug("decay plot updated")

            if self._plot_widget_is_docked("Burst length"):
                self._update_burst_length_plot()
                _LOG.debug("burst-length plot updated")
        except RuntimeError as exc:
            self._status_bar.showMessage(f"Error updating plots: {exc}")
            _LOG.error("runtime error while updating burst plots", error=str(exc))
        except Exception as exc:
            self._status_bar.showMessage(f"Error updating plots: {exc}")
            _LOG.error("error while updating burst plots", error=str(exc))

    def _show_all_photons(self) -> bool:
        """Return whether all-photon diagnostic layers should be shown."""
        try:
            check = getattr(self, "show_all_photons_check", None)
        except RuntimeError:
            check = None
        if check is None:
            try:
                check = getattr(self, "mcs_show_all_check", None)
            except RuntimeError:
                check = None
        return bool(check is None or check.isChecked())

    def _show_selected_photons(self) -> bool:
        """Return whether selected-photon diagnostic layers should be shown."""
        try:
            check = getattr(self, "show_selected_photons_check", None)
        except RuntimeError:
            check = None
        if check is None:
            try:
                check = getattr(self, "mcs_show_selected_check", None)
            except RuntimeError:
                check = None
        return bool(check is None or check.isChecked())

    def _diagnostic_pen(self, file_index: int, selected: bool = False) -> tuple[int, int, int, int]:
        """Return a diagnostic plot color for a file and selection layer."""
        if selected:
            return (0, 255, 255, 230)
        palette = ((255, 255, 0), (255, 180, 0), (255, 0, 255), (180, 120, 255), (0, 255, 0), (255, 0, 0))
        base = palette[file_index % len(palette)]
        return (base[0], base[1], base[2], 70)

    def _update_mcs_plot(self, start: int, stop: int) -> None:
        """Update the MCS intensity trace plot file-by-file."""
        diagnostics = self._safe_getattr("_last_diagnostics", None)
        if not diagnostics and self._safe_getattr("_last_tttr", None) is not None and self._safe_getattr("_last_selected", None) is not None:
            diagnostics = [
                {
                    "path": self._safe_getattr("_last_diagnostic_path", None),
                    "tttr": self._last_tttr,
                    "selected": self._last_selected,
                    "start_stop": self._safe_getattr("_last_start_stop", None),
                }
            ]
        if not diagnostics:
            self.mcs_plot.clear()
            return
        bin_width = float(self.mcs_bin_spin.value()) / 1000.0
        show_all = self._show_all_photons()
        show_selected = self._show_selected_photons()
        self.mcs_plot.clear()
        if not show_all and not show_selected:
            return
        offsets_ms = self._macro_time_offsets_ms(diagnostics)
        offset = 0
        plotted = False
        plot_point_budget = per_curve_budget(
            self._max_plot_points(),
            len(diagnostics) * max(1, int(show_all) + int(show_selected)),
        )
        for file_index, diag in enumerate(diagnostics):
            selected = diag["selected"].astype(bool)
            local_start = max(0, start - offset)
            local_stop = min(len(selected), stop - offset)
            if local_stop <= local_start:
                offset += len(selected)
                continue
            tttr = diag["tttr"]
            if show_all:
                try:
                    range_indices = np.arange(local_start, local_stop)
                    trace_all = tttr[range_indices].get_intensity_trace(time_window_length=bin_width)
                    time_all = np.arange(len(trace_all)) * bin_width + offsets_ms[file_index] / 1000.0
                    time_all, trace_all = thin_for_plot(time_all, trace_all, max_points=plot_point_budget)
                    self.mcs_plot.plot(
                        time_all,
                        trace_all,
                        pen=pg.mkPen(self._diagnostic_pen(file_index), width=1),
                    )
                    plotted = True
                except Exception:
                    self.mcs_plot.plot([], [], pen=pg.mkPen(self._diagnostic_pen(file_index), width=1))
            if show_selected:
                selected_indices = np.where(selected[local_start:local_stop])[0] + local_start
                try:
                    if selected_indices.size:
                        trace_selected = tttr[selected_indices].get_intensity_trace(time_window_length=bin_width)
                        time_selected = np.arange(len(trace_selected)) * bin_width + offsets_ms[file_index] / 1000.0
                        time_selected, trace_selected = thin_for_plot(
                            time_selected, trace_selected, max_points=plot_point_budget
                        )
                        self.mcs_plot.plot(
                            time_selected,
                            trace_selected,
                            pen=pg.mkPen(self._diagnostic_pen(file_index, selected=True), width=_SELECTED_PEN_WIDTH),
                        )
                        plotted = True
                    else:
                        self.mcs_plot.plot([], [], pen=pg.mkPen(self._diagnostic_pen(file_index, selected=True), width=_SELECTED_PEN_WIDTH))
                except Exception:
                    self.mcs_plot.plot([], [], pen=pg.mkPen(self._diagnostic_pen(file_index, selected=True), width=_SELECTED_PEN_WIDTH))
            offset += len(selected)
        if not plotted:
            self.mcs_plot.plot([], [], pen=pg.mkPen((255, 255, 255, 120), width=1))
        self.mcs_plot.setLabel("bottom", "Time (s)")
        self.mcs_plot.setLabel("left", "Intensity")

    def _update_decay_plot(self) -> None:
        """Update the microtime decay plot file-by-file."""
        diagnostics = self._safe_getattr("_last_diagnostics", None)
        if not diagnostics and self._safe_getattr("_last_tttr", None) is not None and self._safe_getattr("_last_selected", None) is not None:
            diagnostics = [
                {
                    "path": self._safe_getattr("_last_diagnostic_path", None),
                    "tttr": self._last_tttr,
                    "selected": self._last_selected,
                    "start_stop": self._safe_getattr("_last_start_stop", None),
                }
            ]
        if not diagnostics:
            self.decay_plot.clear()
            return
        coarse = int(self.decay_bins_spin.value())
        show_all = self._show_all_photons()
        show_selected = self._show_selected_photons()
        self.decay_plot.clear()
        if not show_all and not show_selected:
            return
        plotted = False
        for file_index, diag in enumerate(diagnostics):
            tttr = diag["tttr"]
            selected = diag["selected"].astype(bool)
            selected_indices = np.where(selected)[0]
            if show_all:
                try:
                    y_all, x_all = tttr.get_microtime_histogram(coarse)
                    self._plot_decay(y_all, x_all, self._diagnostic_pen(file_index))
                    plotted = True
                except Exception:
                    self.decay_plot.plot([], [], pen=pg.mkPen(self._diagnostic_pen(file_index), width=1))
            if show_selected:
                try:
                    if selected_indices.size:
                        y_selected, x_selected = tttr[selected_indices].get_microtime_histogram(coarse)
                        self._plot_decay(y_selected, x_selected, self._diagnostic_pen(file_index, selected=True))
                        plotted = True
                    else:
                        self.decay_plot.plot([], [], pen=pg.mkPen(self._diagnostic_pen(file_index, selected=True), width=1))
                except Exception:
                    self.decay_plot.plot([], [], pen=pg.mkPen(self._diagnostic_pen(file_index, selected=True), width=1))
        if not plotted:
            self.decay_plot.plot([], [], pen=pg.mkPen((255, 255, 255, 120), width=1))

    def _plot_decay(self, y: np.ndarray, x: np.ndarray, pen: Any) -> None:
        """Plot decay histogram data after trimming trailing zeros."""
        positive = np.where(y > 0)[0]
        if positive.size:
            last = int(positive[-1]) + 1
            x = x[:last] * 1e9
            y = y[:last]
            self.decay_plot.plot(x, y, pen=pg.mkPen(pen, width=1))

    def _update_burst_length_plot(self) -> None:
        """Update the burst duration histogram file-by-file."""
        self.burst_plot.clear()
        if not self._show_selected_photons():
            self.burst_plot.addItem(pg.TextItem("Selected photons hidden", anchor=(0.5, 0.5), color="w"))
            return
        diagnostics = self._safe_getattr("_last_diagnostics", None)
        if not diagnostics and self._safe_getattr("_last_tttr", None) is not None and self._safe_getattr("_last_selected", None) is not None:
            diagnostics = [
                {
                    "path": self._safe_getattr("_last_diagnostic_path", None),
                    "tttr": self._last_tttr,
                    "selected": self._last_selected,
                    "start_stop": self._safe_getattr("_last_start_stop", None),
                }
            ]
        if not diagnostics:
            self.burst_plot.addItem(pg.TextItem("No burst data available", anchor=(0.5, 0.5), color="w"))
            return
        total = 0
        plotted = False
        bins = int(self.burst_bins_spin.value())
        for file_index, diag in enumerate(diagnostics):
            start_stop = diag.get("start_stop")
            if start_stop is None or len(start_stop) == 0:
                continue
            durations = self._burst_durations_ms_for_diag(diag)
            if durations.size == 0:
                continue
            counts, edges = np.histogram(durations, bins=bins)
            self.burst_plot.addItem(
                pg.BarGraphItem(
                    x0=edges[:-1],
                    x1=edges[1:],
                    y0=0,
                    y1=counts,
                    brush=pg.mkBrush(*self._diagnostic_pen(file_index, selected=True)),
                    pen="w",
                )
            )
            total += int(np.sum(counts))
            plotted = True
        if not plotted:
            self.burst_plot.addItem(pg.TextItem("No burst data available", anchor=(0.5, 0.5), color="w"))
            return
        self.burst_plot.setLabel("bottom", "Burst duration", units="ms")
        self.burst_plot.setLabel("left", "Frequency")
        self.burst_plot.addItem(pg.TextItem(f"Total bursts: {total}", anchor=(0, 0), color="w"))

    def _burst_durations_ms_for_diag(self, diag: dict[str, Any]) -> np.ndarray:
        """Return burst durations in milliseconds for one diagnostic entry."""
        tttr = diag["tttr"]
        start_stop = diag.get("start_stop")
        if tttr is None or start_stop is None:
            return np.array([], dtype=float)
        macro_times = np.asarray(tttr.macro_times)
        if macro_times.size == 0:
            return np.array([], dtype=float)
        resolution_ms = float(tttr.header.macro_time_resolution) * 1000.0
        durations: list[float] = []
        for start, stop in np.asarray(start_stop, dtype=int):
            if 0 <= start < stop < macro_times.size:
                durations.append(float(macro_times[stop] - macro_times[start]) * resolution_ms)
        return np.asarray(durations, dtype=float)

    def _burst_durations_ms(self) -> np.ndarray:
        """Return current burst durations in milliseconds for the first diagnostic file."""
        diagnostics = self._safe_getattr("_last_diagnostics", None)
        if not diagnostics and self._safe_getattr("_last_tttr", None) is not None and self._safe_getattr("_last_start_stop", None) is not None:
            return self._burst_durations_ms_for_diag(
                {
                    "path": self._safe_getattr("_last_diagnostic_path", None),
                    "tttr": self._last_tttr,
                    "selected": self._safe_getattr("_last_selected", None),
                    "start_stop": self._last_start_stop,
                }
            )
        if not diagnostics:
            return np.array([], dtype=float)
        return self._burst_durations_ms_for_diag(diagnostics[0])

    def _valid_histogram_range(self, data: np.ndarray) -> tuple[float, float]:
        """Return valid histogram bounds, falling back to data range."""
        min_value = float(self.hist_min_spin.value())
        max_value = float(self.hist_max_spin.value())
        if min_value >= max_value:
            min_value = float(np.min(data))
            max_value = float(np.max(data))
            if min_value == max_value:
                min_value -= 0.5
                max_value += 0.5
        return min_value, max_value

    def _set_histogram_range_to_data(self) -> None:
        """Set histogram min/max controls to the current feature range."""
        if self._last_frame is None:
            return
        feature = self.feature_combo.currentText()
        if feature not in column_names(self._last_frame):
            return
        data = histogram_data_from_frame(self._last_frame, feature)
        if data.size == 0:
            return
        min_value = float(np.min(data))
        max_value = float(np.max(data))
        if min_value == max_value:
            min_value -= 0.5
            max_value += 0.5
        self.hist_min_spin.blockSignals(True)
        self.hist_max_spin.blockSignals(True)
        self.hist_min_spin.setValue(min_value)
        self.hist_max_spin.setValue(max_value)
        self.hist_min_spin.blockSignals(False)
        self.hist_max_spin.blockSignals(False)
        self.update_histogram()

    def _fit_gmm(self) -> None:
        """Fit and plot a GMM once, then return to normal histogram updates."""
        self._fit_gmm_on_update = True
        try:
            self.update_histogram()
        finally:
            self._fit_gmm_on_update = False

    def _show_gmm_settings(self) -> None:
        """Open the advanced GMM settings dialog and refit on accept."""
        dialog = GMMSettingsDialog(self, self.gmm_settings)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.gmm_settings = dialog.get_settings()
            self._fit_gmm()

    def _gmm_model(self, n_components: int):
        """Build a GaussianMixture using the configured advanced settings."""
        from chisurf.core.ml import GaussianMixture

        s = self.gmm_settings
        return GaussianMixture(
            n_components=n_components,
            covariance_type=s["covariance_type"],
            random_state=s["random_state"],
            max_iter=s["max_iter"],
            n_init=s["n_init"],
            tol=s["tol"],
            reg_covar=s["reg_covar"],
        )

    def _plot_gmm(self, data: np.ndarray, min_value: float, max_value: float, counts: np.ndarray) -> None:
        """Fit and plot an optional Gaussian mixture model."""
        try:
            from chisurf.core.ml import GaussianMixture  # noqa: F401  (availability check)
        except Exception as exc:
            self.gmm_summary.setPlainText(f"GMM fitting failed: {exc}")
            return
        n_components = int(self.gmm_components_spin.value())
        if self.gmm_auto_components_check.isChecked() and n_components == 0 and data.size > 1:
            max_components = min(int(self.gmm_settings["max_components"]), data.size)
            bic_scores = []
            for components in range(1, max_components + 1):
                model = self._gmm_model(components)
                model.fit(data.reshape(-1, 1))
                bic_scores.append(model.bic(data.reshape(-1, 1)))
            n_components = int(np.argmin(bic_scores) + 1)
        if n_components <= 0 or data.size < n_components:
            self.gmm_summary.setPlainText("GMM fitting skipped: not enough data points or zero components.")
            return
        x_fit = np.linspace(min_value, max_value, 200).reshape(-1, 1)
        try:
            model = self._gmm_model(n_components)
            model.fit(data.reshape(-1, 1))
            y_fit = np.exp(model.score_samples(x_fit))
            if np.max(y_fit) > 0:
                scale = float(np.max(counts)) / float(np.max(y_fit))
            else:
                scale = 1.0
            self.histogram_plot.plot(x_fit.ravel(), y_fit * scale, pen=pg.mkPen("r", width=2), name="GMM Fit")
            for index in range(n_components):
                mean = float(model.means_[index, 0])
                variance = float(model.covariances_[index, 0, 0])
                weight = float(model.weights_[index])
                component = weight * np.exp(-0.5 * ((x_fit.ravel() - mean) ** 2) / variance) / np.sqrt(2 * np.pi * variance) * scale
                self.histogram_plot.plot(x_fit.ravel(), component, pen=pg.mkPen(pg.intColor(index, hues=n_components), width=1, style=QtCore.Qt.PenStyle.DashLine), name=f"Gaussian {index + 1}")
            self.histogram_plot.addLegend()
            self.gmm_summary.setPlainText(self._gmm_table(model, n_components))
        except Exception as exc:
            self.gmm_summary.setPlainText(f"GMM fitting failed: {exc}")

    def _gmm_table(self, model: Any, n_components: int) -> str:
        """Return a text table for GMM parameters."""
        lines = ["Gaussian #  Weight  Mean  Std. Dev.", "-" * 36]
        for index in range(n_components):
            std = float(np.sqrt(model.covariances_[index, 0, 0]))
            lines.append(
                f"{index + 1:<10}  {float(model.weights_[index]):>6.3f}  "
                f"{float(model.means_[index, 0]):>8.3f}  {std:>9.3f}"
            )
        return "\n".join(lines)


    def _update_histogram_if_available(self) -> None:
        """Update the histogram only when analysis data is available."""
        if self._last_frame is not None:
            self.update_histogram()

    def _populate_feature_combo(self, frame) -> None:
        """Populate the feature combo from a GUI table's column names.

        ``column_names(frame)``, not ``frame.columns``: a store's ``columns``
        are ``Column`` objects, not name strings, and comparing one against a
        combo-box item's plain string with ``!=`` raises "truth value of an
        array is ambiguous" the moment the two lists are the same length (a
        combo already populated from an earlier selection).
        """
        current = self.feature_combo.currentText()
        columns = column_names(frame)
        if columns != [self.feature_combo.itemText(index) for index in range(self.feature_combo.count())]:
            self.feature_combo.blockSignals(True)
            self.feature_combo.clear()
            self.feature_combo.addItems(columns)
            index = self.feature_combo.findText(current)
            self.feature_combo.setCurrentIndex(index if index >= 0 else self.feature_combo.findText(PROXIMITY_RATIO_COLUMN))
            self.feature_combo.blockSignals(False)

    def _refresh_file_list(self) -> None:
        """Refresh the visible file list."""
        self.file_list.blockSignals(True)
        try:
            self.file_list.clear()
            for path in self._file_paths:
                self.file_list.addItem(str(path))
        finally:
            self.file_list.blockSignals(False)
        # Auto-select first file if available (after unblocking signals)
        if self.file_list.count() > 0:
            self.file_list.setCurrentRow(0)
        # The destination follows the input, so it changes when the input does.
        try:
            self._sync_output_format_controls()
        except (AttributeError, RuntimeError):
            pass

    def _on_file_selected(self) -> None:
        """Handle file selection in the file list and generate plots for the selected file."""
        try:
            _LOG.debug("file selection changed")
            # Use QTimer.singleShot to defer processing to avoid Qt object deletion issues
            QtCore.QTimer.singleShot(0, self._process_file_selection)
        except Exception as exc:
            self._status_bar.showMessage(f"Error scheduling file selection: {exc}")
            _LOG.error("error scheduling file selection", error=str(exc))

    def _process_file_selection(self) -> None:
        """Process the file selection after a small delay."""
        try:
            _LOG.debug("processing file selection")
            if not self.file_list or self.file_list is None:
                _LOG.debug("file selection skipped: file list is missing")
                return
            selected_paths = self._selected_file_paths_from_list()
            if not selected_paths:
                _LOG.debug("file selection skipped: no queued selected items")
                return
            _LOG.debug("selected file paths resolved", paths=[str(path) for path in selected_paths])
            # Get current settings from wizard if _last_settings is not set
            settings = self._last_settings
            if settings is None:
                _LOG.debug("using current controls for diagnostic settings")
                settings = self._settings_from_controls()
            _LOG.debug("updating selected file results", paths=[str(path) for path in selected_paths])
            self._update_selected_files(selected_paths, settings)
        except Exception as exc:
            self._status_bar.showMessage(f"Error selecting file: {exc}")
            _LOG.error("error selecting file", error=str(exc))

    def _show_file_list_context_menu(self, pos: QtCore.QPoint) -> None:
        """Show context menu for file list."""
        menu = QtWidgets.QMenu(self)

        remove_action = QtWidgets.QAction("Remove selected", self)
        remove_action.triggered.connect(self._remove_selected_files)
        menu.addAction(remove_action)

        clear_action = QtWidgets.QAction("Clear all", self)
        clear_action.triggered.connect(self._clear_file_list)
        menu.addAction(clear_action)

        menu.exec_(self.file_list.mapToGlobal(pos))

    def _remove_selected_files(self) -> None:
        """Remove selected files from the file list."""
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            path = Path(item.text())
            if path in self._file_paths:
                self._file_paths.remove(path)
        self._refresh_file_list()

    def _clear_file_list(self) -> None:
        """Clear all files from the file list."""
        self._file_paths.clear()
        self._refresh_file_list()

    def _load_tttr_for_plots(self, paths: Path | list[Path], settings: AnalysisSettings) -> None:
        """Load TTTR diagnostics file-by-file for diagnostic plots."""
        path_list = [paths] if isinstance(paths, Path) else list(paths)
        if not path_list:
            self.summary.append("Diagnostic plots unavailable: no TTTR files selected.")
            self._status_bar.showMessage("No TTTR files selected for diagnostics.")
            return
        diagnostics: list[dict[str, Any]] = []
        try:
            settings_dict = asdict(settings) if settings else {}
            for path in path_list:
                _LOG.debug("loading TTTR diagnostics", path=str(path))
                _LOG.debug("TTTR diagnostic settings prepared", settings=settings_dict)
                self._status_bar.showMessage(f"Loading diagnostics for {path.name}...")
                diag = self._client.load_diagnostics(path, settings_dict)
                _LOG.debug("TTTR diagnostics loaded", keys=list(diag.keys()) if diag else [])
                if not diag or "tttr" not in diag:
                    _LOG.warning("TTTR diagnostics returned no data", path=str(path))
                    raise ValueError("diagnostics returned no data")
                diag["path"] = path
                diagnostics.append(diag)
            self._last_diagnostics = diagnostics
            first = diagnostics[0]
            self._last_tttr = first["tttr"]
            self._last_selected = first["selected"]
            self._last_start_stop = first["start_stop"]
            self._last_diagnostic_path = first["path"]
            total_photons = sum(int(len(diag["selected"])) for diag in diagnostics)
            # Reset to the whole file only when a *different* set of photons
            # arrived. Diagnostics reload on every filter change too, and
            # resetting there threw away a range the user had narrowed by hand
            # -- change one setting and the plot silently went back to drawing
            # all of them.
            previous_total = self.__dict__.get("_diagnostic_photon_total")
            self._diagnostic_photon_total = total_photons
            self._sync_plot_range_controls(
                total_photons, reset=previous_total != total_photons
            )
            _LOG.debug("TTTR diagnostics assigned; updating plots", paths=[str(path) for path in path_list])
            self._status_bar.showMessage("Updating stacked plots...")
            self.update_burst_plots()
            self._status_bar.showMessage("Ready")
        except Exception as exc:
            first_path = path_list[0] if path_list else Path("unknown")
            _LOG.error("error loading TTTR diagnostics", path=str(first_path), error=str(exc))
            self._last_tttr = None
            self._last_selected = None
            self._last_start_stop = None
            self._last_diagnostic_path = None
            self._last_diagnostics.clear()
            self.summary.append(f"Diagnostic plots unavailable for {first_path}: {exc}")
            self._status_bar.showMessage(f"Error loading {first_path.name}: {exc}")

    def _fill_table(self, frame) -> None:
        """Fill the table widget from a GUI table (a DataStore, not a DataFrame).

        A store keeps each column's own dtype -- unlike a pandas
        ``DataFrame.to_numpy()``, which upcasts a whole int+float table to one
        float64 array. Every numeric cell (int or float) is shown through the
        numeric ``DisplayRole`` here for the same reason that upcast existed:
        so an integer column (e.g. photon counts) still sorts and right-aligns
        as a number instead of rendering as left-aligned text.
        """
        rows = rows_from_table(frame)
        self.table.setRowCount(row_count(frame))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row.values()):
                item = QtWidgets.QTableWidgetItem()
                if isinstance(value, (int, float, np.integer, np.floating)):
                    item.setData(QtCore.Qt.ItemDataRole.DisplayRole, float(value))
                else:
                    item.setText(str(value))
                self.table.setItem(row_index, column_index, item)

    def _clear_plots(self) -> None:
        """Clear all result plots."""
        self._clear_burst_plots()
        self.histogram_plot.clear()
        self.gmm_summary.clear()

    def _clear_burst_plots(self) -> None:
        """Clear diagnostic burst plots."""
        try:
            self.dt_plot.clear()
        except RuntimeError:
            pass
        try:
            self.filter_plot.clear()
        except RuntimeError:
            pass
        try:
            self.mcs_plot.clear()
        except RuntimeError:
            pass
        try:
            self.decay_plot.clear()
        except RuntimeError:
            pass
        try:
            self.burst_plot.clear()
        except RuntimeError:
            pass
        self._clear_filter_settings_diagnostics()

    def _update_filter_settings_diagnostics(
        self,
        start: int,
        stop: int,
        indices: np.ndarray,
        selected_slice: np.ndarray,
        d_t: np.ndarray,
        tttr: Any,
        path: Path | None = None,
    ) -> None:
        """Mirror current file diagnostics into the embedded filter-settings plots.

        Parameters
        ----------
        start : int
            First photon index shown in the diagnostic range.
        stop : int
            One-past-last photon index shown in the diagnostic range.
        indices : numpy.ndarray
            Photon indices for the visible range.
        selected_slice : numpy.ndarray
            Boolean selection mask for the visible range.
        d_t : numpy.ndarray
            Delta macro-time values for the visible range, in milliseconds.
        tttr : object
            TTTR object that produced the visible diagnostic data.
        path : pathlib.Path, optional
            Source file path for the visible diagnostic data.

        """
        try:
            wizard = self.wizard
            path = path or self._safe_getattr("_last_diagnostic_path", None)
            if path is not None:
                resolved_path = str(path.resolve())
                wizard.tttr_objects[resolved_path] = tttr
                wizard.settings["tttr_filenames"] = [resolved_path]
                wizard.lineEdit.setText(resolved_path)
                wizard.spinBox_4.blockSignals(True)
                wizard.spinBox_4.setMaximum(0)
                wizard.spinBox_4.setValue(0)
                wizard.spinBox_4.blockSignals(False)

            wizard.tttr = tttr
            wizard.spinBox_2.blockSignals(True)
            wizard.spinBox_2.setValue(start)
            wizard.spinBox_2.blockSignals(False)
            wizard.spinBox_3.blockSignals(True)
            wizard.spinBox_3.setValue(max(start, stop - 1))
            wizard.spinBox_3.blockSignals(False)

            selected_bool = selected_slice.astype(bool)
            # Thinned like every other raw per-photon layer. This one was
            # handed the *whole* array and was, by measurement, the most
            # expensive widget in the window: 0.29 s per repaint against ~0.3 ms
            # for the tool's own dT plot beside it, which had been thinned.
            show_all = self._show_all_photons()
            show_selected = self._show_selected_photons()
            budget = per_curve_budget(
                self._max_plot_points(), max(1, int(show_all) + 2 * int(show_selected))
            )
            if show_all:
                all_x, all_y = thin_for_plot(indices, d_t, max_points=budget)
                wizard.plot_unselected.setData(x=all_x, y=all_y)
            else:
                wizard.plot_unselected.setData([], [])
            if show_selected:
                sel_x, sel_y = thin_for_plot(
                    indices[selected_bool], d_t[selected_bool], max_points=budget
                )
                wizard.plot_selected.setData(x=sel_x, y=sel_y)
                flag_x, flag_y = thin_for_plot(
                    indices, selected_bool.astype(np.uint8), max_points=budget
                )
                wizard.plot_select.setData(x=flag_x, y=flag_y)
            else:
                wizard.plot_selected.setData([], [])
                wizard.plot_select.setData([], [])
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return

    def _clear_filter_settings_diagnostics(self) -> None:
        """Clear the embedded filter-settings diagnostic plots."""
        try:
            self.wizard.plot_selected.setData([], [])
            self.wizard.plot_unselected.setData([], [])
            self.wizard.plot_select.setData([], [])
            self.wizard.tttr = None
        except (AttributeError, RuntimeError):
            pass

    def _macro_time_offsets_ms(self, diagnostics: list[dict[str, Any]]) -> list[float]:
        """Return per-file macro-time offsets that continue across file boundaries."""
        offsets: list[float] = []
        previous_end: float | None = None
        for diag in diagnostics:
            tttr = diag["tttr"]
            macro_times = getattr(tttr, "macro_times", None)
            if macro_times is None:
                offsets.append(0.0)
                continue
            macro_times = np.asarray(macro_times)
            if macro_times.size == 0:
                offsets.append(0.0)
                continue
            resolution_ms = float(tttr.header.macro_time_resolution) * 1000.0
            first = float(macro_times[0])
            if previous_end is None:
                offset_ticks = 0.0
            else:
                offset_ticks = previous_end - first
            offsets.append(offset_ticks * resolution_ms)
            previous_end = float(macro_times[-1])
        return offsets

    def _delta_macro_time_ms(self, tttr: Any, offset_ticks: float = 0.0) -> np.ndarray:
        """Return delta macro times in milliseconds."""
        macro_times = tttr.macro_times
        d_t = np.diff(macro_times, prepend=macro_times[0] - offset_ticks)
        return d_t * tttr.header.macro_time_resolution * 1000.0

    @staticmethod
    def _max_plot_points() -> int:
        """Return the configured decimation budget (``data_loading.max_plot_points``)."""
        from chisurf.core.fio import staging
        from chisurf.core.fio.decimate import DEFAULT_MAX_POINTS

        return int(staging._settings().get("max_plot_points", DEFAULT_MAX_POINTS))

    def _sync_plot_range_controls(self, n_photons: int, reset: bool = False) -> None:
        """Clamp toolbar photon range controls to the current diagnostics.

        Parameters
        ----------
        n_photons : int
            Number of photons across the currently analyzed TTTR files.
        reset : bool
            If ``True``, reset the visible range to the full diagnostic set.

        """
        if not hasattr(self, "plot_min_spin") or not hasattr(self, "plot_max_spin"):
            return
        last_index = max(0, int(n_photons) - 1)
        min_value = 0 if reset else min(max(0, int(self.plot_min_spin.value())), last_index)
        max_value = last_index if reset else min(max(0, int(self.plot_max_spin.value())), last_index)
        if max_value < min_value:
            max_value = min_value

        for spin, value in ((self.plot_min_spin, min_value), (self.plot_max_spin, max_value)):
            block_signals = getattr(spin, "blockSignals", None)
            if block_signals is not None:
                block_signals(True)
            if hasattr(spin, "setRange"):
                spin.setRange(0, last_index)
            elif hasattr(spin, "setMaximum"):
                spin.setMaximum(last_index)
            if hasattr(spin, "setValue"):
                spin.setValue(value)
            if block_signals is not None:
                block_signals(False)

        # The spins are hidden; what the user reads is the "Display" form bound
        # to them through the view-model, and it does not know they moved. Left
        # unsynced, the form said "Last photon 100000" over a plot drawing all
        # 1.8 million -- the range control looked like it was being ignored,
        # because as far as anyone reading the window was concerned it was.
        form = self.__dict__.get("_display_form")
        if form is not None:
            try:
                form.sync_fields()
            except Exception:
                _LOG.debug("could not sync the display form to the photon range")

    def _set_log_dt_range(self, plot: pg.PlotWidget, d_t: np.ndarray) -> None:
        """Set a safe visible range for a log-scale dT plot."""
        positive = d_t[np.isfinite(d_t) & (d_t > 0)]
        if positive.size == 0:
            return
        lower = max(float(np.nanmin(positive)), 1e-12)
        upper = max(float(np.nanmax(positive)), lower * 10.0)
        try:
            plot.setYRange(np.log10(lower), np.log10(upper), padding=0.02)
        except Exception:
            plot.setYRange(lower, upper, padding=0.02)

    def _output_formats_for_inputs(self) -> list[str]:
        """Return where this run's results go, decided by what was loaded.

        Not a setting. A `.pto` is the measurement *and* everything computed
        from it, so its bursts belong inside it and a folder beside it would be
        a second copy that disagrees the moment either is re-run. Anything else
        has nowhere to put them and gets the tab-separated `bi4_bur/` companion
        the external tools read.

        Returns
        -------
        list of str
            ``["pto"]`` or ``["bur"]``. A mixed selection gets both, because
            each measurement still gets the one destination it can use.
        """
        from chisurf.core.fio.pto import SUFFIX

        paths = list(self._file_paths or [])
        if not paths:
            return ["pto"]
        containers = [p for p in paths if Path(p).suffix.lower() == SUFFIX]
        formats = []
        if containers:
            formats.append("pto")
        if len(containers) != len(paths):
            formats.append("bur")
        return formats

    def _sync_output_format_controls(self) -> None:
        """Say where the results will go, and gate the folder-only extras.

        Zipping and removing apply to the companion *folder*; with a `.pto`
        source there is no folder, so they have nothing to act on.
        """
        formats = self._output_formats_for_inputs()
        writes_folder = "bur" in formats
        label = self.__dict__.get("output_destination_label")
        if label is not None:
            if not self._file_paths:
                label.setText("Results go to: the measurement's .pto")
            elif writes_folder and "pto" in formats:
                label.setText("Results go to: each .pto, and a folder per vendor file")
            elif writes_folder:
                label.setText("Results go to: a bi4_bur/ folder beside each file")
            else:
                label.setText("Results go to: the measurement's own .pto")
        self.zip_output_check.setEnabled(writes_folder)
        if not writes_folder:
            self.zip_output_check.setChecked(False)
        self.remove_folder_check.setEnabled(self.zip_output_check.isChecked())
        if not self.zip_output_check.isChecked():
            self.remove_folder_check.setChecked(False)

    def _focus_gmm_controls(self) -> None:
        """Focus the GMM controls."""
        self.fit_gmm_button.setFocus()

    def _setup_toolbar(self) -> None:
        """Create the main toolbar."""
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("burstSelectionMainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QtCore.QSize(16, 16))
        toolbar.setContentsMargins(2, 1, 2, 1)
        if toolbar.layout() is not None:
            toolbar.layout().setSpacing(2)
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        toolbar.setStyleSheet(
            """
            QToolBar#burstSelectionMainToolbar {
                background-color: transparent;
                border: none;
                padding: 1px 2px;
                spacing: 2px;
            }
            QToolBar#burstSelectionMainToolbar::separator {
                width: 1px;
                margin: 2px 4px;
                background: rgba(255, 255, 255, 40);
            }
            QToolBar#burstSelectionMainToolbar QToolButton {
                background-color: rgba(45, 45, 45, 210);
                border: 1px solid rgba(255, 255, 255, 45);
                border-radius: 4px;
                padding: 3px 6px;
                margin: 0px;
            }
            QToolBar#burstSelectionMainToolbar QToolButton:hover {
                background-color: rgba(70, 70, 70, 230);
            }
            QToolBar#burstSelectionMainToolbar QToolButton:pressed {
                background-color: rgba(90, 90, 90, 240);
            }
            QToolBar#burstSelectionMainToolbar QCheckBox,
            QToolBar#burstSelectionMainToolbar QLabel {
                margin: 0px 3px;
            }
            QToolBar#burstSelectionMainToolbar QSpinBox {
                min-width: 70px;
                max-height: 22px;
                margin: 0px 2px;
            }
            QToolBar#burstSelectionMainToolbar #burstToolbarAdd {
                color: #7de3ff;
            }
            QToolBar#burstSelectionMainToolbar #burstToolbarBatch {
                color: #ffb347;
            }
            QToolBar#burstSelectionMainToolbar #burstToolbarProcess {
                color: #8ab4ff;
            }
            QToolBar#burstSelectionMainToolbar #burstToolbarClear {
                color: #ff7b7b;
            }
            QToolBar#burstSelectionMainToolbar #burstToolbarRefresh {
                color: #c0c0c0;
            }
            """
        )

        # Canonical shared actions (same icon / colour / order as every plugin
        # toolbar: Add, Batch, Run🚀, Clear, Refresh). Detail in the tooltip.
        self._act_add = action_button("add", on_click=self.add_files,
                                      tooltip="Add TTTR files")
        self._act_batch = action_button("batch", on_click=self.open_batch_dialog,
                                        tooltip="Batch-process a folder of TTTR files")
        self._act_process = action_button("run", on_click=self.analyze_files,
                                          tooltip="Process all loaded files")
        # A search whose files and settings are unchanged is skipped; this is how
        # the user asks for it anyway.
        self._act_restart = action_button(
            "restart", on_click=self._restart_search,
            tooltip="Search the bursts again even if nothing changed",
        )
        self._act_clear = action_button("clear", on_click=self.clear,
                                        tooltip="Clear loaded files")
        self._act_refresh = action_button("refresh", on_click=self.update_burst_plots,
                                          tooltip="Refresh burst plots")
        for _btn in (self._act_add, self._act_batch, self._act_process,
                     self._act_restart, self._act_clear, self._act_refresh):
            toolbar.addWidget(_btn)

        toolbar.addSeparator()

        # The layer toggles and the photon range are not here any more: they are
        # settings, the toolbar holds actions, and a wide "Show: … Photon
        # Range: … to …" run pushed the actions themselves off to the left. They
        # are built in ``_ensure_display_widgets`` and shown by the AutoForm in
        # Filter Settings — see ``_build_display_form``.
        #
        # One expanding spacer, not the two that used to be here: adjacent
        # stretches share the slack rather than adding to it, so the second did
        # nothing except make the count matter when a third was added. Marking
        # the toolbar as already right-spaced keeps ``add_toolbar_help`` from
        # adding that third and pushing "to ndX" back into the middle.
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        toolbar.addWidget(spacer)
        toolbar.setProperty("_chisurf_right_spacer", True)

        ndx_action = QtWidgets.QAction("🔬 to ndX", self)
        ndx_action.setToolTip(
            "Open a registered burst selection from MMFDB in ndX"
        )
        ndx_action.triggered.connect(self._open_in_ndxplorer)
        toolbar.addAction(ndx_action)

        send_ndx_action = QtWidgets.QAction("→ ndX (current)", self)
        send_ndx_action.setToolTip(
            "Send the current burst-selection result to ndX"
        )
        send_ndx_action.triggered.connect(self._send_current_to_ndxplorer)
        toolbar.addAction(send_ndx_action)

        # The shared ``?`` + **Guide** pair, replacing a hand-rolled dialog that
        # carried this tool's help as HTML inside the source file. Help now lives
        # in ``help.md`` beside this module, where it is editable without
        # touching code and its links are live.
        self.add_toolbar_help(
            toolbar, resource="help.md", title="Burst Selection — help"
        )

    def _setup_statusbar(self) -> None:
        """Create the status bar."""
        self._status_bar = QtWidgets.QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    def _show_help(self) -> None:
        """Open the shared help modal (Help ▸ About, and the toolbar ``?``).

        Both routes now show ``help.md`` through the same modal every other
        ChiSurf tool uses, so the help has one source and its links are live.
        """
        self._help_button.show_help()

    def _open_in_ndxplorer(self) -> None:
        """Open a registered burst selection from MMFDB in ndX (PRD-28)."""
        try:
            from chisurf.plugins.ndxplorer.mmfdb_launcher import open_burst_selection_from_mmfdb

            if self._mmfdb_client is None:
                raise RuntimeError(
                    "an authenticated MMFDB client was not injected into Burst Selection"
                )
            open_burst_selection_from_mmfdb(
                parent=self,
                client=self._mmfdb_client,
            )
        except Exception as exc:
            self._status_bar.showMessage(f"Could not open ndX: {exc}")

    def _send_current_to_ndxplorer(self) -> None:
        """Send the current burst-selection result to ndX (PRD-28 Direction B).

        Resolves the output path from the last analysis result and hands it
        to ndX via :func:`send_path_to_ndxplorer`. No MMFDB picker, no file
        round-trip: the just-produced burst output is opened directly.
        """
        try:
            from chisurf.plugins.ndxplorer.mmfdb_launcher import send_path_to_ndxplorer

            path = self._current_burst_output_path()
            if not path:
                self._status_bar.showMessage(
                    "No burst output to send: run an analysis first."
                )
                return
            send_path_to_ndxplorer(path, parent=self)
        except Exception as exc:
            self._status_bar.showMessage(f"Could not send to ndX: {exc}")

    def _current_burst_output_path(self) -> str | None:
        """Return the directory or file path of the last burst output."""
        result = getattr(self, "_last_service_result", None)
        if not isinstance(result, dict):
            return None
        output_paths = result.get("output_paths", {})
        for key in ("output_folder", "bur", "zip"):
            p = output_paths.get(key)
            if p:
                return str(p)
        by_file = result.get("output_paths_by_file", {})
        for _file, roles in by_file.items():
            for key in ("output_folder", "bur"):
                p = roles.get(key)
                if p:
                    return str(p)
        return None

    def _show_metadata_dialog(self) -> None:
        """Show metadata dialog for editing analysis metadata."""
        dialog = MetadataDialog(self._metadata, parent=self)
        if dialog.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            self._metadata = dialog.get_metadata()
            self.summary.setPlainText(f"Metadata updated. {len(self._metadata)} entries.")

    def export_bur(self) -> None:
        """Export burst data as .bur file."""
        if self._last_frame is None or self._last_frame.empty:
            self.summary.setPlainText("No burst data to export.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export as .bur", "", "BUR files (*.bur);;All files (*)"
        )
        if not path:
            return
        try:
            write_csv_table(path, self._last_frame)
            self.summary.setPlainText(f"Exported to {path}")
        except Exception as exc:
            self.summary.setPlainText(f"Export failed: {exc}")

    def export_flr_cif(self) -> None:
        """Export burst data as flrCIF format."""
        if self._last_frame is None or self._last_frame.empty:
            self.summary.setPlainText("No burst data to export.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export as flrCIF", "", "CIF files (*.cif *.mmcif);;All files (*)"
        )
        if not path:
            return
        try:
            self._write_flr_cif(path)
            self.summary.setPlainText(f"Exported to {path}")
        except Exception as exc:
            self.summary.setPlainText(f"Export failed: {exc}")

    def _write_flr_cif(self, path: Path) -> None:
        """Write burst data in flrCIF format."""
        lines = [
            "# flrCIF export from Burst Selection Tool",
            "#",
            "data_",
            "",
            "# Analysis metadata",
        ]
        for key, value in sorted(self._metadata.items()):
            lines.append(f"_{key} {value}")
        lines.append("")
        lines.append("# Burst data")
        lines.append("loop_")
        names = column_names(self._last_frame)
        for col in names:
            lines.append(f"_{col}")
        for row in rows_from_table(self._last_frame):
            lines.append("\t".join(str(row[name]) for name in names))
        Path(path).write_text("\n".join(lines))

    def open_batch_dialog(self) -> None:
        """Open the folder batch dialog."""
        dialog = BatchProcessingDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            self._add_paths(dialog.folders())

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Save window geometry and dock layout before closing."""
        self._save_window_geometry()
        self._save_dock_layout()
        if self._mmfdb_db is not None:
            self._mmfdb_db.close()
            self._mmfdb_db = None
            self._mmfdb_session = None
        super().closeEvent(event)

    def _save_window_geometry(self) -> None:
        """Save the main window geometry to QSettings."""
        try:
            settings = QtCore.QSettings("chisurf", "BurstSelectionTool")
            settings.setValue("geometry", self.saveGeometry())
            settings.sync()
        except Exception as exc:
            self._status_bar.showMessage(f"Failed to save window geometry: {exc}")

    def _restore_window_geometry(self) -> None:
        """Restore the main window geometry from QSettings."""
        try:
            settings = QtCore.QSettings("chisurf", "BurstSelectionTool")
            geometry = settings.value("geometry")
            if geometry is not None:
                self.restoreGeometry(geometry)
        except Exception as exc:
            self._status_bar.showMessage(f"Failed to restore window geometry: {exc}")

    def _save_dock_layout(self) -> None:
        """Save the current dock layout to QSettings."""
        try:
            import json
            settings = QtCore.QSettings("chisurf", "BurstSelectionTool")
            layout_state = self.dock_area.get_layout_state()
            settings.setValue("dock_layout", json.dumps(layout_state, sort_keys=True))
            settings.sync()
        except Exception as exc:
            self._status_bar.showMessage(f"Failed to save dock layout: {exc}")

    def _restore_dock_layout(self) -> None:
        """Restore the dock layout from QSettings."""
        try:
            import json
            settings = QtCore.QSettings("chisurf", "BurstSelectionTool")
            value = settings.value("dock_layout")
            if isinstance(value, str):
                layout_state = json.loads(value)
            elif isinstance(value, dict):
                layout_state = value
            else:
                return
            self.dock_area.set_layout_state(layout_state, emit_change=False)
        except Exception as exc:
            self._status_bar.showMessage(f"Failed to restore dock layout: {exc}")
