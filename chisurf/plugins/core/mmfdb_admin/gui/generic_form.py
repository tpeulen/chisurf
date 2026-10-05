"""Dynamic, schema-driven detail and edit form widget for MMFDB tables."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qtpy import QtCore, QtWidgets

import chisurf.logging

from .legacy_schemas import SCHEMAS  # noqa: F401  (re-exported for older callers)


class MMFDBDetailWidget(QtWidgets.QWidget):
    """A generic form layout widget driven by MMFDB schemas.

    Accepts either a ``schema_type`` string (for backward compatibility
    with legacy code) or a ``field_specs`` list (preferred for new code).

    Signals
    -------
    dataChanged()
        Fires on every keystroke / live change (kept for backward compat).
    commitRequested()
        Fires only when the user explicitly commits an edit: Enter key on a
        line/spin field, focus-out from a text area, a dropdown selection, or
        a checkbox toggle.  Wire this to auto-save logic — it respects Qt's
        built-in Ctrl+Z undo stack because the user can still undo *within*
        a field before pressing Enter.
    """

    dataChanged = QtCore.Signal()
    commitRequested = QtCore.Signal()

    def __init__(
        self,
        schema_type: str | None = None,
        field_specs: list[dict[str, Any]] | None = None,
        dropdown_providers: dict[str, Callable[[], list[tuple[str, str]]]] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        from .entity_schema import FieldSpec

        super().__init__(parent)
        self.schema_type = schema_type or ""
        self.dropdown_providers = dropdown_providers or {}

        # Build schema from field_specs (preferred) or legacy SCHEMAS dict
        if field_specs:
            self.schema = [
                {
                    "name": fs.name if isinstance(fs, FieldSpec) else fs.get("name", ""),
                    "label": fs.label
                    if isinstance(fs, FieldSpec)
                    else fs.get("label", fs.get("name", "")),
                    "type": fs.widget if isinstance(fs, FieldSpec) else fs.get("type", "str"),
                    "required": fs.required
                    if isinstance(fs, FieldSpec)
                    else fs.get("required", False),
                    "readonly": fs.readonly
                    if isinstance(fs, FieldSpec)
                    else fs.get("readonly", False),
                    "choices": list(fs.choices)
                    if isinstance(fs, FieldSpec)
                    else fs.get("choices", []),
                    "placeholder": fs.placeholder
                    if isinstance(fs, FieldSpec)
                    else fs.get("placeholder", ""),
                    "tooltip": fs.tooltip if isinstance(fs, FieldSpec) else fs.get("tooltip", ""),
                }
                for fs in field_specs
            ]
        else:
            self.schema = SCHEMAS.get(self.schema_type, [])

        self.widgets: dict[str, QtWidgets.QWidget] = {}
        self._loading = False
        self._text_areas: list[QtWidgets.QPlainTextEdit] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QtWidgets.QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        for field in self.schema:
            name = field["name"]
            label = field.get("label", name)
            ftype = field.get("type", "str")
            readonly = field.get("readonly", False)
            required = field.get("required", False)
            placeholder = field.get("placeholder", "")
            tooltip = field.get("tooltip", "")

            if required:
                label = f"* {label}"

            widget: QtWidgets.QWidget
            if ftype == "choice" or name in self.dropdown_providers:
                widget = QtWidgets.QComboBox()
                widget.setEditable(True)
                if ftype == "choice":
                    for choice in field.get("choices", []):
                        widget.addItem(choice, choice)
                # activated fires only on user selection (not programmatic),
                # preserving Ctrl+Z undo within the line edit before selecting.
                widget.activated.connect(self._on_commit)
                widget.currentIndexChanged.connect(self._on_changed)
                # Enter in the editable line of the combo
                if widget.lineEdit() is not None:
                    widget.lineEdit().editingFinished.connect(self._on_commit)
                    widget.lineEdit().textChanged.connect(self._on_changed)
            elif ftype == "bool":
                widget = QtWidgets.QCheckBox()
                widget.stateChanged.connect(self._on_changed)
                widget.toggled.connect(self._on_commit)
            elif ftype == "text":
                widget = QtWidgets.QPlainTextEdit()
                widget.setMinimumHeight(60)
                widget.textChanged.connect(self._on_changed)
                # Commit on focus-out (detected via eventFilter below)
                widget.installEventFilter(self)
                if not readonly:
                    self._text_areas.append(widget)
            elif ftype == "int":
                widget = QtWidgets.QSpinBox()
                widget.setRange(-2147483648, 2147483647)
                widget.valueChanged.connect(self._on_changed)
                widget.editingFinished.connect(self._on_commit)
            elif ftype == "float":
                widget = QtWidgets.QDoubleSpinBox()
                widget.setRange(-1e9, 1e9)
                widget.valueChanged.connect(self._on_changed)
                widget.editingFinished.connect(self._on_commit)
            else:
                widget = QtWidgets.QLineEdit()
                widget.textChanged.connect(self._on_changed)
                widget.editingFinished.connect(self._on_commit)

            if placeholder and hasattr(widget, "setPlaceholderText"):
                widget.setPlaceholderText(placeholder)

            if tooltip:
                widget.setToolTip(tooltip)

            if readonly:
                if hasattr(widget, "setReadOnly"):
                    widget.setReadOnly(True)
                elif hasattr(widget, "setEnabled"):
                    widget.setEnabled(False)

            self.widgets[name] = widget
            layout.addRow(label, widget)

    def refresh_dropdowns(self) -> None:
        """Call dropdown providers to populate choice fields asynchronously/on-demand."""
        old_loading = self._loading
        self._loading = True
        try:
            for name, provider in self.dropdown_providers.items():
                widget = self.widgets.get(name)
                if isinstance(widget, QtWidgets.QComboBox):
                    current_text = widget.currentText()
                    current_data = widget.currentData()
                    widget.clear()
                    try:
                        choices = provider()
                        for item in choices:
                            if isinstance(item, tuple):
                                val, lbl = item
                            else:
                                val = lbl = item
                            widget.addItem(lbl, val)
                    except Exception as _exc:
                        chisurf.logging.warning("Dropdown provider failed: %s", _exc)
                    # Restore selection
                    idx = -1
                    if current_data is not None:
                        idx = widget.findData(current_data)
                    if idx < 0 and current_text:
                        idx = widget.findText(current_text)
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                    else:
                        widget.setEditText(current_text)
        finally:
            self._loading = old_loading

    def _on_changed(self, *args: Any) -> None:
        if not self._loading:
            self.dataChanged.emit()

    def _on_commit(self, *args: Any) -> None:
        """Emit commitRequested when the user explicitly commits an edit."""
        if not self._loading:
            self.commitRequested.emit()

    def eventFilter(self, obj: Any, event: Any) -> bool:
        """Detect focus-out on QPlainTextEdit fields to trigger commit."""
        from qtpy.QtCore import QEvent

        if event.type() == QEvent.FocusOut and obj in self._text_areas:
            self._on_commit()
        return False

    def set_data(self, data: dict[str, Any]) -> None:
        """Populate form fields with database record data."""
        self._loading = True
        try:
            self.refresh_dropdowns()
            for field in self.schema:
                name = field["name"]
                val = data.get(name)
                widget = self.widgets.get(name)
                if not widget:
                    continue

                if isinstance(val, (list, dict)):
                    import json

                    val = json.dumps(val)

                if isinstance(widget, QtWidgets.QComboBox):
                    if val is not None:
                        idx = widget.findData(val)
                        if idx >= 0:
                            widget.setCurrentIndex(idx)
                        else:
                            idx_str = widget.findText(str(val))
                            if idx_str >= 0:
                                widget.setCurrentIndex(idx_str)
                            else:
                                widget.setEditText(str(val))
                    else:
                        widget.setCurrentIndex(-1)
                        widget.setEditText("")
                elif isinstance(widget, QtWidgets.QCheckBox):
                    widget.setChecked(bool(val))
                elif isinstance(widget, QtWidgets.QPlainTextEdit):
                    widget.setPlainText(str(val or ""))
                elif isinstance(widget, QtWidgets.QSpinBox):
                    widget.setValue(int(val) if val is not None and val != "" else 0)
                elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                    widget.setValue(float(val) if val is not None and val != "" else 0.0)
                elif isinstance(widget, QtWidgets.QLineEdit):
                    widget.setText(str(val or ""))
        finally:
            self._loading = False

    def get_data(self) -> dict[str, Any]:
        """Collect form input data into a record dict."""
        data = {}
        for field in self.schema:
            name = field["name"]
            field.get("type", "str")
            widget = self.widgets.get(name)
            if not widget:
                continue

            val: Any = None
            if isinstance(widget, QtWidgets.QComboBox):
                val = widget.currentData()
                if val is None:
                    val = widget.currentText().strip() or None
            elif isinstance(widget, QtWidgets.QCheckBox):
                val = 1 if widget.isChecked() else 0
            elif isinstance(widget, QtWidgets.QPlainTextEdit):
                val = widget.toPlainText().strip() or None
            elif isinstance(widget, QtWidgets.QSpinBox):
                val = widget.value()
            elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                val = widget.value()
            elif isinstance(widget, QtWidgets.QLineEdit):
                val = widget.text().strip() or None

            if name == "laser_wavelengths":
                import json

                try:
                    val = json.loads(val) if val else []
                except Exception:
                    val = []
            elif name == "detector_channels":
                import json

                try:
                    val = json.loads(val) if val else {}
                except Exception:
                    val = {}

            data[name] = val
        return data
