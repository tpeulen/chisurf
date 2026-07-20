"""One shared synthetic-decay editor used across ChiSurf.

A single AutoForm view-model + view for defining a fluorescence decay from an
amplitude/lifetime spectrum (with optional IRF, Poisson shot noise, a loaded
measured pattern, and "Read from Fit"), plus a live preview. The FCS Filter
Calculator's synthetic-component dialog and the acquisition simulator's Decay
modal both embed this, so the two no longer diverge. All previews and outputs go
through the single canonical generator ``core.fluorescence.decay.synthetic_decay``.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable
from typing import Any

import numpy as np

from chisurf.core.fluorescence.decay import validate_lifetime_spectrum

_VIEW = pathlib.Path(__file__).with_name("synthetic_decay_editor.view.json")


class SyntheticDecayEditorModel:
    """Qt-free AutoForm view-model for editing one synthetic decay component.

    Parameters
    ----------
    read_fit : callable, optional
        Zero-arg callable returning ``(spectrum, label, fit)`` or ``None`` — wired
        to the "Read from Fit…" action. When ``None`` the button is inert.
    n_bins, bin_width : int, float
        Preview/generation histogram size and bin width (ns).
    """

    def __init__(
        self,
        *,
        read_fit: Callable | None = None,
        n_bins: int = 256,
        bin_width: float = 0.05,
    ) -> None:
        self.name = "component"
        self.n_bins = int(n_bins)
        self.bin_width = float(bin_width)
        self.start_bin = 0
        self.irf_path = ""
        self.irf_fwhm_ns = 0.0
        self.irf_skew = 0.0
        self.irf_center_ns = 0.0
        self.period_ns = 0.0
        self.time_shift_ns = 0.0
        self.shot_noise = False
        self.photon_count = 100_000
        self.noise_seed = 0
        self.pattern_path = ""
        self.spectrum_rows: list[dict[str, float]] = [
            {"amplitude": 1.0, "lifetime": 1.0},
            {"amplitude": 1.0, "lifetime": 4.0},
        ]
        self.selected_fit = None
        self.selected_fit_label = None
        self._status = "Edit the lifetime spectrum (amplitude + lifetime)."
        self._read_fit = read_fit
        self._changed: Callable[[], None] | None = None

    # -- AutoForm plumbing --------------------------------------------
    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW)

    def set_changed_callback(self, callback: Callable[[], None]) -> None:
        self._changed = callback

    def field_changed(self, _value=None) -> None:
        """Value/toggle-field change hook.

        The AutoForm value/toggle sections that carry ``"call": "field_changed"``
        route here on edit; the framework refreshes the hosting form (preview,
        status) immediately afterwards, so this only needs to fan out to the
        consumer's changed-callback.
        """
        self._notify()

    def _notify(self) -> None:
        # The AutoForm value/toggle/table/button sections refresh the hosting
        # form themselves; this only fans out to an optional consumer callback.
        if self._changed is not None:
            self._changed()

    # -- lifetime spectrum table --------------------------------------
    def update_spectrum_cell(self, row: int, key: str, value: Any) -> None:
        if key not in {"amplitude", "lifetime"}:
            return
        try:
            self.spectrum_rows[int(row)][key] = float(value)
        except (TypeError, ValueError, IndexError):
            pass
        self._notify()

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
        self._status = f"Using {label}. Detector patterns will use its ChiSurf model."
        self._notify()

    # -- measured pattern override ------------------------------------
    def load_pattern(self) -> None:
        from qtpy import QtWidgets

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            None, "Load decay pattern", "",
            "Decay (*.txt *.dat *.csv *.npy);;All files (*)",
        )
        if path:
            self.pattern_path = path
            self._status = f"Using measured pattern: {pathlib.Path(path).name}"
            self._notify()

    def clear_pattern(self) -> None:
        self.pattern_path = ""
        self._status = "Edit the lifetime spectrum (amplitude + lifetime)."
        self._notify()

    def status_text(self) -> str:
        return str(self._status)

    # -- generator + preview ------------------------------------------
    @property
    def lifetime_spectrum(self) -> np.ndarray:
        values: list[float] = []
        for row in self.spectrum_rows:
            values.extend((float(row["amplitude"]), float(row["lifetime"])))
        return validate_lifetime_spectrum(values)

    def _irf(self):
        # A loaded measured pattern already includes the instrument response.
        if self.pattern_path:
            return None
        # An experimental IRF file wins over the synthetic Gaussian.
        if self.irf_path and pathlib.Path(self.irf_path).is_file():
            p = pathlib.Path(self.irf_path)
            return np.load(p) if p.suffix.lower() == ".npy" else np.loadtxt(p)
        # Synthetic (possibly skewed) Gaussian IRF via the canonical helper.
        if float(self.irf_fwhm_ns) > 0.0:
            from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

            n = int(self.n_bins)
            dt = float(self.bin_width)
            time = np.arange(n, dtype=float) * dt
            fwhm = float(self.irf_fwhm_ns)
            center = float(self.irf_center_ns) if self.irf_center_ns > 0.0 else 2.0 * fwhm
            return synthetic_irf(time, center, fwhm, shape=float(self.irf_skew), norm=True)
        return None

    def decay(self) -> np.ndarray:
        """Return the current decay histogram (from a loaded pattern or the spectrum)."""
        if self.pattern_path and pathlib.Path(self.pattern_path).is_file():
            p = pathlib.Path(self.pattern_path)
            y = np.load(p) if p.suffix.lower() == ".npy" else np.loadtxt(p)
            return np.asarray(y, dtype=float).ravel()
        from chisurf.core.fluorescence.decay import synthetic_decay

        spec = self.lifetime_spectrum
        return synthetic_decay(
            int(self.n_bins), spec[1::2], amplitudes=spec[0::2],
            bin_width=float(self.bin_width), irf=self._irf(),
            period=(float(self.period_ns) if self.period_ns > 0.0 else None),
            time_shift=float(self.time_shift_ns),
            normalize=not self.shot_noise,
            photon_count=(float(self.photon_count) if self.shot_noise else None),
            seed=(int(self.noise_seed) if self.shot_noise else None),
        )

    def decay_series(self) -> list[dict]:
        try:
            y = self.decay()
        except Exception:
            return []
        x = (np.arange(y.size) * float(self.bin_width)).tolist()
        return [{"x": x, "y": np.maximum(y, 1e-12).tolist(), "name": "decay", "color": "#22d3ee"}]

    def load_component(self, component: dict) -> None:
        """Prefill the editor from a persisted ``lifetime_spectrum`` component."""
        amps = list(component.get("amplitudes", []))
        taus = list(component.get("lifetimes", []))
        if amps and taus:
            self.spectrum_rows = [
                {"amplitude": float(a), "lifetime": float(t)} for a, t in zip(amps, taus)
            ]
        self.name = str(component.get("name", self.name))
        self.bin_width = float(component.get("bin_width", self.bin_width))
        self.start_bin = int(component.get("start_bin", self.start_bin))
        self.irf_path = str(component.get("irf_path") or "")
        self.irf_fwhm_ns = float(component.get("irf_fwhm_ns", self.irf_fwhm_ns))
        self.irf_skew = float(component.get("irf_skew", self.irf_skew))
        self.period_ns = float(component.get("period_ns", self.period_ns))
        self.time_shift_ns = float(component.get("time_shift_ns", self.time_shift_ns))
        self.shot_noise = bool(component.get("shot_noise", self.shot_noise))
        self.photon_count = int(component.get("photon_count", self.photon_count))
        self.noise_seed = int(component.get("noise_seed", self.noise_seed))

    # -- output -------------------------------------------------------
    def component(self) -> dict:
        """Return a persisted synthetic-component definition (for the Filter Calc)."""
        spec = self.lifetime_spectrum
        irf = self.irf_path if (self.irf_path and pathlib.Path(self.irf_path).is_file()) else None
        return {
            "type": "synthetic",
            "model": "lifetime_spectrum",
            "name": (self.name or "component").strip(),
            "amplitudes": spec[0::2].tolist(),
            "lifetimes": spec[1::2].tolist(),
            "bin_width": float(self.bin_width),
            "start_bin": int(self.start_bin),
            "irf_path": str(pathlib.Path(irf).absolute()) if irf else None,
            "irf_fwhm_ns": float(self.irf_fwhm_ns),
            "irf_skew": float(self.irf_skew),
            "period_ns": float(self.period_ns),
            "time_shift_ns": float(self.time_shift_ns),
            "shot_noise": bool(self.shot_noise),
            "photon_count": int(self.photon_count),
            "noise_seed": int(self.noise_seed),
        }
