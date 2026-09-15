"""A validated single-expression input backed by the safe expression engine.

Where :class:`~chisurf.gui.widgets.equation_editor.EquationTableEditor` edits a
*table* of ``output = expression`` rows, :class:`ExpressionInput` edits **one**
expression — the shape of a parse-model formula (``a1*exp(-x/tau1)`` and the
like). It gives the same "good editor" qualities in a compact form:

* live validation via :mod:`chisurf.core.support.expressions` (a safe AST whitelist) with
  a ✓/✗ badge and the error reason in a tooltip;
* a names & functions reference button;
* an optional inline LaTeX preview of the current formula;
* automatic **parameter discovery** — every name that is not the independent
  variable, a function, or a constant is reported as a free parameter.

It is used by the parse-model formula widgets (TCSPC / FCS / PCF) in place of a
raw text box, so a mistyped or unsafe formula is caught with a clear message
instead of failing silently at evaluation.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.core.support.expressions import (
    PARSE_MODEL_POLICY,
    ExpressionPolicy,
    discover_parameters,
    function_signatures,
    validate_expression,
)

_OK = "✓"   # ✓
_BAD = "✗"  # ✗


class ExpressionInput(QtWidgets.QWidget):
    """A one-line expression editor with live validation and a function reference.

    Parameters
    ----------
    parent
        Qt parent.
    policy
        Expression policy (defaults to
        :data:`~chisurf.core.support.expressions.PARSE_MODEL_POLICY`).
    reserved_names
        Names that are valid but are *not* parameters (e.g. the independent
        variable ``x``).
    names_provider
        Optional ``() -> Sequence[str]`` of extra known names (offered in the
        reference dialog and treated as resolved).
    allow_unknown
        When True (the parse-model default) unknown names are free parameters,
        not errors — only the safe-parse check gates validity.
    show_preview
        Show an inline LaTeX preview of the formula (best-effort).
    placeholder
        Placeholder text for the empty editor.
    """

    #: Emitted on every text change with the current text.
    edited = QtCore.Signal(str)
    #: Emitted on Return when the expression is valid.
    committed = QtCore.Signal(str)
    #: Emitted with the discovered free-parameter names whenever they change.
    parametersChanged = QtCore.Signal(list)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        policy: ExpressionPolicy = PARSE_MODEL_POLICY,
        reserved_names: Sequence[str] = ("x",),
        names_provider: Callable[[], Sequence[str]] | None = None,
        allow_unknown: bool = True,
        show_preview: bool = True,
        placeholder: str = "e.g.  a1*exp(-x/tau1) + a2*exp(-x/tau2)",
    ) -> None:
        super().__init__(parent)
        self._policy = policy
        self._reserved = list(reserved_names)
        self._names_provider = names_provider
        self._allow_unknown = allow_unknown
        self._show_preview = show_preview
        self._parameters: list[str] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        row = QtWidgets.QHBoxLayout()
        self._edit = QtWidgets.QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        mono = QtGui.QFont("monospace")
        mono.setStyleHint(QtGui.QFont.TypeWriter)
        self._edit.setFont(mono)
        self._edit.textChanged.connect(self._on_text_changed)
        self._edit.returnPressed.connect(self._on_return)
        self._badge = QtWidgets.QLabel("")
        self._badge.setFixedWidth(16)
        self._badge.setAlignment(QtCore.Qt.AlignCenter)
        self._btn_names = QtWidgets.QToolButton()
        self._btn_names.setText("\U0001f524")  # 🔤
        self._btn_names.setToolTip("Names & functions you can use")
        self._btn_names.clicked.connect(self._show_reference)
        row.addWidget(self._edit, 1)
        row.addWidget(self._badge)
        row.addWidget(self._btn_names)
        layout.addLayout(row)

        self._preview = QtWidgets.QLabel("")
        self._preview.setAlignment(QtCore.Qt.AlignCenter)
        self._preview.setStyleSheet("background: white;")
        self._preview.setVisible(False)
        layout.addWidget(self._preview)

        self._error = QtWidgets.QLabel("")
        self._error.setStyleSheet("color: #c62828; font-size: 9pt;")
        self._error.setVisible(False)
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

    # -- text surface ------------------------------------------------------
    def text(self) -> str:
        """Return the current expression text."""
        return self._edit.text().strip()

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming)
        """Set the expression text (revalidates)."""
        self._edit.setText("" if text is None else str(text))

    # Aliases that read naturally at call sites.
    expression = text

    def set_expression(self, text: str) -> None:
        """Set the expression text without emitting :pyattr:`committed`."""
        self.setText(text)

    def set_text_silently(self, text: str) -> None:
        """Set the text without emitting :pyattr:`edited` (still validates)."""
        self._edit.blockSignals(True)
        self._edit.setText("" if text is None else str(text))
        self._edit.blockSignals(False)
        self._revalidate()

    def discovered_parameters(self) -> list[str]:
        """Return the current free-parameter names (in appearance order)."""
        return list(self._parameters)

    def is_valid(self) -> bool:
        """Return True when the current expression validates."""
        return bool(self._validate().ok) if self.text() else False

    # -- known names -------------------------------------------------------
    def _known(self) -> list[str]:
        names = list(self._reserved)
        if self._names_provider is not None:
            try:
                names += [str(n) for n in self._names_provider()]
            except Exception:
                pass
        return names

    # -- validation --------------------------------------------------------
    def _validate(self):
        return validate_expression(
            self.text(), self._known(), self._policy, allow_unknown=self._allow_unknown
        )

    def _on_text_changed(self, _text: str) -> None:
        self._revalidate()
        self.edited.emit(self.text())

    def _revalidate(self) -> None:
        text = self.text()
        if not text:
            self._badge.setText("")
            self._error.setVisible(False)
            self._preview.setVisible(False)
            self._set_parameters([])
            return
        res = self._validate()
        if res.ok:
            self._badge.setText(_OK)
            self._badge.setStyleSheet("color: #2e7d32;")
            self._badge.setToolTip("")
            self._error.setVisible(False)
            self._set_parameters(
                discover_parameters(text, self._known(), self._policy)
            )
            if self._show_preview:
                self._update_preview(text)
        else:
            self._badge.setText(_BAD)
            self._badge.setStyleSheet("color: #c62828;")
            self._badge.setToolTip(res.message or "invalid")
            self._error.setText(res.message or "invalid")
            self._error.setVisible(True)
            self._preview.setVisible(False)
            self._set_parameters([])

    def _set_parameters(self, params: list[str]) -> None:
        if params != self._parameters:
            self._parameters = params
            self.parametersChanged.emit(list(params))

    def _on_return(self) -> None:
        if self.is_valid():
            self.committed.emit(self.text())

    # -- reference ---------------------------------------------------------
    def _show_reference(self) -> None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Names & functions")
        dlg.setMinimumSize(340, 420)
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.addWidget(QtWidgets.QLabel(
            "Double-click to insert. Any name that is not a function, a constant,\n"
            "or the independent variable becomes a fitting parameter."))
        lst = QtWidgets.QListWidget()

        def _header(text: str) -> None:
            it = QtWidgets.QListWidgetItem(f"— {text} —")
            it.setFlags(QtCore.Qt.ItemIsEnabled)
            it.setForeground(QtGui.QBrush(QtGui.QColor("#888")))
            lst.addItem(it)

        reserved = self._reserved + [
            str(n) for n in (self._names_provider() if self._names_provider else [])
        ]
        if reserved:
            _header("Reserved / known")
            for n in reserved:
                lst.addItem(QtWidgets.QListWidgetItem(str(n)))
        _header("Constants")
        for c in sorted(self._policy.constants):
            lst.addItem(QtWidgets.QListWidgetItem(str(c)))
        _header("Functions")
        for fn, doc in function_signatures(self._policy).items():
            it = QtWidgets.QListWidgetItem(f"{fn}()")
            if doc:
                it.setToolTip(doc)
            it.setData(QtCore.Qt.UserRole, f"{fn}(")
            lst.addItem(it)

        def _insert(item: QtWidgets.QListWidgetItem) -> None:
            token = item.data(QtCore.Qt.UserRole) or item.text()
            self._edit.insert(token)
            self._edit.setFocus()

        lst.itemDoubleClicked.connect(_insert)
        lay.addWidget(lst)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn.rejected.connect(dlg.reject)
        btn.accepted.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec_()

    # -- preview -----------------------------------------------------------
    def _update_preview(self, expr: str) -> None:
        pix = self._render_latex(expr)
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
            fig = plt.figure(figsize=(4.0, 0.5), dpi=100)
            fig.patch.set_facecolor("white")
            fig.text(0.5, 0.5, f"${tex}$", ha="center", va="center", fontsize=13, color="black")
            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.05, facecolor="white")
            plt.close(fig)
            buf.seek(0)
            pix = QtGui.QPixmap()
            pix.loadFromData(buf.getvalue())
            return pix
        except Exception:
            return None


__all__ = ["ExpressionInput"]
