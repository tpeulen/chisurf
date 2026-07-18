"""Qt-free AutoForm view-model for the synthetic decay generator."""

from __future__ import annotations

import pathlib
from typing import Any

from ..core.algorithms import compute_decay

_VIEW = pathlib.Path(__file__).with_name("synthetic_decay.view.json")


class SyntheticDecayViewModel:
    """Backing model for the AutoForm view (``synthetic_decay.view.json``).

    Holds an editable lifetime spectrum (amplitude/lifetime rows) plus histogram,
    IRF and shot-noise options, and generates the decay through the shared core
    generator. The plot reads :meth:`decay_series`.
    """

    def __init__(self) -> None:
        self.n_bins = 256
        self.bin_width = 0.032
        self.start_bin = 0
        self.irf_path = ""
        self.shot_noise = False
        self.photon_count = 1_000_000.0
        self.seed = 1
        self.spectrum_rows: list[dict[str, float]] = [
            {"amp": 1.0, "tau": 1.2},
            {"amp": 1.0, "tau": 4.0},
        ]
        self.selected_row = -1
        self.status = "Edit the lifetime spectrum and press Generate."
        self._x: list[float] = []
        self._y: list[float] = []
        self._form: Any = None

    # ── view / table binding ─────────────────────────────────────────
    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW)

    def spectrum_source(self) -> list[dict[str, float]]:
        return [dict(row) for row in self.spectrum_rows]

    def update_spectrum(self, row_index: int, column_key: str, value: Any) -> None:
        try:
            self.spectrum_rows[int(row_index)][column_key] = float(value)
        except (ValueError, IndexError, TypeError):
            pass

    def add_row(self) -> None:
        self.spectrum_rows.append({"amp": 1.0, "tau": 2.0})
        self._refresh_fields()

    def remove_row(self) -> None:
        idx = int(self.selected_row)
        if 0 <= idx < len(self.spectrum_rows) and len(self.spectrum_rows) > 1:
            self.spectrum_rows.pop(idx)
            self._refresh_fields()

    # ── compute ──────────────────────────────────────────────────────
    def generate(self) -> None:
        try:
            amps = [float(r.get("amp", 1.0)) for r in self.spectrum_rows]
            taus = [float(r.get("tau", 1.0)) for r in self.spectrum_rows]
            noisy = bool(self.shot_noise)
            result = compute_decay(
                n_bins=int(self.n_bins),
                lifetimes=taus,
                amplitudes=amps,
                bin_width=float(self.bin_width),
                start_bin=int(self.start_bin),
                irf=(self.irf_path or None),
                normalize=not noisy,
                photon_count=(float(self.photon_count) if noisy else None),
                seed=(int(self.seed) if noisy else None),
            )
            self._x = result["x"]
            self._y = result["y"]
            self.status = f"Generated {len(self._y)} bins ({len(self.spectrum_rows)} components)."
        except Exception as exc:
            self._x, self._y = [], []
            self.status = f"Error: {exc}"
        self._refresh_plots()

    def status_text(self) -> str:
        return str(self.status)

    def decay_series(self) -> list[dict]:
        if not self._y:
            return []
        return [{"x": self._x, "y": self._y, "name": "decay", "color": "#22d3ee"}]

    def save(self) -> None:
        if not self._y:
            self.status = "Nothing to save — press Generate first."
            self._refresh_fields()
            return
        from qtpy import QtWidgets

        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            None, "Save decay", "synthetic_decay.csv",
            "CSV (*.csv);;Text (*.txt);;NumPy (*.npy);;JSON (*.json)",
        )
        if not path:
            return
        import json

        import numpy as np

        low = path.lower()
        if low.endswith(".npy"):
            np.save(path, np.asarray(self._y, dtype=float))
        elif low.endswith(".json"):
            with open(path, "w") as fh:
                json.dump({"x": self._x, "y": self._y}, fh, indent=2)
        else:
            np.savetxt(
                path, np.column_stack([self._x, self._y]), header="time_ns\tcounts"
            )
        self.status = f"Saved {len(self._y)} bins to {pathlib.Path(path).name}."
        self._refresh_fields()

    # ── refresh helpers ──────────────────────────────────────────────
    def _refresh_fields(self) -> None:
        form = self._form
        if form is not None:
            try:
                form.sync_fields()
            except Exception:
                pass

    def _refresh_plots(self) -> None:
        form = self._form
        if form is not None:
            try:
                form.refresh_plots()
            except Exception:
                pass
            self._refresh_fields()
