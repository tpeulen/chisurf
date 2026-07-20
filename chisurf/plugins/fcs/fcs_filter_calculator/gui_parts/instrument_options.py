"""AutoForm view-model for the Filter Calculator's instrument / calibration
parameters (α, β, γ, δ, G-factor, l1, l2, Förster radius, laser period).

The values are pre-populated from the selected detector setup and consumed by the
auto-fit (periodic convolution, polarization-aware fitting) and the FRET-species
decay computation.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable


_VIEW = pathlib.Path(__file__).with_name("instrument_options.view.json")

#: Field name → default value. These are the instrument constants the plugin uses.
DEFAULTS: dict[str, float | bool] = {
    "alpha": 0.0,       # spectral crosstalk / donor leakage into the acceptor channel
    "beta": 0.0,        # direct acceptor excitation (relative to donor)
    "gamma": 1.0,       # detection / quantum-yield correction
    "delta": 0.0,       # acceptor direct-excitation probability
    "g_factor": 1.0,    # polarization detection ratio (parallel / perpendicular)
    "l1": 0.0,          # polarization mixing factor 1
    "l2": 0.0,          # polarization mixing factor 2
    "forster_radius": 52.0,  # Förster radius R0 (Å)
    "period_ns": 0.0,   # laser period (ns); 0 ⇒ use the full micro-time window
    "periodic": False,  # enable periodic (wrap-around) convolution
}


class InstrumentViewModel:
    """Plain scalar instrument parameters, edited through an AutoForm scalar table."""

    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        for key, value in DEFAULTS.items():
            setattr(self, key, value)
        self._on_change = on_change
        self._refresh: Callable[[], None] | None = None

    def set_refresh_callback(self, callback: Callable[[], None]) -> None:
        self._refresh = callback

    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW)

    def field_changed(self, _value=None) -> None:
        """Any instrument field changed → notify the host (recompute/prepopulate)."""
        if self._on_change is not None:
            self._on_change()

    def to_dict(self) -> dict:
        return {key: getattr(self, key, DEFAULTS[key]) for key in DEFAULTS}

    def update_from(self, values: dict) -> None:
        """Set known fields from a mapping (e.g. a setup's calibration), then refresh."""
        for key in DEFAULTS:
            if key in values and values[key] is not None:
                try:
                    setattr(self, key,
                            bool(values[key]) if key == "periodic" else float(values[key]))
                except (TypeError, ValueError):
                    pass
        if self._refresh is not None:
            self._refresh()
