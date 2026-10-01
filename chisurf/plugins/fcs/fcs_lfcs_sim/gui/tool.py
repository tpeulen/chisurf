"""Lifetime-FCS (FLCS) simulator panel — AutoForm tool for the FCS toolbox.

Simulates diffusing species with distinct fluorescence lifetimes and optional
interconversion (``tttrlib.SimEngine``), builds the lifetime filters, and shows the
species-filtered auto-/cross-correlations. It is the interactive, GUI-side companion
to :mod:`chisurf.core.fluorescence.fcs.simulate` and the ``examples/lifetime_fcs.py``
worked example.

The parameter form is rendered declaratively from ``lfcs_sim.view.json`` via
:class:`chisurf.gui.autoform.AutoForm`; the heavy lifting is Qt-free core code, so
the same simulation runs headlessly in tests.
"""

from __future__ import annotations

import numpy as np
from qtpy import QtWidgets

from chisurf.gui import chiplot as cp
from chisurf.gui import dialogs
from chisurf.gui.autoform import AutoForm, register_section
from chisurf.gui.widgets.tools.help_guide import (
    attach_help_and_guide,
    promote_to_toolbar,
)
from chisurf.plugins.fcs.fcs_lfcs_sim.model import LifetimeFcsSimModel  # noqa: F401  (re-exported)

_SPECIES_COLORS = ("#1f77b4", "#d62728")
_CROSS_COLOR = "#2ca02c"


class LifetimeFcsSimWidget(QtWidgets.QWidget):
    """Docked AutoForm panel: simulate + plot lifetime-FCS species correlations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = LifetimeFcsSimModel()

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # A hairline strip for the ``?`` and **Guide** pair. This tool is a plain
        # QWidget with no toolbar of its own, so it gets one rather than the
        # buttons landing beside the plot in the content row.
        toolbar = QtWidgets.QToolBar(self)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setStyleSheet("QToolBar { border: none; padding: 0px; spacing: 2px; }")
        outer.addWidget(toolbar)

        content = QtWidgets.QWidget(self)
        outer.addWidget(content, 1)
        layout = QtWidgets.QHBoxLayout(content)
        layout.setContentsMargins(6, 6, 6, 6)

        self._form = AutoForm(self._model, parent=self)
        # The single thing this tool does goes on the strip; the status line it
        # sat beside stays in the form, where the result belongs.
        promote_to_toolbar(self._form, toolbar, ("simulate",))
        attach_help_and_guide(
            self, toolbar, title="Lifetime-FCS simulator — help", model=self._model
        )
        form_holder = QtWidgets.QWidget()
        fh = QtWidgets.QVBoxLayout(form_holder)
        fh.setContentsMargins(0, 0, 0, 0)
        fh.addWidget(self._form)
        fh.addStretch(1)
        form_holder.setMaximumWidth(320)
        layout.addWidget(form_holder)

        self._plot = self._make_plot()
        layout.addWidget(self._plot, 1)

    def _make_plot(self):
        plot = cp.Plot()
        plot.set_log(x=True)
        # Keep the raw "ms" unit rather than an auto SI prefix. This used to
        # reach through ``.native`` to pyqtgraph's axis; chiplot has had the API
        # for it, so the escape hatch was never a gap — only legacy.
        plot.set_si_prefix(x=False)
        plot.set_labels(bottom="lag time (ms)", left="G(τ)")
        plot.legend()
        plot.grid(x=True, y=True, alpha=0.3)
        return plot

    def simulate(self) -> None:
        """Run the simulation and refresh the correlation plot (blocking)."""
        window = self.window() or self
        try:
            window.setCursor(window.cursor())
            datasets = self._model.run()
        except Exception as exc:  # noqa: BLE001
            dialogs.error(self, "Simulation failed", str(exc))
            return
        self._refresh_plot(datasets)

    def _refresh_plot(self, datasets: list[dict]) -> None:
        self._plot.clear()
        self._plot.legend()  # idempotent: resets the legend for the redraw
        for d in datasets:
            a, b = d["species_a"], d["species_b"]
            if a == b:
                color = _SPECIES_COLORS[a % len(_SPECIES_COLORS)]
                width = 2
            else:
                color = _CROSS_COLOR
                width = 2
            x = np.asarray(d["x"], dtype=float)
            y = np.asarray(d["y"], dtype=float)
            good = x > 0
            self._plot.line(
                x[good],
                y[good],
                name=d["name"],
                pen=color,
                width=width,
            )


@register_section("lfcs_sim_controls")
class _LfcsSimControls(QtWidgets.QWidget):
    """The 'Simulate & Correlate' button + status line (AutoForm custom section)."""

    def __init__(self, model, target: str = "", **options):
        super().__init__()
        self._model = model
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.btn = QtWidgets.QPushButton("Simulate + Correlate")
        # Tagged like an AutoForm button_row entry so the tool can promote it to
        # its toolbar: this is the one thing the tool does, and it should not be
        # the last control in a settings column.
        self.btn._autoform_action = "simulate"
        self.btn.setStyleSheet(
            "QPushButton { background-color: #1f7a1f; color: white; "
            "border: 1px solid #166016; border-radius: 4px; "
            "padding: 4px 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #249124; }"
        )
        self.btn.clicked.connect(self._on_click)
        layout.addWidget(self.btn)

        self._status = QtWidgets.QLabel("Set parameters and simulate.")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

    def _find_widget(self) -> LifetimeFcsSimWidget | None:
        w = self.parent()
        while w is not None and not isinstance(w, LifetimeFcsSimWidget):
            w = w.parent()
        return w

    def _on_click(self) -> None:
        widget = self._find_widget()
        self._status.setText("Simulating…")
        QtWidgets.QApplication.processEvents()
        if widget is not None:
            widget.simulate()
        else:  # headless fallback: still compute
            self._model.run()
        self._status.setText(self._model.status())
