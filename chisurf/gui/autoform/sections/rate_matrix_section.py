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
- ``diagonal`` — when false (default) the i→i cells are fixed at 0 and disabled.
"""

from __future__ import annotations

from typing import Any

from qtpy import QtCore, QtWidgets

from .registry import register_section


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

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        header_bits = []
        if self._title:
            header_bits.append(f"<b>{self._title}</b>")
        header_bits.append(f"i → j rate ({self._unit})" if self._unit else "i → j rate")
        hint = QtWidgets.QLabel("  ·  ".join(header_bits))
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)
        self.table = QtWidgets.QTableWidget(0, 0)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        layout.addWidget(self.table)
        # Do not let the grid stretch to fill the panel — keep it tight.
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self._spins: dict[tuple[int, int], QtWidgets.QDoubleSpinBox] = {}
        self._build()

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

    def _write_back(self, n: int) -> None:
        flat = [0.0] * (n * n)
        for (i, j), spin in self._spins.items():
            if i < n and j < n:
                flat[i * n + j] = float(spin.value())
        if self._attr:
            setattr(self._model, self._attr, flat)

    # -- build / refresh ----------------------------------------------
    def _build(self) -> None:
        n = self._size()
        flat = self._flat()
        labels = self._labels(n)
        self.table.blockSignals(True)
        self.table.clear()
        self._spins.clear()
        self.table.setRowCount(n)
        self.table.setColumnCount(n)
        self.table.setHorizontalHeaderLabels(labels)
        self.table.setVerticalHeaderLabels(labels)
        for i in range(n):
            for j in range(n):
                spin = QtWidgets.QDoubleSpinBox()
                spin.setRange(self._min, self._max)
                spin.setDecimals(self._decimals)
                spin.setKeyboardTracking(False)
                spin.setMaximumWidth(78)
                idx = i * n + j
                spin.setValue(flat[idx] if idx < len(flat) else 0.0)
                if i == j and not self._diagonal:
                    spin.setValue(0.0)
                    spin.setEnabled(False)
                    spin.setToolTip("Self-transition (i→i) is fixed at 0.")
                else:
                    spin.setToolTip(f"Rate from state {labels[i]} to state {labels[j]}"
                                    + (f" ({self._unit})" if self._unit else ""))
                    spin.valueChanged.connect(lambda _v, ni=n: self._write_back(ni))
                self._spins[(i, j)] = spin
                self.table.setCellWidget(i, j, spin)
        self.table.resizeColumnsToContents()
        row_h = 32
        header_h = 26
        self.table.setFixedHeight(header_h + row_h * n + 4)
        self.table.blockSignals(False)
        self._write_back(n)

    def refresh(self) -> None:
        # Rebuild when the state count changed (tracks size_attr, e.g. n_species).
        if self.table.rowCount() != self._size():
            self._build()
        else:
            flat = self._flat()
            for (i, j), spin in self._spins.items():
                idx = i * self.table.rowCount() + j
                spin.blockSignals(True)
                spin.setValue(flat[idx] if idx < len(flat) else 0.0)
                spin.blockSignals(False)
