"""Custom AutoForm sections for the Burst Browser.

Four bespoke widgets, registered under string keys referenced by
``burst_browser.view.json``: the source/open bar (``browser_source``), the
detector/column + gating controls (``browser_controls``), the burst table
(``browser_table``) and the per-column histogram (``browser_histogram``). Each
observes the Qt-free :class:`~..view_model.BurstBrowserViewModel` and reacts to
its ``data`` / ``gating`` / ``selection`` events — no AutoForm rebuild needed.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from qtpy import QtCore, QtWidgets

from chisurf.gui import chiplot as cp
from chisurf.gui.autoform.sections.registry import register_section
from chisurf.gui.widgets.collapsible_box import CollapsibleBox
from chisurf.gui.widgets.tool_buttons import action_button

logger = logging.getLogger(__name__)


class _BurstTableModel(QtCore.QAbstractTableModel):
    """Qt table model over a DataFrame with a gating row-mask."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._rows: np.ndarray | None = None

    def set_dataframe(self, df):
        self.beginResetModel()
        self._df = df
        self._rows = np.arange(len(df), dtype=int) if df is not None else None
        self.endResetModel()

    def set_mask(self, mask):
        if self._df is None:
            return
        mask = np.asarray(mask, dtype=bool)
        if mask.shape[0] != len(self._df):
            return
        self.beginResetModel()
        self._rows = np.where(mask)[0]
        self.endResetModel()

    def base_row(self, view_row: int):
        if self._rows is None:
            return view_row
        try:
            return int(self._rows[view_row])
        except Exception:
            return None

    def rowCount(self, parent=QtCore.QModelIndex()):  # noqa: N802
        if parent.isValid() or self._df is None or self._rows is None:
            return 0
        return int(self._rows.size)

    def columnCount(self, parent=QtCore.QModelIndex()):  # noqa: N802
        if parent.isValid() or self._df is None:
            return 0
        return int(self._df.shape[1])

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if (not index.isValid() or self._df is None or self._rows is None
                or role not in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole)):
            return None
        try:
            value = self._df.iat[int(self._rows[index.row()]), index.column()]
        except Exception:
            return None
        return f"{value:.4g}" if isinstance(value, float) else str(value)

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):  # noqa: N802
        if role != QtCore.Qt.DisplayRole or self._df is None:
            return None
        if orientation == QtCore.Qt.Horizontal:
            try:
                return str(self._df.columns[section])
            except Exception:
                return None
        return str(section + 1)


# ── source / open bar ────────────────────────────────────────────────────────
@register_section("browser_source")
def browser_source(model, target=None, **options):
    """Open-folder action + the current path label."""
    return _SourceSection(model)


