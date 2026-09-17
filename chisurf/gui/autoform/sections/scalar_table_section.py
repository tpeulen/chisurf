"""Reusable AutoForm section: a compact table of plain scalar model attributes.

Like :class:`parameter_group_table` but for plain ``float`` / ``int`` / ``bool``
model attributes (not ``FittingParameter`` objects) — a space-saving name/value
table for parameter-dense editors (FRET crosstalk, anisotropy, …) instead of one
labelled row per field. Uses the central table formatting
(:func:`chisurf.gui.widgets.general.table_font`) so it matches the log and the
other tables, and renders HTML labels (sub/superscripts).

Declare it in a view spec::

    {"type": "custom", "key": "scalar_table",
     "options": {"title": "Crosstalk (α/β/γ/δ)", "call": "field_changed",
                 "rows": [{"attr": "alpha", "label": "α leakage"},
                          {"attr": "gamma", "label": "γ detection"}]}}

- ``rows`` — ordered ``[{attr, label, kind, decimals}]``; ``kind`` is
  ``float`` (default) / ``int`` / ``bool``.
- ``call`` — optional model method name invoked after each edit (e.g. to refresh
  a preview); the hosting form is refreshed regardless.
- ``title`` — optional compact header.
"""

from __future__ import annotations

from typing import Any

from qtpy import QtCore, QtWidgets

from .parameter_table import _RichTextDelegate
from .registry import register_section


@register_section("scalar_table")
class ScalarTableWidget(QtWidgets.QWidget):
    """Compact name/value table bound to plain scalar model attributes."""

    AUTOFORM_REFRESH = True
    is_form_field = False

    def __init__(self, model, target: str = "", **options: Any):
        super().__init__()
        self._model = getattr(model, target) if target else model
        self._host = model
        self._rows = [dict(r) for r in options.get("rows", [])]
        self._call = str(options.get("call", ""))
        title = str(options.get("title", ""))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        if title:
            header = QtWidgets.QLabel(f"<b>{title}</b>")
            header.setStyleSheet("color: palette(mid);")
            layout.addWidget(header)

        self.table = QtWidgets.QTableWidget(len(self._rows), 2)
        self.table.setHorizontalHeaderLabels(["Name", "Value"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
            | QtWidgets.QAbstractItemView.SelectedClicked
        )
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.table.setItemDelegateForColumn(0, _RichTextDelegate(self.table))
        self.table.horizontalHeader().setStretchLastSection(False)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)
        layout.addWidget(self.table)

        # Central table formatting (monospace) + compact row/header heights.
        try:
            from chisurf.gui.widgets.general import (
                table_font,
                table_header_height,
                table_row_height,
            )

            self._row_h = table_row_height()
            self.table.setFont(table_font())
            self.table.horizontalHeader().setFont(table_font())
            self.table.verticalHeader().setDefaultSectionSize(self._row_h)
            self.table.horizontalHeader().setFixedHeight(table_header_height())
        except Exception:
            self._row_h = 20

        self._build()
        self.table.itemChanged.connect(self._on_item_changed)

    def _build(self) -> None:
        self.table.blockSignals(True)
        try:
            from chisurf.gui.autoform.sections.builtin import _wrap_tooltip
        except Exception:
            _wrap_tooltip = lambda s: s  # noqa: E731
        for r, row in enumerate(self._rows):
            attr = str(row.get("attr", ""))
            name = QtWidgets.QTableWidgetItem(str(row.get("label", attr)))
            name.setFlags(QtCore.Qt.ItemIsEnabled)
            if row.get("description"):
                name.setToolTip(_wrap_tooltip(str(row["description"])))
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, self._value_item(row))
        self.table.blockSignals(False)
        header = self.table.horizontalHeader()
        # Size the name column to the longest label instead of a fixed width: a
        # truncated "α (donor leakage…" names nothing. Bounded so one verbose
        # row cannot squeeze the value column out of the panel.
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.table.resizeColumnToContents(0)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(0, max(90, min(self.table.columnWidth(0) + 8, 260)))
        self.table.setFixedHeight(self._natural_height())

    def _natural_height(self) -> int:
        """Exact pixel height of header + every row, so no row is clipped.

        Assuming a uniform row height clips the last row whenever the painted
        rows are taller than the configured default (a larger UI font, a
        platform style with more padding) — and a half-drawn last row reads as
        "that is all of them".
        """
        header = self.table.horizontalHeader()
        height = max(header.height(), header.sizeHint().height())
        for r in range(self.table.rowCount()):
            height += self.table.rowHeight(r) or self._row_h
        return height + 2 * self.table.frameWidth() + 2

    def _value_item(self, row: dict) -> QtWidgets.QTableWidgetItem:
        attr = str(row.get("attr", ""))
        kind = str(row.get("kind", "float"))
        value = getattr(self._model, attr, None)
        item = QtWidgets.QTableWidgetItem()
        item.setData(QtCore.Qt.UserRole, (attr, kind))
        if kind == "bool":
            item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if bool(value) else QtCore.Qt.Unchecked)
        else:
            decimals = int(row.get("decimals", 4))
            if kind == "int":
                text = str(int(value)) if value is not None else "0"
            else:
                text = f"{float(value):.{decimals}g}" if value is not None else ""
            item.setText(text)
            item.setFlags(
                QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable
            )
            item.setTextAlignment(int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter))
        return item

    def _on_item_changed(self, item) -> None:
        if item.column() != 1:
            return
        attr, kind = item.data(QtCore.Qt.UserRole) or ("", "float")
        if not attr:
            return
        try:
            if kind == "bool":
                setattr(self._model, attr, item.checkState() == QtCore.Qt.Checked)
            elif kind == "int":
                setattr(self._model, attr, int(float(item.text())))
            else:
                setattr(self._model, attr, float(item.text()))
        except (TypeError, ValueError):
            return
        if self._call:
            fn = getattr(self._host, self._call, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
        self._refresh_host_form()

    def _refresh_host_form(self) -> None:
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, "sync_fields") and hasattr(widget, "refresh_plots"):
                try:
                    widget.refresh_plots()
                except Exception:
                    pass
                return
            widget = widget.parent()

    def refresh(self) -> None:
        """Re-read model values into the value column (AUTOFORM_REFRESH)."""
        self.table.blockSignals(True)
        for r, row in enumerate(self._rows):
            self.table.setItem(r, 1, self._value_item(row))
        self.table.blockSignals(False)
