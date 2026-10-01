"""
Trace Browser Plugin

A simple two-page plugin to browse intensity traces from PTU/TTTR files in a folder.
Page 0: Setup definition using DetectorWizardPage (TTTR channel setup).
Page 1: Trace browser with folder selection, file list, star quality rating (0–3),
        annotation text, filter by rating, preview plot, and export selected files.

Metadata (ratings and annotations) are stored in a JSON file in the same folder
as the traces: .trace_browser_meta.json

The state and the work behind the widgets (folder scan, rating filter, ratings and
notes, caches, trace loading) are in :class:`.gui.model.TraceBrowserModel`; this
module is the Qt view of it.
"""

import csv
import importlib.util
import os
import pathlib
import shutil
from typing import Dict, List, Optional, Tuple

import numpy as np
from qtpy.QtCore import QEvent, QSize, Qt, QTimer, Signal
from qtpy.QtGui import QColor, QFont, QPainter
from qtpy.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Logging
from chisurf import logging
from chisurf.gui import dialogs
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.widgets.fitting.scientific_spinbox import ScientificDoubleSpinBox
from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizardPage

# Reuse existing widgets/utilities
from chisurf.plugins.tttr.intensity_trace import IntensityPlotWidget, IntensityTrace

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:

    def persist_plugin_state(n):
        return lambda c: c


# Import TTTR Time Window plugin
try:
    from chisurf.plugins.tttr.tttr_time_windows.api.selection import compute_bids_from_tttr
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import (
        TTTRTimeWindowTool as TTTRTimeWindowWizard,
    )
except Exception:
    TTTRTimeWindowWizard = None
    compute_bids_from_tttr = None

try:
    import tttrlib
except Exception:
    tttrlib = None

# Burst analysis and NDXplorer integration
try:
    from chisurf.core.fio.fluorescence import burst as burstio
except Exception:
    burstio = None

# Optional docx dependency (python-docx)
try:
    from docx import Document
    from docx.shared import Inches
except Exception:
    Document = None
    Inches = None

# Qt-free state and logic (scan, filter, ratings/notes, caches, trace loading)
from chisurf.plugins.tttr.trace_browser.gui.model import (  # noqa: F401  (re-exported)
    TraceBrowserModel,
    get_tttr_supported_exts,
)


