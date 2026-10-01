"""Settings and Qt-free compute of the lifetime-FCS simulator, shared by the Qt and emtk tools.

The form over it is ``gui/lfcs_sim.view.json``.
"""

from __future__ import annotations

import pathlib

import numpy as np

_GUI_DIR = pathlib.Path(__file__).resolve().parent / "gui"


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
        from chisurf.core.dataspec import load_view_spec

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
            sim.macro_times,
            sim.micro_times,
            filters,
            sim.macro_time_resolution_s,
            n_bins=8,
            n_casc=25,
            labels=labels,
        )
        return self.datasets

    def status(self) -> str:
        """The status line after a run, in the Qt tool's words."""
        n = len(self.datasets)
        return (f"{n} species correlation(s); filter condition number {self.condition_number:.1f}."
                if n else "Simulation produced no curves.")
