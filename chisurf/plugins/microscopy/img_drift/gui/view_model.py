"""Qt-free view model for the drift-correction tool.

Holds the settings the AutoForm binds to, runs the Qt-free compute, and exposes
the results as the plot/table/image sources the view spec names. No Qt import
here, so the whole thing is testable headlessly.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Callable
from typing import Any

import numpy as np

from chisurf.core.fluorescence.imaging import load_image_stack

from .. import core as _core

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "drift.view.json"


class DriftViewModel:
    """Settings and results for one drift-correction session."""

    def __init__(self) -> None:
        """Initialize with an empty selection and the reference-implementation defaults."""
        self._view_json = _VIEW_JSON
        self._observers: list[Callable[[str], None]] = []
        self.filename: str = ""
        self.channel: Any = 0
        self.reference: str = "first"
        self.mode: str = "wrap"
        self.smooth: float = 2.0
        self.subpixel: bool = False
        self.colormap: str = "inferno"

        self._channel_names: list[str] = []
        self._result: _core.DriftResult | None = None
        self._status: str = "No image loaded."

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
                logger.debug("drift observer failed", exc_info=True)

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(self._view_json)

    # ── source ──
    @property
    def channel_names(self) -> list[str]:
        """Channel names of the loaded source, for the channel selector."""
        return list(self._channel_names)

    @property
    def status(self) -> str:
        """One-line description of the current state, for the host status bar."""
        return self._status

    @property
    def result(self) -> _core.DriftResult | None:
        """The last measurement, or ``None`` before one has run."""
        return self._result

    def set_filename(self, filename: str) -> bool:
        """Load a file's channel list and clear any previous result.

        Parameters
        ----------
        filename : str
            Path to a TIFF stack or a photon stream.

        Returns
        -------
        bool
            ``True`` when the source could be read.
        """
        self.filename = str(filename or "")
        self._result = None
        self._channel_names = []
        if not self.filename or not pathlib.Path(self.filename).is_file():
            self._status = "No image loaded."
            return False
        try:
            stack = load_image_stack(self.filename)
        except Exception as exc:
            logger.debug("could not read %s", self.filename, exc_info=True)
            self._status = f"Could not read the image: {exc}"
            return False

        self._channel_names = list(stack.channel_names)
        if self.channel not in self._channel_names and not isinstance(self.channel, int):
            self.channel = 0
        if stack.n_frames < 2:
            self._status = f"{stack.n_frames} frame(s): drift correction needs at least two."
            return False
        self._status = (
            f"{stack.n_frames} frames, {stack.n_channels} channel(s), "
            f"{stack.frame_shape[0]}x{stack.frame_shape[1]} px ({stack.kind})."
        )
        self.notify("file")
        return True

    # ── compute ──
    def compute(self, progress: Callable[[float, str], None] | None = None) -> bool:
        """Measure the drift of the loaded file.

        Parameters
        ----------
        progress : callable, optional
            Called with ``(fraction, message)`` as the run proceeds.

        Returns
        -------
        bool
            ``True`` when a measurement was produced.
        """
        if not self.filename:
            self._status = "No image loaded."
            return False
        if progress:
            progress(0.1, "Reading image…")
        try:
            self._result = _core.measure_drift(
                self.filename,
                self.channel,
                reference=self.reference,
                smooth=float(self.smooth),
                subpixel=bool(self.subpixel),
                mode=self.mode,
            )
        except Exception as exc:
            logger.debug("drift measurement failed", exc_info=True)
            self._result = None
            self._status = f"Drift measurement failed: {exc}"
            return False
        if progress:
            progress(1.0, "Done")

        total = self._result.total_drift
        verdict = (
            "below one pixel — correction changes nothing" if total < 1.0 else f"{total:.1f} px"
        )
        self._status = f"Max drift {verdict} over {self._result.n_frames} frames."
        return True

    # ── export ──
    def export(self, stack_path: str = "", shifts_path: str = "") -> dict:
        """Write the corrected stack and/or the shift table.

        Parameters
        ----------
        stack_path : str
            Destination for the corrected multi-page TIFF; skipped when empty.
        shifts_path : str
            Destination for the per-frame CSV; skipped when empty.

        Returns
        -------
        dict
            Mapping of what was written to where.
        """
        if self._result is None:
            return {}
        written: dict[str, str] = {}
        if shifts_path:
            written["shifts"] = _core.write_shifts_csv(self._result.shifts, shifts_path)
        if stack_path:
            data, _ = _core.corrected_stack(
                self.filename,
                self.channel,
                shifts=self._result.shifts,
                mode=self.mode,
            )
            written["stack"] = _core.write_stack_tiff(data, stack_path)
        return written

    # ── view sources named by drift.view.json ──
    def drift_series(self) -> list[dict]:
        """Return the drift trace as AutoForm plot series."""
        if self._result is None:
            return []
        sh = np.asarray(self._result.shifts, dtype=float)
        frames = np.arange(len(sh), dtype=float)
        # Distinct colours: the two axes are read against each other, and the
        # magnitude is the summary line, so they must not all look alike.
        return [
            {"x": frames, "y": sh[:, 1], "name": "dx", "color": "#4c9be8"},
            {"x": frames, "y": sh[:, 0], "name": "dy", "color": "#e8734c"},
            {
                "x": frames,
                "y": np.hypot(sh[:, 0], sh[:, 1]),
                "name": "|d|",
                "color": "#b0b0b0",
                "width": 2,
            },
        ]

    def shift_rows(self) -> list[dict]:
        """Return one row per frame for the shift table."""
        if self._result is None:
            return []
        sh = np.asarray(self._result.shifts, dtype=float)
        return [
            {
                "frame": int(i),
                "dx": f"{sh[i, 1]:+.2f}",
                "dy": f"{sh[i, 0]:+.2f}",
                "magnitude": f"{float(np.hypot(sh[i, 0], sh[i, 1])):.2f}",
            }
            for i in range(len(sh))
        ]

    def before_image(self):
        """Return the frame-summed projection before correction."""
        return None if self._result is None else np.asarray(self._result.before)

    def after_image(self):
        """Return the frame-summed projection after correction."""
        return None if self._result is None else np.asarray(self._result.after)
