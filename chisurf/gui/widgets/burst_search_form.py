"""A burst-search parameter form generated from tttrlib's algorithm registry.

The burst-search parameters in the photon-filter wizard are a fixed set of
Qt Designer spinboxes that get re-labelled, re-ranged and re-tooltipped per
algorithm at runtime, with the algorithm-to-widget mapping held implicitly in
widget names. Adding an algorithm means editing the .ui file, the relabelling
code, a settings dataclass and the marshalling code.

This widget takes the other route: tttrlib publishes each burst search's
parameters as a JSON Schema through ``TTTR.burst_search_algorithms()``, chisurf
already renders JSON Schema via :class:`~chisurf.core.dataspec.rpc.RpcMethodView`
and :class:`~chisurf.gui.autoform.AutoForm`, so the form is generated rather than
authored. Labels, ranges, units, tooltips and defaults all come from tttrlib, and
a burst search added there appears here on upgrade with no change to this file.

Usage::

    widget = BurstSearchForm()
    widget.algorithm          # -> "maxtree"
    widget.parameters         # -> {"L": 20, "m": 10, ...}
    widget.parametersChanged.connect(on_change)
"""

from __future__ import annotations

import typing

from qtpy import QtWidgets, QtCore

from chisurf.core.dataspec.rpc import RpcMethodView
from chisurf.core.fluorescence.burst import tttrlib_search
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
    """

    #: Emitted when the algorithm or any of its parameters changes.
    parametersChanged = QtCore.Signal()

    def __init__(
        self,
        algorithm: typing.Optional[str] = None,
        values: typing.Optional[typing.Mapping[str, typing.Any]] = None,
        parent: typing.Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)
        self._algorithms = tttrlib_search.algorithms()
        self._view: typing.Optional[RpcMethodView] = None
        self._form: typing.Optional[AutoForm] = None
        self._initial_values = dict(values or {})

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        chooser = QtWidgets.QHBoxLayout()
        chooser.addWidget(QtWidgets.QLabel("Algorithm"))
        self.combo_algorithm = QtWidgets.QComboBox()
        for name, spec in self._algorithms.items():
            # The name is carried as item data so the visible label can change
            # without breaking stored settings.
            self.combo_algorithm.addItem(spec.get("label", name), name)
            index = self.combo_algorithm.count() - 1
            self.combo_algorithm.setItemData(
                index, spec.get("summary", ""), QtCore.Qt.ToolTipRole
            )
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
                self.combo_algorithm.setCurrentIndex(
                    self.combo_algorithm.findData(algorithm)
                )
            self._rebuild()

        self.combo_algorithm.currentIndexChanged.connect(self._on_algorithm_changed)

    # -- state ----------------------------------------------------------------
    @property
    def algorithm(self) -> str:
        """Name of the selected burst search."""
        return self.combo_algorithm.currentData() or ""

    @property
    def parameters(self) -> typing.Dict[str, typing.Any]:
        """Current parameter values for the selected algorithm."""
        if self._view is None:
            return {}
        return self._view.params()

    def set_state(
        self,
        algorithm: str,
        parameters: typing.Optional[typing.Mapping[str, typing.Any]] = None,
    ) -> None:
        """Select ``algorithm`` and load ``parameters`` into the form."""
        index = self.combo_algorithm.findData(algorithm)
        if index < 0:
            raise ValueError(
                f"unknown burst search {algorithm!r}; "
                f"available: {sorted(self._algorithms)}"
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

    def _rebuild(self) -> None:
        spec = self._algorithms.get(self.algorithm)
        if spec is None:
            return
        self.label_summary.setText(spec.get("summary", ""))
        self.label_summary.setToolTip(spec.get("description", ""))

        self._view = RpcMethodView(
            spec,
            values=self._initial_values or None,
            on_change=self.parametersChanged.emit,
            title=spec.get("label", self.algorithm),
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
