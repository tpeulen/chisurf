from __future__ import annotations

import pathlib
from typing import Dict, List

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.glyphs import Glyphs

# Removed reference to .models since it doesn't exist in gui_parts
HAS_DETECTOR_WIZARD = True
try:
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizardPage  # noqa: F401
except ImportError:
    HAS_DETECTOR_WIZARD = False


def irf_width_skew_ns(vector, bin_width_ns: float) -> tuple[float, float]:
    """Estimate a measured IRF's width (FWHM, ns) and skew from its shape.

    FWHM is the full width at half maximum in bins × ``bin_width_ns``; skew is the
    intensity-weighted skewness of the bin positions (dimensionless). Both are
    display/starting estimates, not a fit.
    """
    y = np.asarray(vector, dtype=float).ravel()
    if y.size == 0 or not np.any(y > 0):
        return 0.2, 0.0
    y = np.clip(y, 0.0, None)
    peak = int(np.argmax(y))
    half = y[peak] / 2.0
    # left/right half-max crossings around the peak
    left = peak
    while left > 0 and y[left] > half:
        left -= 1
    right = peak
    while right < y.size - 1 and y[right] > half:
        right += 1
    fwhm_bins = max(1.0, float(right - left))
    x = np.arange(y.size, dtype=float)
    w = y / y.sum()
    mean = float((w * x).sum())
    var = float((w * (x - mean) ** 2).sum())
    std = var ** 0.5
    skew = float((w * (x - mean) ** 3).sum() / std**3) if std > 0 else 0.0
    return round(fwhm_bins * float(bin_width_ns or 0.05), 4), round(skew, 3)


