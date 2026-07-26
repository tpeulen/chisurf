"""Reusable AutoForm section: an editable N×N transition-rate matrix.

A transition-rate matrix appears in several ChiSurf domains — species
interconversion in the photon simulator, kinetic state models, exchange in
lifetime-FCS, etc. This section renders one editable grid so those all share a
single control instead of hand-built tables.

Declare it in a view spec as a custom section::

    {"type": "custom", "key": "rate_matrix", "target": "k_ex",
     "options": {"size_attr": "n_states", "labels_attr": "state_names",
                 "minimum": 0.0, "decimals": 4, "diagonal": false, "unit": "1/ms"}}

- ``target`` — model attribute holding the flat row-major ``N*N`` rates
  (``rate[i*N + j]`` is the i→j rate). Read on build/refresh, written on edit.
- ``size_attr`` — model attribute (or zero-arg method) giving N; the grid
  resizes to it on ``refresh`` (so it can track e.g. the species count).
- ``labels_attr`` — optional per-state row/column labels; defaults to ``1..N``.
- ``minimum`` / ``maximum`` / ``decimals`` — what a cell can show. The grid is a
  *view*: a stored rate outside that range is displayed clamped and in red, and
  is left untouched in the model until that cell is actually edited. Building or
  refreshing the grid never writes a value back.
- ``diagonal`` — when false (default) the i→i cells are fixed at 0 and disabled.
- ``popup`` — when true the grid lives behind a button instead of sitting in the
  panel. An N×N grid costs N rows of vertical space whether or not anyone is
  editing it, which is the wrong trade when the scheme is a secondary control
  (two of them, as in the acquisition simulator, push everything else off the
  screen). The button carries a live summary — size and how many transitions are
  non-zero — so the panel still says what the scheme is without being opened.
  The same grid is used either way; only where it is parented differs.
"""

from __future__ import annotations

import logging
from typing import Any

from qtpy import QtCore, QtWidgets

from .registry import register_section

logger = logging.getLogger(__name__)


def _resolve(model: Any, name: str, default=None):
    if not name or not hasattr(model, name):
        return default
    value = getattr(model, name)
    return value() if callable(value) else value


