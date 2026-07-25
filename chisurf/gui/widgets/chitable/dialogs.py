"""Small helper dialogs for :mod:`chisurf.gui.widgets.chitable`.

:class:`ColumnPickerDialog` is the generalised form of the column chooser that
previously existed only inside ndXplorer; :class:`ColumnFilterDialog` edits one
column's predicate.
"""

from __future__ import annotations

from collections.abc import Sequence

from qtpy import QtCore, QtWidgets

from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.chitable.filters import (
    ALL_OPS,
    NULL_OPS,
    NUMERIC_OPS,
    OP_LABELS,
    ColumnFilter,
)


class ColumnPickerDialog(QtWidgets.QDialog):
    """Checkbox list for choosing which columns a table shows.

    Parameters
    ----------
    columns : sequence of (str, bool)
        ``(label, visible)`` per column, in table order.
    parent : qtpy.QtWidgets.QWidget, optional
        Parent widget.
    title : str
        Window title.
    """

    def __init__(
        self,
        columns: Sequence[tuple[str, bool]],
        parent: QtWidgets.QWidget | None = None,
        title: str = "Select columns",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(320, 460)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._search = QtWidgets.QLineEdit(self)
        self._search.setPlaceholderText(f"{Glyphs.SEARCH} Filter column names…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_name_filter)
        layout.addWidget(self._search)

        self._list = QtWidgets.QListWidget(self)
        for label, visible in columns:
            item = QtWidgets.QListWidgetItem(str(label), self._list)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if visible else QtCore.Qt.Unchecked)
        layout.addWidget(self._list, 1)

        buttons = QtWidgets.QHBoxLayout()
        btn_all = QtWidgets.QToolButton(self)
        btn_all.setText(f"{Glyphs.CHECKBOX_ON} All")
        btn_all.setToolTip("Show every column")
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none = QtWidgets.QToolButton(self)
        btn_none.setText(f"{Glyphs.CHECKBOX_OFF} None")
        btn_none.setToolTip("Hide every column")
        btn_none.clicked.connect(lambda: self._set_all(False))
        buttons.addWidget(btn_all)
        buttons.addWidget(btn_none)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, parent=self
        )
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _apply_name_filter(self, text: str) -> None:
        """Hide list entries whose label does not contain ``text``.

        Parameters
        ----------
        text : str
            Case-insensitive substring.
        """
        needle = text.strip().lower()
        for row in range(self._list.count()):
            item = self._list.item(row)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _set_all(self, checked: bool) -> None:
        """Check or uncheck every visible entry.

        Parameters
        ----------
        checked : bool
            Target state.
        """
        state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
        for row in range(self._list.count()):
            item = self._list.item(row)
            if not item.isHidden():
                item.setCheckState(state)

    def visibility(self) -> list[bool]:
        """Return the chosen visibility per column, in table order.

        Returns
        -------
        list of bool
        """
        return [
            self._list.item(row).checkState() == QtCore.Qt.Checked
            for row in range(self._list.count())
        ]


class ColumnFilterDialog(QtWidgets.QDialog):
    """Editor for a single column's filter predicate.

    Parameters
    ----------
    column : int
        Column index the filter applies to.
    label : str
        Column title, shown in the dialog.
    numeric : bool
        Offer the numeric comparisons rather than the text ones.
    current : ColumnFilter, optional
        Existing predicate to pre-fill.
    parent : qtpy.QtWidgets.QWidget, optional
        Parent widget.
    """

    def __init__(
        self,
        column: int,
        label: str,
        numeric: bool,
        current: ColumnFilter | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._column = int(column)
        self.setWindowTitle(f"Filter — {label}")

        form = QtWidgets.QFormLayout(self)
        form.setContentsMargins(10, 10, 10, 10)

        self._op = QtWidgets.QComboBox(self)
        ops = (
            (NUMERIC_OPS + NULL_OPS)
            if numeric
            else tuple(op for op in ALL_OPS if op not in NUMERIC_OPS)
        )
        for op in ops:
            self._op.addItem(OP_LABELS.get(op, op), op)
        form.addRow("Condition", self._op)

        self._value = QtWidgets.QLineEdit(self)
        self._value.setPlaceholderText("value")
        form.addRow("Value", self._value)

        self._value2 = QtWidgets.QLineEdit(self)
        self._value2.setPlaceholderText("upper bound")
        form.addRow("and", self._value2)

        self._case = QtWidgets.QCheckBox("Case sensitive", self)
        self._case.setVisible(not numeric)
        form.addRow("", self._case)

        if current is not None:
            pos = self._op.findData(current.op)
            if pos >= 0:
                self._op.setCurrentIndex(pos)
            self._value.setText("" if current.value is None else str(current.value))
            self._value2.setText("" if current.value2 is None else str(current.value2))
            self._case.setChecked(bool(current.case_sensitive))

        self._op.currentIndexChanged.connect(self._sync_enabled)
        self._sync_enabled()

        box = QtWidgets.QDialogButtonBox(self)
        box.addButton(QtWidgets.QDialogButtonBox.Ok)
        box.addButton(QtWidgets.QDialogButtonBox.Cancel)
        self._clear_button = box.addButton("Clear", QtWidgets.QDialogButtonBox.ResetRole)
        self._cleared = False
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        self._clear_button.clicked.connect(self._on_clear)
        form.addRow(box)

    def _sync_enabled(self) -> None:
        """Enable only the operand fields the chosen predicate uses."""
        op = self._op.currentData()
        self._value.setEnabled(op not in NULL_OPS)
        self._value2.setEnabled(op in ("between", "outside"))

    def _on_clear(self) -> None:
        """Accept the dialog with an explicit "no filter" result."""
        self._cleared = True
        self.accept()

    def result_filter(self) -> ColumnFilter | None:
        """Return the edited predicate, or ``None`` to clear the column.

        Returns
        -------
        ColumnFilter or None
        """
        if self._cleared:
            return None
        op = self._op.currentData()
        value = self._value.text().strip()
        value2 = self._value2.text().strip()
        if op not in NULL_OPS and value == "":
            return None
        return ColumnFilter(
            column=self._column,
            op=op,
            value=value or None,
            value2=value2 or None,
            case_sensitive=self._case.isChecked(),
        )