class StarCombo(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Ratings 0..3
        self.addItem(f"{Glyphs.STAR_OFF}{Glyphs.STAR_OFF}{Glyphs.STAR_OFF}", 0)
        self.addItem(f"{Glyphs.STAR_ON}{Glyphs.STAR_OFF}{Glyphs.STAR_OFF}", 1)
        self.addItem(f"{Glyphs.STAR_ON}{Glyphs.STAR_ON}{Glyphs.STAR_OFF}", 2)
        self.addItem(f"{Glyphs.STAR_ON}{Glyphs.STAR_ON}{Glyphs.STAR_ON}", 3)

    def set_rating(self, r: int):
        idx = max(0, min(3, int(r)))
        self.setCurrentIndex(idx)

    def rating(self) -> int:
        return int(self.currentData())

    def keyPressEvent(self, event):
        # Make Tab/Shift+Tab jump directly between rating controls (same column, next/prev row)
        try:
            key = event.key()
            if key in (Qt.Key_Tab, Qt.Key_Backtab):
                table = self.parent()
                if isinstance(table, QTableWidget):
                    my_row = -1
                    col = 1
                    for r in range(table.rowCount()):
                        if table.cellWidget(r, col) is self:
                            my_row = r
                            break
                    if my_row != -1:
                        forward = (key == Qt.Key_Tab) and not (event.modifiers() & Qt.ShiftModifier)
                        step = 1 if forward else -1
                        next_row = my_row + step
                        if 0 <= next_row < table.rowCount():
                            nxt = table.cellWidget(next_row, col)
                            # Accept either StarCombo or StarRatingWidget
                            if isinstance(nxt, (StarCombo, StarRatingWidget)):
                                table.selectRow(next_row)
                                nxt.setFocus(Qt.TabFocusReason)
                                event.accept()
                                return
        except Exception:
            pass
        super().keyPressEvent(event)


class StarRatingWidget(QWidget):
    ratingChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rating = 0
        self._stars = 3
        self._padding = 4
        self.setFocusPolicy(Qt.StrongFocus)
        try:
            self.setCursor(Qt.PointingHandCursor)
        except Exception:
            pass

    def sizeHint(self):
        try:
            # Approximate width for 3 stars at a decent font size
            return QSize(60, 22)
        except Exception:
            return super().sizeHint()

    def set_rating(self, r: int):
        r = max(0, min(self._stars, int(r)))
        if r != self._rating:
            self._rating = r
            self.update()

    def rating(self) -> int:
        return int(self._rating)

    def _rating_from_pos(self, x: int) -> int:
        # Map click x-position to 1..3; clicking same rating toggles to 0
        w = max(1, self.width() - 2 * self._padding)
        rel = max(0.0, min(1.0, (x - self._padding) / float(w)))
        new_r = int(rel * self._stars) + 1
        new_r = max(1, min(self._stars, new_r))
        # toggle off if clicking same value
        if new_r == self._rating:
            return 0
        return new_r

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.LeftButton:
                new_r = self._rating_from_pos(event.x())
                if new_r != self._rating:
                    self._rating = new_r
                    self.update()
                    self.ratingChanged.emit(int(self._rating))
                    event.accept()
                    return
            elif event.button() == Qt.RightButton:
                # Right-click clears rating
                if self._rating != 0:
                    self._rating = 0
                    self.update()
                    self.ratingChanged.emit(0)
                    event.accept()
                    return
        except Exception:
            pass
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        try:
            key = event.key()
            # Left/Right adjust rating as usual
            if key == Qt.Key_Left:
                self.set_rating(self._rating - 1)
                self.ratingChanged.emit(int(self._rating))
                event.accept()
                return
            elif key == Qt.Key_Right:
                self.set_rating(self._rating + 1)
                self.ratingChanged.emit(int(self._rating))
                event.accept()
                return
            # Up/Down should exclusively change the trace (row) selection in the table
            elif key in (Qt.Key_Up, Qt.Key_Down):
                table = self.parent()
                if isinstance(table, QTableWidget):
                    # Find my row in the table
                    my_row = -1
                    col = 1
                    for r in range(table.rowCount()):
                        if table.cellWidget(r, col) is self:
                            my_row = r
                            break
                    if my_row != -1:
                        delta = -1 if key == Qt.Key_Up else 1
                        next_row = my_row + delta
                        if 0 <= next_row < table.rowCount():
                            table.selectRow(next_row)
                            try:
                                table.setCurrentCell(next_row, 0)
                            except Exception:
                                pass
                            try:
                                table.setFocus(Qt.OtherFocusReason)
                            except Exception:
                                pass
                        # Even if we can't move (top/bottom), consume the event to keep exclusivity
                        event.accept()
                        return
            elif key in (Qt.Key_Tab, Qt.Key_Backtab):
                table = self.parent()
                if isinstance(table, QTableWidget):
                    my_row = -1
                    col = 1
                    for r in range(table.rowCount()):
                        if table.cellWidget(r, col) is self:
                            my_row = r
                            break
                    if my_row != -1:
                        forward = (key == Qt.Key_Tab) and not (event.modifiers() & Qt.ShiftModifier)
                        step = 1 if forward else -1
                        next_row = my_row + step
                        if 0 <= next_row < table.rowCount():
                            nxt = table.cellWidget(next_row, col)
                            if isinstance(nxt, (StarCombo, StarRatingWidget)):
                                table.selectRow(next_row)
                                nxt.setFocus(Qt.TabFocusReason)
                                event.accept()
                                return
        except Exception:
            pass
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            rect = self.rect().adjusted(self._padding, 0, -self._padding, 0)
            # Choose font size to fit height
            font = painter.font()
            font.setPointSize(max(9, int(rect.height() * 0.6)))
            painter.setFont(font)
            stars_str = (Glyphs.STAR_ON * int(self._rating)) + (
                Glyphs.STAR_OFF * int(self._stars - self._rating)
            )
            # Center text
            painter.setPen(QColor(240, 180, 0))
            painter.drawText(rect, Qt.AlignCenter, stars_str)
        finally:
            painter.end()


class NoHoverSelectTable(QTableWidget):
    """A table view that never changes selection on mere mouse hover.
    Selection only changes on clicks/keyboard. Mouse move without button is ignored.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        try:
            self.setMouseTracking(False)
            self.setAttribute(Qt.WA_Hover, False)
        except Exception:
            pass

    def mouseMoveEvent(self, event):
        try:
            if getattr(event, "buttons", lambda: Qt.NoButton)() == Qt.NoButton:
                # Ignore pure hover moves to avoid hover-driven selection changes
                event.ignore()
                return
        except Exception:
            pass
        try:
            super().mouseMoveEvent(event)
        except Exception:
            pass

    def event(self, event):
        try:
            et = event.type() if event is not None else None
            if et in (QEvent.HoverEnter, QEvent.HoverMove, QEvent.HoverLeave):
                return False  # do not handle hover events at all
        except Exception:
            pass
        return super().event(event)


@persist_plugin_state("trace_browser")
def _model_property(name: str) -> property:
    """Return a property that reads and writes ``self.model.<name>``."""
    return property(
        lambda self: getattr(self.model, name),
        lambda self, value: setattr(self.model, name, value),
    )


class TraceBrowser(QWidget):
    # State that lives in the Qt-free model; the widget reads and writes it through these.
    current_folder = _model_property("current_folder")
    meta = _model_property("meta")
    setup_settings = _model_property("setup_settings")
    selected_channels = _model_property("selected_channels")
    _current_file = _model_property("current_file")
    _client = _model_property("_client")
    _trace_mem_cache = _model_property("_trace_mem_cache")
    _is_image_cache = _model_property("_is_image_cache")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = TraceBrowserModel()
        # the CLSM image probe stays overridable on the widget
        self.model.image_probe = lambda p: self._is_image_tttr(p)
        self.setWindowTitle("Trace Browser")
        # Set default window size
        try:
            self.resize(800, 600)
        except Exception:
            pass

        # State (folder, setup, channels, metadata, caches) lives in self.model
        self._is_loading: bool = False
        # Debounced metadata saving to keep UI snappy on rating changes
        self._meta_save_timer: QTimer | None = None
        try:
            self._meta_save_timer = QTimer(self)
            self._meta_save_timer.setSingleShot(True)
            self._meta_save_timer.setInterval(300)
            self._meta_save_timer.timeout.connect(self._flush_meta_to_disk)
        except Exception:
            self._meta_save_timer = None

        # Two-page layout using a simple stacked layout approach
        self.root_layout = QVBoxLayout(self)
        try:
            self.root_layout.setContentsMargins(0, 0, 0, 0)
            self.root_layout.setSpacing(0)
        except Exception:
            pass

        # Page 0: Detector setup
        self.page0 = QWidget(self)
        p0_layout = QVBoxLayout(self.page0)
        p0_layout.addWidget(QLabel("Setup definition (DetectorWizard)", self.page0))
        self.detector_page = DetectorWizardPage(
            show_help=False,
            show_setups_file=True,
            show_setup_selection=True,
            show_tttr_reading=True,
            show_tables=True,
            show_add_inputs=True,
        )
        self.btn_continue = QPushButton("Continue", self.page0)
        self.btn_continue.setToolTip("Accept detector setup and open trace browser")
        self.btn_continue.clicked.connect(self._on_continue)
        try:
            self.btn_continue.setMaximumHeight(26)
            self.btn_continue.setStyleSheet(
                "QPushButton{padding:2px 8px; background-color:#2e7d32; color:white; font-weight:bold;} QPushButton:hover{background-color:#388e3c;}"
            )
        except Exception:
            pass
        p0_top = QWidget(self.page0)
        p0_top_layout = QHBoxLayout(p0_top)
        try:
            p0_top_layout.setContentsMargins(0, 0, 0, 0)
            p0_top_layout.setSpacing(4)
        except Exception:
            pass
        p0_top_layout.addWidget(self.btn_continue)
        p0_top_layout.addStretch(1)
        p0_layout.addWidget(p0_top)
        p0_layout.addWidget(self.detector_page)

        # Page 1: Trace browser
        self.page1 = QWidget(self)
        p1_layout = QVBoxLayout(self.page1)
        try:
            p1_layout.setContentsMargins(0, 0, 0, 0)
            p1_layout.setSpacing(0)
        except Exception:
            pass

        # Controls row
        ctrl_row = QHBoxLayout()
        try:
            ctrl_row.setContentsMargins(0, 0, 0, 0)
            ctrl_row.setSpacing(0)
        except Exception:
            pass
        self.folder_label = QLabel("No folder selected", self.page1)

        # Back to setup button
        self.btn_back = QPushButton("\u2190 Select setup", self.page1)
        self.btn_back.clicked.connect(self._on_back_to_setup)
        try:
            self.btn_back.setMaximumHeight(26)
            self.btn_back.setStyleSheet(
                "QPushButton{padding:2px 6px; background-color: #ffd166; color: #222;} QPushButton:hover{background-color:#ffca3a;}"
            )
        except Exception:
            pass
        ctrl_row.addWidget(self.btn_back)

        # Include subfolder option (renamed from "Process subfolders")
        self.chk_subfolders = QCheckBox("Include subfolders", self.page1)
        self.chk_subfolders.setChecked(False)
        try:
            self.chk_subfolders.toggled.connect(lambda _=None: self._on_subfolders_toggled())
        except Exception:
            pass

        self.filter_combo = QComboBox(self.page1)
        self.filter_combo.addItems(
            [
                "All",
                f"≥ 1{Glyphs.STAR_ON}",
                f"≥ 2{Glyphs.STAR_ON}{Glyphs.STAR_ON}",
                f"≥ 3{Glyphs.STAR_ON}{Glyphs.STAR_ON}{Glyphs.STAR_ON}",
                f"Only 0{Glyphs.STAR_ON}",
            ]
        )
        self.filter_combo.currentIndexChanged.connect(self._apply_filter)

        # Clear button to clear the file list (compact tool button)
        self.btn_clear = QToolButton(self.page1)
        self.btn_clear.setText("Clear")
        self.btn_clear.setToolTip("Clear file list")
        self.btn_clear.clicked.connect(self._on_clear)
        try:
            self.btn_clear.setAutoRaise(True)
            self.btn_clear.setToolButtonStyle(Qt.ToolButtonTextOnly)
        except Exception:
            pass

        # Clear caches button (in-memory and on-disk caches) - compact
        self.btn_clear_caches = QToolButton(self.page1)
        self.btn_clear_caches.setText("Clear caches")
        self.btn_clear_caches.setToolTip("Clear in-memory and on-disk caches for this folder")
        self.btn_clear_caches.clicked.connect(self._on_clear_caches)
        try:
            self.btn_clear_caches.setAutoRaise(True)
            self.btn_clear_caches.setToolButtonStyle(Qt.ToolButtonTextOnly)
        except Exception:
            pass

        ctrl_row.addWidget(self.folder_label)
        ctrl_row.addWidget(QLabel("Filter:"))
        ctrl_row.addWidget(self.filter_combo)

        self.window_ms_spin = QDoubleSpinBox(self.page1)
        self.window_ms_spin.setDecimals(3)
        self.window_ms_spin.setRange(0.001, 10000.0)
        self.window_ms_spin.setSingleStep(0.1)
        self.window_ms_spin.setValue(10.0)
        self.window_ms_spin.setSuffix(" ms bin")
        self.window_ms_spin.setKeyboardTracking(False)
        self.window_ms_spin.valueChanged.connect(self._on_window_changed)
        ctrl_row.addWidget(self.window_ms_spin)

        # Y-range controls - place Ymin above Ymax
        ymin_label = QLabel("Ymin:", self.page1)
        self.y_min_spin = ScientificDoubleSpinBox(self.page1)
        self.y_min_spin.setRange(-1e9, 1e12)
        self.y_min_spin.setDecimals(0)
        self.y_min_spin.setValue(0)
        self.y_min_spin.sigValueChanged.connect(self._on_y_range_changed)
        # Update while typing too
        try:
            self.y_min_spin.sigValueChanging.connect(self._on_y_range_changed)
        except Exception:
            pass
        # Make spinbox expand and keep a reasonable minimum width
        try:
            self.y_min_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.y_min_spin.setMinimumWidth(70)
        except Exception:
            pass

        ymax_label = QLabel("Ymax:", self.page1)
        self.y_max_spin = ScientificDoubleSpinBox(self.page1)
        self.y_max_spin.setRange(-1e9, 1e12)
        self.y_max_spin.setDecimals(0)
        self.y_max_spin.setValue(1000)
        self.y_max_spin.sigValueChanged.connect(self._on_y_range_changed)
        # Update while typing too
        try:
            self.y_max_spin.sigValueChanging.connect(self._on_y_range_changed)
        except Exception:
            pass
        # Make spinbox expand and keep a reasonable minimum width
        try:
            self.y_max_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.y_max_spin.setMinimumWidth(70)
        except Exception:
            pass

        # Stack Ymin above Ymax in a compact grid inside a group box and add to the control row
        y_group = QGroupBox("", self.page1)
        try:
            y_group.setFlat(True)
        except Exception:
            pass
        y_layout = QGridLayout(y_group)
        try:
            y_layout.setContentsMargins(0, 0, 0, 0)
            y_layout.setHorizontalSpacing(0)
            y_layout.setVerticalSpacing(0)
        except Exception:
            pass
        y_layout.addWidget(ymin_label, 0, 0)
        y_layout.addWidget(self.y_min_spin, 0, 1)
        y_layout.addWidget(ymax_label, 1, 0)
        y_layout.addWidget(self.y_max_spin, 1, 1)
        ctrl_row.addWidget(y_group)

        self.btn_export = QToolButton(self.page1)
        self.btn_export.setText("Export selected…")
        self.btn_export.setToolTip("Export selected raw trace files")
        self.btn_export.clicked.connect(self._on_export)
        try:
            self.btn_export.setAutoRaise(True)
            self.btn_export.setToolButtonStyle(Qt.ToolButtonTextOnly)
        except Exception:
            pass

        self.btn_export_csv = QToolButton(self.page1)
        self.btn_export_csv.setText("Export CSV…")
        self.btn_export_csv.setToolTip(
            "Export computed intensity traces as CSV files (per listed file)"
        )
        self.btn_export_csv.clicked.connect(self._on_export_csv)
        try:
            self.btn_export_csv.setAutoRaise(True)
            self.btn_export_csv.setToolButtonStyle(Qt.ToolButtonTextOnly)
        except Exception:
            pass

        self.btn_export_docx = QToolButton(self.page1)
        self.btn_export_docx.setText("Export DOCX…")
        self.btn_export_docx.setToolTip("Export selected traces and annotations as a DOCX report")
        self.btn_export_docx.clicked.connect(self._on_export_docx)
        try:
            self.btn_export_docx.setAutoRaise(True)
            self.btn_export_docx.setToolButtonStyle(Qt.ToolButtonTextOnly)
        except Exception:
            pass

        self.btn_transfer_to_analysis = QToolButton(self.page1)
        self.btn_transfer_to_analysis.setText("to HMM")
        self.btn_transfer_to_analysis.setToolTip(
            "Open selected trace in Single-Molecule Intensity Trace plugin for HMM analysis"
        )
        self.btn_transfer_to_analysis.clicked.connect(self._on_transfer_to_analysis)
        try:
            self.btn_transfer_to_analysis.setAutoRaise(True)
            self.btn_transfer_to_analysis.setToolButtonStyle(Qt.ToolButtonTextOnly)
        except Exception:
            pass

        self.btn_transfer_to_tw = QToolButton(self.page1)
        self.btn_transfer_to_tw.setText("to TW")
        self.btn_transfer_to_tw.setToolTip(
            "Open selected trace in TTTR Time Window plugin for BID generation"
        )
        self.btn_transfer_to_tw.clicked.connect(self._on_transfer_to_tw)
        try:
            self.btn_transfer_to_tw.setAutoRaise(True)
            self.btn_transfer_to_tw.setToolButtonStyle(Qt.ToolButtonTextOnly)
        except Exception:
            pass

        # One-click NDXplorer button
        self.btn_ndx_oneclick = QToolButton(self.page1)
        self.btn_ndx_oneclick.setText("to NDX")
        self.btn_ndx_oneclick.setToolTip("Compute burst analysis (from current TW) and open in ndX")
        self.btn_ndx_oneclick.clicked.connect(self._on_open_in_ndxplorer)
        try:
            self.btn_ndx_oneclick.setAutoRaise(True)
            self.btn_ndx_oneclick.setToolButtonStyle(Qt.ToolButtonTextOnly)
        except Exception:
            pass

        # Add the top control row (compact)
        ctrl_row.addStretch(1)

        # New compact tools row below subfolder/filter
        tools_row = QHBoxLayout()
        try:
            tools_row.setContentsMargins(0, 0, 0, 0)
            tools_row.setSpacing(0)
        except Exception:
            pass
        # Order: to HMM | to TW | Export | CSV | DOCX | Clear | Clear caches
        tools_row.addWidget(self.btn_transfer_to_analysis)
        tools_row.addWidget(self.btn_transfer_to_tw)
        tools_row.addWidget(self.btn_ndx_oneclick)
        tools_row.addSpacing(8)
        tools_row.addWidget(self.btn_export)
        tools_row.addWidget(self.btn_export_csv)
        tools_row.addWidget(self.btn_export_docx)
        tools_row.addSpacing(8)
        tools_row.addWidget(self.btn_clear)
        tools_row.addWidget(self.btn_clear_caches)
        tools_row.addStretch(1)
        for tool_btn in (
            self.btn_transfer_to_analysis,
            self.btn_transfer_to_tw,
            self.btn_ndx_oneclick,
            self.btn_export,
            self.btn_export_csv,
            self.btn_export_docx,
            self.btn_clear,
            self.btn_clear_caches,
        ):
            try:
                tool_btn.setVisible(False)
            except Exception:
                pass

        # Wrap the two top rows in a fixed-height container so they don't scale in fullscreen
        top_bar = QWidget(self.page1)
        top_bar_layout = QVBoxLayout(top_bar)
        try:
            top_bar_layout.setContentsMargins(0, 0, 0, 0)
            top_bar_layout.setSpacing(0)
        except Exception:
            pass
        top_bar_layout.addLayout(ctrl_row)
        top_bar_layout.addLayout(tools_row)
        try:
            top_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            # Constrain the height to its sizeHint to prevent vertical growth
            top_bar.setMaximumHeight(top_bar.sizeHint().height())
        except Exception:
            pass
        p1_layout.addWidget(top_bar)

        # Splitter: left list, right details
        splitter = QSplitter(self.page1)
        splitter.setOrientation(Qt.Horizontal)
        try:
            splitter.setHandleWidth(2)
        except Exception:
            pass

        # Left: table of files with rating and size
        self.table = NoHoverSelectTable(self.page1)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["File", "Rating", "Size (MB)"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        # Make Size column a bit narrower
        try:
            self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        except Exception:
            pass
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # Enable header-based sorting
        try:
            self.table.setSortingEnabled(True)
            self.table.horizontalHeader().setSortIndicatorShown(True)
        except Exception:
            pass
        # Disable mouse hover effects for the table
        try:
            self.table.setAttribute(Qt.WA_Hover, False)
        except Exception:
            pass
        try:
            self.table.setMouseTracking(False)
        except Exception:
            pass
        # Neutralize hover highlight via stylesheet (keeps normal selection highlight)
        self.table.setStyleSheet("QTableView::item:hover { background: transparent; }")
        # Make table rows and text more space efficient
        try:
            self.table.setWordWrap(False)
            self.table.setTextElideMode(Qt.ElideMiddle)
            vh = self.table.verticalHeader()
            vh.setVisible(False)
            vh.setDefaultSectionSize(18)
            vh.setMinimumSectionSize(16)
        except Exception:
            pass
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        splitter.addWidget(self.table)

        # Right: plot and annotation separated by a vertical splitter
        right_splitter = QSplitter(self.page1)
        right_splitter.setOrientation(Qt.Vertical)
        try:
            right_splitter.setHandleWidth(2)
        except Exception:
            pass

        # Top: main plot
        self.plot = IntensityPlotWidget(self.page1)
        right_splitter.addWidget(self.plot)

        # Bottom: annotation editor (resizable via splitter)
        self.annotation = QTextEdit(self.page1)
        try:
            self.annotation.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            # Remove fixed max height so splitter controls the space
            self.annotation.setMaximumHeight(16777215)
            self.annotation.setPlaceholderText("Annotation")
            self.annotation.setStyleSheet("QTextEdit { padding: 0; }")
            self.annotation.setMinimumHeight(60)
        except Exception:
            pass
        self.annotation.textChanged.connect(self._on_annotation_changed)
        right_splitter.addWidget(self.annotation)

        # Prefer more space for plot initially
        try:
            right_splitter.setStretchFactor(0, 3)
            right_splitter.setStretchFactor(1, 1)
        except Exception:
            pass

        splitter.addWidget(right_splitter)

        p1_layout.addWidget(splitter, 1)

        # Add pages to root (start on browser)
        self.root_layout.addWidget(self.page0)
        self.root_layout.addWidget(self.page1)
        self.page0.hide()
        self.page1.show()

        self._annotation_changing: bool = False

        # Accept drops on the whole widget and the file table
        self.setAcceptDrops(True)
        self.table.setAcceptDrops(True)
        # Forward drag-and-drop events from table to this widget via event filter
        self.table.installEventFilter(self)

        # Initialize subfolder checkbox after UI is built
        try:
            if hasattr(self, "chk_subfolders") and callable(
                getattr(self.chk_subfolders, "isChecked", None)
            ):
                # No-op; state already set
                pass
        except Exception:
            pass

        # Store reference to intensity trace windows to prevent garbage collection
        self.intensity_trace_windows = []
        # Store reference to time window wizards to prevent garbage collection
        self.time_window_wizards = []
        # Store reference to NDXplorer windows to prevent garbage collection
        self.ndxplorer_windows = []

        self._on_continue()

    def _on_continue(self):
        # Store setup settings and selected channels (union of all detector channels)
        self.model.apply_setup(self.detector_page.get_settings(), self._setup_filetype())
        logging.info("TraceBrowser: Setup accepted from DetectorWizard")
        logging.debug(f"TraceBrowser: Selected channels = {self.selected_channels}")
        self.page0.hide()
        self.page1.show()

    def _on_back_to_setup(self):
        logging.info("TraceBrowser: Back to setup")
        try:
            self.page1.hide()
            self.page0.show()
        except Exception:
            pass

    def _on_pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select folder with PTU/TTTR files")
        if not path:
            return
        self._open_folder(pathlib.Path(path))

    def _open_folder(self, folder: pathlib.Path):
        try:
            if not folder.exists() or not folder.is_dir():
                logging.warning(f"TraceBrowser: Selected path is not a folder: {folder}")
                return
            self._is_loading = True
            self.current_folder = folder
            self.folder_label.setText(str(folder))
            logging.info(f"TraceBrowser: Opened folder {folder}")
            self.model.load_meta()
            self._scan_and_fill()
        except Exception as e:
            logging.exception(f"TraceBrowser: Failed to open folder {folder}: {e}")
        finally:
            self._is_loading = False

    def _rel_key(self, path: pathlib.Path) -> str:
        return self.model.rel_key(path)

    def _meta_get(self, path: pathlib.Path) -> dict:
        return self.model.meta_get(path)

    def _meta_set(self, path: pathlib.Path, rec: dict):
        self.model.meta_set(path, rec)

    def _setup_filetype(self):
        """Return the setup page's selected file type (``None`` for Auto or unavailable)."""
        try:
            return self.detector_page.filetype
        except Exception:
            return None

    def _sync_model(self):
        """Copy the widget-held view state (checkbox, filter, bin window, y range) to the model."""
        m = self.model
        try:
            m.include_subfolders = bool(
                getattr(self, "chk_subfolders", None) and self.chk_subfolders.isChecked()
            )
        except Exception:
            m.include_subfolders = False
        m.filter_index = self.filter_combo.currentIndex()
        m.setup_filetype = self._setup_filetype()
        m.window_ms = float(self.window_ms_spin.value())
        m.y_min = float(self.y_min_spin.value())
        m.y_max = float(self.y_max_spin.value())

    def _scan_and_fill(self):
        if not self.current_folder:
            return
        # The model scans the folder (setup extensions, optional recursion, .trash and
        # image files skipped, channel auto-detection) and applies the rating filter.
        self._sync_model()
        rows = self.model.scan()
        # Fill table
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            p = pathlib.Path(row["path"])
            rating = int(row["rating"])
            sz = int(row["size"])
            # Display relative path for clarity when using subfolders
            item_name = QTableWidgetItem(row["name"])
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)
            item_name.setData(Qt.UserRole, str(p))
            self.table.setItem(r, 0, item_name)

            # Provide an item in the Rating column for proper sorting
            rating_item = QTableWidgetItem()
            rating_item.setFlags(rating_item.flags() & ~Qt.ItemIsEditable)
            rating_item.setData(Qt.EditRole, int(rating))  # numeric sort key
            self.table.setItem(r, 1, rating_item)

            # Size column (display in MB; numeric sort key also in MB)
            size_item = QTableWidgetItem()
            size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)
            size_item.setText(row["size_text"])
            size_item.setToolTip(f"{row['size_text']} ({sz} bytes)")
            size_item.setData(Qt.EditRole, float(row["size_mb"]))  # numeric sort key in MB
            self.table.setItem(r, 2, size_item)

            stars = StarRatingWidget(self.table)
            stars.set_rating(rating)

            def _on_rating_changed(val, row=r, path=p, w=stars):
                # Update meta
                self._update_rating(path, int(val))
                # Determine current row of this widget (sorting/filtering may have moved it)
                cur_row = -1
                try:
                    for rr in range(self.table.rowCount()):
                        if self.table.cellWidget(rr, 1) is w:
                            cur_row = rr
                            break
                except Exception:
                    cur_row = row  # fall back to original row if something goes wrong
                # Update sort key for the rating column item at the current row
                try:
                    it = self.table.item(cur_row, 1)
                    if it is not None:
                        it.setData(Qt.EditRole, int(val))
                except Exception:
                    pass
                # Re-apply current filter and maintain current sorting (lightweight)
                self._refresh_list()
                try:
                    header = self.table.horizontalHeader()
                    self.table.sortItems(header.sortIndicatorSection(), header.sortIndicatorOrder())
                except Exception:
                    pass

            stars.ratingChanged.connect(_on_rating_changed)
            self.table.setCellWidget(r, 1, stars)

        # Initial sort by File ascending for convenience
        try:
            self.table.sortItems(0, Qt.AscendingOrder)
        except Exception:
            pass
        if rows:
            # Keep selection on the first visible row
            self.table.selectRow(0)
        else:
            self._clear_plot_and_annotation()
        # After populating, precompute traces for all listed files for snappy browsing
        try:
            self._precompute_all_traces()
        except Exception as _e:
            logging.debug(f"TraceBrowser: Precompute skipped or failed: {_e}")

    def _update_rating(self, path: pathlib.Path, rating: int):
        if not self.current_folder:
            return
        self._sync_model()
        self.model.set_rating(path, int(rating), flush=False)
        # Defer disk write to keep UI responsive
        self._schedule_meta_save()

    def _apply_filter(self):
        # Lightweight refresh: only update row visibility based on current filter and allowed extensions
        self._refresh_list()

    def _schedule_meta_save(self):
        try:
            if self._meta_save_timer is not None:
                # restart the debounce timer
                self._meta_save_timer.start()
            else:
                # fallback: immediate save if timer is unavailable
                self.model.flush_meta()
        except Exception:
            self.model.flush_meta()

    def _flush_meta_to_disk(self):
        self.model.flush_meta()

    def _refresh_list(self):
        # Update row visibility without rescanning files or recomputing traces
        try:
            rows = []
            missing_rows = []
            for r in range(self.table.rowCount()):
                item0 = self.table.item(r, 0)
                if item0 is None:
                    continue
                p_str = item0.data(Qt.UserRole)
                if not p_str:
                    continue
                p = pathlib.Path(p_str)
                # Drop rows whose files no longer exist (e.g., moved to .trash or deleted externally)
                try:
                    if not p.exists():
                        missing_rows.append(r)
                        continue
                except Exception:
                    # If existence check fails, be conservative and keep the row
                    pass
                rec = self._meta_get(p)
                rating = int(rec.get("rating", 0))
                rows.append((r, p, rating))
            # Remove rows for missing files (from bottom to top to keep indices valid)
            if missing_rows:
                for rr in sorted(missing_rows, reverse=True):
                    try:
                        self.table.removeRow(rr)
                    except Exception:
                        # If removeRow fails, just hide it
                        try:
                            self.table.setRowHidden(rr, True)
                        except Exception:
                            pass
                # If current plotted file no longer exists, clear plot/annotation
                try:
                    if self._current_file and not self._current_file.exists():
                        self._clear_plot_and_annotation()
                except Exception:
                    pass
                # After structural changes, rebuild the rows snapshot
                rows = []
                for r in range(self.table.rowCount()):
                    item0 = self.table.item(r, 0)
                    if item0 is None:
                        continue
                    p_str = item0.data(Qt.UserRole)
                    if not p_str:
                        continue
                    p = pathlib.Path(p_str)
                    rec = self._meta_get(p)
                    rating = int(rec.get("rating", 0))
                    rows.append((r, p, rating))
            # Filter rows by rating and by allowed extensions (in case setup filetype changed)
            self.model.filter_index = self.filter_combo.currentIndex()
            allowed_exts = self._allowed_exts_for_setup()
            visible = [t[0] for t in rows if self.model.accepts(t[2], t[1], allowed_exts)]
            # Hide all, then show accepted
            for r in range(self.table.rowCount()):
                self.table.setRowHidden(r, True)
            for r in visible:
                self.table.setRowHidden(r, False)
            # Keep a valid selection
            try:
                sel = (
                    self.table.selectionModel().selectedRows()
                    if self.table.selectionModel()
                    else []
                )
                sel_rows = [s.row() for s in sel]
                sel_rows = [r for r in sel_rows if r in visible]
                if not sel_rows and visible:
                    self.table.selectRow(visible[0])
            except Exception:
                if visible:
                    self.table.selectRow(visible[0])
            # Maintain existing sort order
            try:
                header = self.table.horizontalHeader()
                self.table.sortItems(header.sortIndicatorSection(), header.sortIndicatorOrder())
            except Exception:
                pass
        except Exception:
            # Fallback silently on any error
            pass

    def _allowed_exts_for_setup(self) -> set:
        """Return the extensions allowed by the setup page's current file type (see the model)."""
        self.model.setup_filetype = self._setup_filetype()
        return self.model.allowed_exts()

    def _on_clear(self):
        # Clear the file list (non-destructive; does not modify files or metadata)
        try:
            self.table.setRowCount(0)
            self._clear_plot_and_annotation()
            self.model.clear()
        except Exception:
            pass

    def _on_clear_caches(self):
        """Clear in-memory and on-disk caches for the current folder."""
        try:
            removed_dirs = self.model.clear_caches()
            logging.info(f"TraceBrowser: Cleared caches (memory + {removed_dirs} dir(s) removed)")
            try:
                dialogs.information(self, "Caches cleared", "Trace caches have been cleared.")
            except Exception:
                pass
        except Exception as e:
            logging.warning(f"TraceBrowser: Failed to clear caches: {e}")

    def _filter_accept(self, rating: int) -> bool:
        self.model.filter_index = self.filter_combo.currentIndex()
        return self.model.filter_accept(rating)

    def _on_selection_changed(self):
        # Commit current annotation for the currently shown file before switching
        try:
            self._commit_current_annotation()
        except Exception:
            pass
        paths = self._selected_paths()
        self.model.selected_files = [str(p) for p in paths]
        if not paths:
            self._clear_plot_and_annotation()
            return
        # Plot only first selected for preview
        self._plot_file(paths[0])
        # Ensure y-range from spinboxes is applied on selection change
        try:
            self._on_y_range_changed()
        except Exception:
            pass
        # Load annotation of the first selected
        self._annotation_changing = True
        try:
            rec = self._meta_get(paths[0])
            # Block signals while setting text to avoid spurious textChanged
            try:
                self.annotation.blockSignals(True)
            except Exception:
                pass
            self.annotation.setPlainText(rec.get("annotation", ""))
        finally:
            try:
                self.annotation.blockSignals(False)
            except Exception:
                pass
            self._annotation_changing = False

    def _on_annotation_changed(self):
        if (
            getattr(self, "_is_loading", False)
            or self._annotation_changing
            or not self.current_folder
        ):
            return
        paths = self._selected_paths()
        if not paths:
            return
        # Update annotation of the first selected
        self.model.set_notes(paths[0], self.annotation.toPlainText())

    def _commit_current_annotation(self):
        """Persist current annotation text for the currently displayed file, if any."""
        try:
            if not self.current_folder:
                return
            p = getattr(self, "_current_file", None)
            if p is None:
                return
            self.model.set_notes(p, self.annotation.toPlainText())
        except Exception:
            pass

    def _on_window_changed(self, _):
        # Re-plot with new binning if a file is selected
        paths = self._selected_paths()
        if paths:
            self._plot_file(paths[0])

    def _on_y_range_changed(self, *_):
        # Apply y-range to current plots whenever either spinbox changes
        y_min = float(self.y_min_spin.value()) if hasattr(self, "y_min_spin") else None
        y_max = float(self.y_max_spin.value()) if hasattr(self, "y_max_spin") else None
        print(f"_on_y_range_changed {y_min}, {y_max}")
        if y_min is None or y_max is None:
            return
        if y_min > y_max:
            y_min, y_max = y_max, y_min
        try:
            # Preferred path: delegate to IntensityPlotWidget if available
            if hasattr(self.plot, "set_y_range"):
                self.plot.set_y_range(y_min, y_max)
                return
        except Exception:
            pass
        # Fallback: directly adjust Y range on underlying trace plots
        try:
            plots = getattr(self.plot, "plots", []) or []
            for trace_plot, _ in list(plots):
                try:
                    trace_plot.setYRange(float(y_min), float(y_max), padding=0)
                except Exception:
                    pass
        except Exception:
            pass

    # --- Image detection helpers ---
    def _is_image_tttr(self, path: pathlib.Path) -> bool:
        return self.model.probe_image(path)

    # --- Caching helpers (the cache and trace-loading logic is in the model) ---
    def _trace_signature(self, file_path: pathlib.Path, window_ms: float) -> str:
        return self.model.trace_signature(file_path, window_ms)

    def _load_trace_cache(self, file_path: pathlib.Path, window_ms: float):
        return self.model.load_trace_cache(file_path, window_ms)

    def _compute_trace_cached(self, file_path: pathlib.Path, window_ms: float):
        return self.model.compute_trace_cached(file_path, window_ms)

    def _precompute_all_traces(self):
        if self.current_folder is None or tttrlib is None:
            return
        self._sync_model()
        state: dict = {"dlg": None, "tried": False}

        def progress(i: int, total: int, path) -> bool:
            # Show progress dialog only for files we are going to process
            if not state["tried"]:
                state["tried"] = True
                try:
                    dlg = ChiSurfProgress(self, "Precomputing traces...", total)
                    dlg.setWindowTitle("Precomputing traces")
                    dlg.setAutoClose(True)
                    dlg.setAutoReset(False)
                    dlg.setMinimumDuration(0)
                    state["dlg"] = dlg
                except Exception:
                    state["dlg"] = None
            dlg = state["dlg"]
            if path is None:
                if dlg is not None:
                    try:
                        dlg.setValue(total)
                        dlg.close()
                    except Exception:
                        pass
                return True
            if dlg is not None:
                try:
                    dlg.setValue(i)
                    dlg.setLabelText(f"Processing {path.name} ({i + 1}/{total})")
                except Exception:
                    pass
            QApplication.processEvents()
            return not (dlg is not None and dlg.wasCanceled())

        self.model.precompute_all_traces(progress)

    def _plot_file(self, path: pathlib.Path):
        if not tttrlib:
            logging.warning("TraceBrowser: tttrlib not available - cannot plot")
            self.folder_label.setText("tttrlib not available - cannot plot")
            return
        try:
            window_ms = self.window_ms_spin.value()
            self._sync_model()
            time_axis, padded, labels = self.model.load_trace(path, window_ms)
            self.plot.plot_trace_and_histogram(
                time_axis,
                padded,
                labels,
                bin_count=100,
                time_window_ms=window_ms,
                hist_min=None,
                hist_max=None,
                hmm_states=None,
            )
            # Apply y-range from spinboxes if available
            try:
                y_min = float(self.y_min_spin.value()) if hasattr(self, "y_min_spin") else None
                y_max = float(self.y_max_spin.value()) if hasattr(self, "y_max_spin") else None
                if y_min is not None and y_max is not None:
                    if y_min > y_max:
                        y_min, y_max = y_max, y_min
                    self.plot.set_y_range(y_min, y_max)
            except Exception:
                pass
            self._current_file = path
        except Exception as e:
            logging.exception(f"TraceBrowser: Failed to plot {path}: {e}")
            self.folder_label.setText(f"Failed to plot {path.name}: {e}")

    def _clear_plot_and_annotation(self):
        self.plot.plot_widget.clear()
        self.annotation.clear()
        self._current_file = None

    def _selected_paths(self) -> list[pathlib.Path]:
        sel = []
        for idx in self.table.selectionModel().selectedRows():
            item = self.table.item(idx.row(), 0)
            if item is not None:
                p = pathlib.Path(item.data(Qt.UserRole))
                sel.append(p)
        return sel

    def _build_channel_labels(self, chs: list[int]) -> list[str]:
        return self.model.build_channel_labels(chs)

    # Drag-and-drop support
    def eventFilter(self, obj, event):
        try:
            if obj is self.table and event is not None:
                et = event.type()
                if et in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):
                    # Forward to the widget handlers
                    if et == QEvent.DragEnter:
                        self.dragEnterEvent(event)
                        return True
                    elif et == QEvent.DragMove:
                        self.dragMoveEvent(event)
                        return True
                    elif et == QEvent.Drop:
                        self.dropEvent(event)
                        return True
                # Handle Delete key to move selected traces to .trash
                if et == QEvent.KeyPress:
                    try:
                        key = getattr(event, "key", None)
                        if key is not None and event.key() in (Qt.Key_Delete,):
                            self._on_delete_selected()
                            return True
                    except Exception:
                        pass
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _on_subfolders_toggled(self):
        try:
            if not self.current_folder:
                return
            # Re-scan and refill based on new recursion setting
            self._scan_and_fill()
        except Exception:
            pass

    def _first_dropped_directory(self, event) -> pathlib.Path | None:
        try:
            md = event.mimeData()
            if md and md.hasUrls():
                for url in md.urls():
                    local = url.toLocalFile()
                    if local:
                        p = pathlib.Path(local)
                        if p.exists() and p.is_dir():
                            return p
        except Exception:
            return None
        return None

    def dragEnterEvent(self, event):
        folder = self._first_dropped_directory(event)
        if folder is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        folder = self._first_dropped_directory(event)
        if folder is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        folder = self._first_dropped_directory(event)
        if folder is not None:
            event.acceptProposedAction()
            self._open_folder(folder)
        else:
            event.ignore()

    def _trash_dir(self) -> pathlib.Path | None:
        base = self.current_folder
        if base is None:
            return None
        trash = base / ".trash"
        try:
            trash.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return trash

    def _on_delete_selected(self):
        # Move selected files to .trash within current_folder, then refresh list (no prompts)
        # Capture current selection anchor (top-most selected row) to restore position after deletion
        try:
            sel_model = self.table.selectionModel()
            sel_rows = [s.row() for s in sel_model.selectedRows()] if sel_model else []
            sel_rows.sort()
            anchor_row = sel_rows[0] if sel_rows else None
        except Exception:
            anchor_row = None
        selected_paths = self._selected_paths()
        if not selected_paths:
            return
        # Build a de-duplicated set of files to move: selected files + any siblings with the same stem
        to_move_set = set()
        try:
            # Helper to add a path if it's a file and not already under .trash
            def _maybe_add(fp: pathlib.Path):
                try:
                    if not fp.exists() or not fp.is_file():
                        return
                    # Exclude files already inside any .trash subpath of current_folder
                    try:
                        relp = fp.relative_to(self.current_folder)
                        if any(part == ".trash" for part in relp.parts):
                            return
                    except Exception:
                        pass
                    to_move_set.add(fp)
                except Exception:
                    pass

            for p in selected_paths:
                _maybe_add(p)
                # Add all siblings with the same stem in the same directory
                try:
                    parent = p.parent
                    stem = p.stem
                    for sib in parent.glob(stem + ".*"):
                        _maybe_add(sib)
                except Exception:
                    pass
        except Exception:
            # Fallback: just move the selected paths
            to_move_set = set(selected_paths)
        if not to_move_set:
            return
        trash = self._trash_dir()
        if trash is None:
            return
        import time

        moved = 0
        total = len(to_move_set)
        for p in sorted(to_move_set):
            try:
                if not p.exists() or not p.is_file():
                    continue
                # Compute relative target inside .trash, preserving subfolders when possible
                try:
                    rel = p.relative_to(self.current_folder)
                except Exception:
                    rel = pathlib.Path(p.name)
                dest = trash / rel
                # Ensure parent exists
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                # Avoid overwrite: if exists, add timestamp suffix
                final_dest = dest
                if final_dest.exists():
                    ts = time.strftime("%Y%m%d-%H%M%S")
                    final_dest = final_dest.with_name(f"{final_dest.stem}__{ts}{final_dest.suffix}")
                shutil.move(str(p), str(final_dest))
                logging.info(f"TraceBrowser: moved to trash: '{p}' -> '{final_dest}'")
                moved += 1
                # Drop any meta entry for this file
                try:
                    key = self._rel_key(p)
                    if key in self.meta:
                        del self.meta[key]
                except Exception:
                    pass
            except Exception as e:
                logging.warning(f"TraceBrowser: Failed to move {p} to .trash: {e}")
        if moved:
            logging.info(f"TraceBrowser: moved {moved}/{total} file(s) to .trash at '{trash}'.")
        # Save meta after changes
        try:
            self._schedule_meta_save()
        except Exception:
            pass
        # Refresh list and clear plot if current file moved
        try:
            if self._current_file and not self._current_file.exists():
                self._clear_plot_and_annotation()
        except Exception:
            pass
        self._refresh_list()
        # Restore selection near the previous anchor and keep view position
        try:
            if anchor_row is not None and self.table.rowCount() > 0:
                target = min(max(anchor_row, 0), self.table.rowCount() - 1)
                row_to_select = None
                # Prefer next visible row at or after target
                for r in range(target, self.table.rowCount()):
                    if not self.table.isRowHidden(r):
                        row_to_select = r
                        break
                # Fallback: previous visible rows
                if row_to_select is None:
                    for r in range(min(target - 1, self.table.rowCount() - 1), -1, -1):
                        if not self.table.isRowHidden(r):
                            row_to_select = r
                            break
                # Final fallback: first visible row
                if row_to_select is None:
                    for r in range(self.table.rowCount()):
                        if not self.table.isRowHidden(r):
                            row_to_select = r
                            break
                if row_to_select is not None:
                    self.table.selectRow(row_to_select)
                    try:
                        item = self.table.item(row_to_select, 0)
                        if item is not None:
                            self.table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                    except Exception:
                        pass
                    try:
                        self.table.setFocus(Qt.OtherFocusReason)
                    except Exception:
                        pass
        except Exception:
            pass

    def _on_export(self):
        # Export all files currently listed (respecting active filter/sort)
        paths: list[pathlib.Path] = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is not None:
                p_str = item.data(Qt.UserRole)
                if p_str:
                    paths.append(pathlib.Path(p_str))
        if not paths:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Select destination folder")
        if not out_dir:
            return
        out = pathlib.Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        copied = 0
        for p in paths:
            try:
                shutil.copy2(str(p), str(out / p.name))
                copied += 1
            except Exception as e:
                logging.warning(f"TraceBrowser: Failed to copy {p} to {out}: {e}")
        logging.info(f"TraceBrowser: Exported {copied}/{len(paths)} files to {out}")

    def _on_export_csv(self):
        # Export computed intensity traces as CSV for all files currently listed (respecting filter/sort)
        # Collect all paths from the table
        paths: list[pathlib.Path] = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is not None:
                p_str = item.data(Qt.UserRole)
                if p_str:
                    paths.append(pathlib.Path(p_str))
        if not paths:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Select destination folder for CSV files")
        if not out_dir:
            return
        out = pathlib.Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        window_ms = float(self.window_ms_spin.value()) if hasattr(self, "window_ms_spin") else 10.0
        try:
            exported_paths = self._client.export_csv(
                [str(path) for path in paths],
                str(out),
                time_window_ms=window_ms,
                setup_settings=self.setup_settings,
                selected_channels=self.selected_channels,
            )
            if exported_paths:
                logging.info(
                    f"TraceBrowser: CSV exported through RPC for {len(exported_paths)}/{len(paths)} files to: {out}"
                )
                dialogs.information(
                    self,
                    "CSV Export",
                    f"Exported {len(exported_paths)}/{len(paths)} CSV files to: {out}",
                )
                return
        except Exception:
            logging.debug("TraceBrowser: RPC CSV export failed; falling back to local export")
        exported = 0
        skipped = 0
        for p in paths:
            try:
                # Skip image-like TTTR files
                if self._is_image_tttr(p):
                    skipped += 1
                    continue
                # Compute or load cached trace
                time_axis, padded, labels = self._compute_trace_cached(p, window_ms)
                # Expect padded shape (num_bins, num_series)
                if time_axis is None or padded is None or len(time_axis) == 0:
                    skipped += 1
                    continue
                # Ensure labels
                if not labels:
                    # Try to build from selected channels if available
                    try:
                        tt = tttrlib.TTTR(str(p)) if tttrlib is not None else None
                        if tt is not None:
                            chs = sorted(tt.get_used_routing_channels())
                            labels = [str(c) for c in chs]
                    except Exception:
                        labels = []
                # Sanitize labels to avoid commas/newlines in header
                safe_labels = [
                    str(l).replace("\n", " ").replace("\r", " ").replace(",", ";") for l in labels
                ]
                header = ["time_s"] + safe_labels
                # Prepare rows
                bin_tag = (f"{window_ms:g}").replace(".", "p")
                csv_path = out / f"{p.stem}_bin{bin_tag}ms.csv"
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(header)
                    nb = int(padded.shape[0])
                    # Ensure 2D behavior
                    if len(padded.shape) == 1:
                        for i in range(nb):
                            writer.writerow([float(time_axis[i]), float(padded[i])])
                    else:
                        nc = int(padded.shape[1])
                        for i in range(nb):
                            row = [float(time_axis[i])] + [float(padded[i, j]) for j in range(nc)]
                            writer.writerow(row)
                exported += 1
            except Exception as e:
                logging.warning(f"TraceBrowser: Failed to export CSV for {p}: {e}")
        logging.info(
            f"TraceBrowser: CSV exported for {exported}/{len(paths)} files to {out}; skipped {skipped}"
        )
        try:
            dialogs.information(
                self, "CSV Export", f"Exported {exported}/{len(paths)} CSV files to: {out}"
            )
        except Exception:
            pass

    def _on_export_docx(self):
        # Collect all paths that are currently displayed in the table (respecting filter/sort)
        paths: list[pathlib.Path] = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is not None:
                p_str = item.data(Qt.UserRole)
                if p_str:
                    paths.append(pathlib.Path(p_str))
        if not paths:
            return
        # Check for python-docx availability
        if Document is None:
            try:
                dialogs.warning(
                    self,
                    "DOCX Export",
                    "python-docx is not installed. Please install 'python-docx' to enable DOCX export.",
                )
            except Exception:
                pass
            return
        # Determine output path automatically: save as '<foldername>.docx' in the parent of that folder
        folder = self.current_folder
        if folder is None and paths:
            folder = paths[0].parent
        if folder is None:
            try:
                dialogs.error(
                    self,
                    "DOCX Export",
                    "No folder context available to determine DOCX save location.",
                )
            except Exception:
                pass
            return
        docx_name = (folder.name or "traces") + ".docx"
        save_path = folder / docx_name
        try:
            import tempfile

            tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="trace_export_"))
        except Exception:
            tmpdir = self.current_folder or pathlib.Path(".")
        doc = Document()
        # Add a title
        try:
            doc.add_heading("Trace Browser Export", level=1)
        except Exception:
            pass
        # Remember current selection to restore later
        current_selected = self._selected_paths()
        # Iterate displayed traces
        for p in paths:
            # Plot the file in the existing widget to reuse rendering
            try:
                self._plot_file(p)
                QApplication.processEvents()
            except Exception:
                pass
            # Save snapshot of the plot area
            img_path = tmpdir / f"{p.stem}.png"
            try:
                pix = self.plot.plot_widget.grab()
                pix.save(str(img_path), "PNG")
            except Exception:
                img_path = None
            # Read metadata
            rec = self._meta_get(p)
            rating = int(rec.get("rating", 0))
            annotation = rec.get("annotation", "")
            folder_text = str(p.parent)
            # Write docx content
            try:
                doc.add_heading(p.name, level=2)
            except Exception:
                pass
            try:
                doc.add_paragraph(f"Folder: {folder_text}")
                doc.add_paragraph(f"Rating: {rating}")
                if annotation:
                    doc.add_paragraph(f"Annotation: {annotation}")
            except Exception:
                pass
            # Insert image if available
            if img_path and img_path.exists():
                try:
                    if Inches is not None:
                        doc.add_picture(str(img_path), width=Inches(6))
                    else:
                        doc.add_picture(str(img_path))
                except Exception:
                    pass
            try:
                doc.add_paragraph("")  # spacing
            except Exception:
                pass
        # Save the document
        try:
            doc.save(str(save_path))
            logging.info(f"TraceBrowser: DOCX exported to {save_path}")
            try:
                dialogs.information(self, "DOCX Export", f"Saved: {save_path}")
            except Exception:
                pass
        except Exception as e:
            logging.exception(f"TraceBrowser: Failed to save DOCX {save_path}: {e}")
            try:
                dialogs.error(self, "DOCX Export", f"Failed to save DOCX: {e}")
            except Exception:
                pass
        # Cleanup temp images
        try:
            if tmpdir and tmpdir.exists() and tmpdir.name.startswith("trace_export_"):
                import shutil as _sh

                _sh.rmtree(str(tmpdir), ignore_errors=True)
        except Exception:
            pass
        # Restore the first selected plot if any, otherwise the first row
        try:
            if current_selected:
                self._plot_file(current_selected[0])
            elif paths:
                self._plot_file(paths[0])
        except Exception:
            pass

    def _on_transfer_to_analysis(self):
        """Transfer the currently selected trace to the Single-Molecule Intensity Trace plugin."""
        selected_paths = self._selected_paths()
        if not selected_paths:
            try:
                dialogs.information(
                    self, "Transfer to Analysis", "Please select a trace file first."
                )
            except Exception:
                pass
            return

        # Use the first selected file
        selected_file = selected_paths[0]

        try:
            logging.info(
                f"TraceBrowser: Starting transfer of {selected_file.name} to Intensity Trace Analysis"
            )

            # Create a new IntensityTrace window and store reference to prevent garbage collection
            intensity_trace_window = IntensityTrace()

            # Store reference to keep window alive
            self.intensity_trace_windows.append(intensity_trace_window)

            # Set window title to make it clear this is from trace browser
            intensity_trace_window.setWindowTitle(
                f"Intensity Trace Analysis - {selected_file.name}"
            )

            # Set up the file path
            intensity_trace_window.file_label.setText(f"Selected file: {selected_file}")

            # Get current settings from trace browser
            time_window_ms = float(self.window_ms_spin.value())
            time_window_ms / 1000.0

            logging.info(f"TraceBrowser: Using time window {time_window_ms} ms")

            # Determine channels to use
            selected_channels = self.selected_channels
            if selected_channels is None:
                try:
                    tttr_obj = tttrlib.TTTR(str(selected_file))
                    selected_channels = sorted(tttr_obj.get_used_routing_channels())
                    logging.info(f"TraceBrowser: Auto-detected channels: {selected_channels}")
                except Exception as e:
                    selected_channels = [0, 2]  # Default channels
                    logging.warning(
                        f"TraceBrowser: Failed to detect channels, using default {selected_channels}: {e}"
                    )
            else:
                logging.info(f"TraceBrowser: Using configured channels: {selected_channels}")

            # Set the parameters in the intensity trace window
            intensity_trace_window.window_spin.setValue(time_window_ms)

            # Pass detector setup
            if self.setup_settings:
                intensity_trace_window._detector_settings = self.setup_settings
                intensity_trace_window._refresh_detector_checkboxes()

            # Load the file, which will also trigger processing
            intensity_trace_window.load_file(file_path=str(selected_file))

            # Update the plot
            logging.info("TraceBrowser: Updating plot...")
            intensity_trace_window.update_plot()

            # Show the window and bring it to front
            intensity_trace_window.show()
            intensity_trace_window.raise_()
            intensity_trace_window.activateWindow()

            # Connect window close event to remove from our list
            def on_window_closed():
                try:
                    if intensity_trace_window in self.intensity_trace_windows:
                        self.intensity_trace_windows.remove(intensity_trace_window)
                    logging.info(
                        f"TraceBrowser: Intensity trace window for {selected_file.name} closed"
                    )
                except Exception:
                    pass

            # Connect the close event (this is a bit tricky with Qt, so we'll use a simple approach)
            original_close_event = intensity_trace_window.closeEvent

            def close_event_wrapper(event):
                on_window_closed()
                if original_close_event:
                    original_close_event(event)
                else:
                    event.accept()

            intensity_trace_window.closeEvent = close_event_wrapper

            logging.info(
                f"TraceBrowser: Successfully transferred {selected_file.name} to Intensity Trace Analysis"
            )

        except Exception as e:
            logging.exception(f"TraceBrowser: Failed to transfer {selected_file} to analysis: {e}")
            try:
                dialogs.error(
                    self,
                    "Transfer Failed",
                    f"Failed to transfer trace to analysis:\n\n{str(e)}\n\nCheck the log for more details.",
                )
            except Exception:
                pass

    def _on_transfer_to_tw(self):
        """Transfer the currently selected trace to the TTTR Time Window plugin for BID generation."""
        paths = self._selected_paths()
        if not paths:
            dialogs.warning(self, "No Selection", "Please select a trace file to transfer.")
            return

        path = paths[0]
        time_window_ms = self.window_ms_spin.value()

        logging.info(f"TraceBrowser: Starting transfer of {path.name} to TTTR Time Window plugin")
        logging.info(f"TraceBrowser: Using time window {time_window_ms} ms")

        try:
            # Ensure the plugin is available
            if TTTRTimeWindowWizard is None:
                raise ImportError("TTTRTimeWindowWizard plugin not available.")

            time_window_wizard = TTTRTimeWindowWizard()

            # Pre-configure the wizard with current settings
            time_window_wizard.tws_spin.setValue(time_window_ms)

            # Pre-populate the files page with the selected file
            time_window_wizard.file_list.addItem(str(path))

            # Set a descriptive window title
            time_window_wizard.setWindowTitle(f"Time Window BID Generation: {path.name}")
            time_window_wizard.show()

            # Store a reference to prevent garbage collection
            self.time_window_wizards.append(time_window_wizard)

            # Cleanup on close
            def on_wizard_closed():
                try:
                    if time_window_wizard in self.time_window_wizards:
                        self.time_window_wizards.remove(time_window_wizard)
                except ValueError:
                    pass

            original_close_event = time_window_wizard.closeEvent

            def close_event_wrapper(event):
                on_wizard_closed()
                original_close_event(event)

            time_window_wizard.closeEvent = close_event_wrapper

            # Also connect to the finished signal if available
            try:
                time_window_wizard.finished.connect(on_wizard_closed)
            except Exception:
                pass

            logging.info(
                f"TraceBrowser: Successfully transferred {path.name} to TTTR Time Window plugin"
            )

        except Exception as e:
            logging.error(f"TraceBrowser: Failed to transfer {path} to time window plugin: {e}")
            dialogs.error(
                self,
                "Transfer Failed",
                f"Could not open trace in time window plugin.\n\nError: {e}",
            )

    def _on_open_in_ndxplorer(self):
        """One-click pipeline: Use current TW → compute BIDs → write burst analysis → open NDXplorer.
        - Uses current time-window from Trace Browser.
        - BIDs are saved to a temporary folder (.bst) for debugging, but main output is a burst analysis folder
          next to the data (bi4_bur/*.bur with Info/*.mti), following existing naming conventions.
        """
        # Validate selection
        selected_paths = self._selected_paths()
        if not selected_paths:
            try:
                dialogs.information(self, "ndX", "Please select a trace file first.")
            except Exception:
                pass
            return
        if tttrlib is None:
            try:
                dialogs.error(self, "ndX", "tttrlib is not available.")
            except Exception:
                pass
            return
        if importlib.util.find_spec("ndxplorer") is None:
            try:
                dialogs.error(self, "ndX", "ndX components are not available.")
            except Exception:
                pass
            return

        src = selected_paths[0]
        try:
            tw_ms = float(self.window_ms_spin.value())
        except Exception:
            tw_ms = 10.0
        tw_s = tw_ms / 1000.0

        logging.info(f"TraceBrowser: NDX one-click for {src.name} with TW={tw_ms} ms")

        try:
            # Load TTTR
            tttr = tttrlib.TTTR(str(src))

            # Compute BIDs using helper if available, else fallback
            if compute_bids_from_tttr is not None:
                bids = compute_bids_from_tttr(tttr, tw_s)
            else:
                # Minimal fallback: bin macro times into fixed windows
                mt = tttr.macro_times
                res = float(getattr(tttr.header, "macro_time_resolution", 0.0)) or float(
                    getattr(tttr, "macro_time_resolution", 0.0)
                )
                if res <= 0:
                    raise RuntimeError("Macro time resolution unavailable from TTTR header")
                clocks_per_bin = max(1, int(np.floor(tw_s / res)))
                max_clock = int(mt.max()) if len(mt) else 0
                edges = np.arange(0, max_clock + 1, clocks_per_bin, dtype=np.int64)
                starts = np.searchsorted(mt, edges, side="left")
                stops = np.searchsorted(mt, edges + clocks_per_bin, side="left")
                bids = np.stack([starts, stops], axis=1)

            if bids is None or getattr(bids, "size", 0) == 0:
                try:
                    dialogs.warning(self, "ndX", "No data to compute burst IDs.")
                except Exception:
                    pass
                return

            # Optionally save BIDs to a temp .bst file for inspection
            try:
                import tempfile

                tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="chisurf_bst_"))
                bst_file = tmpdir / f"{src.stem}.bst"
                np.savetxt(str(bst_file), bids.astype(np.int64), fmt="%d\t%d")
                logging.info(f"TraceBrowser: Saved temporary BIDs: {bst_file}")
            except Exception as _e:
                logging.debug(f"TraceBrowser: Could not save temporary BIDs: {_e}")

            # Build analysis directory next to data; keep naming consistent with TW tool
            analysis_dir = src.parent / f"{src.stem}_TW_{tw_ms:.0f}ms"
            bi4_bur_dir = analysis_dir / "bi4_bur"
            info_dir = analysis_dir / "Info"
            try:
                bi4_bur_dir.mkdir(parents=True, exist_ok=True)
                info_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logging.exception(f"TraceBrowser: Could not create analysis directories: {e}")
                try:
                    dialogs.error(self, "ndX", f"Failed to create analysis folder:\n{e}")
                except Exception:
                    pass
                return

            # Derive detectors and windows from setup if present; else auto-detect a single 'all' detector/window
            detectors = None
            windows = None
            try:
                if (
                    isinstance(self.setup_settings, dict)
                    and "detectors" in self.setup_settings
                    and self.setup_settings["detectors"]
                ):
                    detectors = self.setup_settings["detectors"]
                    # Build windows as union of all micro_time_ranges if not explicitly given
                    # Here, keep a single window spanning full micro-time if necessary
                else:
                    # Auto-detector: use all routing channels
                    try:
                        chs = sorted(tttr.get_used_routing_channels())
                    except Exception:
                        chs = []
                    mt_max = int(np.max(tttr.micro_times)) + 1 if len(tttr) > 0 else 0
                    detectors = {
                        "all": {
                            "chs": chs,
                            "micro_time_ranges": [(0, mt_max if mt_max > 0 else 4096)],
                        }
                    }
                # Windows: single full micro-time window by default
                if windows is None:
                    mt_max = int(np.max(tttr.micro_times)) + 1 if len(tttr) > 0 else 0
                    windows = {"all": (0, mt_max if mt_max > 0 else 4096)}
            except Exception as e:
                logging.debug(f"TraceBrowser: Falling back to default detectors/windows: {e}")
                mt_max = int(np.max(tttr.micro_times)) + 1 if len(tttr) > 0 else 0
                detectors = {
                    "all": {"chs": [], "micro_time_ranges": [(0, mt_max if mt_max > 0 else 4096)]}
                }
                windows = {"all": (0, mt_max if mt_max > 0 else 4096)}

            # Convert BIDs to start/stop tuples
            try:
                start_stop = [(int(s), int(e)) for s, e in np.asarray(bids).tolist()]
            except Exception:
                start_stop = [(int(s), int(e)) for s, e in bids]

            # Write BUR file (via DataFrame pipeline) following existing conventions
            bur_path = bi4_bur_dir / f"{src.stem}.bur"
            try:
                if burstio is None:
                    raise ImportError("burst utilities unavailable")
                df = burstio.generate_burst_dataframe(
                    start_stop, str(src.name), tttr, windows, detectors
                )
                burstio.write_dataframe_to_bur(df, str(bur_path))
                logging.info(f"TraceBrowser: Wrote BUR: {bur_path}")
            except Exception as e:
                logging.exception(f"TraceBrowser: Failed to write BUR: {e}")
                try:
                    dialogs.error(self, "ndX", f"Failed to write .bur file:\n{e}")
                except Exception:
                    pass
                return

            # Write MTI summary for completeness
            try:
                if burstio is not None:
                    max_macro_time = 0.0
                    try:
                        res = float(getattr(tttr.header, "macro_time_resolution", 0.0)) or float(
                            getattr(tttr, "macro_time_resolution", 0.0)
                        )
                        if len(tttr) > 0 and res > 0:
                            max_macro_time = float(tttr.macro_times.max()) * res
                    except Exception:
                        max_macro_time = 0.0
                    burstio.write_mti_summary(
                        src, analysis_dir, max_macro_time=max_macro_time, append=True
                    )
            except Exception as _e:
                logging.debug(f"TraceBrowser: MTI write skipped: {_e}")

            # Open in ndX: ChiSurf's one ndX window, reading the folder itself
            # (so it knows where the table came from: title, working path,
            # the calibration and session stored beside it).
            try:
                from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

                ndx = build_ndxplorer_window(analysis_dir)
                ndx.show()
                ndx.raise_()
                ndx.activateWindow()

                self.ndxplorer_windows.append(ndx)

                # Hook close to drop reference
                original_close_event = getattr(ndx, "closeEvent", None)

                def _close_wrapper(event):
                    try:
                        if ndx in self.ndxplorer_windows:
                            self.ndxplorer_windows.remove(ndx)
                    except Exception:
                        pass
                    if original_close_event:
                        original_close_event(event)
                    else:
                        event.accept()

                ndx.closeEvent = _close_wrapper

                logging.info("TraceBrowser: ndX opened successfully")
            except Exception as e:
                logging.exception(f"TraceBrowser: Failed to open ndX: {e}")
                try:
                    dialogs.error(self, "ndX", f"Failed to open ndX:\n{e}")
                except Exception:
                    pass

        except Exception as e:
            logging.exception(f"TraceBrowser: One-click NDX workflow failed: {e}")
            try:
                dialogs.error(self, "ndX", f"One-click workflow failed:\n{e}")
            except Exception:
                pass


if __name__ == "__main__":
    # Basic manual run to show the widget standalone
    import sys

    app = QApplication(sys.argv)
    w = TraceBrowser()
    w.show()
    app.exec()

# When the plugin is loaded as a module with __name__ == "plugin",
# this code will be executed by the Plugin Manager
if __name__ == "plugin":
    from chisurf.plugins.tttr.trace_browser.gui.tool import TraceBrowserTool

    window = TraceBrowserTool()
    window.show()
    window.raise_()
    window.activateWindow()