@register_section("rate_matrix")
class RateMatrixWidget(QtWidgets.QWidget):
    """Editable N×N rate matrix bound to a flat row-major model list."""

    AUTOFORM_REFRESH = True
    is_form_field = False

    def __init__(self, model, target: str = "", **options):
        super().__init__()
        self._model = model
        self._attr = target or options.get("attr", "")
        self._size_attr = options.get("size_attr", "")
        self._labels_attr = options.get("labels_attr", "")
        self._min = float(options.get("minimum", 0.0))
        self._max = float(options.get("maximum", 1_000_000.0))
        self._decimals = int(options.get("decimals", 4))
        self._diagonal = bool(options.get("diagonal", False))
        self._unit = str(options.get("unit", ""))
        self._title = str(options.get("title", ""))
        self._popup = bool(options.get("popup", False))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        self.table = QtWidgets.QTableWidget(0, 0)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        self.button = None
        self._dialog = None
        if self._popup:
            # One button standing in for N rows of grid. It is a real summary,
            # not just a label: a collapsed control that says nothing about its
            # contents makes the panel lie about the model's state.
            self.button = QtWidgets.QToolButton()
            self.button.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
            self.button.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                      QtWidgets.QSizePolicy.Fixed)
            self.button.clicked.connect(self._open)
            layout.addWidget(self.button)
        else:
            layout.addWidget(self._header())
            layout.addWidget(self.table)
        # Do not let the grid stretch to fill the panel — keep it tight.
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self._spins: dict[tuple[int, int], QtWidgets.QDoubleSpinBox] = {}
        # Per cell: (value read from the model, value the spin box can show).
        # The two differ whenever the model holds a rate outside the configured
        # range or finer than ``decimals`` -- see :meth:`_load`.
        self._loaded: dict[tuple[int, int], tuple[float, float]] = {}
        self._build()

    def _header(self) -> QtWidgets.QLabel:
        """Return the caption naming the matrix and its rate direction."""
        bits = []
        if self._title:
            bits.append(f"<b>{self._title}</b>")
        bits.append(f"i → j rate ({self._unit})" if self._unit else "i → j rate")
        label = QtWidgets.QLabel("  ·  ".join(bits))
        label.setStyleSheet("color: palette(mid);")
        return label

    # -- popup ---------------------------------------------------------
    def _open(self) -> None:
        """Show the grid in its own window, building it on first use."""
        if self._dialog is None:
            self._dialog = QtWidgets.QDialog(self)
            self._dialog.setWindowTitle(self._title or "Transition rates")
            inner = QtWidgets.QVBoxLayout(self._dialog)
            inner.addWidget(self._header())
            inner.addWidget(self.table)
            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
            buttons.rejected.connect(self._dialog.hide)
            inner.addWidget(buttons)
        # Deliberately modeless: edits apply live, so the user can watch what a
        # rate does to the model while changing it -- and a modal dialog on an
        # offscreen run has nobody to close it.
        self._dialog.show()
        self._dialog.raise_()

    def _update_button(self) -> None:
        """Put the scheme's size and how much of it is set on the button."""
        if self.button is None:
            return
        n = self.table.rowCount()
        active = sum(
            1 for (i, j), spin in self._spins.items()
            if i != j and abs(spin.value()) > 0.0
        )
        name = self._title or "Transition rates"
        unit = f" {self._unit}" if self._unit else ""
        self.button.setText(f"\u2197 {name}  ({n}\u00d7{n}, {active} set)")
        self.button.setToolTip(
            f"{name}: {n} states, {active} of {max(n * (n - 1), 0)} transitions "
            f"non-zero{unit}. Click to edit the i \u2192 j rate matrix."
        )

    # -- data helpers --------------------------------------------------
    def _size(self) -> int:
        n = _resolve(self._model, self._size_attr, None)
        try:
            return max(1, int(n))
        except (TypeError, ValueError):
            # Fall back to the stored matrix length (√len).
            flat = self._flat()
            return max(1, int(round(len(flat) ** 0.5)) if flat else 1)

    def _flat(self) -> list[float]:
        value = getattr(self._model, self._attr, None) if self._attr else None
        if value is None:
            return []
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            return []

    def _labels(self, n: int) -> list[str]:
        labels = _resolve(self._model, self._labels_attr, None)
        if isinstance(labels, (list, tuple)) and len(labels) >= n:
            return [str(labels[i]) for i in range(n)]
        return [str(i + 1) for i in range(n)]

    def _load(self, i: int, j: int, spin: QtWidgets.QDoubleSpinBox, raw: float) -> None:
        """Show one model value in its cell and remember what was read.

        A ``QDoubleSpinBox`` silently clamps to its range and rounds to its
        ``decimals``, so a rate the grid cannot represent would come back
        changed on the next write-back. Both numbers are kept: the value the
        model holds and the value the box ends up showing. A cell that still
        shows the latter has not been edited, so :meth:`_cell_value` writes the
        former back untouched instead of the display.
        """
        spin.blockSignals(True)
        spin.setValue(raw)
        spin.blockSignals(False)
        shown = float(spin.value())
        self._loaded[(i, j)] = (float(raw), shown)
        # Rounding to ``decimals`` is what a grid is for and is handled silently
        # by keeping the value that was read. Clamping is not: the number on
        # screen is then a different rate, so say so in the log, the tooltip and
        # in colour.
        clamped = not self._min <= raw <= self._max
        spin.setStyleSheet("color: #c62828;" if clamped else "")
        if clamped:
            logger.warning(
                "rate_matrix: %s[%d, %d] = %g is outside the range this grid "
                "shows (%g..%g); it is displayed as %g and kept unchanged in "
                "the model until the cell is edited.",
                self._attr or "rates", i, j, raw, self._min, self._max, shown,
            )
            spin.setToolTip(
                f"Stored value {raw:g} is outside the range this grid shows "
                f"({self._min:g} … {self._max:g}), so it is shown as {shown:g}. "
                f"Editing this cell replaces it with the shown value."
            )

    def _cell_value(self, i: int, j: int, spin: QtWidgets.QDoubleSpinBox) -> float:
        """Return the value to store for one cell: the edit, or what was read."""
        loaded = self._loaded.get((i, j))
        if loaded is not None and float(spin.value()) == loaded[1]:
            return loaded[0]
        return float(spin.value())

    def _write_back(self, n: int) -> None:
        flat = [0.0] * (n * n)
        for (i, j), spin in self._spins.items():
            if i < n and j < n:
                flat[i * n + j] = self._cell_value(i, j, spin)
        if self._attr:
            setattr(self._model, self._attr, flat)
        self._update_button()

    # -- build / refresh ----------------------------------------------
    def _build(self) -> None:
        n = self._size()
        flat = self._flat()
        labels = self._labels(n)
        self.table.blockSignals(True)
        self.table.clear()
        self._spins.clear()
        self._loaded.clear()
        self.table.setRowCount(n)
        self.table.setColumnCount(n)
        self.table.setHorizontalHeaderLabels(labels)
        self.table.setVerticalHeaderLabels(labels)
        # Size a cell to the widest value it can hold rather than to a fixed
        # number of pixels: a rate of 1e5 with three decimals does not fit in the
        # same box as 0.5, and a silently clipped number in an editable grid is
        # worse than a wide column.
        widest = f"{max(abs(self._min), abs(self._max)):.{self._decimals}f}"
        cell_width = QtWidgets.QApplication.fontMetrics().horizontalAdvance(
            widest + "0"
        ) + 34          # spin buttons + frame
        for i in range(n):
            for j in range(n):
                spin = QtWidgets.QDoubleSpinBox()
                spin.setRange(self._min, self._max)
                spin.setDecimals(self._decimals)
                spin.setKeyboardTracking(False)
                spin.setMinimumWidth(min(cell_width, 160))
                idx = i * n + j
                raw = flat[idx] if idx < len(flat) else 0.0
                if i == j and not self._diagonal:
                    self._load(i, j, spin, 0.0)
                    spin.setEnabled(False)
                    spin.setToolTip("Self-transition (i→i) is fixed at 0.")
                else:
                    spin.setToolTip(f"Rate from state {labels[i]} to state {labels[j]}"
                                    + (f" ({self._unit})" if self._unit else ""))
                    self._load(i, j, spin, raw)
                    spin.valueChanged.connect(lambda _v, ni=n: self._write_back(ni))
                self._spins[(i, j)] = spin
                self.table.setCellWidget(i, j, spin)
        self.table.resizeColumnsToContents()
        row_h = 32
        header_h = 26
        self.table.setFixedHeight(header_h + row_h * n + 4)
        self.table.blockSignals(False)
        # Building the grid is not an edit: opening a panel must leave the model
        # exactly as it was found. The one case that does need a write is a
        # genuine resize, where the stored matrix no longer holds N*N entries
        # and nothing else reshapes it.
        if len(flat) != n * n:
            self._write_back(n)
        self._update_button()

    def refresh(self) -> None:
        """Re-read the model, rebuilding only if the state count changed."""
        # Rebuild when the state count changed (tracks size_attr, e.g. n_species).
        if self.table.rowCount() != self._size():
            self._build()
        else:
            flat = self._flat()
            n = self.table.rowCount()
            for (i, j), spin in self._spins.items():
                idx = i * n + j
                raw = flat[idx] if idx < len(flat) else 0.0
                if i == j and not self._diagonal:
                    raw = 0.0
                self._load(i, j, spin, raw)
            self._update_button()
