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
``minimum_attr`` / ``maximum_attr`` on a column name model **lists** of bounds
indexed by row, for the case where the rows are not interchangeable — a table of
estimator parameters, where a lifetime and a fraction have nothing to do with
each other's range. Without them a column's ``minimum``/``maximum`` applies to
every row, which is right when the rows are the same kind of thing.

A column's ``kind`` chooses the editor: ``"float"`` (the default) is a spin box,
``"bool"`` a checkbox, and ``"readonly"`` a value the model writes and the user
does not — a fitted result beside the initial value it started from. That last
pair is why a *parameter* table is the same widget as a state table: rows are
things, columns are aspects of them, and only the cell editor differs.

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

    def _bound(self, column: dict, key: str, row: int, fallback: float) -> float:
        """Return one bound of a cell, per row when the column names a list."""
        listed = _resolve(self._model, column.get(f"{key}_attr", ""), None)
        if isinstance(listed, (list, tuple)) and row < len(listed):
            try:
                return float(listed[row])
            except (TypeError, ValueError):
                pass
        return float(column.get(key, fallback))

    def _spin(self, column: dict, value: float, row: int = 0) -> QtWidgets.QDoubleSpinBox:
        """Return a spin box configured for one cell."""
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(self._bound(column, "minimum", row, self._minimum),
                      self._bound(column, "maximum", row, self._maximum))
        spin.setDecimals(int(column.get("decimals", self._decimals)))
        spin.setKeyboardTracking(False)
        spin.setMaximumWidth(96)
        spin.setValue(float(value))
        return spin

    def _check(self, value: bool) -> QtWidgets.QWidget:
        """Return a checkbox centred in its cell.

        Wrapped in a container because a bare checkbox in a table cell sits hard
        against the left edge, which reads as belonging to the column before it.
        """
        holder = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        box = QtWidgets.QCheckBox()
        box.setChecked(bool(value))
        layout.addWidget(box)
        holder.checkbox = box
        return holder

    def _cell(self, column: dict, value: float, row: int = 0):
        """Return the editor for one cell, by the column's ``kind``."""
        kind = str(column.get("kind", "float"))
        if kind == "bool":
            return self._check(bool(value))
        spin = self._spin(column, value, row)
        if kind == "readonly" or column.get("readonly"):
            spin.setReadOnly(True)
            spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            spin.setFocusPolicy(QtCore.Qt.NoFocus)
        return spin

    @staticmethod
    def _value_of(widget) -> float:
        """Return a cell widget's value, whatever kind it is."""
        box = getattr(widget, "checkbox", None)
        if box is not None:
            return float(box.isChecked())
        return float(widget.value())

    @staticmethod
    def _set_value(widget, value: float) -> None:
        """Write a value into a cell widget without echoing a change back."""
        box = getattr(widget, "checkbox", None)
        target = box if box is not None else widget
        target.blockSignals(True)
        if box is not None:
            box.setChecked(bool(value))
        else:
            widget.setValue(float(value))
        target.blockSignals(False)

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
                widget = self._cell(column, value, row)
                box = getattr(widget, "checkbox", None)
                if box is not None:
                    box.toggled.connect(
                        lambda v, c=column, r=row: self._write(c, r, float(v))
                    )
                elif not (column.get("kind") == "readonly" or column.get("readonly")):
                    widget.valueChanged.connect(
                        lambda v, c=column, r=row: self._write(c, r, v)
                    )
                self._cells[(row, index)] = widget
                self.table.setCellWidget(row, index, widget)

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
                merged = {**column, **cell}
                widget = self._cell(merged, float(getattr(self._model, attr, 0.0)), row)
                box = getattr(widget, "checkbox", None)
                if box is not None:
                    box.toggled.connect(lambda v, a=attr: setattr(self._model, a, bool(v)))
                elif not (merged.get("kind") == "readonly" or merged.get("readonly")):
                    widget.valueChanged.connect(
                        lambda v, a=attr: setattr(self._model, a, float(v))
                    )
                self._cells[(row, index)] = widget
                self.table.setCellWidget(row, index, widget)

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
                widget = self._cells.get((row, index))
                store = self._store(column)
                if widget is None or store is None:
                    continue
                position = self._index(column, row)
                self._set_value(widget, store[position] if position < len(store) else 0.0)
        for offset, extra in enumerate(trailing):
            for index, cell in enumerate(extra.get("cells", [])):
                widget = self._cells.get((rows + offset, index))
                if widget is None or not isinstance(cell, dict) or not cell.get("attr"):
                    continue
                self._set_value(widget, float(getattr(self._model, cell["attr"], 0.0)))
