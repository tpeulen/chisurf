"""PyQt GUI for TTTR Time Window Bins backed by the new API."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from chisurf import logging
from chisurf.core.support import i18n
from chisurf.gui import chiplot as cp
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.misc_helpers import persist_plugin_state
from chisurf.gui.widgets.dock_area.dock_area import DockArea
from chisurf.gui.widgets.tools import ChisurfDockTool

from ..api.models import TimeWindowResult
from .client import TimeWindowClient

# Reuse the intensity plot widget for preview visualisation
try:
    from chisurf.plugins.tttr.intensity_trace import IntensityPlotWidget
except Exception:
    IntensityPlotWidget = None


def _supported_exts() -> set[str]:
    """Return the set of supported TTTR file extensions."""
    norm: set[str] = set()
    try:
        import tttrlib

        exts = getattr(tttrlib, "get_supported_filetypes", lambda: [])()
        for e in exts:
            s = str(e).strip().lower()
            if not s:
                continue
            if not s.startswith("."):
                s = "." + s
            norm.add(s)
    except Exception:
        pass
    if not norm:
        norm = {".ptu", ".phu", ".ht2", ".ht3", ".pt3", ".t3r"}
    return norm


def _is_supported_path(path: str) -> bool:
    """Return whether a path has a supported TTTR extension (optionally .gz/.bz2)."""
    lower = path.lower()
    return any(
        lower.endswith(ext) or lower.endswith(ext + ".gz") or lower.endswith(ext + ".bz2")
        for ext in _supported_exts()
    )


class _FileListModel:
    """Adapter exposing the tool's ``_file_paths`` to the unified ``PathListWidget``.

    ``PathListWidget`` reads/writes ``files`` (list[str]) and calls ``update()`` on
    every change; this bridges that onto the tool's canonical ``_file_paths``
    (``list[Path]``, the source of truth for batch processing) and forwards
    changes to ``_on_files_changed`` so the preview combo stays in sync.
    """

    def __init__(self, tool: TTTRTimeWindowTool) -> None:
        self._tool = tool

    @property
    def files(self) -> list[str]:
        return [str(p) for p in self._tool._file_paths]

    @files.setter
    def files(self, value: list[str]) -> None:
        self._tool._file_paths = [Path(p) for p in value]

    def update(self) -> None:
        self._tool._on_files_changed()


class HelpDialog(QtWidgets.QDialog):
    """Help dialog with description and CLI reference."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("About TTTR Time-Window BIDs"))
        self.resize(640, 520)
        layout = QtWidgets.QVBoxLayout(self)

        text = QtWidgets.QTextEdit(self)
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
            i18n.tr(
                """
            <h2>TTTR → Time-Window BIDs</h2>
            <p>This tool splits TTTR (Time-Tagged Time-Resolved) photon data
            into fixed-duration <b>time windows</b> and saves the photon-index
            boundaries as <b>.bst</b> (BID) files.</p>

            <h3>How it works</h3>
            <ol>
              <li>Select one or more TTTR files (.ptu, .ht3, .phu, …)</li>
              <li>Set the <b>time window</b> duration (in milliseconds)</li>
              <li>Choose an output folder (or let the tool create one)</li>
              <li>Click <b>Process</b> to compute start/stop photon indices
                  for each window</li>
            </ol>

            <h3>Output</h3>
            <p>For each input file a <code>.bst</code> file is written with
            tab-separated <code>[start_idx, stop_idx)</code> pairs, one per
            time window.</p>

            <h3>Use case</h3>
            <p>The resulting BID files can be used to split a TTTR stream
            into consecutive segments for downstream analysis such as
            time-correlated single-photon counting (TCSPC) or fluorescence
            correlation spectroscopy (FCS).</p>

            <hr>
            <h3>CLI Reference</h3>
            """
            )
            + cli_text
        )
        layout.addWidget(text, 1)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok,
        )
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