class DetectorIrfTableWidget(QtWidgets.QGroupBox):
    """Unified detector selection + per-detector IRF editor.

    One table row per detector (per parallel/perpendicular channel when polarized):
    a selection checkbox, the detector name, editable synthetic-IRF Width (FWHM ns)
    and Skew, and an IRF column whose ``…`` button loads a measured IRF file (then
    becomes ``✕`` to unload). While a measured IRF is loaded, Width/Skew are
    disabled and show the values estimated from that IRF.

    Keeps the old ``DetectorSelectionWidget`` surface (``selectionChanged``,
    ``checkboxes``, ``refresh``, ``get_selected``) so the host widget is unchanged
    where it only needs selection.
    """

    selectionChanged = QtCore.Signal()

    _ROLES = ("parallel", "perpendicular")
    _SUFFIX = {"": "", "parallel": "  ∥", "perpendicular": "  ⊥"}

    def __init__(self, parent=None):
        super().__init__("Detectors", parent)
        self.setToolTip(
            "Select detectors and set each one's scatter/IRF. Load a measured IRF "
            f"with … (then {Glyphs.CLOSE} to unload); otherwise a synthetic IRF is fitted from "
            "the Width/Skew starting values."
        )
        self._polarized = False
        self._detectors: List[str] = []
        self._bin_width_ns = 0.05
        # per (detector, role) state; role is "" unless polarized
        self._irf: Dict[tuple, str] = {}
        self._width: Dict[tuple, float] = {}
        self._skew: Dict[tuple, float] = {}
        self._shift: Dict[tuple, float] = {}
        self._width_spins: Dict[tuple, QtWidgets.QDoubleSpinBox] = {}
        self._skew_spins: Dict[tuple, QtWidgets.QDoubleSpinBox] = {}
        self._shift_spins: Dict[tuple, QtWidgets.QDoubleSpinBox] = {}
        self.checkboxes: Dict[str, QtWidgets.QCheckBox] = {}

        # Coalesce rapid Width/Skew edits into a single recompute.
        self._recompute_timer = QtCore.QTimer(self)
        self._recompute_timer.setSingleShot(True)
        self._recompute_timer.setInterval(250)
        self._recompute_timer.timeout.connect(self.selectionChanged.emit)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)
        self.table = QtWidgets.QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(
            ["", "Detector", "Width", "Skew", "Shift", "IRF"]
        )
        self.table.horizontalHeaderItem(2).setToolTip("Synthetic-IRF start FWHM (ns)")
        self.table.horizontalHeaderItem(3).setToolTip("Synthetic-IRF generalized-Gaussian skew")
        self.table.horizontalHeaderItem(4).setToolTip(
            "IRF time shift (ns) — applied to the measured or synthetic IRF"
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        header.resizeSection(2, 66)
        header.resizeSection(3, 60)
        header.resizeSection(4, 60)
        layout.addWidget(self.table)

    # ── configuration ────────────────────────────────────────────────
    def set_bin_width_ns(self, bin_width_ns: float) -> None:
        self._bin_width_ns = float(bin_width_ns or 0.05)

    def set_polarized(self, polarized: bool) -> None:
        if bool(polarized) != self._polarized:
            self._polarized = bool(polarized)
            self._rebuild()

    def refresh(self, detector_names: List[str], tttr_data=None) -> None:
        names = [str(n) for n in (detector_names or [])]
        if not names and tttr_data is not None:
            try:
                names = [f"routing_{ch}" for ch in sorted(set(tttr_data.routing_channels))[:8]]
            except Exception:
                names = []
        self._detectors = names
        self._rebuild()

    # ── row model ────────────────────────────────────────────────────
    def _roles(self) -> tuple:
        return self._ROLES if self._polarized else ("",)

    def _key(self, detector: str, role: str = "") -> tuple:
        return (detector, role if self._polarized else "")

    def _rebuild(self) -> None:
        prev_checked = {n: cb.isChecked() for n, cb in self.checkboxes.items()}
        self.table.setRowCount(0)
        self.checkboxes.clear()
        self._width_spins.clear()
        self._skew_spins.clear()
        self._shift_spins.clear()
        for detector in self._detectors:
            first_row = self.table.rowCount()
            for role in self._roles():
                self._add_row(detector, role, prev_checked.get(detector, True))
            if self._polarized:
                # one selection checkbox per detector, spanning its two rows
                self.table.setSpan(first_row, 0, len(self._ROLES), 1)
        self._fit_height()
        self.selectionChanged.emit()

    def _fit_height(self) -> None:
        """Size the table to show up to 8 rows without a vertical scrollbar."""
        rows = self.table.rowCount()
        if rows == 0:
            self.table.setMaximumHeight(16777215)
            return
        row_h = max(self.table.rowHeight(0), 28)
        header_h = self.table.horizontalHeader().height() or 24
        shown = min(rows, 8)
        height = header_h + row_h * shown + 6
        self.table.setMinimumHeight(height if rows <= 3 else 0)
        self.table.setMaximumHeight(height if rows <= 8 else 16777215)

    def _add_row(self, detector: str, role: str, checked: bool) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        key = self._key(detector, role)

        # col 0 — selection checkbox (only on the group's first row when polarized)
        if not self._polarized or role == self._ROLES[0]:
            cb = QtWidgets.QCheckBox()
            cb.setChecked(bool(checked))
            cb.stateChanged.connect(self.selectionChanged.emit)
            self.checkboxes[detector] = cb
            self.table.setCellWidget(row, 0, self._centered(cb))

        # col 1 — name
        name_item = QtWidgets.QTableWidgetItem(f"{detector}{self._SUFFIX.get(role, '')}")
        name_item.setFlags(QtCore.Qt.ItemIsEnabled)
        self.table.setItem(row, 1, name_item)

        # col 2/3 — width / skew spin boxes
        wsb = QtWidgets.QDoubleSpinBox()
        wsb.setRange(0.0001, 100.0)
        wsb.setDecimals(3)
        wsb.setValue(float(self._width.get(key, 0.2)))
        wsb.setMaximumWidth(64)
        wsb.setKeyboardTracking(False)
        wsb.setToolTip("Synthetic-IRF start FWHM (ns)")
        wsb.valueChanged.connect(lambda v, k=key: self._edit_value(self._width, k, v))
        self._width_spins[key] = wsb
        self.table.setCellWidget(row, 2, wsb)
        ssb = QtWidgets.QDoubleSpinBox()
        ssb.setRange(-10.0, 10.0)
        ssb.setDecimals(2)
        ssb.setValue(float(self._skew.get(key, 0.0)))
        ssb.setMaximumWidth(58)
        ssb.setKeyboardTracking(False)
        ssb.setToolTip("Synthetic-IRF generalized-Gaussian skew")
        ssb.valueChanged.connect(lambda v, k=key: self._edit_value(self._skew, k, v))
        self._skew_spins[key] = ssb
        self.table.setCellWidget(row, 3, ssb)

        # col 4 — IRF time shift (ns); applies to measured *and* synthetic IRF
        shsb = QtWidgets.QDoubleSpinBox()
        shsb.setRange(-100.0, 100.0)
        shsb.setDecimals(3)
        shsb.setSingleStep(0.01)
        shsb.setValue(float(self._shift.get(key, 0.0)))
        shsb.setMaximumWidth(60)
        shsb.setKeyboardTracking(False)
        shsb.setToolTip("IRF time shift (ns) — applied to the measured or synthetic IRF")
        shsb.valueChanged.connect(lambda v, k=key: self._edit_value(self._shift, k, v))
        self._shift_spins[key] = shsb
        self.table.setCellWidget(row, 4, shsb)

        # col 5 — IRF load / unload
        btn = QtWidgets.QToolButton()
        btn.clicked.connect(lambda _=False, k=key: self._on_irf_button(k))
        self.table.setCellWidget(row, 5, btn)

        self._sync_row(row, key)

    def _edit_value(self, store: Dict[tuple, float], key: tuple, value) -> None:
        """Store an edited Width/Skew value and schedule a (debounced) recompute."""
        store[key] = float(value)
        self._recompute_timer.start()

    @staticmethod
    def _centered(widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        holder = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch(1)
        lay.addWidget(widget)
        lay.addStretch(1)
        return holder

    def _sync_row(self, row: int, key: tuple) -> None:
        """Reflect the loaded/unloaded IRF state in a row's widgets."""
        has_irf = bool(self._irf.get(key))
        wsb = self.table.cellWidget(row, 2)
        ssb = self.table.cellWidget(row, 3)
        if wsb is not None:
            wsb.blockSignals(True)
            wsb.setValue(float(self._width.get(key, 0.2)))
            wsb.setEnabled(not has_irf)
            wsb.blockSignals(False)
        if ssb is not None:
            ssb.blockSignals(True)
            ssb.setValue(float(self._skew.get(key, 0.0)))
            ssb.setEnabled(not has_irf)
            ssb.blockSignals(False)
        shsb = self.table.cellWidget(row, 4)
        if shsb is not None:
            # Shift applies to both measured and synthetic IRFs → always enabled.
            shsb.blockSignals(True)
            shsb.setValue(float(self._shift.get(key, 0.0)))
            shsb.blockSignals(False)
        btn = self.table.cellWidget(row, 5)
        if btn is not None:
            btn.setText(Glyphs.CLOSE if has_irf else "…")
            btn.setToolTip(
                f"Unload measured IRF\n{self._irf.get(key, '')}" if has_irf
                else "Load a measured IRF file for this detector"
            )

    def _row_of(self, key: tuple) -> int:
        want = f"{key[0]}{self._SUFFIX.get(key[1], '')}"
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item is not None and item.text() == want:
                return row
        return -1

    def _on_irf_button(self, key: tuple) -> None:
        if self._irf.get(key):
            self._irf.pop(key, None)  # unload
        else:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Load measured IRF", "", "IRF (*.txt *.dat *.csv *.npy);;All files (*)"
            )
            if not path:
                return
            self._irf[key] = path
            try:
                from .data_loading import load_vector

                w, s = irf_width_skew_ns(load_vector(pathlib.Path(path)), self._bin_width_ns)
                self._width[key] = w
                self._skew[key] = s
            except Exception:
                pass
        row = self._row_of(key)
        if row >= 0:
            self._sync_row(row, key)
        self.selectionChanged.emit()

    # ── accessors for the compute path ───────────────────────────────
    def get_selected(self) -> List[str]:
        return [name for name, cb in self.checkboxes.items() if cb.isChecked()]

    def irf_path(self, detector: str, role: str = "") -> str:
        return self._irf.get(self._key(detector, role), "")

    def width(self, detector: str, role: str = "") -> float:
        return float(self._width.get(self._key(detector, role), 0.2))

    def set_width(self, detector: str, value: float, role: str = "") -> None:
        """Set a detector's synthetic-IRF FWHM and update its spinbox display."""
        key = self._key(detector, role)
        self._width[key] = float(value)
        spin = self._width_spins.get(key)
        if spin is not None:
            spin.blockSignals(True)
            spin.setValue(float(value))
            spin.blockSignals(False)

    def skew(self, detector: str, role: str = "") -> float:
        return float(self._skew.get(self._key(detector, role), 0.0))

    def set_skew(self, detector: str, value: float, role: str = "") -> None:
        """Set a detector's synthetic-IRF skew and update its spinbox display."""
        key = self._key(detector, role)
        self._skew[key] = float(value)
        spin = self._skew_spins.get(key)
        if spin is not None:
            spin.blockSignals(True)
            spin.setValue(float(value))
            spin.blockSignals(False)

    def shift(self, detector: str, role: str = "") -> float:
        """Return a detector's IRF time shift (ns); applies to measured & synthetic."""
        return float(self._shift.get(self._key(detector, role), 0.0))

    def set_shift(self, detector: str, value: float, role: str = "") -> None:
        """Set a detector's IRF time shift (ns) and update its spinbox display."""
        key = self._key(detector, role)
        self._shift[key] = float(value)
        spin = self._shift_spins.get(key)
        if spin is not None:
            spin.blockSignals(True)
            spin.setValue(float(value))
            spin.blockSignals(False)

    # ── persistence ──────────────────────────────────────────────────
    def export_state(self) -> dict:
        def enc(d):
            return {f"{k[0]}|{k[1]}": v for k, v in d.items()}

        return {"irf": enc(self._irf), "width": enc(self._width),
                "skew": enc(self._skew), "shift": enc(self._shift)}

    def import_state(self, state: dict) -> None:
        def dec(d):
            out = {}
            for k, v in (d or {}).items():
                det, _, role = str(k).partition("|")
                out[(det, role)] = v
            return out

        if not isinstance(state, dict):
            return
        self._irf = {k: str(v) for k, v in dec(state.get("irf")).items()}
        self._width = {k: float(v) for k, v in dec(state.get("width")).items()}
        self._skew = {k: float(v) for k, v in dec(state.get("skew")).items()}
        self._shift = {k: float(v) for k, v in dec(state.get("shift")).items()}
        self._rebuild()

class DetectorSelectionWidget(QtWidgets.QGroupBox):
    """Widget for selecting detectors/channels."""
    selectionChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__("Detectors", parent)
        self.setToolTip("Select the detector definitions used to compute decay patterns and filters.")
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(1, 1, 1, 1)
        self.layout.setSpacing(1)
        self.checkboxes: Dict[str, QtWidgets.QCheckBox] = {}

    def refresh(self, detector_names: List[str], tttr_data=None):
        """Refresh checkboxes based on detector names or TTTR data."""
        # Clear existing
        for cb in self.checkboxes.values():
            cb.setParent(None)
            cb.deleteLater()
        self.checkboxes.clear()

        # Add new
        for name in detector_names:
            cb = QtWidgets.QCheckBox(str(name))
            cb.setChecked(True)
            cb.stateChanged.connect(self.selectionChanged.emit)
            self.layout.addWidget(cb)
            self.checkboxes[str(name)] = cb

        if not detector_names and tttr_data:
            try:
                # Use micro_times to check if data exists, but routing is what we want
                routing_channels = sorted(set(tttr_data.routing_channels))
                for ch in routing_channels[:8]:
                    name = f"routing_{ch}"
                    cb = QtWidgets.QCheckBox(f"Routing {ch}")
                    cb.setChecked(True)
                    cb.stateChanged.connect(self.selectionChanged.emit)
                    self.layout.addWidget(cb)
                    self.checkboxes[name] = cb
            except Exception:
                pass

    def get_selected(self) -> List[str]:
        return [name for name, cb in self.checkboxes.items() if cb.isChecked()]

class SpeciesListWidget(QtWidgets.QListWidget):
    """List widget for species decays with custom behavior."""
    filesChanged = QtCore.Signal()  # Emitted when files are added/removed (invalidate cache)
    checkStateChanged = QtCore.Signal()  # Emitted when checkboxes toggle (keep cache)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.itemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, item: QtWidgets.QListWidgetItem) -> None:
        # Checkbox state changed - don't invalidate cache
        self.checkStateChanged.emit()

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        if event.mimeData().hasUrls():
            paths = [pathlib.Path(url.toLocalFile()) for url in event.mimeData().urls()]
            self.add_pattern(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
            self.filesChanged.emit()

    def add_pattern(self, paths: List[pathlib.Path]) -> None:
        """Add a new decay pattern from a set of files."""
        if not paths:
            return
            
        valid_paths = [p for p in paths if p.is_file()]
        if not valid_paths:
            return

        # Create a single entry representing this pattern (one or more files)
        name = valid_paths[0].name
        if len(valid_paths) > 1:
            name += f" (+{len(valid_paths)-1} files)"
            
        item = QtWidgets.QListWidgetItem(name)
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
        item.setCheckState(QtCore.Qt.Checked)
        tooltip = "\n".join([str(p.absolute()) for p in valid_paths])
        item.setToolTip(tooltip)
        # Store the list of paths in the UserRole
        item.setData(QtCore.Qt.UserRole, valid_paths)
        self.addItem(item)
        self.filesChanged.emit()

    def add_synthetic(
        self,
        name: str,
        lifetime: float,
        bin_width: float,
        start_bin: int = 0,
        irf_path: pathlib.Path | None = None,
    ) -> None:
        """Add a generated single-exponential species pattern."""
        source = {
            "type": "synthetic",
            "model": "lifetime",
            "name": str(name),
            "lifetime": float(lifetime),
            "bin_width": float(bin_width),
            "start_bin": int(start_bin),
            "irf_path": str(irf_path.absolute()) if irf_path else None,
        }
        self.add_synthetic_source(source)

    @staticmethod
    def _synthetic_summary(source: dict) -> str:
        """One-line summary describing a synthetic component."""
        model = str(source.get("model", "lifetime"))
        if model == "fret_species":
            state = {"d_only": "donor-only", "da": "FRET pair", "a_only": "acceptor-only"}.get(
                str(source.get("state", "da")), str(source.get("state", "da")))
            if source.get("fret_mode") == "distance":
                fret = f"R={float(source.get('distance', 0)):g}Å"
            else:
                fret = f"E={float(source.get('transfer_efficiency', 0)):g}"
            return f"{state}, {fret}"
        if model == "lifetime":
            summary = f"τ={float(source['lifetime']):g} ns"
        elif model == "lifetime_spectrum":
            summary = f"{len(source.get('lifetimes', []))} lifetime terms"
        elif model == "gaussian_lifetime":
            summary = (
                f"τ={float(source['mean_lifetime']):g}±"
                f"{float(source['sigma_lifetime']):g} ns"
            )
        elif model == "gaussian_distance":
            summary = (
                f"R={float(source['mean_distance']):g}±"
                f"{float(source['sigma_distance']):g} Å"
            )
        else:
            summary = model.replace("_", " ")
        if source.get("patterns_by_detector"):
            summary += ", fit model" if source.get("source_fit") else ", detector IRF"
        if source.get("shot_noise"):
            summary += f", Poisson {int(source.get('photon_count', 0)):,} photons"
        return summary

    def _apply_synthetic_source(self, item: QtWidgets.QListWidgetItem, source: dict) -> None:
        """Populate ``item``'s label, tooltip and data from a synthetic source."""
        name = str(source.get("name", "component"))
        summary = self._synthetic_summary(source)
        item.setText(f"{name}  [synthetic, {summary}]")
        tooltip = f"Synthetic component: {summary}"
        if source.get("source_fit"):
            tooltip += f"\nSource fit: {source['source_fit']}"
        if source.get("irf_path"):
            tooltip += f"\nIRF: {source['irf_path']}"
        item.setToolTip(tooltip)
        item.setData(QtCore.Qt.UserRole, source)

    def add_synthetic_source(self, source: dict) -> None:
        """Add any serializable synthetic component definition."""
        source = dict(source)
        source.setdefault("type", "synthetic")
        item = QtWidgets.QListWidgetItem()
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
        item.setCheckState(QtCore.Qt.Checked)
        self._apply_synthetic_source(item, source)
        self.addItem(item)
        self.filesChanged.emit()

    def replace_synthetic_source(self, item: QtWidgets.QListWidgetItem, source: dict) -> None:
        """Replace an existing component in place (edit), preserving its check state."""
        source = dict(source)
        source.setdefault("type", "synthetic")
        self._apply_synthetic_source(item, source)
        self.filesChanged.emit()
