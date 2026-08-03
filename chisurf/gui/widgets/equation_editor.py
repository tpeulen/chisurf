"""A general, validated table editor for named expressions.

:class:`EquationTableEditor` edits a set of ``output = expression`` rows — the
kind of thing found in a derived-column formula list, an analytical parameter
relation, or a model equation catalogue. Each row is validated live against a
caller-supplied symbol table: the output name, the expression, and a ✓/✗ column
whose tooltip carries the reason a row is invalid (a parse error, a forbidden
construct, or an unresolved name).

It is deliberately general and configurable:

* **Validation** is backed by :mod:`chisurf.core.expressions` (a safe AST
  whitelist) by default, but a caller may inject its own ``validator`` so the
  editor's ✓/✗ stays perfectly in step with whatever engine will *evaluate* the
  expressions (ndX does this so the editor never accepts a formula its own
  compute engine would drop).
* **Names** come from a ``names_provider`` returning ``{category: [names]}`` —
  shown grouped in a reference dialog and flattened for validation. Earlier
  output names are offered as forward references.
* **Serialisation** matches the lightweight ``CodeEditor`` surface
  (``text()`` / ``setText`` / ``load_file`` / ``save_text`` / ``save_callback``
  / ``filename``) so the widget is a drop-in wherever a YAML equation blob was
  edited as raw text.

The widget emits :pyattr:`applied` after *Apply* (validate + ``save_callback``)
and :pyattr:`edited` on any row change, so a host can recompute and redraw.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import yaml
from qtpy import QtCore, QtGui, QtWidgets

from chisurf.core.expressions import (
    DEFAULT_POLICY,
    ExpressionPolicy,
    function_signatures,
    validate_expression,
)
from chisurf.gui import dialogs

_OK = "✓"   # ✓
_BAD = "✗"  # ✗

#: A validator maps ``(expression, known_names, output_names) -> (ok, message)``.
Validator = Callable[[str, Sequence[str], Sequence[str]], tuple[bool, str | None]]


class EquationTableEditor(QtWidgets.QWidget):
    """Validated table of ``output = expression`` rows.

    Parameters
    ----------
    parent
        Qt parent.
    names_provider
        ``() -> Mapping[str, Sequence[str]]`` (category -> names) or ``() ->
        Sequence[str]``. Used both to validate references and to populate the
        Names reference dialog. Called lazily so it always reflects live state.
    policy
        Expression policy for the default validator (ignored if ``validator`` is
        given). Defaults to the rich :data:`~chisurf.core.expressions.DEFAULT_POLICY`.
    validator
        Optional override ``(expr, known_names, output_names) -> (ok, message)``.
        When given, replaces the built-in policy-based validator entirely.
    allow_output_refs
        Offer earlier output names as valid (forward) references.
    quote_names
        Insert ``'name'`` (quoted) rather than ``name`` from the Names dialog.
        Defaults to the policy convention (quoted-only policies quote).
    show_preview
        Show a rendered preview of the focused expression (best-effort; auto-off
        for quoted-name conventions where a formula is not plain maths).
    output_label, expr_label
        Column header text.
    """

    #: Emitted after *Apply* (validation + ``save_callback``): recompute + redraw.
    applied = QtCore.Signal()
    #: Emitted on any row edit/add/remove.
    edited = QtCore.Signal()

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        names_provider: Callable[[], object] | None = None,
        policy: ExpressionPolicy = DEFAULT_POLICY,
        validator: Validator | None = None,
        allow_output_refs: bool = True,
        quote_names: bool | None = None,
        show_preview: bool = True,
        output_label: str = "Output",
        expr_label: str = "Expression",
    ) -> None:
        super().__init__(parent)
        self._names_provider = names_provider
        self._policy = policy
        self._validator = validator
        self._allow_output_refs = allow_output_refs
        self._quote = (
            quote_names
            if quote_names is not None
            else (policy.quoted_names and not policy.bare_names)
        )
        # A plain-maths preview only makes sense when names are bare identifiers.
        self._show_preview = bool(show_preview and not self._quote)

        #: ``CodeEditor``-compatible attributes.
        self.save_callback: Callable[[], None] | None = None
        self.filename: str | None = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        layout.addLayout(self._build_toolbar())

        self._table = QtWidgets.QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels([output_label, expr_label, ""])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self._table.setColumnWidth(0, 160)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.currentCellChanged.connect(self._on_current_cell)
        # Monospace expressions read better.
        mono = QtGui.QFont("monospace")
        mono.setStyleHint(QtGui.QFont.TypeWriter)
        self._table.setFont(mono)
        layout.addWidget(self._table, 1)

        self._preview = QtWidgets.QLabel("")
        self._preview.setAlignment(QtCore.Qt.AlignCenter)
        self._preview.setStyleSheet("background: white;")
        self._preview.setVisible(False)
        layout.addWidget(self._preview)

        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color: #666; font-size: 9pt;")
        layout.addWidget(self._status)

    # -- toolbar -----------------------------------------------------------
    def _build_toolbar(self) -> QtWidgets.QHBoxLayout:
        bar = QtWidgets.QHBoxLayout()
        self._btn_add = QtWidgets.QToolButton()
        self._btn_add.setText("➕")  # ➕
        self._btn_add.setToolTip("Add an equation")
        self._btn_add.clicked.connect(self._add_row)
        self._btn_del = QtWidgets.QToolButton()
        self._btn_del.setText("➖")  # ➖
        self._btn_del.setToolTip("Remove the selected equation")
        self._btn_del.clicked.connect(self._remove_selected)
        self._btn_names = QtWidgets.QToolButton()
        self._btn_names.setText("\U0001f524")  # 🔤
        self._btn_names.setToolTip("Names & functions you can use")
        self._btn_names.clicked.connect(self._show_reference)
        self._btn_apply = QtWidgets.QPushButton("Apply")
        self._btn_apply.setToolTip("Validate all equations and apply")
        self._btn_apply.clicked.connect(self.apply)
        for b in (self._btn_add, self._btn_del, self._btn_names):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(self._btn_apply)
        return bar

    # -- names -------------------------------------------------------------
    def set_names_provider(self, fn: Callable[[], object]) -> None:
        """Set the callable that yields the reference symbol table."""
        self._names_provider = fn

    def _grouped_names(self) -> dict[str, list[str]]:
        if self._names_provider is None:
            return {}
        try:
            raw = self._names_provider()
        except Exception:
            return {}
        if isinstance(raw, Mapping):
            return {str(k): [str(x) for x in v] for k, v in raw.items()}
        # A flat iterable of names.
        return {"Names": [str(x) for x in raw]}

    def _all_names(self) -> list[str]:
        out: list[str] = []
        for names in self._grouped_names().values():
            out.extend(names)
        return out

    def _output_names(self) -> list[str]:
        return [n for r in range(self._table.rowCount()) if (n := self._name_at(r))]

    # -- rows --------------------------------------------------------------
    def _name_at(self, row: int) -> str:
        it = self._table.item(row, 0)
        return it.text().strip() if it is not None else ""

    def _expr_at(self, row: int) -> str:
        it = self._table.item(row, 1)
        return it.text().strip() if it is not None else ""

    def _append_row(self, name: str = "", expr: str = "") -> int:
        row = self._table.rowCount()
        self._table.blockSignals(True)
        self._table.insertRow(row)
        self._table.setItem(row, 0, QtWidgets.QTableWidgetItem(name))
        self._table.setItem(row, 1, QtWidgets.QTableWidgetItem(expr))
        status = QtWidgets.QTableWidgetItem("")
        status.setFlags(QtCore.Qt.ItemIsEnabled)  # read-only status cell
        status.setTextAlignment(QtCore.Qt.AlignCenter)
        self._table.setItem(row, 2, status)
        self._table.blockSignals(False)
        return row

    def _add_row(self) -> None:
        row = self._append_row()
        self._validate_all()
        self._table.setCurrentCell(row, 0)
        self._table.editItem(self._table.item(row, 0))
        self.edited.emit()

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self._table.selectedItems()}, reverse=True)
        if not rows:
            return
        self._table.blockSignals(True)
        for r in rows:
            self._table.removeRow(r)
        self._table.blockSignals(False)
        self._validate_all()
        self.edited.emit()

    def _on_item_changed(self, _item) -> None:
        self._validate_all()
        self.edited.emit()

    def _on_current_cell(self, row, _col, _prow, _pcol) -> None:
        if self._show_preview and row >= 0:
            self._update_preview(self._expr_at(row))

    # -- validation --------------------------------------------------------
    def _validate_one(self, expr: str, known: Sequence[str], outputs: Sequence[str]):
        if self._validator is not None:
            return self._validator(expr, list(known), list(outputs))
        res = validate_expression(
            expr, known, self._policy, extra_names=outputs if self._allow_output_refs else ()
        )
        return res.ok, res.message

    def _validate_all(self) -> None:
        known = self._all_names()
        outputs = self._output_names() if self._allow_output_refs else []
        n_bad = 0
        for row in range(self._table.rowCount()):
            name = self._name_at(row)
            ok, msg = self._validate_one(self._expr_at(row), known, outputs)
            if not name:
                ok, msg = False, "missing output name"
            self._set_status(row, ok, msg)
            n_bad += 0 if ok else 1
        total = self._table.rowCount()
        if n_bad:
            self._status.setText(f"{total} equation(s), {n_bad} with problems")
            self._status.setStyleSheet("color: #c62828; font-size: 9pt;")
        else:
            self._status.setText(f"{total} equation(s), all valid")
            self._status.setStyleSheet("color: #2e7d32; font-size: 9pt;")

    def _set_status(self, row: int, ok: bool, msg: str | None) -> None:
        item = self._table.item(row, 2)
        if item is None:
            return
        item.setText(_OK if ok else _BAD)
        item.setForeground(QtGui.QBrush(QtGui.QColor("#2e7d32" if ok else "#c62828")))
        item.setToolTip("" if ok else (msg or "invalid"))

    def is_valid(self) -> bool:
        """Return True when every non-empty row validates."""
        known = self._all_names()
        outputs = self._output_names() if self._allow_output_refs else []
        for row in range(self._table.rowCount()):
            if not self._name_at(row):
                return False
            ok, _ = self._validate_one(self._expr_at(row), known, outputs)
            if not ok:
                return False
        return True

    # -- reference dialog --------------------------------------------------
    def _show_reference(self) -> None:
        grouped = self._grouped_names()
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Names & functions")
        dlg.setMinimumSize(380, 460)
        lay = QtWidgets.QVBoxLayout(dlg)
        hint = "Double-click a name to insert it into the focused expression."
        lay.addWidget(QtWidgets.QLabel(hint))
        lst = QtWidgets.QListWidget()

        def _header(text: str) -> None:
            it = QtWidgets.QListWidgetItem(f"— {text} —")
            it.setFlags(QtCore.Qt.ItemIsEnabled)
            it.setForeground(QtGui.QBrush(QtGui.QColor("#888")))
            lst.addItem(it)

        for cat, names in grouped.items():
            if not names:
                continue
            _header(cat)
            for n in names:
                lst.addItem(QtWidgets.QListWidgetItem(str(n)))
        _header("Functions")
        for fn, doc in function_signatures(self._policy).items():
            it = QtWidgets.QListWidgetItem(f"{fn}()")
            if doc:
                it.setToolTip(doc)
            it.setData(QtCore.Qt.UserRole, f"{fn}(")
            lst.addItem(it)

        def _insert(item: QtWidgets.QListWidgetItem) -> None:
            token = item.data(QtCore.Qt.UserRole)
            if token is None:
                name = item.text()
                token = f"'{name}'" if self._quote else name
            self._insert_into_focused(token)

        lst.itemDoubleClicked.connect(_insert)
        lay.addWidget(lst)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn.rejected.connect(dlg.reject)
        btn.accepted.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec_()

    def _insert_into_focused(self, token: str) -> None:
        row = self._table.currentRow()
        if row < 0:
            row = self._append_row()
        item = self._table.item(row, 1)
        if item is None:
            item = QtWidgets.QTableWidgetItem("")
            self._table.setItem(row, 1, item)
        item.setText((item.text() + token).strip())

    # -- preview -----------------------------------------------------------
    def _update_preview(self, expr: str) -> None:
        pix = self._render_latex(expr) if expr else None
        if pix is None:
            self._preview.setVisible(False)
            return
        self._preview.setPixmap(pix)
        self._preview.setVisible(True)

    def _render_latex(self, expr: str) -> QtGui.QPixmap | None:
        """Best-effort math render of ``expr``; None if it cannot be rendered."""
        try:
            import io

            import matplotlib.pyplot as plt

            from chisurf.gui.widgets.models.parse.latex import (
                convert_python_expression_to_latex,
                sanitize_latex_for_mathtext,
            )

            tex = sanitize_latex_for_mathtext(convert_python_expression_to_latex(expr))
            fig = plt.figure(figsize=(3.0, 0.5), dpi=100)
            fig.patch.set_facecolor("white")
            fig.text(0.5, 0.5, f"${tex}$", ha="center", va="center", fontsize=13, color="black")
            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.05,
                        facecolor="white")
            plt.close(fig)
            buf.seek(0)
            pix = QtGui.QPixmap()
            pix.loadFromData(buf.getvalue())
            return pix
        except Exception:
            return None

    # -- equations <-> table ----------------------------------------------
    def equations(self) -> list[dict]:
        """Return the equations as ``[{name: expr}, ...]`` (rows with both set)."""
        out: list[dict] = []
        for row in range(self._table.rowCount()):
            name, expr = self._name_at(row), self._expr_at(row)
            if name and expr:
                out.append({name: expr})
        return out

    def set_equations(self, equations) -> None:
        """Populate the table from ``[{name: expr}, ...]``."""
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for mapping in (equations or []):
            for name, expr in mapping.items():
                self._append_row(str(name), str(expr))
        self._table.blockSignals(False)
        self._validate_all()

    # -- CodeEditor-compatible surface ------------------------------------
    def text(self) -> str:
        """Serialise the table to YAML (a list of one-key maps)."""
        return yaml.safe_dump(self.equations(), sort_keys=False, default_flow_style=False)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming)
        """Parse YAML ``text`` (a list of one-key maps) into the table."""
        try:
            data = yaml.safe_load(text) or []
        except Exception:
            data = []
        self.set_equations(data)

    def load_file(self, filename: str | None = None, **_kwargs) -> None:
        """Load equations from a YAML file (prompt if ``filename`` is None)."""
        if filename is None:
            filename, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Open equations", "", "YAML (*.yaml *.yml)"
            )
        if not filename:
            return
        try:
            with open(filename, encoding="utf-8") as fp:
                self.setText(fp.read())
            self.filename = filename
        except OSError as exc:  # pragma: no cover - UI path
            dialogs.warning(self, "Equations", f"Could not load:\n{exc}")

    def save_text(self, _event=None) -> None:
        """Write the equations to ``filename`` (prompt if unset) + call save_callback."""
        if not self.filename:
            self.filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save equations", "", "YAML (*.yaml *.yml)"
            )
            if not self.filename:
                return
        try:
            with open(self.filename, "w", encoding="utf-8") as fp:
                fp.write(self.text())
        except OSError as exc:  # pragma: no cover - UI path
            dialogs.warning(self, "Equations", f"Could not save:\n{exc}")
            return
        if callable(self.save_callback):
            self.save_callback()

    def apply(self) -> None:
        """Validate, push via ``save_callback``, and emit :pyattr:`applied`."""
        self._validate_all()
        if callable(self.save_callback):
            self.save_callback()
        self.applied.emit()


__all__ = ["EquationTableEditor", "Validator"]