@persist_plugin_state("tttr_time_windows")
class TTTRTimeWindowTool(ChisurfDockTool):
    """Single-window TTTR→BID tool with split docks, toolbar, and preview.

    Consolidates setup, file selection, preview, and processing into one
    resizable window with draggable dock panels.
    """

    tool_settings_name = "TTTRTimeWindowTool"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowTitle(i18n.tr("TTTR Time-Window BIDs"))
        try:
            self.resize(1000, 700)
        except Exception:
            pass

        self._client = TimeWindowClient()
        self._file_paths: list[Path] = []
        self._last_result: TimeWindowResult | None = None

        self.setAcceptDrops(True)
        self._create_plot_widgets()
        self._build_ui()
        self._setup_toolbar()
        self._setup_statusbar()
        self._setup_menu()

    # ── UI construction ────────────────────────────────────────────

    def _create_plot_widgets(self) -> None:
        """Create plot widgets early to avoid hot-reload issues."""
        self.preview_plot: cp.Plot = cp.Plot(self)
        self.preview_plot.set_labels(bottom=i18n.tr("Time (s)"), left=i18n.tr("Intensity (counts)"))
        self.preview_plot.set_title(i18n.tr("Intensity trace preview"))

        self.status_log: QtWidgets.QTextEdit = QtWidgets.QTextEdit(self)
        self.status_log.setReadOnly(True)
        self.status_log.setPlaceholderText(i18n.tr("Processing log will appear here…"))

    def _build_ui(self) -> None:
        """Build the main layout with dock area."""
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(2)

        self.dock_area = DockArea(central)
        self._build_docks()
        layout.addWidget(self.dock_area, 1)

    def _build_docks(self) -> None:
        """Create dock panels."""
        # ⚙️ Settings dock
        settings_panel = self._build_settings_panel(self.dock_area)
        self.dock_area.addTab(settings_panel, f"⚙️\ufe0f {i18n.tr('Settings')}")

        # 📁 Files dock
        files_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self.dock_area)
        hint = QtWidgets.QLabel(i18n.tr("Drop TTTR files here"), self.dock_area)
        hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: gray; font-style: italic;")
        files_splitter.addWidget(hint)

        # Unified AutoForm file/folder list (drag-drop + Files/Folder/Database/
        # Remove/Clear + MMFDB); replaces the hand-rolled PathDropListWidget wiring
        # and the toolbar's separate Add/Database actions.
        from chisurf.gui.autoform.sections.path_list_section import PathListWidget

        self._file_model = _FileListModel(self)
        self.file_list = PathListWidget(
            self._file_model,
            "files",
            extensions=sorted(_supported_exts()),
            path_filter=_is_supported_path,  # also accepts compressed *.ptu.gz
        )
        files_splitter.addWidget(self.file_list)
        files_splitter.setStretchFactor(0, 0)
        files_splitter.setStretchFactor(1, 1)

        self.dock_area.addTab(files_splitter, f"{Glyphs.FOLDER} {i18n.tr('Files')}")

        # 👁️ Preview dock
        preview_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self.dock_area)
        preview_controls = self._build_preview_controls(self.dock_area)
        preview_splitter.addWidget(preview_controls)
        preview_splitter.addWidget(self.preview_plot)
        preview_splitter.setStretchFactor(0, 0)
        preview_splitter.setStretchFactor(1, 1)
        self.dock_area.addTab(preview_splitter, f"👁️\ufe0f {i18n.tr('Preview')}")

        # 📋 Summary dock
        self.dock_area.addTab(self.status_log, f"{Glyphs.COPY} {i18n.tr('Summary')}")

        self.dock_area.setTabsClosable(True)
        self.dock_area.layoutChanged.connect(self._save_dock_layout)
        self._restore_dock_layout()

    # ── Settings panel ──────────────────────────────────────────────

    def _build_settings_panel(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Create the settings control panel."""
        panel = QtWidgets.QWidget(parent)
        form = QtWidgets.QFormLayout(panel)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(6)

        self.tws_spin = QtWidgets.QDoubleSpinBox(panel)
        self.tws_spin.setDecimals(3)
        self.tws_spin.setRange(0.001, 3600 * 1000.0)
        self.tws_spin.setSingleStep(1.0)
        self.tws_spin.setValue(10.0)
        self.tws_spin.setSuffix(" ms")
        self.tws_spin.setToolTip(
            i18n.tr(
                "Duration of each time window in milliseconds. "
                "Smaller values create more windows with fewer photons each."
            )
        )
        self.tws_spin.valueChanged.connect(self._on_settings_changed)
        form.addRow(i18n.tr("Time window:"), self.tws_spin)

        out_layout = QtWidgets.QHBoxLayout()
        self.output_edit = QtWidgets.QLineEdit(panel)
        self.output_edit.setPlaceholderText(i18n.tr("Auto (derived from first file)"))
        self.output_edit.setToolTip(
            i18n.tr(
                "Output folder for .bst files. Leave empty to auto-generate "
                "a folder next to the first input file."
            )
        )
        self.btn_browse = QtWidgets.QPushButton(i18n.tr("Browse…"), panel)
        self.btn_browse.setToolTip(i18n.tr("Choose an output folder manually."))
        self.btn_browse.clicked.connect(self._choose_dir)
        out_layout.addWidget(self.output_edit, 1)
        out_layout.addWidget(self.btn_browse)
        form.addRow(i18n.tr("Output folder:"), out_layout)

        preview_label = QtWidgets.QLabel(
            i18n.tr("Select a file to preview its intensity trace."), panel
        )
        preview_label.setWordWrap(True)
        preview_label.setStyleSheet("color: gray; font-style: italic;")
        form.addRow(preview_label)

        panel.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        return panel

    # ── Preview controls ───────────────────────────────────────────

    def _build_preview_controls(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Create the preview file selector."""
        panel = QtWidgets.QWidget(parent)
        layout = QtWidgets.QHBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)

        layout.addWidget(QtWidgets.QLabel(i18n.tr("Preview file:"), panel))
        self.cmb_file = QtWidgets.QComboBox(panel)
        self.cmb_file.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.cmb_file.setToolTip(
            i18n.tr(
                "Select a loaded TTTR file to preview its intensity trace "
                "with time-window boundary lines."
            )
        )
        self.cmb_file.currentIndexChanged.connect(self._on_select_file)
        layout.addWidget(self.cmb_file, 1)

        return panel

    # ── Toolbar ─────────────────────────────────────────────────────

    def _setup_toolbar(self) -> None:
        """Create the main toolbar with emoji-styled buttons."""
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("twTimeWindowToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QtCore.QSize(16, 16))
        toolbar.setContentsMargins(4, 2, 4, 2)
        if toolbar.layout() is not None:
            toolbar.layout().setSpacing(6)
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.setStyleSheet(
            """
            QToolBar#twTimeWindowToolbar {
                background-color: transparent;
                border: none;
                padding: 3px 4px;
                spacing: 6px;
            }
            QToolBar#twTimeWindowToolbar::separator {
                width: 8px;
            }
            QToolBar#twTimeWindowToolbar QToolButton {
                background-color: rgba(45, 45, 45, 210);
                border: 1px solid rgba(255, 255, 255, 45);
                border-radius: 4px;
                padding: 4px 8px;
                margin: 0px;
            }
            QToolBar#twTimeWindowToolbar QToolButton:hover {
                background-color: rgba(70, 70, 70, 230);
            }
            QToolBar#twTimeWindowToolbar QToolButton:pressed {
                background-color: rgba(90, 90, 90, 240);
            }
            QToolBar#twTimeWindowToolbar #twToolbarAdd {
                color: #7de3ff;
                font-weight: bold;
            }
            QToolBar#twTimeWindowToolbar #twToolbarProcess {
                color: #8aff8a;
                font-weight: bold;
            }
            QToolBar#twTimeWindowToolbar #twToolbarClear {
                color: #ff7b7b;
                font-weight: bold;
            }
            QToolBar#twTimeWindowToolbar #twToolbarHelp {
                color: #ffb86c;
                font-weight: bold;
            }
            """
        )

        # File add / database selection are provided by the unified file list's
        # own ➕ Files / 📁 Folder / 🗄️ Database buttons (no duplicate toolbar actions).
        process_action = QtWidgets.QAction(f"{Glyphs.CLOCK} {i18n.tr('Process')}", self)
        process_action.setToolTip(
            i18n.tr(
                "Compute time-window BIDs for all queued TTTR files and save .bst output files."
            )
        )
        process_action.triggered.connect(self._process_all)
        toolbar.addAction(process_action)

        toolbar.addSeparator()

        clear_action = QtWidgets.QAction(f"🗑️\ufe0f {i18n.tr('Clear')}", self)
        clear_action.setToolTip(i18n.tr("Clear the file list and processing results."))
        clear_action.triggered.connect(self._clear_all)
        toolbar.addAction(clear_action)

        toolbar.addSeparator()

        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        toolbar.addWidget(spacer)

        help_action = QtWidgets.QAction(f"ℹ️\ufe0f {i18n.tr('Help')}", self)
        help_action.setToolTip(i18n.tr("Show a short help page explaining how this tool works."))
        help_action.triggered.connect(self._show_help)
        toolbar.addAction(help_action)

        # Apply object names for stylesheet targeting
        name_map = {
            f"{Glyphs.OPEN} Add Files": "twToolbarAdd",
            f"{Glyphs.DATABASE} Database": "twToolbarDatabase",
            f"{Glyphs.CLOCK} {i18n.tr('Process')}": "twToolbarProcess",
            f"🗑️\ufe0f {i18n.tr('Clear')}": "twToolbarClear",
            f"ℹ️\ufe0f {i18n.tr('Help')}": "twToolbarHelp",
        }
        for widget in toolbar.children():
            if isinstance(widget, QtWidgets.QToolButton):
                action = widget.defaultAction()
                if action is None:
                    continue
                object_name = name_map.get(action.text())
                if object_name is not None:
                    widget.setObjectName(object_name)
                    widget.setAutoRaise(True)

    # ── Status bar ──────────────────────────────────────────────────

    def _setup_statusbar(self) -> None:
        """Create the status bar."""
        self._status_bar = QtWidgets.QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage(i18n.tr("Ready"))

    # ── Menu ────────────────────────────────────────────────────────

    def _setup_menu(self) -> None:
        """Create menu actions."""
        file_menu = self.menuBar().addMenu(i18n.tr("File"))
        exit_action = QtWidgets.QAction(i18n.tr("Exit"), self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = self.menuBar().addMenu(i18n.tr("Help"))
        about_action = QtWidgets.QAction(i18n.tr("About"), self)
        about_action.triggered.connect(self._show_help)
        help_menu.addAction(about_action)

    # ── Slots ───────────────────────────────────────────────────────

    def _choose_dir(self) -> None:
        """Open a directory chooser dialog."""
        from chisurf.gui.widgets.general import get_directory

        d, _ = get_directory(caption=i18n.tr("Select output folder"))
        if d is not None:
            self.output_edit.setText(str(d))

    def _on_files_changed(self) -> None:
        """Rebuild the preview combo when the unified file list changes."""
        self.cmb_file.blockSignals(True)
        current = self.cmb_file.currentData()
        self.cmb_file.clear()
        for path in self._file_paths:
            self.cmb_file.addItem(path.name, str(path))
        if current is not None:
            idx = self.cmb_file.findData(current)
            if idx >= 0:
                self.cmb_file.setCurrentIndex(idx)
        elif self.cmb_file.count() > 0:
            self.cmb_file.setCurrentIndex(0)
        self.cmb_file.blockSignals(False)

        if self.cmb_file.count() > 0:
            self._on_select_file(0)

    def _on_select_file(self, _idx: int) -> None:
        """Load a preview for the selected file."""
        path_str = self.cmb_file.currentData()
        if not path_str:
            self.preview_plot.clear()
            return
        path = Path(path_str)
        tw_ms = float(self.tws_spin.value())

        self._status_bar.showMessage(f"Loading preview for {path.name}…")
        try:
            diag = self._client.load_preview(path, tw_ms)
            if not diag or "counts" not in diag:
                self.preview_plot.clear()
                self._status_bar.showMessage(i18n.tr("Preview unavailable"))
                return

            counts = diag["counts"]
            time_axis = diag["time_axis"]

            self.preview_plot.clear()
            self.preview_plot.line(time_axis, counts, pen="y", width=1)

            tw_s = tw_ms / 1000.0
            dashed = cp.to_pen("w", width=1, style="dash")
            for t in np.arange(0, time_axis[-1] + tw_s, tw_s):
                if t == 0:
                    continue
                self.preview_plot.vline(t, pen=dashed)

            self._status_bar.showMessage(f"Preview: {path.name}")
        except Exception as exc:
            self.preview_plot.clear()
            self._log(f"Preview failed for {path.name}: {exc}")
            self._status_bar.showMessage(i18n.tr("Preview failed"))

    def _on_settings_changed(self) -> None:
        """Refresh preview when time window changes."""
        self._on_select_file(self.cmb_file.currentIndex())

    def _process_all(self) -> None:
        """Compute time-window BIDs for all queued files."""
        if not self._file_paths:
            self._log("No TTTR files to process. Add files first.")
            self._status_bar.showMessage(i18n.tr("No files to process"))
            return

        tw_ms = float(self.tws_spin.value())
        out_dir_txt = self.output_edit.text().strip()
        output_dir: Path | None = Path(out_dir_txt) if out_dir_txt else None

        self._status_bar.showMessage(i18n.tr("Processing files…"))
        self._log(f"Processing {len(self._file_paths)} file(s) with time window = {tw_ms:.3f} ms…")

        try:
            result = self._client.analyze_files(
                self._file_paths,
                time_window_ms=tw_ms,
                output_dir=output_dir,
            )
            self._last_result = TimeWindowResult(**result)

            metadata = result.get("metadata", {})
            out_dir = metadata.get("output_dir", "?")
            total_windows = metadata.get("total_windows", 0)

            if out_dir and out_dir != "?":
                self.output_edit.setText(str(out_dir))

            self._log(
                f"Done: {len(self._file_paths)} file(s), "
                f"{total_windows} total windows. "
                f"Output: {out_dir}"
            )

            n_windows = result.get("n_windows", {})
            for fp, cnt in n_windows.items():
                self._log(f"  {Path(fp).name}: {cnt} windows")

            self._status_bar.showMessage(
                f"Processed {len(self._file_paths)} file(s), {total_windows} windows"
            )
        except Exception as exc:
            self._log(f"Processing failed: {exc}")
            self._status_bar.showMessage(i18n.tr("Processing failed"))

    def _clear_all(self) -> None:
        """Clear the file list and results."""
        self.file_list.clear()  # clears the list + _file_paths (via model) + combo
        self._last_result = None
        self.preview_plot.clear()
        self.status_log.clear()
        self._status_bar.showMessage(i18n.tr("Cleared"))

    def _show_help(self) -> None:
        """Show the help dialog."""
        dialog = HelpDialog(self)
        dialog.exec_()

    # ── Logging ─────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        """Append a message to the status log."""
        try:
            logging.info(msg)
        except Exception:
            pass
        try:
            self.status_log.append(msg)
            self.status_log.ensureCursorVisible()
        except Exception:
            pass

    # ── Drag-drop on main window ────────────────────────────────────

    # ── Dock layout persistence ────────────────────────────────────

    def _save_dock_layout(self) -> None:
        """Save the current dock layout to QSettings."""
        try:
            import json

            settings = QtCore.QSettings("chisurf", "TTTRTimeWindowTool")
            layout_state = self.dock_area.get_layout_state()
            settings.setValue("dock_layout", json.dumps(layout_state, sort_keys=True))
            settings.sync()
        except Exception:
            pass

    def _restore_dock_layout(self) -> None:
        """Restore the dock layout from QSettings."""
        try:
            import json

            settings = QtCore.QSettings("chisurf", "TTTRTimeWindowTool")
            value = settings.value("dock_layout")
            if isinstance(value, str):
                layout_state = json.loads(value)
            elif isinstance(value, dict):
                layout_state = value
            else:
                return
            self.dock_area.set_layout_state(layout_state, emit_change=False)
        except Exception:
            pass

    # ── Window geometry persistence ─────────────────────────────────

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Save window geometry and dock layout before closing."""
        self._save_dock_layout()
        self._save_geometry()
        super().closeEvent(event)

    def _save_geometry(self) -> None:
        """Save window geometry to QSettings."""
        try:
            settings = QtCore.QSettings("chisurf", "TTTRTimeWindowTool")
            settings.setValue("geometry", self.saveGeometry())
            settings.sync()
        except Exception:
            pass
