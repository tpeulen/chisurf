"""An MLE fit-model chooser plus an auto-generated parameter form.

The burst-MLE and imaging-MLE fit-parameter panels were hand-authored: a fixed
pool of spin boxes wired to ``[tau, gamma, r0, rho]`` with the model implicitly
fit23. tttrlib now publishes each lifetime estimator (fit23/24/25/26) in its
registry with a JSON-Schema for its optimisable parameters, and chisurf already
renders JSON Schema via
:func:`~chisurf.core.registry.tttrlib.entry_form_view_auto` and
:class:`~chisurf.gui.autoform.AutoForm`, so this form is generated rather than
authored — exactly as :class:`~chisurf.gui.widgets.burst_search_form.BurstSearchForm`
does for burst searches. Labels, ranges, units, defaults and the
``fixed_default`` flags all come from tttrlib; a fit model added there appears
here on upgrade with no change to this file.

Usage::

    widget = FitModelForm()
    widget.model            # -> "fit23"
    widget.parameters       # -> {"tau": 2.0, "gamma": 0.1, ...}
    widget.parametersChanged.connect(on_change)
"""

from __future__ import annotations

import typing

from qtpy import QtCore, QtWidgets

from chisurf.core.registry import tttrlib as tttrlib_registry
from chisurf.core.fluorescence.mle import registry as fit_registry
from chisurf.gui.autoform import AutoForm


class FitModelForm(QtWidgets.QWidget):
    """Estimator chooser plus an auto-generated parameter form.

    Parameters
    ----------
    model : str, optional
        Initially selected fit model. Defaults to the first available.
    values : mapping, optional
        Initial parameter values, overriding the registry defaults.
    parent : QWidget, optional
    combo : QComboBox, optional
        An existing combobox to drive instead of creating one — lets a host keep
        its own selector in its layout while this widget lays out only the
        summary and the parameter form. When omitted the widget builds its own
        chooser row.
    """

    #: Emitted when the fit model or any of its parameters changes.
    parametersChanged = QtCore.Signal()

    def __init__(
        self,
        model: str | None = None,
        values: typing.Mapping[str, typing.Any] | None = None,
        parent: QtWidgets.QWidget | None = None,
        combo: QtWidgets.QComboBox | None = None,
    ):
        super().__init__(parent)
        self._models = fit_registry.fit_models()
        self._view = None
        self._form: AutoForm | None = None
        self._initial_values = dict(values or {})

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.combo_model = combo if combo is not None else QtWidgets.QComboBox()
        self.combo_model.clear()
        for name, spec in self._models.items():
            # The name is carried as item data so the visible label can change
            # without breaking stored settings.
            self.combo_model.addItem(spec.get("label", name), name)
            index = self.combo_model.count() - 1
            self.combo_model.setItemData(
                index, spec.get("summary", ""), QtCore.Qt.ToolTipRole
            )
        if combo is None:
            chooser = QtWidgets.QHBoxLayout()
            chooser.addWidget(QtWidgets.QLabel("Fit model"))
            chooser.addWidget(self.combo_model, 1)
            layout.addLayout(chooser)

        self.label_summary = QtWidgets.QLabel()
        self.label_summary.setWordWrap(True)
        self.label_summary.setEnabled(False)
        layout.addWidget(self.label_summary)

        self.container = QtWidgets.QVBoxLayout()
        layout.addLayout(self.container)
        layout.addStretch(1)

        if not self._models:
            self.combo_model.setEnabled(False)
            self.label_summary.setText(
                "The installed tttrlib does not publish a fit-model registry; "
                "upgrade tttrlib to select fit models here."
            )
        else:
            if model in self._models:
                self.combo_model.setCurrentIndex(self.combo_model.findData(model))
            self._rebuild()

        self.combo_model.currentIndexChanged.connect(self._on_model_changed)

    # -- state ----------------------------------------------------------------
    @property
    def model(self) -> str:
        """Name of the selected fit model."""
        return self.combo_model.currentData() or ""

    @property
    def parameters(self) -> dict[str, typing.Any]:
        """Current parameter values for the selected model."""
        if self._view is None:
            return {}
        return self._view.params()

    def set_state(
        self,
        model: str,
        parameters: typing.Mapping[str, typing.Any] | None = None,
    ) -> None:
        """Select ``model`` and load ``parameters`` into the form."""
        index = self.combo_model.findData(model)
        if index < 0:
            raise ValueError(
                f"unknown fit model {model!r}; available: {sorted(self._models)}"
            )
        self._initial_values = dict(parameters or {})
        blocked = self.combo_model.blockSignals(True)
        self.combo_model.setCurrentIndex(index)
        self.combo_model.blockSignals(blocked)
        self._rebuild()

    # -- internals ------------------------------------------------------------
    def _on_model_changed(self, _index: int) -> None:
        # Parameters are per model, so a switch starts from that model's defaults
        # rather than carrying over values that may not even apply.
        self._initial_values = {}
        self._rebuild()
        self.parametersChanged.emit()

    def _on_change(self) -> None:
        self.parametersChanged.emit()

    def _rebuild(self) -> None:
        spec = self._models.get(self.model)
        if spec is None:
            return
        self.label_summary.setText(spec.get("summary", ""))
        self.label_summary.setToolTip(spec.get("description", ""))

        self._view = tttrlib_registry.entry_form_view_auto(
            tttrlib_registry.FIT_MODEL,
            self.model,
            values=self._initial_values or None,
            on_change=self._on_change,
        )
        form = AutoForm(self._view)
        while self.container.count():
            item = self.container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.container.addWidget(form)
        self._form = form
