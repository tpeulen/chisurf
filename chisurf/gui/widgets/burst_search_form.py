"""A burst-search parameter form generated from tttrlib's algorithm registry.

The burst-search parameters in the photon-filter wizard are a fixed set of
Qt Designer spinboxes that get re-labelled, re-ranged and re-tooltipped per
algorithm at runtime, with the algorithm-to-widget mapping held implicitly in
widget names. Adding an algorithm means editing the .ui file, the relabelling
code, a settings dataclass and the marshalling code.

This widget takes the other route: tttrlib publishes each burst search's
parameters as a JSON Schema through its registry, and chisurf already renders
JSON Schema via :func:`~chisurf.core.registry.tttrlib.entry_form_view_auto` and
:class:`~chisurf.gui.autoform.AutoForm`, so the form is generated rather than
authored. Labels, ranges, units, tooltips and defaults all come from tttrlib, and
a burst search added there appears here on upgrade with no change to this file.

Because it goes through :func:`entry_form_view_auto`, a composite search (the
``coincident`` search runs whichever search you name inside each detector group)
renders its delegated parameters as a real nested panel, and a search's
parameters are split into foldable groups — both driven by the schema, neither
authored here. This is the single "pick a burst search, edit its parameters"
widget; embed it wherever that is needed rather than rebuilding the pair.

Usage::

    widget = BurstSearchForm()
    widget.algorithm          # -> "maxtree"
    widget.parameters         # -> {"L": 20, "m": 10, ...}
    widget.parametersChanged.connect(on_change)
"""

from __future__ import annotations

import typing

from qtpy import QtCore, QtWidgets

from chisurf.core.fluorescence.burst import tttrlib_search
from chisurf.core.registry import tttrlib as tttrlib_registry
from chisurf.gui.autoform import AutoForm


