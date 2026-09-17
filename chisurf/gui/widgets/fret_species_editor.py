"""Editor for a coupled smFRET labeling-state decay component.

Unlike the plain synthetic-decay editor (one decay shared across detectors), a
FRET species produces *different, coupled* green/red/yellow decays — the red
channel is the FRET-sensitized acceptor shaped by the donor decay, mixed with
donor leakage and direct excitation via the calibration crosstalk factors. Built
on :mod:`chisurf.core.fluorescence.fret.species_decay`.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable

import numpy as np

_VIEW = pathlib.Path(__file__).with_name("fret_species_editor.view.json")
_COLORS = {"green": "#4ade80", "red": "#fb4d4d", "yellow": "#facc15"}


class FretSpeciesEditorModel:
    """AutoForm view-model for one FRET labeling-state component."""

    def __init__(self, *, n_bins: int = 256, bin_width: float = 0.05) -> None:
        self.name = "FRET species"
        self.state = "da"  # d_only | da | a_only
        self.n_bins = int(n_bins)
        self.bin_width = float(bin_width)
        self.donor_rows: list[dict[str, float]] = [{"amplitude": 1.0, "lifetime": 4.0}]
        self.acceptor_rows: list[dict[str, float]] = [{"amplitude": 1.0, "lifetime": 2.0}]
        # FRET input
        self.fret_mode = "efficiency"  # efficiency | distance
        self.transfer_efficiency = 0.5
        # Distance distribution (Gaussian components), reusing the fit inputs.
        self.distance_rows: list[dict[str, float]] = [
            {"mean": 50.0, "sigma": 6.0, "amplitude": 1.0}
        ]
        self.forster_radius = 52.0
        self.kappa2 = 2.0 / 3.0
        self.x_donly = 0.0
        # Crosstalk (Hellenkamp) — seeded from the setup calibration, editable.
        self.alpha = 0.0
        self.beta = 1.0
        self.gamma = 1.0
        self.delta = 0.0
        # Anisotropy — a spectrum r(t) = Σ b_i·exp(-t/ρ_i) + r∞ per chromophore.
        self.donor_aniso_rows: list[dict[str, float]] = [{"amplitude": 0.38, "rho": 1.0}]
        self.acceptor_aniso_rows: list[dict[str, float]] = [{"amplitude": 0.38, "rho": 1.0}]
        self.r_inf = 0.0
        self.g_factor = 1.0
        self.polarized = False
        # Convolution. The per-channel IRF itself comes from the per-detector
        # Detector settings (normalized to unity) at compute time; these set the
        # laser repetition period (periodic convolution) and a sub-bin colour shift.
        self.period_ns = 0.0
        self.time_shift_ns = 0.0
        self._changed: Callable[[], None] | None = None
        self._seed_calibration: Callable[[], dict] | None = None

    # -- AutoForm plumbing --------------------------------------------
    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW)

    def set_changed_callback(self, callback: Callable[[], None]) -> None:
        self._changed = callback

    def set_calibration_seed(self, provider: Callable[[], dict] | None) -> None:
        self._seed_calibration = provider

    def field_changed(self, _value=None) -> None:
        if self._changed is not None:
            self._changed()

    # -- spectrum tables ----------------------------------------------
    def _update(self, rows, row, key, value):
        if key in {"amplitude", "lifetime"}:
            try:
                rows[int(row)][key] = float(value)
            except (TypeError, ValueError, IndexError):
                pass
        self.field_changed()

    def update_donor_cell(self, row, key, value):
        self._update(self.donor_rows, row, key, value)

    def update_acceptor_cell(self, row, key, value):
        self._update(self.acceptor_rows, row, key, value)

    def update_distance_cell(self, row, key, value):
        if key in {"mean", "sigma", "amplitude"}:
            try:
                self.distance_rows[int(row)][key] = float(value)
            except (TypeError, ValueError, IndexError):
                pass
        self.field_changed()

    def add_distance_row(self):
        self.distance_rows.append({"mean": 60.0, "sigma": 6.0, "amplitude": 1.0})
        self.field_changed()

    def remove_distance_row(self):
        if len(self.distance_rows) > 1:
            self.distance_rows.pop()
            self.field_changed()

    def _update_aniso(self, rows, row, key, value):
        if key in {"amplitude", "rho"}:
            try:
                rows[int(row)][key] = float(value)
            except (TypeError, ValueError, IndexError):
                pass
        self.field_changed()

    def update_donor_aniso_cell(self, row, key, value):
        self._update_aniso(self.donor_aniso_rows, row, key, value)

    def update_acceptor_aniso_cell(self, row, key, value):
        self._update_aniso(self.acceptor_aniso_rows, row, key, value)

    def add_donor_aniso_row(self):
        self.donor_aniso_rows.append({"amplitude": 0.1, "rho": 10.0})
        self.field_changed()

    def remove_donor_aniso_row(self):
        if len(self.donor_aniso_rows) > 1:
            self.donor_aniso_rows.pop()
            self.field_changed()

    def add_acceptor_aniso_row(self):
        self.acceptor_aniso_rows.append({"amplitude": 0.1, "rho": 10.0})
        self.field_changed()

    def remove_acceptor_aniso_row(self):
        if len(self.acceptor_aniso_rows) > 1:
            self.acceptor_aniso_rows.pop()
            self.field_changed()

    def add_donor_row(self):
        self.donor_rows.append({"amplitude": 1.0, "lifetime": 4.0})
        self.field_changed()

    def remove_donor_row(self):
        if len(self.donor_rows) > 1:
            self.donor_rows.pop()
            self.field_changed()

    def add_acceptor_row(self):
        self.acceptor_rows.append({"amplitude": 1.0, "lifetime": 2.0})
        self.field_changed()

    def remove_acceptor_row(self):
        if len(self.acceptor_rows) > 1:
            self.acceptor_rows.pop()
            self.field_changed()

    def seed_from_calibration(self):
        """Fill α/β/γ/δ (and R0) from the selected detector-setup calibration."""
        if self._seed_calibration is None:
            return
        seed = self._seed_calibration() or {}
        for key in ("alpha", "beta", "gamma", "delta", "forster_radius"):
            if key in seed:
                setattr(self, key, float(seed[key]))
        self.field_changed()

    # -- generation / preview -----------------------------------------
    def _spectrum(self, rows) -> list[float]:
        values: list[float] = []
        for r in rows:
            values.extend((float(r["amplitude"]), float(r["lifetime"])))
        return values

    def _species(self):
        from chisurf.core.fluorescence.fret.species_decay import fret_species_from_dict

        return fret_species_from_dict(self.component())

    def _patterns(self):
        from chisurf.core.fluorescence.fret.species_decay import fret_species_patterns

        # Ideal (no-IRF) preview — the per-detector IRF is applied at compute time.
        return fret_species_patterns(
            int(self.n_bins),
            self._species(),
            dt=float(self.bin_width),
            irf=None,
            polarized=bool(self.polarized),
            normalize=True,
        )

    def channel_series(self) -> list[dict]:
        try:
            patterns = self._patterns()
        except Exception:
            return []
        x = (np.arange(int(self.n_bins)) * float(self.bin_width)).tolist()
        series = []
        for key, decay in patterns.items():
            base = key.split("_")[0]
            color = _COLORS.get(base, "#22d3ee")
            series.append(
                {"x": x, "y": np.maximum(decay, 1e-12).tolist(), "name": key, "color": color}
            )
        return series

    # -- output -------------------------------------------------------
    def component(self) -> dict:
        return {
            "type": "synthetic",
            "model": "fret_species",
            "name": (self.name or "FRET species").strip(),
            "state": self.state,
            "donor_spectrum": self._spectrum(self.donor_rows),
            "acceptor_spectrum": self._spectrum(self.acceptor_rows),
            "fret_mode": self.fret_mode,
            "transfer_efficiency": float(self.transfer_efficiency),
            "distance_rows": [dict(r) for r in self.distance_rows],
            "forster_radius": float(self.forster_radius),
            "kappa2": float(self.kappa2),
            "x_donly": float(self.x_donly),
            "crosstalk": {
                "alpha": float(self.alpha),
                "beta": float(self.beta),
                "gamma": float(self.gamma),
                "delta": float(self.delta),
            },
            "anisotropy": {
                "r_inf": float(self.r_inf),
                "g_factor": float(self.g_factor),
                "donor_spectrum": [dict(r) for r in self.donor_aniso_rows],
                "acceptor_spectrum": [dict(r) for r in self.acceptor_aniso_rows],
            },
            "bin_width": float(self.bin_width),
            "polarized": bool(self.polarized),
            "period_ns": float(self.period_ns),
            "time_shift_ns": float(self.time_shift_ns),
        }

    def load_component(self, component: dict) -> None:
        self.name = str(component.get("name", self.name))
        self.state = str(component.get("state", self.state))
        self.donor_rows = self._rows_from(component.get("donor_spectrum"), self.donor_rows)
        self.acceptor_rows = self._rows_from(component.get("acceptor_spectrum"), self.acceptor_rows)
        self.fret_mode = str(component.get("fret_mode", self.fret_mode))
        self.transfer_efficiency = float(
            component.get("transfer_efficiency", self.transfer_efficiency)
        )
        rows = component.get("distance_rows")
        if rows:
            self.distance_rows = [dict(r) for r in rows]
        elif "distance" in component:
            self.distance_rows = [
                {"mean": float(component["distance"]), "sigma": 0.0, "amplitude": 1.0}
            ]
        self.forster_radius = float(component.get("forster_radius", self.forster_radius))
        self.kappa2 = float(component.get("kappa2", self.kappa2))
        self.x_donly = float(component.get("x_donly", self.x_donly))
        ct = component.get("crosstalk", {}) or {}
        self.alpha, self.beta = float(ct.get("alpha", self.alpha)), float(ct.get("beta", self.beta))
        self.gamma, self.delta = (
            float(ct.get("gamma", self.gamma)),
            float(ct.get("delta", self.delta)),
        )
        an = component.get("anisotropy", {}) or {}
        self.r_inf = float(an.get("r_inf", self.r_inf))
        self.g_factor = float(an.get("g_factor", self.g_factor))
        if an.get("donor_spectrum"):
            self.donor_aniso_rows = [dict(r) for r in an["donor_spectrum"]]
        elif "donor_r0" in an:
            self.donor_aniso_rows = [
                {"amplitude": float(an["donor_r0"]), "rho": float(an.get("donor_rho", 1.0))}
            ]
        if an.get("acceptor_spectrum"):
            self.acceptor_aniso_rows = [dict(r) for r in an["acceptor_spectrum"]]
        elif "acceptor_r0" in an:
            self.acceptor_aniso_rows = [
                {"amplitude": float(an["acceptor_r0"]), "rho": float(an.get("acceptor_rho", 1.0))}
            ]
        self.bin_width = float(component.get("bin_width", self.bin_width))
        self.polarized = bool(component.get("polarized", self.polarized))
        self.period_ns = float(component.get("period_ns", self.period_ns))
        self.time_shift_ns = float(component.get("time_shift_ns", self.time_shift_ns))

    @staticmethod
    def _rows_from(spectrum, default):
        if not spectrum:
            return default
        values = list(spectrum)
        return [
            {"amplitude": float(a), "lifetime": float(t)}
            for a, t in zip(values[0::2], values[1::2])
        ]