class _SourceSection(QtWidgets.QWidget):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        btn = action_button("folder", tooltip="Open a folder of .bur files")
        btn.clicked.connect(self._open)
        self._path = QtWidgets.QLabel(model.path_text)
        self._path.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        lay.addWidget(btn)
        lay.addWidget(self._path, 1)
        model.add_observer(self._on_event)

    def _open(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select folder with .bur files")
        if d:
            self._model.load_folder(Path(d))

    def _on_event(self, _event):
        self._path.setText(self._model.path_text)


# ── detector / column + gating controls ──────────────────────────────────────
@register_section("browser_controls")
def browser_controls(model, target=None, **options):
    """Detector + histogram-column combos and the E/S/size gating box."""
    return _ControlsSection(model)


class _ControlsSection(QtWidgets.QWidget):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        self._syncing = False
        form = QtWidgets.QVBoxLayout(self)
        form.setContentsMargins(2, 2, 2, 2)

        top = QtWidgets.QFormLayout()
        self.detector_combo = QtWidgets.QComboBox()
        self.column_combo = QtWidgets.QComboBox()
        top.addRow("Detector", self.detector_combo)
        top.addRow("Histogram column", self.column_combo)
        form.addLayout(top)

        box = CollapsibleBox("Gating", expanded=True)
        grid_w = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(grid_w)
        grid.setContentsMargins(2, 2, 2, 2)

        def _f():
            s = QtWidgets.QDoubleSpinBox()
            s.setRange(0.0, 1.0)
            s.setSingleStep(0.01)
            s.setDecimals(3)
            return s

        def _i():
            s = QtWidgets.QSpinBox()
            s.setRange(0, 10_000_000)
            return s

        self.e_min, self.e_max = _f(), _f()
        self.s_min, self.s_max = _f(), _f()
        self.size_min, self.size_max = _i(), _i()
        for row, (lbl_a, a, lbl_b, b) in enumerate((
            ("E min", self.e_min, "E max", self.e_max),
            ("S min", self.s_min, "S max", self.s_max),
            ("Size min", self.size_min, "Size max", self.size_max),
        )):
            grid.addWidget(QtWidgets.QLabel(lbl_a), row, 0)
            grid.addWidget(a, row, 1)
            grid.addWidget(QtWidgets.QLabel(lbl_b), row, 2)
            grid.addWidget(b, row, 3)
        box.add_widget(grid_w)
        form.addWidget(box)

        self.use_selection = QtWidgets.QCheckBox("Histogram uses table selection")
        form.addWidget(self.use_selection)
        form.addStretch(1)

        # Wiring.
        self.detector_combo.currentIndexChanged.connect(self._on_detector)
        self.column_combo.currentIndexChanged.connect(self._on_column)
        for w in (self.e_min, self.e_max, self.s_min, self.s_max,
                  self.size_min, self.size_max):
            w.valueChanged.connect(self._on_gate)
        self.use_selection.toggled.connect(self._on_toggle)

        model.add_observer(self._on_event)
        self._sync_from_model(full=True)

    # -- model → widgets ------------------------------------------------------
    def _on_event(self, event):
        if event in ("data",):
            self._sync_from_model(full=True)

    def _sync_from_model(self, full: bool) -> None:
        m = self._model
        self._syncing = True
        try:
            if full:
                self.detector_combo.clear()
                for opt in m.detector_options():
                    self.detector_combo.addItem(opt, opt)
                self._reload_columns()
                # Seed gating ranges/values from the data.
                self._seed_range(self.e_min, self.e_max, m.e_min, m.e_max, m.have_E)
                self._seed_range(self.s_min, self.s_max, m.s_min, m.s_max, m.have_S)
                self._seed_int(self.size_min, self.size_max, m.size_min, m.size_max,
                               m._col_size is not None)
                self.use_selection.setChecked(bool(m.use_selection))
        finally:
            self._syncing = False

    def _reload_columns(self) -> None:
        self.column_combo.blockSignals(True)
        self.column_combo.clear()
        for opt in self._model.hist_column_options():
            self.column_combo.addItem(opt, opt)
        self.column_combo.blockSignals(False)
        if self.column_combo.count():
            self.column_combo.setCurrentIndex(0)
            self._model.hist_column = self.column_combo.currentData()

    @staticmethod
    def _seed_range(w_min, w_max, lo, hi, enabled):
        for w in (w_min, w_max):
            w.blockSignals(True)
        w_min.setValue(float(lo))
        w_max.setValue(float(hi))
        for w in (w_min, w_max):
            w.blockSignals(False)
            w.setEnabled(bool(enabled))

    @staticmethod
    def _seed_int(w_min, w_max, lo, hi, enabled):
        for w in (w_min, w_max):
            w.blockSignals(True)
        w_min.setValue(int(lo))
        w_max.setValue(int(hi))
        for w in (w_min, w_max):
            w.blockSignals(False)
            w.setEnabled(bool(enabled))

    # -- widgets → model ------------------------------------------------------
    def _on_detector(self, _idx):
        if self._syncing:
            return
        self._model.on_detector_changed(self.detector_combo.currentData() or "All")
        self._reload_columns()  # detector-scoped columns changed

    def _on_column(self, _idx):
        if self._syncing:
            return
        self._model.hist_column = self.column_combo.currentData() or ""
        self._model.refresh()

    def _on_gate(self, _v):
        if self._syncing:
            return
        m = self._model
        m.e_min, m.e_max = self.e_min.value(), self.e_max.value()
        m.s_min, m.s_max = self.s_min.value(), self.s_max.value()
        m.size_min, m.size_max = self.size_min.value(), self.size_max.value()
        m.refresh()

    def _on_toggle(self, checked):
        if self._syncing:
            return
        self._model.use_selection = bool(checked)
        self._model.refresh()


# ── table ─────────────────────────────────────────────────────────────────────
@register_section("browser_table")
def browser_table(model, target=None, **options):
    """Return the per-burst table (gated rows) with a live 'N / total' status line."""
    return _TableSection(model)


class _TableSection(QtWidgets.QWidget):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._tmodel = _BurstTableModel(self)
        self.view = QtWidgets.QTableView()
        self.view.setModel(self._tmodel)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.view.setSortingEnabled(True)
        sm = self.view.selectionModel()
        if sm is not None:
            sm.selectionChanged.connect(self._on_sel)
        lay.addWidget(self.view, 1)
        self._status = QtWidgets.QLabel(model.status_text())
        self._status.setStyleSheet("color: #888; padding: 0 4px;")
        lay.addWidget(self._status)
        model.add_observer(self._on_event)
        self._refresh(load=True)

    def _on_event(self, event):
        self._refresh(load=(event == "data"))

    def _refresh(self, load: bool) -> None:
        if load:
            self._tmodel.set_dataframe(self._model.dataframe)
        if self._model.mask is not None:
            self._tmodel.set_mask(self._model.mask)
        self._status.setText(self._model.status_text())

    def _on_sel(self, _sel, _desel):
        sm = self.view.selectionModel()
        rows = []
        if sm is not None:
            for idx in sm.selectedRows():
                br = self._tmodel.base_row(int(idx.row()))
                if br is not None:
                    rows.append(br)
        self._model.selected_indices = rows
        if self._model.use_selection:
            self._model.notify("selection")


# ── histogram ─────────────────────────────────────────────────────────────────
@register_section("browser_histogram")
def browser_histogram(model, target=None, **options):
    """Return a bar histogram of the selected per-burst column."""
    return _HistogramSection(model)


class _HistogramSection(QtWidgets.QWidget):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.plot = cp.Plot()
        self.plot.set_labels(left="Counts")
        lay.addWidget(self.plot)
        model.add_observer(self._on_event)
        self._redraw()

    def _on_event(self, _event):
        self._redraw()

    def _redraw(self):
        self.plot.clear()
        h = self._model.histogram()
        if not h:
            return
        self.plot.bars(h["centers"], h["counts"], width=h["width"], brush="b", pen="k")
        self.plot.set_labels(bottom=h["label"])
