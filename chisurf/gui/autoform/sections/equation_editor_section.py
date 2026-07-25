"""AutoForm section: a validated ``output = expression`` table editor.

Wraps the general :class:`~chisurf.gui.widgets.equation_editor.EquationTableEditor`
so a model view spec can expose an equation list (derived columns, analytical
relations, a formula catalogue) with live ✓/✗ validation.

Declare it in a view spec::

    {"type": "custom", "key": "equation_editor",
     "options": {"attr": "equations",        # model attr: [{name: expr}, ...]
                 "names": "equation_names",   # model attr/method -> {cat: [names]}
                 "call": "apply_equations",   # model method run after Apply
                 "policy": "default"}}        # "default" (rich) or "ndx" (quoted)

- ``attr`` — model attribute holding ``[{name: expr}, ...]``; read on build and
  written back on *Apply*.
- ``names`` — model attribute or zero-arg method returning ``{category: [names]}``
  (or a flat list) used for validation + the reference dialog.
- ``call`` — optional model method invoked after *Apply* (e.g. recompute).
- ``policy`` — ``"default"`` (rich Python-like) or ``"ndx"`` (quoted names,
  arithmetic + ``abs``); defaults to ``"default"``.
"""

from __future__ import annotations

from typing import Any

from qtpy import QtWidgets

from chisurf.core.expressions import DEFAULT_POLICY, NDX_POLICY
from chisurf.gui.widgets.equation_editor import EquationTableEditor

from .registry import register_section

_POLICIES = {"default": DEFAULT_POLICY, "ndx": NDX_POLICY}


@register_section("equation_editor")
class EquationEditorSection(QtWidgets.QWidget):
    """View-spec section hosting an :class:`EquationTableEditor`."""

    AUTOFORM_REFRESH = True
    is_form_field = False

    def __init__(self, model, target: str = "", **options: Any):
        super().__init__()
        self._model = getattr(model, target) if target else model
        self._attr = str(options.get("attr", "equations"))
        self._names = str(options.get("names", ""))
        self._call = str(options.get("call", ""))
        policy = _POLICIES.get(str(options.get("policy", "default")), DEFAULT_POLICY)
        quote = policy is NDX_POLICY

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.editor = EquationTableEditor(
            names_provider=self._resolve_names,
            policy=policy,
            quote_names=quote,
            output_label=str(options.get("output_label", "Output")),
            expr_label=str(options.get("expr_label", "Expression")),
        )
        layout.addWidget(self.editor)

        self.editor.set_equations(getattr(self._model, self._attr, []) or [])
        self.editor.applied.connect(self._on_applied)

    def _resolve_names(self):
        if not self._names:
            return {}
        src = getattr(self._model, self._names, None)
        if callable(src):
            try:
                return src()
            except Exception:
                return {}
        return src or {}

    def _on_applied(self) -> None:
        try:
            setattr(self._model, self._attr, self.editor.equations())
        except Exception:
            return
        if self._call:
            fn = getattr(self._model, self._call, None)
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
        """Re-read the model's equations into the table (AUTOFORM_REFRESH)."""
        self.editor.set_equations(getattr(self._model, self._attr, []) or [])
