"""Qt-free view model for the RICS-precision calculator."""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Callable

import numpy as np

from .. import core as _core

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "precision.view.json"


class PrecisionViewModel:
    """Settings and results for one RICS-precision prediction."""

    def __init__(self) -> None:
        """Initialize with a typical confocal acquisition."""
        self._view_json = _VIEW_JSON
        self._observers: list[Callable[[str], None]] = []

        # ── sample ──
        self.diffusion_coefficient: float = 10.0     # µm²/s
        self.n_particles: float = 50.0
        self.brightness_khz: float = 100.0           # kHz per molecule

        # ── optics ──
        self.w_r: float = 0.25                       # µm
        self.w_z: float = 1.25                       # µm
        self.pixel_size_nm: float = 50.0
        self.two_d: bool = False

        # ── acquisition ──
        self.pixel_time_us: float = 8.0
        self.line_overhead: float = 1.2
        self.nx: int = 64
        self.ny: int = 64
        self.n_images: int = 100

        # ── estimator ──
        self.n_lags: int = 4
        self.n_repeats: int = 40
        self.seed: int = 1

        self._sweep: _core.PrecisionSweep | None = None
        self._status = "Set the sample and the scan, then press Predict."

    # ── observer hook ──
    def add_observer(self, cb: Callable[[str], None]) -> None:
        """Register *cb* to be called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that state changed."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("precision observer failed", exc_info=True)

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(self._view_json)

    # ── state ──
    @property
    def status(self) -> str:
        """One-line summary for the host status bar."""
        return self._status

    @property
    def sweep(self) -> _core.PrecisionSweep | None:
        """The last sweep, or ``None`` before one has run."""
        return self._sweep

    def _kwargs(self) -> dict:
        """Return the predictor arguments implied by the current settings."""
        return dict(
            pixel_size=float(self.pixel_size_nm) * 1e-3,     # nm -> µm
            ny=int(self.ny),
            n_particles=float(self.n_particles),
            w_r=float(self.w_r),
            w_z=float(self.w_z),
            brightness=float(self.brightness_khz) * 1e3,     # kHz -> photons/s
            n_images=int(self.n_images),
            n_lags=int(self.n_lags),
            n_repeats=int(self.n_repeats),
            two_d=bool(self.two_d),
            seed=int(self.seed),
        )

    # ── compute ──
    def compute(self, progress: Callable[[float, str], None] | None = None) -> bool:
        """Sweep the dwell time and predict the precision at each.

        Parameters
        ----------
        progress : callable, optional
            Called with ``(fraction, message)`` as the sweep proceeds.

        Returns
        -------
        bool
            ``True`` when a usable curve was produced.
        """
        try:
            self._sweep = _core.sweep_dwell(
                float(self.diffusion_coefficient),
                _core.default_dwell_range(9),
                nx=int(self.nx),
                line_overhead=float(self.line_overhead),
                current_dwell=float(self.pixel_time_us) * 1e-6,
                progress=progress,
                **self._kwargs(),
            )
        except Exception as exc:
            logger.debug("precision prediction failed", exc_info=True)
            self._sweep = None
            self._status = f"Prediction failed: {exc}"
            return False

        # The sweep tolerates individual unrealisable dwell times so one bad
        # point cannot take the curve down. When *every* point failed the cause
        # is a setting shared by all of them (a zero waist, a nonsense D), and
        # reporting success with a curve of holes would hide it.
        if not np.isfinite(np.asarray(self._sweep.relative_error, dtype=float)).any():
            self._sweep = None
            self._status = (
                "Prediction failed: no dwell time is realisable with these "
                "settings — check the waists, the pixel size and D."
            )
            return False

        self._status = self._summary()
        return True

    def _summary(self) -> str:
        """Return the sentence that tells the user what to do."""
        s = self._sweep
        if s is None:
            return "No prediction."
        best_us = s.best_dwell * 1e6
        if s.current is None:
            return f"Best around {best_us:.3g} µs, at {s.best_error * 100:.1f} % error."

        here = s.current.relative_error
        verdict = (
            "unusable" if here > 0.5 else
            "poor" if here > 0.2 else
            "usable" if here > 0.05 else
            "good"
        )
        gain = here / s.best_error if s.best_error > 0 else float("nan")
        tail = (
            " — already near the optimum."
            if gain < 1.3
            else f" — about {gain:.1f}x worse than the best dwell ({best_us:.3g} µs)."
        )
        return f"At {self.pixel_time_us:.3g} µs: {here * 100:.1f} % error ({verdict}){tail}"

    # ── view sources named by precision.view.json ──
    def sweep_series(self) -> list[dict]:
        """Return the precision-vs-dwell curve as AutoForm plot series."""
        s = self._sweep
        if s is None:
            return []
        dwell_us = np.asarray(s.dwell, dtype=float) * 1e6
        err_pct = np.asarray(s.relative_error, dtype=float) * 100.0
        series = [{"x": dwell_us, "y": err_pct, "name": "predicted error",
                   "color": "#4c9be8", "width": 2, "symbol": "o", "symbol_size": 6}]
        if s.current is not None:
            # A single point drawn as a line is invisible, so it needs a symbol
            # and no pen of its own.
            series.append({
                "x": np.array([float(self.pixel_time_us)]),
                "y": np.array([s.current.relative_error * 100.0]),
                "name": "your setting", "color": "#e8734c",
                "symbol": "d", "symbol_size": 14, "no_line": True,
            })
        return series

    def sweep_rows(self) -> list[dict]:
        """Return one row per swept dwell time for the table."""
        s = self._sweep
        if s is None:
            return []
        rows = []
        for dwell, line, err in zip(s.dwell, s.line_time, s.relative_error):
            rows.append({
                "dwell": f"{dwell * 1e6:.3g}",
                "line": f"{line * 1e3:.3g}",
                "error": "—" if not np.isfinite(err) else f"{err * 100:.1f}",
                "frame": f"{line * self.ny:.2f}",
            })
        return rows
