"""Reusable AutoForm section: one row per state, one column per property.

The rectangular sibling of the ``rate_matrix`` section. That one edits how states
*interconvert* (an N×N matrix); this one edits what each state *is* — molecules,
diffusion coefficient, per-channel brightness, an efficiency, a weight. Both grow
and shrink with the same kind of count attribute, so a simulator or a model that
gains a species gets consistent behaviour from both without writing a table.

There is already a table for rows of
:class:`~chisurf.core.fitting.parameter.FittingParameter`
(``parameter_group_table`` and ``dynamic_group``). This section is for the other
case: **plain numeric attributes** — Python lists on a view-model, which is what
simulator settings and plugin configs hold. Hand-rolling that is how the
acquisition simulator ended up with a bespoke 90-line species table.

Declare it in a view spec as a custom section::

    {"type": "custom", "key": "state_table",
     "options": {"size_attr": "n_species",
                 "columns": [{"attr": "species_M", "label": "M", "default": 50.0},
                             {"attr": "species_D", "label": "D", "default": 3.0}]}}

- ``size_attr`` — model attribute (or zero-arg method) giving the row count; the
  table resizes to it on ``refresh``.
- ``columns`` — static column specs, or ``columns_source`` naming a model method
  that returns them, for a table whose columns depend on the model's own state
  (which detection channels are enabled, say).
- ``row_labels_attr`` — optional row labels; defaults to ``1..N``.
- ``trailing_rows_source`` — a model method returning rows appended below the
  states, whose cells address **scalar** attributes rather than per-state ones.
  A background row belongs there: it is not a state, but it is edited in the
  same grid because it is read in the same column.

Column spec
-----------
A column with ``action`` instead of ``attr`` is a **button per row**, calling
``model.<action>(row)``. That is how a state gets a sub-editor — a decay
spectrum, a spectrum file, anything too big for a cell — without a separate
"which state am I editing" selector beside the table: the row *is* the
selector, and there is no second place for the two to disagree about which
state is current.

``attr`` is the model attribute holding the values, and the cell for row *r* is
``getattr(model, attr)[r * stride + slot]`` — ``stride``/``slot`` default to
``1``/``0``, which is the plain one-value-per-state case. A strided store (six
brightness slots per species, of which two are shown per colour) is addressed by
setting them. ``default`` is what the list is grown with when the state count
rises; the widget never lets a list be shorter than the table.
"""

from __future__ import annotations

from typing import Any

from qtpy import QtCore, QtWidgets

from .registry import register_section


def _resolve(model: Any, name: str, default=None):
    """Return ``model.name``, calling it when it is a method."""
    if not name or not hasattr(model, name):
        return default
    value = getattr(model, name)
    return value() if callable(value) else value


