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

import pathlib

import numpy as np
from qtpy import QtWidgets

from chisurf.core.dataspec import load_view_spec
from chisurf.gui import chiplot as cp
from chisurf.gui import dialogs
from chisurf.gui.autoform import AutoForm, register_section
from chisurf.gui.widgets.tools.help_guide import attach_help_and_guide

_GUI_DIR = pathlib.Path(__file__).resolve().parent

_SPECIES_COLORS = ("#1f77b4", "#d62728")
_CROSS_COLOR = "#2ca02c"


class LifetimeFcsSimModel:
    """Settings + Qt-free compute for the lifetime-FCS simulator."""

    def __init__(self):
        self.tau1_ns = 1.0
        self.d1_um2_ms = 8.0
        self.tau2_ns = 4.0
        self.d2_um2_ms = 0.5
        self.exchange_rate_ms = 0.0
        self.n_photons = 400_000
        self.seed = 1

        self.reference_decays: list[np.ndarray] = []
        self.micro_time_resolution_ns = 0.0
        self.datasets: list[dict] = []
        self.condition_number = float("nan")

    def view_spec(self):
        """Return the declarative AutoForm view spec for the parameter form."""
        return load_view_spec(_GUI_DIR / "lfcs_sim.view.json")

    def run(self) -> list[dict]:
        """Simulate, build filters, and correlate; returns species-pair datasets.

        Each dataset dict carries ``x`` (lag, ms), ``y`` (G(τ)), ``name`` and the
        species indices — the same shape emitted by the FLCS correlator core.
        """
        from chisurf.core.fluorescence.fcs.filtered import (
            calc_ffcs_filters,
            filter_condition_number,
        )
        from chisurf.core.fluorescence.fcs.simulate import simulate_lifetime_fcs
        from chisurf.plugins.fcs.fcs_correlator.core import filtered_correlation_datasets

        sim = simulate_lifetime_fcs(
            lifetimes_ns=(float(self.tau1_ns), float(self.tau2_ns)),
            diffusion_um2_ms=(float(self.d1_um2_ms), float(self.d2_um2_ms)),
            exchange_rate_ms=float(self.exchange_rate_ms),
            n_photons=int(self.n_photons),
            seed=int(self.seed),
        )
        self.reference_decays = list(sim.reference_decays)
        self.micro_time_resolution_ns = sim.micro_time_resolution_ns
        self.condition_number = filter_condition_number(sim.total_decay, sim.reference_decays)
        filters, _, _ = calc_ffcs_filters(sim.total_decay, sim.reference_decays)
        labels = [f"τ={self.tau1_ns:g} ns", f"τ={self.tau2_ns:g} ns"]
        self.datasets = filtered_correlation_datasets(
            sim.macro_times, sim.micro_times, filters, sim.macro_time_resolution_s,
            n_bins=8, n_casc=25, labels=labels,
        )
        return self.datasets


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
        attach_help_and_guide(
            self, toolbar, title="Lifetime-FCS simulator — help", model=self._model
        )
        outer.addWidget(toolbar)

        content = QtWidgets.QWidget(self)
        outer.addWidget(content, 1)
        layout = QtWidgets.QHBoxLayout(content)
        layout.setContentsMargins(6, 6, 6, 6)

        self._form = AutoForm(self._model, parent=self)
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
                x[good], y[good], name=d["name"],
                pen=color, width=width,
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
        n = len(self._model.datasets)
        cond = self._model.condition_number
        self._status.setText(
            f"{n} species correlation(s); filter condition number {cond:.1f}."
            if n else "Simulation produced no curves."
        )
