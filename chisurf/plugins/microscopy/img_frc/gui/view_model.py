"""Qt-free view model for the FRC resolution calculator.

Holds the settings the AutoForm binds to, drives the Qt-free compute through the
plugin client (so the GUI takes the same RPC path as the CLI), and exposes the
results as the plot/table/image/info sources the view spec names. No Qt import
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

_VIEW_JSON = pathlib.Path(__file__).parent / "frc.view.json"

#: Labels shown for the split modes, in the order of ``core.SPLITS``.
SPLIT_LABELS = (
    "Even / odd frames",
    "First / second half",
    "Two channels",
    "Two files",
)

#: Labels shown for the threshold criteria.
CRITERION_LABELS = ("Fixed 1/7", "½-bit", "2σ")


class FrcViewModel:
    """Settings and results for one resolution measurement."""

    def __init__(self, client: Any = None) -> None:
        """Initialize with an empty selection and the usual defaults.

        Parameters
        ----------
        client : object, optional
            A :class:`~...client.FrcClient`-like object. Constructed lazily on
            first use when omitted, so building the widget costs nothing.
        """
        self._view_json = _VIEW_JSON
        self._observers: list[Callable[[str], None]] = []
        self._client = client

        self.filename: str = ""
        self.second_filename: str = ""
        self.split: str = "even_odd"
        self.channel: Any = 0
        self.channel_2: Any = ""
        self.pixel_size_nm: float = 0.0
        self.criterion: str = "fixed_1/7"
        self.bin_width: float = 0.0
        self.smooth: int = 3
        self.axis_order: str = "auto"
        self.colormap: str = "inferno"

        self._channel_names: list[str] = []
        self._result: _core.FrcAnalysis | None = None
        self._status: str = "No image loaded."
        #: Named detector windows from the shared Setup panel (photon streams).
        self.detectors: dict[str, dict] = {}
        #: Imaging HDF5 remembered by the toolbox pipeline, if any.
        self.pipeline_hdf5: str = ""

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
                logger.debug("frc observer failed", exc_info=True)

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(self._view_json)

    # ── source ──
    @property
    def client(self):
        """Return the RPC client, building the in-process one on first use."""
        if self._client is None:
            from ..client import FrcClient

            self._client = FrcClient()
        return self._client

    @property
    def channel_names(self) -> list[str]:
        """Channel names of the loaded source, for the channel selectors."""
        return list(self._channel_names)

    @property
    def status(self) -> str:
        """One-line description of the current state, for the host status bar."""
        return self._status

    @property
    def result(self) -> _core.FrcAnalysis | None:
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
            stack = load_image_stack(
                self.filename,
                windows=self.detectors or None,
                channel_axis=_core.channel_axis_for(self.axis_order),
            )
        except Exception as exc:
            logger.debug("could not read %s", self.filename, exc_info=True)
            self._status = f"Could not read the image: {exc}"
            return False

        self._channel_names = list(stack.channel_names)
        if not isinstance(self.channel, int) and self.channel not in self._channel_names:
            self.channel = 0
        self._status = (
            f"{stack.n_frames} frames, {stack.n_channels} channel(s), "
            f"{stack.frame_shape[0]}x{stack.frame_shape[1]} px ({stack.kind})."
        )
        if stack.n_frames < 2 and self.split in ("even_odd", "halves"):
            self._status += " One frame: pick a channel or a two-file split."
        self.notify("file")
        return True

    def set_second_filename(self, filename: str) -> bool:
        """Set the second acquisition used by the two-file split."""
        self.second_filename = str(filename or "")
        self._result = None
        self.notify("file")
        return bool(self.second_filename)

    # ── imaging-toolbox adapters ──
    def apply_setup_settings(self, payload: dict) -> None:
        """Adopt the shared detector definition (photon streams only).

        The Setup panel of Image Tools defines the detector windows once for the
        whole workflow. Adopting them here means a photon stream is filled by
        *named window* rather than by raw routing channel, so "green" and "red"
        are what the channel selector offers — and a two-channel FRC then
        correlates the two detectors the user actually defined.
        """
        try:
            from chisurf.core.fluorescence.imaging import windows_from_payload

            windows = windows_from_payload(payload)
            if windows:
                self.detectors = windows
                if self.filename:
                    self.set_filename(self.filename)
        except Exception:
            logger.debug("apply_setup_settings failed", exc_info=True)

    def apply_pipeline_context(self, payload: dict) -> None:
        """Adopt the toolbox's current source, so the panel opens on it.

        Every step of Image Tools is freely navigable, so a panel reached with a
        file already loaded elsewhere must not start empty.
        """
        try:
            source = (payload or {}).get("source")
            hdf5 = (payload or {}).get("hdf5")
            if hdf5:
                self.pipeline_hdf5 = str(hdf5)
            if source and str(source) != self.filename:
                self.set_filename(str(source))
        except Exception:
            logger.debug("apply_pipeline_context failed", exc_info=True)

    # ── compute ──
    def compute(self, progress: Callable[[float, str], None] | None = None) -> bool:
        """Measure the resolution of the loaded file.

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
            self._result = _core.analyse(
                self.filename,
                split=self.split,
                channel=self.channel,
                channel_2=self.channel_2 or None,
                second_filename=self.second_filename or None,
                pixel_size_nm=float(self.pixel_size_nm) or None,
                criterion=self.criterion,
                bin_width=float(self.bin_width) or None,
                smooth=int(self.smooth),
                axis_order=self.axis_order,
                windows=self.detectors or None,
            )
        except Exception as exc:
            logger.debug("frc measurement failed", exc_info=True)
            self._result = None
            self._status = f"FRC failed: {exc}"
            return False
        if progress:
            progress(1.0, "Done")

        result = self._result
        if not result.crossed:
            self._status = "The FRC never crosses its threshold — see the help."
        else:
            self._status = f"Resolution {result.resolution:.4g} {result.unit} ({result.criterion})."
        return True

    def export_csv(self, path: str) -> str:
        """Write the curve, its threshold and the ring counts to *path*."""
        if self._result is None or not path:
            return ""
        return _core.write_csv(self._result, path)

    # ── view sources named by frc.view.json ──
    def frc_series(self) -> list[dict]:
        """Return the FRC curve, its threshold and the crossing as plot series."""
        result = self._result
        if result is None:
            return []
        series = [
            {
                "x": np.asarray(result.frequency, dtype=float),
                "y": np.nan_to_num(np.asarray(result.correlation, dtype=float)),
                "name": "FRC",
                "color": "#4c9be8",
                "width": 2,
            },
            {
                "x": np.asarray(result.frequency, dtype=float),
                "y": np.asarray(result.threshold, dtype=float),
                "name": f"threshold ({result.criterion})",
                "color": "#e8734c",
            },
        ]
        if result.crossed:
            # A single point drawn as a line is invisible; the crossing is the
            # one number on this plot, so it gets a symbol of its own.
            series.append(
                {
                    "x": np.array([float(result.crossing)]),
                    "y": np.array(
                        [
                            float(
                                np.interp(
                                    result.crossing,
                                    np.asarray(result.frequency, dtype=float),
                                    np.asarray(result.threshold, dtype=float),
                                )
                            )
                        ]
                    ),
                    "name": "resolution",
                    "color": "#f2c744",
                    "symbol": "d",
                    "symbol_size": 12,
                    "no_line": True,
                }
            )
        return series

    def ring_rows(self) -> list[dict]:
        """Return one row per ring for the numbers table."""
        result = self._result
        if result is None:
            return []
        unit = "1/nm" if result.unit == "nm" else "1/px"
        rows = []
        for i, frequency in enumerate(result.frequency):
            correlation = float(result.correlation[i])
            rows.append(
                {
                    "frequency": f"{float(frequency):.5g}",
                    "period": f"{(1.0 / frequency) if frequency else float('inf'):.4g}",
                    "correlation": f"{correlation:.4f}",
                    "threshold": f"{float(result.threshold[i]):.4f}",
                    "pixels": int(result.counts[i]),
                    "_unit": unit,
                }
            )
        return rows

    def summary_html(self) -> str:
        """Return the headline result as HTML for the info box."""
        result = self._result
        if result is None:
            return (
                "<p>Load a TIFF stack or a photon stream, choose how to split it "
                "into two independent halves, and press <b>Measure</b>.</p>"
            )
        if not result.crossed:
            return (
                "<p><b>No crossing.</b> The correlation never falls through the "
                f"{result.criterion} threshold. Either the two halves agree "
                "everywhere — the image is resolved beyond what this sampling can "
                "show — or the split did not produce independent halves.</p>"
            )
        unit = result.unit
        period = 1.0 / result.crossing if result.crossing else float("inf")
        pixel_note = (
            "" if unit == "nm" else "<p><i>No pixel size given, so this is in pixels.</i></p>"
        )
        return (
            f"<h3>{result.resolution:.4g} {unit}</h3>"
            f"<p>Criterion <b>{result.criterion}</b>, crossing at "
            f"{result.crossing:.5g} 1/{unit} (period {period:.4g} {unit}).</p>"
            f"<p>{result.n_frames} frames, {result.kind} source, "
            f"{len(result.frequency)} rings.</p>"
            f"{pixel_note}"
        )

    def half_1_image(self):
        """Return the first half image."""
        return None if self._result is None else np.asarray(self._result.half_1)

    def half_2_image(self):
        """Return the second half image."""
        return None if self._result is None else np.asarray(self._result.half_2)


__all__ = ["CRITERION_LABELS", "SPLIT_LABELS", "FrcViewModel"]