@register_section("state_table")
class StateTableWidget(QtWidgets.QWidget):
    """Editable rows-are-states table bound to plain numeric model lists."""

    AUTOFORM_REFRESH = True
    is_form_field = False

    def __init__(self, model, target: str = "", **options):
        """Build the table for *model* from the section options."""
        super().__init__()
        self._model = model
        self._size_attr = options.get("size_attr", "")
        self._columns_source = options.get("columns_source", "")
        self._static_columns = list(options.get("columns", []) or [])
        self._row_labels_attr = options.get("row_labels_attr", "")
        self._trailing_source = options.get("trailing_rows_source", "")
        self._title = str(options.get("title", ""))
        self._decimals = int(options.get("decimals", 4))
        self._maximum = float(options.get("maximum", 1e12))
        self._minimum = float(options.get("minimum", 0.0))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        if self._title:
            caption = QtWidgets.QLabel(f"<b>{self._title}</b>")
            caption.setStyleSheet("color: palette(mid);")
            layout.addWidget(caption)
        self.table = QtWidgets.QTableWidget(0, 0)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.table)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self._cells: dict[tuple[int, int], QtWidgets.QDoubleSpinBox] = {}
        self._build()

    # -- shape ---------------------------------------------------------

    def _rows(self) -> int:
        """Return the number of state rows."""
        try:
            return max(1, int(_resolve(self._model, self._size_attr, 1)))
        except (TypeError, ValueError):
            return 1

    def _columns(self) -> list:
        """Return the column specs, from the model when it supplies them."""
        if self._columns_source:
            dynamic = _resolve(self._model, self._columns_source, None)
            if isinstance(dynamic, (list, tuple)):
                return [dict(c) for c in dynamic]
        return [dict(c) for c in self._static_columns]

    def _trailing(self) -> list:
        """Return the extra rows appended below the states."""
        if not self._trailing_source:
            return []
        rows = _resolve(self._model, self._trailing_source, None)
        return [dict(r) for r in rows] if isinstance(rows, (list, tuple)) else []

    def _labels(self, n: int) -> list:
        """Return the row labels for the ``n`` states."""
        labels = _resolve(self._model, self._row_labels_attr, None)
        if isinstance(labels, (list, tuple)) and len(labels) >= n:
            return [str(labels[i]) for i in range(n)]
        return [str(i + 1) for i in range(n)]

    # -- data ----------------------------------------------------------

    def _store(self, column: dict) -> list | None:
        """Return the model list a column is bound to, or ``None``."""
        store = getattr(self._model, column.get("attr", ""), None)
        return store if isinstance(store, list) else None

    def _index(self, column: dict, row: int) -> int:
        """Return the index in the backing list for ``row`` of ``column``."""
        return row * int(column.get("stride", 1)) + int(column.get("slot", 0))

    def _grow(self, rows: int) -> None:
        """Extend every backing list so the table can address every cell.

        A list shorter than the table is not an error to report but a state the
        user has not filled in yet — the count is theirs to set, and the values
        follow.
        """
        for column in self._columns():
            if column.get("action"):
                continue
            store = self._store(column)
            if store is None:
                continue
            needed = max(self._index(column, r) for r in range(rows)) + 1
            default = float(column.get("default", 0.0))
            while len(store) < needed:
                store.append(default)

    def _write(self, column: dict, row: int, value: float) -> None:
        """Write one cell back into its backing list."""
        store = self._store(column)
        if store is None:
            return
        index = self._index(column, row)
        while len(store) <= index:
            store.append(float(column.get("default", 0.0)))
        store[index] = float(value)

    # -- build / refresh -----------------------------------------------

    def _spin(self, column: dict, value: float) -> QtWidgets.QDoubleSpinBox:
        """Return a spin box configured for one column."""
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(float(column.get("minimum", self._minimum)),
                      float(column.get("maximum", self._maximum)))
        spin.setDecimals(int(column.get("decimals", self._decimals)))
        spin.setKeyboardTracking(False)
        spin.setMaximumWidth(96)
        spin.setValue(float(value))
        return spin

    def _button(self, column: dict, row: int) -> QtWidgets.QToolButton:
        """Return the per-row button of an action column."""
        button = QtWidgets.QToolButton()
        button.setText(str(column.get("text", column.get("label", "\u2026"))))
        if column.get("description"):
            button.setToolTip(str(column["description"]))
        button.clicked.connect(lambda _=False, r=row, a=column["action"]: self._invoke(a, r))
        return button

    def _invoke(self, action: str, row: int) -> None:
        """Call the model's action for one row, then re-read the table.

        The action may change what the row holds -- that is usually the point --
        so the values are re-read afterwards rather than left showing what they
        were before the editor opened.
        """
        method = getattr(self._model, action, None)
        if callable(method):
            method(row)
            self.refresh()

    def _build(self) -> None:
        """Rebuild the whole grid from the model."""
        rows, columns = self._rows(), self._columns()
        trailing = self._trailing()
        self._grow(rows)
        self.table.blockSignals(True)
        self.table.clear()
        self._cells.clear()
        self.table.setColumnCount(len(columns))
        self.table.setRowCount(rows + len(trailing))
        self.table.setHorizontalHeaderLabels([str(c.get("label", "")) for c in columns])
        for index, column in enumerate(columns):
            header = self.table.horizontalHeaderItem(index)
            if header is not None and column.get("description"):
                header.setToolTip(str(column["description"]))
        self.table.setVerticalHeaderLabels(
            self._labels(rows) + [str(r.get("label", "")) for r in trailing]
        )

        for row in range(rows):
            for index, column in enumerate(columns):
                action = column.get("action", "")
                if action:
                    self.table.setCellWidget(row, index, self._button(column, row))
                    continue
                store = self._store(column)
                position = self._index(column, row)
                value = store[position] if store is not None and position < len(store) else 0.0
                spin = self._spin(column, value)
                spin.valueChanged.connect(
                    lambda v, c=column, r=row: self._write(c, r, v)
                )
                self._cells[(row, index)] = spin
                self.table.setCellWidget(row, index, spin)

        # Trailing rows address scalar attributes, so they are bound directly
        # rather than through a column's backing list.
        for offset, extra in enumerate(trailing):
            row = rows + offset
            cells = list(extra.get("cells", []))
            for index, column in enumerate(columns):
                cell = cells[index] if index < len(cells) else None
                if not isinstance(cell, dict) or not cell.get("attr"):
                    item = QtWidgets.QTableWidgetItem("—")
                    item.setFlags(QtCore.Qt.ItemIsEnabled)
                    self.table.setItem(row, index, item)
                    continue
                attr = cell["attr"]
                spin = self._spin({**column, **cell}, float(getattr(self._model, attr, 0.0)))
                spin.valueChanged.connect(
                    lambda v, a=attr: setattr(self._model, a, float(v))
                )
                self._cells[(row, index)] = spin
                self.table.setCellWidget(row, index, spin)

        self.table.resizeColumnsToContents()
        self._fit_height()
        self.table.blockSignals(False)

    def _fit_height(self) -> None:
        """Size the table to exactly the rows it holds.

        Measured rather than assumed: a guessed row height loses the last row on
        a platform whose rows are a pixel taller, and the horizontal scrollbar
        that appears once the columns overflow takes its space out of the same
        budget. Losing the *last* row is the bad case, because that is where a
        trailing row such as the background sits -- present in the model,
        invisible on screen.
        """
        total = self.table.horizontalHeader().height() + 2 * self.table.frameWidth()
        for row in range(self.table.rowCount()):
            total += self.table.rowHeight(row)
        total += self.table.horizontalScrollBar().sizeHint().height()
        self.table.setFixedHeight(total)

    def refresh(self) -> None:
        """Re-read the model, rebuilding only when the grid's shape changed."""
        rows, columns = self._rows(), self._columns()
        trailing = self._trailing()
        if (self.table.rowCount() != rows + len(trailing)
                or self.table.columnCount() != len(columns)):
            self._build()
            return
        for row in range(rows):
            for index, column in enumerate(columns):
                if column.get("action"):
                    continue
                spin = self._cells.get((row, index))
                store = self._store(column)
                if spin is None or store is None:
                    continue
                position = self._index(column, row)
                spin.blockSignals(True)
                spin.setValue(store[position] if position < len(store) else 0.0)
                spin.blockSignals(False)
        for offset, extra in enumerate(trailing):
            for index, cell in enumerate(extra.get("cells", [])):
                spin = self._cells.get((rows + offset, index))
                if spin is None or not isinstance(cell, dict) or not cell.get("attr"):
                    continue
                spin.blockSignals(True)
                spin.setValue(float(getattr(self._model, cell["attr"], 0.0)))
                spin.blockSignals(False)