class BurstSearchForm(QtWidgets.QWidget):
    """Algorithm chooser plus an auto-generated parameter form.

    Parameters
    ----------
    algorithm : str, optional
        Initially selected algorithm. Defaults to the first available.
    values : mapping, optional
        Initial parameter values, overriding the registry defaults.
    parent : QWidget, optional
    combo : QComboBox, optional
        An existing combobox to drive instead of creating one. Passing the host's
        own selector (as the photon-filter wizard does) is what lets this widget
        be the single burst-search picker while the selector keeps its place in
        the host's layout; the widget then lays out only the summary and the
        parameter form. When omitted, the widget builds and shows its own chooser
        row.
    """

    #: Emitted when the algorithm or any of its parameters changes.
    parametersChanged = QtCore.Signal()

    def __init__(
        self,
        algorithm: str | None = None,
        values: typing.Mapping[str, typing.Any] | None = None,
        parent: QtWidgets.QWidget | None = None,
        combo: QtWidgets.QComboBox | None = None,
    ):
        super().__init__(parent)
        self._algorithms = tttrlib_search.algorithms()
        self._view = None
        self._form: AutoForm | None = None
        self._initial_values = dict(values or {})
        # The selector value the current form was built for, so a composite
        # search whose inner algorithm changed can rebuild only its nested panel.
        self._selector: str | None = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Populate the selector — a host-supplied one keeps its place in the host
        # layout; otherwise build a chooser row inside this widget.
        self.combo_algorithm = combo if combo is not None else QtWidgets.QComboBox()
        self.combo_algorithm.clear()
        for name, spec in self._algorithms.items():
            # The name is carried as item data so the visible label can change
            # without breaking stored settings.
            self.combo_algorithm.addItem(spec.get("label", name), name)
            index = self.combo_algorithm.count() - 1
            self.combo_algorithm.setItemData(index, spec.get("summary", ""), QtCore.Qt.ToolTipRole)
        if combo is None:
            chooser = QtWidgets.QHBoxLayout()
            chooser.addWidget(QtWidgets.QLabel("Algorithm"))
            chooser.addWidget(self.combo_algorithm, 1)
            layout.addLayout(chooser)

        self.label_summary = QtWidgets.QLabel()
        self.label_summary.setWordWrap(True)
        self.label_summary.setEnabled(False)
        layout.addWidget(self.label_summary)

        self.container = QtWidgets.QVBoxLayout()
        layout.addLayout(self.container)
        layout.addStretch(1)

        if not self._algorithms:
            self.combo_algorithm.setEnabled(False)
            self.label_summary.setText(
                "The installed tttrlib does not publish a burst-search registry; "
                "upgrade tttrlib to use registry-driven burst searches."
            )
        else:
            if algorithm in self._algorithms:
                self.combo_algorithm.setCurrentIndex(self.combo_algorithm.findData(algorithm))
            self._rebuild()

        self.combo_algorithm.currentIndexChanged.connect(self._on_algorithm_changed)

    # -- state ----------------------------------------------------------------
    @property
    def algorithm(self) -> str:
        """Name of the selected burst search."""
        return self.combo_algorithm.currentData() or ""

    @property
    def parameters(self) -> dict[str, typing.Any]:
        """Current parameter values for the selected algorithm."""
        if self._view is None:
            return {}
        return self._view.params()

    def set_state(
        self,
        algorithm: str,
        parameters: typing.Mapping[str, typing.Any] | None = None,
    ) -> None:
        """Select ``algorithm`` and load ``parameters`` into the form."""
        index = self.combo_algorithm.findData(algorithm)
        if index < 0:
            raise ValueError(
                f"unknown burst search {algorithm!r}; available: {sorted(self._algorithms)}"
            )
        self._initial_values = dict(parameters or {})
        blocked = self.combo_algorithm.blockSignals(True)
        self.combo_algorithm.setCurrentIndex(index)
        self.combo_algorithm.blockSignals(blocked)
        self._rebuild()

    # -- internals ------------------------------------------------------------
    def _on_algorithm_changed(self, _index: int) -> None:
        # Parameters are per algorithm, so a switch starts from that algorithm's
        # defaults rather than carrying over values that may not even apply.
        self._initial_values = {}
        self._rebuild()
        self.parametersChanged.emit()

    def _on_change(self) -> None:
        self.parametersChanged.emit()
        # A composite search (the coincident search runs whichever search you
        # name inside each detector group) builds its nested panel from the inner
        # algorithm its selector currently names; changing that selector makes the
        # panel stale. The rebuild is deferred because this runs from inside a
        # widget's own signal, and tearing that widget down synchronously is not
        # safe.
        view = self._view
        should = getattr(view, "should_rebuild", None)
        if should is not None and should(self._selector):
            QtCore.QTimer.singleShot(0, self._rebuild_nested)

    def _rebuild_nested(self) -> None:
        # Carry the values already entered across the rebuild, so switching the
        # inner search does not discard the outer parameters (the detector
        # grouping above all, which is tedious to retype and cannot be defaulted).
        view = self._view
        if view is None or not hasattr(view, "should_rebuild"):
            return
        self._initial_values = view.params()
        self._rebuild()

    def _rebuild(self) -> None:
        spec = self._algorithms.get(self.algorithm)
        if spec is None:
            return
        self.label_summary.setText(spec.get("summary", ""))
        self.label_summary.setToolTip(spec.get("description", ""))

        # entry_form_view_auto renders any registry entry: a composite entry gets
        # its delegated parameters as a nested panel rather than a JSON text box,
        # and a flat entry's parameters are split into foldable groups. Both
        # expose the same params()/view_spec() surface AutoForm consumes.
        self._view = tttrlib_registry.entry_form_view_auto(
            tttrlib_registry.BURST_SEARCH,
            self.algorithm,
            values=self._initial_values or None,
            on_change=self._on_change,
        )
        self._selector = getattr(self._view, "selector_value", None)
        form = AutoForm(self._view)
        while self.container.count():
            item = self.container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.container.addWidget(form)
        self._form = form
