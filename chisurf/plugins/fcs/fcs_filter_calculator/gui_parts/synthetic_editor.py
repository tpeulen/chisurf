"""AutoForm view-model for editing a synthetic lifetime spectrum."""

from __future__ import annotations

import pathlib
from collections.abc import Callable

import numpy as np

from chisurf.core.fluorescence.decay import validate_lifetime_spectrum


_VIEW = pathlib.Path(__file__).with_name("synthetic_editor.view.json")


class SyntheticSpectrumViewModel:
    """Qt-free state edited by the shared AutoForm table infrastructure."""

    def __init__(self, read_fit: Callable | None = None) -> None:
        self.name = "component"
        self.bin_width = 0.05
        self.start_bin = 0
        self.irf_path = ""
        self.shot_noise = False
        self.photon_count = 100_000
        self.noise_seed = 0
        self.spectrum_rows = [
            {"amplitude": 1.0, "lifetime": 1.0},
            {"amplitude": 1.0, "lifetime": 4.0},
        ]
        self._fit_status = "Ideal decay (no fit model selected)."
        self.selected_fit = None
        self.selected_fit_label = None
        self._read_fit = read_fit
        self._changed: Callable[[], None] | None = None

    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW)

    def set_changed_callback(self, callback: Callable[[], None]) -> None:
        self._changed = callback

    def _notify(self) -> None:
        if self._changed is not None:
            self._changed()

    def update_spectrum_cell(self, row: int, key: str, value: str) -> None:
        if key not in {"amplitude", "lifetime"}:
            return
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            self._notify()
            return
        self.spectrum_rows[row][key] = numeric

    def add_spectrum_row(self) -> None:
        self.spectrum_rows.append({"amplitude": 1.0, "lifetime": 4.0})
        self._notify()

    def remove_spectrum_row(self) -> None:
        if len(self.spectrum_rows) > 1:
            self.spectrum_rows.pop()
            self._notify()

    def read_from_fit(self) -> None:
        if self._read_fit is None:
            return
        selected = self._read_fit()
        if selected is None:
            return
        spectrum, label, fit = selected
        spectrum = validate_lifetime_spectrum(spectrum)
        self.spectrum_rows = [
            {"amplitude": float(a), "lifetime": float(t)}
            for a, t in zip(spectrum[0::2], spectrum[1::2])
        ]
        self.name = str(label)
        self.selected_fit = fit
        self.selected_fit_label = str(label)
        self._fit_status = (
            f"Using {label}. Detector patterns will be computed through its ChiSurf model."
        )
        self._notify()

    def fit_status(self) -> str:
        return self._fit_status

    @property
    def lifetime_spectrum(self) -> np.ndarray:
        values = []
        for row in self.spectrum_rows:
            values.extend((row["amplitude"], row["lifetime"]))
        return validate_lifetime_spectrum(values)
