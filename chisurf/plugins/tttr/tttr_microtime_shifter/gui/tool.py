"""Micro-time Shifter GUI using DockArea (burst_selection pattern)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from chisurf.core import i18n
from chisurf.gui import chiplot as cp
from chisurf.gui.autoform.sections.path_list_section import PathListWidget
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.dock_area.dock_area import DockArea
from chisurf.gui.widgets.fitting.scientific_spinbox import ScientificDoubleSpinBox
from chisurf.gui.widgets.tools import ChisurfDockTool

from .client import MicrotimeShifterClient
from chisurf.gui import dialogs

#: TTTR file extensions the shifter accepts (used by the unified file list).
# From the reading seam, so the picker offers exactly what the reader opens --
# `.pto` first.
from chisurf.core.fio.staging import TTTR_EXTENSIONS as _TTTR_EXTENSIONS


class _FileListModel:
    """Adapter exposing the tool's ``_file_paths`` to the unified ``PathListWidget``.

    ``PathListWidget`` reads/writes a model ``list[str]`` attribute and calls
    ``update()`` on every change; this bridges that contract onto the tool's
    canonical ``_file_paths`` (``list[Path]``) without giving the ``QWidget`` tool
    an ``update()`` method (which would collide with ``QWidget.update``).
    """

    def __init__(self, tool: "MicrotimeShifterTool") -> None:
        self._tool = tool

    @property
    def files(self) -> list[str]:
        return [str(p) for p in self._tool._file_paths]

    @files.setter
    def files(self, value: list[str]) -> None:
        self._tool._file_paths = [Path(p) for p in value]

    def update(self) -> None:
        self._tool._on_files_changed()


class MicrotimeShifterTool(ChisurfDockTool):
    """Micro-time Shifter with DockArea tabs and toolbar."""

    tool_settings_name = "MicrotimeShifterTool"

    def __init__(
        self,
        *args: object,
        mmfdb_client: Any = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowTitle(i18n.tr("Micro-time Shifter"))
        self.resize(1000, 500)
        self._mmfdb_client = mmfdb_client
        self._mmfdb_db: Any = None
        self._mmfdb_session: Any = None
        self._client = MicrotimeShifterClient(
            mmfdb_db_provider=self.acquire_mmfdb_connection,
            mmfdb_session_provider=self.acquire_mmfdb_session,
        )

        # state
        self._file_paths: list[Path] = []
        self._current_path: str | None = None
        self.setAcceptDrops(True)
        self._routing_channels: list[int] = []
        self._n_mt: int = 0
        self._global_shift: int = 0
        self._channel_shifts: dict[int, int] = {}
        self._orig_mt: np.ndarray | None = None
        self._routing: np.ndarray | None = None
        self._mmfdb_status: str = ""

        # Trigger / Auto-align state
        self._trigger_level: int = 0
        self._trigger_pos: int = 0

        self._create_widgets()
        self._build_docks()
        self._setup_toolbar()
        self._setup_statusbar()
        self._restore_window_geometry()

    def _create_widgets(self) -> None:
        """Create plot, control, and files list widgets."""
        self.plot = cp.Plot()
        self.plot.set_labels(bottom=i18n.tr("Micro-time bin"), left=i18n.tr("Counts"))
        self.plot.set_title(i18n.tr("Micro-time Histograms"))

        # Create trigger lines (initially visible, movable). A horizontal line
        # marks the count trigger level; a vertical line marks the bin position.
        self.trigger_level_line = self.plot.hline(
            0.0, movable=True, pen=cp.to_pen("y", width=2, style="dash")
        )
        self.trigger_pos_line = self.plot.vline(
            0.0, movable=True, pen=cp.to_pen("g", width=2, style="dash")
        )

        # Connect line signals: ``final=False`` fires on user drag, ``final=True``
        # once the drag ends (programmatic ``set_value`` does not fire either).
        self.trigger_level_line.on_change(self._on_trigger_level_line_changed, final=False)
        self.trigger_pos_line.on_change(self._on_trigger_pos_line_changed, final=False)
        self.trigger_level_line.on_change(self._on_trigger_level_line_finished, final=True)
        self.trigger_pos_line.on_change(self._on_trigger_pos_line_finished, final=True)

        self.controls_panel = QtWidgets.QWidget()
        self.controls_layout = QtWidgets.QVBoxLayout(self.controls_panel)
        self.controls_layout.setContentsMargins(2, 2, 2, 2)
        self.controls_layout.setSpacing(2)

        controls_header = QtWidgets.QLabel(i18n.tr("Micro-time Shift"))
        controls_header.setObjectName("microtimeShiftHeader")
        controls_header.setStyleSheet(
            "font-weight: bold; font-size: 13px; padding: 4px;"
        )
        self.controls_layout.addWidget(controls_header)

        # Trigger / Auto-align controls (instantiated here, added to toolbar)
        self.trigger_level_spin = ScientificDoubleSpinBox(value=0, int=True, step=10, bounds=[0, 1000000])
        self.trigger_level_spin.setMinimumWidth(80)
        self.trigger_level_spin.setMaximumWidth(120)

        self.trigger_pos_spin = ScientificDoubleSpinBox(value=0, int=True, step=1, bounds=[0, 100000])
        self.trigger_pos_spin.setMinimumWidth(60)
        self.trigger_pos_spin.setMaximumWidth(100)

        # Connect spin box signals
        self.trigger_level_spin.editingFinished.connect(self._on_trigger_level_spin_changed)
        self.trigger_pos_spin.editingFinished.connect(self._on_trigger_pos_spin_changed)

        # Container layout for channel shifts
        self.shifts_container = QtWidgets.QWidget()
        self.shifts_layout = QtWidgets.QVBoxLayout(self.shifts_container)
        self.shifts_layout.setContentsMargins(0, 0, 0, 0)
        self.shifts_layout.setSpacing(2)
        self.controls_layout.addWidget(self.shifts_container)

        self.plot_panel = QtWidgets.QWidget()
        self.plot_layout = QtWidgets.QVBoxLayout(self.plot_panel)
        self.plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_header = QtWidgets.QLabel(i18n.tr("Histogram"))
        plot_header.setObjectName("histogramHeader")
        plot_header.setStyleSheet(
            "font-weight: bold; font-size: 13px; padding: 4px;"
        )
        self.plot_layout.addWidget(plot_header)
        self.plot_layout.addWidget(self.plot, 1)

        self.status_panel = QtWidgets.QWidget()
        self.status_layout = QtWidgets.QVBoxLayout(self.status_panel)
        self.status_layout.setContentsMargins(2, 2, 2, 2)
        self.status_label = QtWidgets.QLabel(i18n.tr("No file loaded."))
        self.status_label.setWordWrap(True)
        self.status_layout.addWidget(self.status_label)
        self.status_layout.addStretch()

        self.files_panel = QtWidgets.QWidget()
        self.files_layout = QtWidgets.QVBoxLayout(self.files_panel)
        self.files_layout.setContentsMargins(2, 2, 2, 2)
        self.files_layout.setSpacing(4)

        files_header = QtWidgets.QLabel(i18n.tr("Files"))
        files_header.setObjectName("filesHeader")
        files_header.setStyleSheet(
            "font-weight: bold; font-size: 13px; padding: 4px;"
        )
        self.files_layout.addWidget(files_header)

        # Unified AutoForm file/folder list (drag-drop + Files/Folder/Database/
        # Remove/Clear), with built-in MMFDB selection. Replaces the former
        # hand-rolled QListWidget + custom add/refresh/context-menu/MMFDB code.
        self._file_model = _FileListModel(self)
        self.file_list = PathListWidget(
            self._file_model,
            "files",
            extensions=_TTTR_EXTENSIONS,
            title=None,
            mmfdb_kinds=["raw_measurement", "processed_data"],
            mmfdb_scope="mine",
            select_first=True,
        )
        self.file_list.selectionChanged.connect(self._on_file_selection)
        self.files_layout.addWidget(self.file_list, 1)

    def _build_docks(self) -> None:
        """Build DockArea with tabs for files, controls, histogram, and status."""
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.dock_area = DockArea(central)
        self.dock_area.setContextMenuEnabled(True)
        self.dock_area.setContextMenuMode("basic")
        self.dock_area.setTabsClosable(True)
        self.dock_area.setCloseTabCallback(self._on_dock_tab_close_requested)
        self.dock_area.setContextMenuCallback(self._add_dock_context_menu_actions)

        self.dock_area.addTab(self.files_panel, i18n.tr("Files"))
        self.dock_area.addTab(self.controls_panel, i18n.tr("Micro-time Shift"))
        self.dock_area.addTab(self.plot_panel, i18n.tr("Histogram"))
        self.dock_area.addTab(self.status_panel, i18n.tr("Status"))
        layout.addWidget(self.dock_area, 1)

        self.dock_area.layoutChanged.connect(self._save_dock_layout)
        self._restore_dock_layout()

    def _setup_toolbar(self) -> None:
        """Create toolbar with Load/Save actions."""
        tb = QtWidgets.QToolBar("Main")
        tb.setObjectName("microtimeShifterMainToolbar")
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, tb)
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QtCore.QSize(16, 16))
        tb.setContentsMargins(4, 2, 4, 2)
        if tb.layout() is not None:
            tb.layout().setSpacing(6)
        tb.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.setStyleSheet("""
            QToolBar#microtimeShifterMainToolbar {
                background-color: transparent;
                border: none;
                padding: 3px 4px;
                spacing: 6px;
            }
            QToolBar#microtimeShifterMainToolbar QToolButton {
                background-color: #2a2a4a;
                border: 1px solid #5a5a8a;
                border-radius: 5px;
                padding: 5px 10px;
                margin: 0px;
                font-weight: bold;
                font-size: 12px;
                color: #ffffff;
            }
            QToolBar#microtimeShifterMainToolbar QToolButton:hover {
                background-color: #3a3a6a;
                border-color: #8a8aba;
            }
            QToolBar#microtimeShifterMainToolbar QToolButton:pressed {
                background-color: #4a4a8a;
            }
            QToolBar#microtimeShifterMainToolbar QToolButton:disabled {
                color: #666;
                background-color: #1a1a2e;
                border-color: #3a3a5e;
            }
            QToolBar#microtimeShifterMainToolbar QToolButton:checked {
                background-color: #4a4a8a;
                border-color: #a0a0ff;
            }
            QToolBar#microtimeShifterMainToolbar QLabel {
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                margin-left: 4px;
                margin-right: 2px;
            }
        """)

        # File loading (local + MMFDB) is handled by the unified file list's
        # ➕ Files / 📁 Folder / 🗄️ Database buttons, so no separate Load action.
        self.save_action = QtWidgets.QAction(f"{Glyphs.SAVE} {i18n.tr('Save...')}", self)
        self.save_action.setObjectName("microtimeShifterSave")
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self._open_save_dialog)
        tb.addAction(self.save_action)

        tb.addSeparator()

        self.show_trigger_action = QtWidgets.QAction(f"{Glyphs.TARGET} {i18n.tr('Show Trigger')}", self, checkable=True)
        self.show_trigger_action.setObjectName("microtimeShifterShowTrigger")
        self.show_trigger_action.setChecked(True)
        self.show_trigger_action.toggled.connect(self._on_toggle_trigger_lines)
        tb.addAction(self.show_trigger_action)

        self.logy_action = QtWidgets.QAction(f"{Glyphs.CHART_UP} {i18n.tr('Log Y')}", self, checkable=True)
        self.logy_action.setObjectName("microtimeShifterLogY")
        self.logy_action.setChecked(False)
        self.logy_action.toggled.connect(self._on_toggle_logy)
        tb.addAction(self.logy_action)

        tb.addSeparator()

        lbl_level = QtWidgets.QLabel(i18n.tr("Level:"))
        tb.addWidget(lbl_level)
        tb.addWidget(self.trigger_level_spin)

        lbl_pos = QtWidgets.QLabel(i18n.tr("Pos:"))
        tb.addWidget(lbl_pos)
        tb.addWidget(self.trigger_pos_spin)

        tb.addSeparator()

        self.auto_align_action = QtWidgets.QAction(f"⚡ {i18n.tr('Auto Align')}", self)
        self.auto_align_action.setObjectName("microtimeShifterAutoAlign")
        self.auto_align_action.triggered.connect(self.auto_align)
        tb.addAction(self.auto_align_action)

    def _setup_statusbar(self) -> None:
        self.statusBar().showMessage(i18n.tr("Ready"))

    # ── file list (unified PathListWidget) ─────────────────────────

    def _on_file_path(self, path: str) -> None:
        if not path:
            return
        self._current_path = path
        self._load_metadata()
        self._identify_file()
        self._build_shift_controls()
        self._update_plot()

    def _on_files_changed(self) -> None:
        """React to the unified file list changing (add / remove / clear / DB).

        ``PathListWidget`` already updated ``_file_paths`` (via the model); here we
        only reset the preview/save state when the list becomes empty.
        """
        if not self._file_paths:
            self._current_path = None
            self.plot.clear()
            self.save_action.setEnabled(False)
            self._update_status()

    def _on_file_selection(self, paths: list[str]) -> None:
        """Preview the first selected file when the list selection changes."""
        if paths and paths[0] != self._current_path:
            self._on_file_path(paths[0])

    def _load_metadata(self) -> None:
        if not self._current_path:
            return
        try:
            meta = self._client.load_metadata(Path(self._current_path))
            self._routing_channels = meta.get("routing_channels", [])
            self._n_mt = int(meta.get("n_mt", 0))
            self._channel_shifts = {ch: 0 for ch in self._routing_channels}
            self._global_shift = 0

            # Calculate sensible defaults for trigger levels and positions
            histogram = self._client.histogram(
                self._file_paths,
                global_shift=self._global_shift,
                channel_shifts=self._channel_shifts,
            )
            max_peak = 0
            for hist_values in histogram.get("histograms", {}).values():
                if hist_values:
                    max_peak = max(max_peak, int(max(hist_values)))

            self._trigger_level = int(max_peak * 0.2) if max_peak > 0 else 100
            self._trigger_pos = int(self._n_mt * 0.1) if self._n_mt > 0 else 50

            # Update controls and lines
            self.trigger_level_spin.blockSignals(True)
            self.trigger_level_spin.setOpts(bounds=[0, max(1000000, max_peak)])
            self.trigger_level_spin.setValue(self._trigger_level)
            self.trigger_level_spin.blockSignals(False)

            self.trigger_pos_spin.blockSignals(True)
            self.trigger_pos_spin.setOpts(bounds=[0, self._n_mt - 1])
            self.trigger_pos_spin.setValue(self._trigger_pos)
            self.trigger_pos_spin.blockSignals(False)

            self.trigger_level_line.set_value(self._trigger_level)
            self.trigger_pos_line.set_value(self._trigger_pos)

            self.save_action.setEnabled(True)
            self.statusBar().showMessage(f"Loaded: {self._current_path}")
        except Exception as exc:
            dialogs.error(
                self, i18n.tr("Error"), f"{i18n.tr('Cannot load file:')}\n{exc}"
            )

    def _identify_file(self) -> None:
        if not self._current_path:
            return
        try:
            info = self._client.identify(Path(self._current_path))
            if info.get("found"):
                self._mmfdb_status = (
                    f"Identified (artifact: {info.get('artifact_id', '?')[:8]})"
                )
            else:
                self._mmfdb_status = i18n.tr("New file (not in MMFDB)")
        except Exception:
            self._mmfdb_status = i18n.tr("MMFDB check unavailable")
        self._update_status()

    def _update_status(self) -> None:
        parts = []
        if self._current_path:
            parts.append(f"File: {self._current_path}")
        if self._mmfdb_status:
            parts.append(f"MMFDB: {self._mmfdb_status}")
        if not self._current_path:
            parts.append(i18n.tr("No file loaded."))
        self.status_label.setText("\n".join(parts))

    # ── shift controls ─────────────────────────────────────────────

    def _build_shift_controls(self) -> None:
        while self.shifts_layout.count():
            w = self.shifts_layout.takeAt(0).widget()
            if w:
                w.setParent(None)

        for ch in sorted(self._channel_shifts):
            self._add_shift_row(f"Ch{ch}", ch)
        self.shifts_layout.addStretch()

    def _add_shift_row(self, label: str, channel: int | None) -> None:
        row = QtWidgets.QWidget()
        rl = QtWidgets.QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(2)
        lbl = QtWidgets.QLabel(label)
        lbl.setFixedWidth(30)
        rl.addWidget(lbl)

        value = (
            self._global_shift
            if channel is None
            else self._channel_shifts.get(channel, 0)
        )
        spin = ScientificDoubleSpinBox(
            value=value,
            int=True,
            step=1,
            bounds=[-(self._n_mt - 1), self._n_mt - 1],
        )
        spin.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        rl.addWidget(spin)

        if channel is None:
            spin.editingFinished.connect(self._make_global_fn(spin))
        else:
            spin.editingFinished.connect(self._make_chan_fn(channel, spin))

        btn = QtWidgets.QPushButton(Glyphs.REFRESH)
        btn.setFixedWidth(30)
        if channel is None:
            btn.clicked.connect(self._make_global_reset_fn(spin))
        else:
            btn.clicked.connect(self._make_chan_reset_fn(channel, spin))
        rl.addWidget(btn)

        self.shifts_layout.addWidget(row)

    def _make_global_fn(self, spin: ScientificDoubleSpinBox):
        def fn() -> None:
            try:
                self._global_shift = int(spin.value())
            except Exception:
                return
            self._update_plot()
        return fn

    def _make_chan_fn(self, ch: int, spin: ScientificDoubleSpinBox):
        def fn() -> None:
            try:
                self._channel_shifts[ch] = int(spin.value())
            except Exception:
                return
            self._update_plot()
        return fn

    def _make_global_reset_fn(self, spin: ScientificDoubleSpinBox):
        def fn() -> None:
            self._global_shift = 0
            spin.blockSignals(True)
            spin.setValue(0)
            spin.blockSignals(False)
            self._update_plot()
        return fn

    def _make_chan_reset_fn(self, ch: int, spin: ScientificDoubleSpinBox):
        def fn() -> None:
            self._channel_shifts[ch] = 0
            spin.blockSignals(True)
            spin.setValue(0)
            spin.blockSignals(False)
            self._update_plot()
        return fn

    # ── plot ───────────────────────────────────────────────────────

    def _update_plot(self) -> None:
        """Update the micro-time histogram plot via RPC."""
        if not self._file_paths or self._n_mt < 1:
            return

        try:
            histogram = self._client.histogram(
                self._file_paths,
                global_shift=self._global_shift,
                channel_shifts=self._channel_shifts,
            )
        except Exception:
            self.plot.clear()
            self.plot.set_title(i18n.tr("Cannot load files for preview"))
            return

        self.plot.clear()
        # Add back trigger lines
        self.plot.add(self.trigger_level_line)
        self.plot.add(self.trigger_pos_line)

        edges = np.arange(self._n_mt + 1)

        is_logy = self.logy_action.isChecked()
        for i, ch in enumerate(sorted(self._channel_shifts)):
            hist_values = histogram.get("histograms", {}).get(str(ch), [])
            if not hist_values:
                continue
            hist = np.array(hist_values, dtype=int)
            c = cp.int_color(i, len(self._channel_shifts))
            if is_logy:
                self.plot.line(edges, hist, pen=c, step=True, name=str(ch))
            else:
                faded = c.with_alpha(100)
                self.plot.line(
                    edges, hist, pen=faded, step=True, fill=faded, name=str(ch)
                )

        try:
            self.plot.legend()
        except Exception:
            pass
        self.plot.set_title(i18n.tr("Micro-time Histograms (preview)"))

    def auto_align(self) -> None:
        if not self._file_paths or self._n_mt < 1:
            return

        target_bin = int(self._trigger_pos)
        trigger_level = int(self._trigger_level)

        try:
            histogram = self._client.histogram(
                self._file_paths,
                global_shift=self._global_shift,
                channel_shifts=self._channel_shifts,
            )
        except Exception:
            return

        for ch in self._channel_shifts:
            hist_values = histogram.get("histograms", {}).get(str(ch), [])
            if not hist_values:
                continue
            hist = np.array(hist_values, dtype=int)
            peak_bin = int(np.argmax(hist))
            peak_val = hist[peak_bin]

            # Find rising edge crossing the trigger level
            below_peak = hist[:peak_bin + 1]
            crossings = np.where(below_peak >= trigger_level)[0]
            if len(crossings) > 0:
                ch_trigger_bin = crossings[0]
            else:
                ch_trigger_bin = peak_bin

            # Calculate required shift
            current_shift = self._channel_shifts.get(ch, 0)
            shift = (current_shift + target_bin - ch_trigger_bin) % self._n_mt
            self._channel_shifts[ch] = int(shift)

        # Update the UI spinboxes for the channel shifts
        self._build_shift_controls()
        self._update_plot()

    def _on_trigger_level_spin_changed(self, *args: object) -> None:
        val = int(self.trigger_level_spin.value())
        val = max(1, val)
        self._trigger_level = val
        if self.logy_action.isChecked():
            self.trigger_level_line.set_value(np.log10(val))
        else:
            self.trigger_level_line.set_value(val)
        self.auto_align()

    def _on_trigger_pos_spin_changed(self, *args: object) -> None:
        val = int(self.trigger_pos_spin.value())
        self._trigger_pos = val
        self.trigger_pos_line.set_value(val)
        self.auto_align()

    def _on_trigger_level_line_changed(self, line_val: float) -> None:
        if self.logy_action.isChecked():
            val = int(round(10**line_val))
        else:
            val = int(round(line_val))
        val = max(1, val)
        self._trigger_level = val
        self.trigger_level_spin.blockSignals(True)
        self.trigger_level_spin.setValue(val)
        self.trigger_level_spin.blockSignals(False)

    def _on_trigger_pos_line_changed(self, line_val: float) -> None:
        val = int(line_val)
        self._trigger_pos = val
        self.trigger_pos_spin.blockSignals(True)
        self.trigger_pos_spin.setValue(val)
        self.trigger_pos_spin.blockSignals(False)

    def _on_trigger_level_line_finished(self, *args: object) -> None:
        self.auto_align()

    def _on_trigger_pos_line_finished(self, *args: object) -> None:
        self.auto_align()

    def _on_toggle_trigger_lines(self, checked: bool) -> None:
        self.trigger_level_line.visible = checked
        self.trigger_pos_line.visible = checked

    def _on_toggle_logy(self, checked: bool) -> None:
        self.plot.set_log(x=False, y=checked)
        if checked:
            self.trigger_level_line.set_value(np.log10(max(1, self._trigger_level)))
        else:
            self.trigger_level_line.set_value(self._trigger_level)
        self._update_plot()
        self.plot.autoscale()

    def acquire_mmfdb_connection(self) -> Any:
        """Return this tool's explicitly owned MMFDB connection."""
        if self._mmfdb_db is not None:
            return self._mmfdb_db
        from ..api.mmfdb import active_mmfdb_connection

        self._mmfdb_db = active_mmfdb_connection()
        return self._mmfdb_db

    def _db(self) -> Any:
        """Return the active MMFDB connection if available."""
        return self.acquire_mmfdb_connection()

    def acquire_mmfdb_session(self) -> Any:
        """Return a verified session derived from the injected authenticated client."""
        if self._mmfdb_session is not None:
            return self._mmfdb_session
        token = getattr(self._mmfdb_client, "token", None)
        db = self.acquire_mmfdb_connection()
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

    # ── save ───────────────────────────────────────────────────────

    def _open_save_dialog(self) -> None:
        if not self._file_paths:
            return
        paths_to_shift = self._file_paths

        db = self._db()
        has_mmfdb = db is not None

        mode = "file"
        if has_mmfdb:
            answer = dialogs.choice(
                self,
                i18n.tr("Save Shifted Files"),
                i18n.tr("An active MMFDB database connection was found."),
                {
                    "db": i18n.tr("Register in DB"),
                    "file": i18n.tr("Save to File/Folder..."),
                    "cancel": i18n.tr("Cancel"),
                },
                default="file",
                informative=i18n.tr(
                    "Would you like to register the shifted files in the database, "
                    "or save them to a local file/folder?"
                ),
            )
            if not answer or answer.key == "cancel":
                return
            mode = answer.key

        if mode == "db":
            from chisurf.gui.widgets.sample_picker import show_sample_picker_dialog
            sample_id = show_sample_picker_dialog(db=db, parent=self)
            if not sample_id:
                return

            # Prepare the MMFDB Context
            mmfdb_context = {
                "enabled": True,
                "sample_id": sample_id,
                "register_missing_inputs": True,
            }

            try:
                result = self._client.apply(
                    file_paths=paths_to_shift,
                    global_shift=self._global_shift,
                    channel_shifts=self._channel_shifts,
                    mmfdb=mmfdb_context,
                )
                warnings = result.get("warnings", [])
                warn_str = "\nWarnings:\n" + "\n".join(warnings) if warnings else ""
                dialogs.information(
                    self, i18n.tr("Success"), f"Successfully registered {len(paths_to_shift)} file(s) in MMFDB.{warn_str}"
                )
                self.statusBar().showMessage(f"Registered in MMFDB: {len(paths_to_shift)} file(s)")
            except Exception as exc:
                dialogs.error(
                    self, i18n.tr("Error"), f"Failed to register in MMFDB:\n{exc}"
                )

        else:  # mode == "file"
            if len(paths_to_shift) == 1:
                path = paths_to_shift[0]
                d = path.parent
                f = path.name
                sp, _ = QtWidgets.QFileDialog.getSaveFileName(
                    self, i18n.tr("Save shifted TTTR file"), str(d / f), i18n.tr("TTTR Files (*.*)")
                )
                if not sp:
                    return
                try:
                    result = self._client.apply(
                        file_paths=paths_to_shift,
                        global_shift=self._global_shift,
                        channel_shifts=self._channel_shifts,
                        output_dir=Path(sp).parent,
                        mmfdb={"enabled": False},
                    )
                    shifted_generated = result.get("output_paths_by_file", {}).get(str(path))
                    saved_path = sp
                    if shifted_generated and shifted_generated != sp:
                        try:
                            import os
                            import shutil
                            if os.path.exists(sp):
                                os.remove(sp)
                            shutil.move(shifted_generated, sp)
                        except Exception:
                            saved_path = shifted_generated
                    self.statusBar().showMessage(f"Saved to: {saved_path}")
                    dialogs.information(
                        self, i18n.tr("Saved"), f"Saved to:\n{saved_path}"
                    )
                except Exception as exc:
                    dialogs.error(
                        self, i18n.tr("Error"), f"Cannot save:\n{exc}"
                    )
            else:
                output_dir = QtWidgets.QFileDialog.getExistingDirectory(
                    self, i18n.tr("Select Output Directory"), ""
                )
                if not output_dir:
                    return
                try:
                    result = self._client.apply(
                        file_paths=paths_to_shift,
                        global_shift=self._global_shift,
                        channel_shifts=self._channel_shifts,
                        output_dir=Path(output_dir),
                        mmfdb={"enabled": False},
                    )
                    self.statusBar().showMessage(f"Saved {len(paths_to_shift)} file(s) to: {output_dir}")
                    dialogs.information(
                        self, i18n.tr("Saved"), f"Saved {len(paths_to_shift)} file(s) to:\n{output_dir}"
                    )
                except Exception as exc:
                    dialogs.error(
                        self, i18n.tr("Error"), f"Cannot save:\n{exc}"
                    )

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
            settings = QtCore.QSettings("chisurf", "MicrotimeShifterTool")
            settings.setValue("geometry", self.saveGeometry())
            settings.sync()
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to save window geometry: {exc}")

    def _restore_window_geometry(self) -> None:
        """Restore the main window geometry from QSettings."""
        try:
            settings = QtCore.QSettings("chisurf", "MicrotimeShifterTool")
            geometry = settings.value("geometry")
            if geometry is not None:
                self.restoreGeometry(geometry)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to restore window geometry: {exc}")

    def _save_dock_layout(self) -> None:
        """Save the current dock layout to QSettings."""
        try:
            import json
            settings = QtCore.QSettings("chisurf", "MicrotimeShifterTool")
            layout_state = self.dock_area.get_layout_state()
            settings.setValue("dock_layout", json.dumps(layout_state, sort_keys=True))
            settings.sync()
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to save dock layout: {exc}")

    def _restore_dock_layout(self) -> None:
        """Restore the dock layout from QSettings, or load default."""
        try:
            import json
            settings = QtCore.QSettings("chisurf", "MicrotimeShifterTool")
            value = settings.value("dock_layout")
            if isinstance(value, str):
                layout_state = json.loads(value)
                if self.dock_area.set_layout_state(layout_state, emit_change=False):
                    return
            elif isinstance(value, dict):
                if self.dock_area.set_layout_state(value, emit_change=False):
                    return
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to restore dock layout: {exc}")

        # Default layout fallback: split controls and status (left) from plot (right)
        try:
            default_layout = {
                "version": 1,
                "root": {
                    "type": "splitter",
                    "orientation": "horizontal",
                    "sizes": [300, 700],
                    "children": [
                        {
                            "type": "tab",
                            "current_index": 0,
                            "tabs": [
                                {
                                    "widget_key": i18n.tr("Micro-time Shift"),
                                    "tab_name": i18n.tr("Micro-time Shift"),
                                    "tab_text": i18n.tr("Micro-time Shift")
                                },
                                {
                                    "widget_key": i18n.tr("Status"),
                                    "tab_name": i18n.tr("Status"),
                                    "tab_text": i18n.tr("Status")
                                }
                            ]
                        },
                        {
                            "type": "tab",
                            "current_index": 0,
                            "tabs": [
                                {
                                    "widget_key": i18n.tr("Histogram"),
                                    "tab_name": i18n.tr("Histogram"),
                                    "tab_text": i18n.tr("Histogram")
                                }
                            ]
                        }
                    ]
                },
                "active_tab_widget": None,
                "current_index": 0
            }
            self.dock_area.set_layout_state(default_layout, emit_change=False)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to set default dock layout: {exc}")

    def _on_dock_tab_close_requested(self, index: int) -> None:
        """Hide closed dock tabs instead of deleting them."""
        self.dock_area.hideTab(index)

    def _add_dock_context_menu_actions(self, menu: QtWidgets.QMenu, index: int) -> None:
        """Add context menu actions to restore hidden tabs."""
        hidden_names = []
        for widget in [self.controls_panel, self.plot_panel, self.status_panel]:
            idx = self.dock_area.indexOf(widget)
            if idx != -1 and not self.dock_area.isTabVisible(idx):
                hidden_names.append((self.dock_area.tabText(idx), widget))

        if hidden_names:
            menu.addSeparator()
            show_menu = menu.addMenu(i18n.tr("Reopen closed docks"))
            for name, widget in hidden_names:
                action = show_menu.addAction(name)
                action.triggered.connect(
                    lambda _checked=False, w=widget: self._show_dock(w)
                )

    def _show_dock(self, widget: QtWidgets.QWidget) -> None:
        """Show a hidden dock widget."""
        idx = self.dock_area.indexOf(widget)
        if idx != -1:
            self.dock_area.showTab(idx)
