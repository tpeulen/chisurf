"""Qt-free view model for the flow-map tool.

Holds the settings the AutoForm binds to, drives the Qt-free compute through the
plugin client (so the GUI takes the same RPC path as the CLI), and exposes the
results as the quiver/plot/table/info sources the view spec names. No Qt import
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

_VIEW_JSON = pathlib.Path(__file__).parent / "flow.view.json"

#: Labels shown for the estimators, in the order of ``core.METHODS``.
METHOD_LABELS = (
    "STICS — where the peak moves",
    "Pair correlation — when it arrives",
)


class FlowViewModel:
    """Settings and results for one velocity-field measurement."""

    def __init__(self, client: Any = None) -> None:
        """Initialize with an empty selection and the demo-friendly defaults.

        Parameters
        ----------
        client : object, optional
            A :class:`~...client.FlowClient`-like object. Constructed lazily on
            first use when omitted, so building the widget costs nothing.
        """
        self._view_json = _VIEW_JSON
        self._observers: list[Callable[[str], None]] = []
        self._client = client

        self.filename: str = ""
        self.channel: Any = 0
        self.method: str = "stics"
        self.tile: int = 24
        self.step: int = 0
        self.n_lags: int = 5
        self.distance: int = 4
        self.subtract_average: str = "frame"
        self.min_quality: float = 0.5
        self.arrow_scale: float = 1.0

        self.pixel_duration_us: float = 20.0
        self.line_duration_ms: float = 0.0
        self.frame_duration_ms: float = 0.0
        self.pixel_size_nm: float = 100.0

        self._channel_names: list[str] = []
        self._result: _core.FlowAnalysis | None = None
        self._status: str = "No image loaded."
        self._demo: dict[str, Any] | None = None
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
                logger.debug("flow observer failed", exc_info=True)

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(self._view_json)

    @property
    def client(self):
        """The plugin client, constructed on first use."""
        if self._client is None:
            from ..client import FlowClient

            self._client = FlowClient()
        return self._client

    # ── selection ──
    def set_filename(self, path: str) -> None:
        """Point the tool at an image or photon stream and read its channels."""
        self.filename = str(path or "")
        self._result = None
        self._channel_names = []
        if not self.filename:
            self._status = "No image loaded."
            self.notify()
            return
        try:
            stack = load_image_stack(self.filename)
            self._channel_names = list(stack.channel_names)
            n_frames, _, ny, nx = stack.data.shape
            self._status = (
                f"{pathlib.Path(self.filename).name}: {n_frames} frames of "
                f"{ny}x{nx}, {len(self._channel_names)} channel(s). "
                + ("Ready." if n_frames >= 3
                   else "Too few frames — a flow map needs the sample to move between them.")
            )
        except Exception as exc:
            logger.debug("could not read %s", self.filename, exc_info=True)
            self._status = f"Could not read the file: {exc}"
        self.notify()

    def channel_names(self) -> list[str]:
        """Channel names of the loaded file, for the choice field."""
        return list(self._channel_names)

    # ── the demo ──
    def load_demo(self, progress: Callable[[float, str], None] | None = None) -> str:
        """Simulate (or reuse) the demo photon stream and select it.

        Returns
        -------
        str
            The path that was loaded.
        """
        from ..demo import create_demo

        self._status = "Simulating the demo scan…"
        self.notify()
        result = create_demo(progress=progress)
        self._demo = result
        timing = result["timing"]
        self.pixel_duration_us = float(timing["pixel_duration_us"])
        self.line_duration_ms = float(timing["line_duration_ms"])
        self.frame_duration_ms = float(timing["frame_duration_ms"])
        self.pixel_size_nm = float(timing["pixel_size_nm"])
        self.set_filename(result["path"])
        return result["path"]

    @property
    def demo_truth(self) -> dict[str, Any] | None:
        """Ground truth of the loaded demo, or ``None`` for a real file."""
        if self._demo is None:
            return None
        if str(self._demo.get("path", "")) != str(self.filename):
            return None
        return dict(self._demo.get("truth", {}))

    # ── compute ──
    @property
    def result(self) -> _core.FlowAnalysis | None:
        """The last velocity field, or ``None``."""
        return self._result

    @property
    def status(self) -> str:
        """One-line status for the host status bar."""
        return self._status

    def compute(self, progress: Callable[[float, str], None] | None = None) -> bool:
        """Measure the velocity field with the current settings.

        Parameters
        ----------
        progress : callable, optional
            Called as ``progress(fraction, text)``.

        Returns
        -------
        bool
            Whether a field was produced.
        """
        if not self.filename:
            self._status = "Load an image first."
            self.notify()
            return False
        if progress:
            progress(0.05, "Reading the image")
        try:
            analysis = _core.analyse_file(
                self.filename,
                channel=self.channel,
                method=self.method,
                tile=int(self.tile),
                step=int(self.step),
                n_lags=int(self.n_lags),
                distance=int(self.distance),
                subtract_average=self.subtract_average,
                pixel_duration_us=float(self.pixel_duration_us),
                line_duration_ms=float(self.line_duration_ms),
                frame_duration_ms=float(self.frame_duration_ms),
                pixel_size_nm=float(self.pixel_size_nm),
            )
        except Exception as exc:
            logger.debug("flow map failed", exc_info=True)
            self._status = f"Flow map failed: {exc}"
            self._result = None
            self.notify()
            return False
        if progress:
            progress(1.0, "Done")
        self._result = analysis
        summary = analysis.summary(self.min_quality)
        kept, total = int(summary["n_kept"]), int(summary["n_tiles"])
        if kept:
            self._status = (
                f"{kept}/{total} tiles, mean speed {summary['mean_speed']:.3g} µm/s"
            )
            if analysis.n_escaped:
                self._status += (
                    f" — {analysis.n_escaped} tile(s) refused (peak left the tile)"
                )
        else:
            # Strip the markup: this line goes to a status bar, not a browser.
            import re

            self._status = "No arrows: " + re.sub(r"<[^>]+>", "", self.diagnose())
        self.notify()
        return True

    # ── AutoForm sources ──
    def flow_image(self):
        """The time-averaged image the arrows are drawn on."""
        return None if self._result is None else self._result.image

    def flow_extent(self):
        """``(x0, x1, y0, y1)`` of the image in µm, so arrows share its axes."""
        if self._result is None:
            return None
        ny, nx = self._result.image.shape
        pixel_um = float(self._result.timing.pixel_size_nm) * 1e-3
        return (0.0, nx * pixel_um, 0.0, ny * pixel_um)

    def flow_vectors(self) -> list[dict[str, float]]:
        """The arrows worth drawing, in µm and µm/s."""
        if self._result is None:
            return []
        x, y, vx, vy = self._result.arrows(self.min_quality)
        return [
            {"x": float(a), "y": float(b), "dx": float(c), "dy": float(d)}
            for a, b, c, d in zip(x, y, vx, vy)
        ]

    def vector_rows(self) -> list[dict[str, Any]]:
        """One row per tile, for the results table."""
        if self._result is None:
            return []
        return [
            {k: (f"{v:.4g}" if isinstance(v, float) else v) for k, v in row.items()}
            for row in _core.to_rows(self._result, 0.0)
        ]

    def profile_series(self) -> list[dict[str, Any]]:
        """The flow profile across the image: speed against position down the frame.

        A field is hard to read as a table and easy to read as a profile, and for
        the demo it is *checkable* — the simulated channel is parabolic, so the
        recovered curve has to rise to the middle and fall again.
        """
        if self._result is None:
            return []
        kept = self._result.kept(self.min_quality)
        with np.errstate(invalid="ignore"):
            vx = np.where(kept, self._result.vx, np.nan)
            speed = np.where(kept, self._result.speed, np.nan)
            mean_vx = np.nanmean(vx, axis=1)
            mean_speed = np.nanmean(speed, axis=1)
        y = np.asarray(self._result.y)[:, 0]
        series = [
            {"x": list(y), "y": list(mean_speed), "name": "speed",
             "color": "#ffb000", "width": 2, "symbol": "o", "symbol_size": 7},
            {"x": list(y), "y": list(mean_vx), "name": "v_x",
             "color": "#4da6ff", "width": 1, "style": "dash"},
        ]
        truth = self.demo_truth
        if truth:
            from ..demo import expected_profile

            series.append(
                {
                    "x": list(y),
                    "y": list(expected_profile(y, v_max=truth["v_max_um_s"],
                                               field_um=truth["field_um"])),
                    "name": "simulated truth",
                    "color": "#2ca02c",
                    "width": 2,
                    "style": "dot",
                }
            )
        return series

    def diagnose(self) -> str:
        """Say *why* a field came back empty, in the terms of the settings.

        "Nothing passed the quality threshold" is true and useless. There are
        only a few reasons a flow map can be empty, each with a different fix,
        and the numbers to tell them apart are already in hand.
        """
        result = self._result
        if result is None:
            return "Nothing has been measured yet."
        if result.n_escaped:
            return (
                f"All {result.n_escaped} tile(s) were refused: the correlation "
                "peak travelled past the edge of its tile, where it wraps around "
                "and fits a velocity pointing the wrong way. <b>Use fewer frame "
                "lags, or a larger tile.</b>"
            )
        finite = result.speed[np.isfinite(result.speed)]
        best = float(np.nanmax(result.quality)) if result.quality.size else 0.0
        pixel_um = float(result.timing.pixel_size_nm) * 1e-3
        frame_s = float(result.timing.frame_duration_ms) * 1e-3
        floor = pixel_um / (frame_s * max(1, int(self.n_lags) - 1)) if frame_s else 0.0
        if finite.size and float(np.nanmax(finite)) < 0.5 * floor:
            return (
                f"Every tile is slower than {floor:.3g} µm/s, which is one pixel "
                f"over the whole lag range — below that there is no peak "
                "displacement to fit. <b>Either the sample is not flowing, or "
                "you need more frame lags</b> (or a sample that moves faster "
                "than this scan can see)."
            )
        if best < float(self.min_quality):
            return (
                f"The best tile scored {best:.2f} against a threshold of "
                f"{self.min_quality:.2f}. The peak track is not a straight line, "
                "which usually means too few molecules per tile or too few "
                "frames. <b>Try a larger tile, or lower the threshold to look at "
                "what is there.</b>"
            )
        return "No tile passed the quality threshold."

    def summary_html(self) -> str:
        """The headline numbers, and the warnings that matter."""
        if self._result is None:
            return f"<p>{self._status}</p>"
        summary = self._result.summary(self.min_quality)
        if not summary["n_kept"]:
            return (
                "<p><b>No arrows.</b><br/>" + self.diagnose() + "</p>"
            )
        rows = [
            f"<b>{summary['mean_speed']:.4g} µm/s</b> mean speed "
            f"({int(summary['n_kept'])} of {int(summary['n_tiles'])} tiles)",
            f"mean vector ({summary['mean_vx']:.3g}, {summary['mean_vy']:.3g}) µm/s "
            f"at {summary['angle_deg']:.0f}°",
            f"coherence {summary['coherence']:.2f} — "
            + ("one direction everywhere" if summary["coherence"] > 0.8
               else "a structured field, not a uniform one"),
        ]
        if self._result.n_escaped:
            rows.append(
                f"<span style='color:#c04040'><b>{self._result.n_escaped} tile(s) "
                "refused</b>: the correlation peak left the tile, where it wraps "
                "around and fits a confident <i>backwards</i> velocity. Use fewer "
                "lags or a larger tile.</span>"
            )
        truth = self.demo_truth
        if truth:
            rows.append(
                f"<span style='color:#2a7'>Demo: the simulated flow is "
                f"{truth['profile']} along {truth['axis']}, peak "
                f"<b>{truth['v_max_um_s']:.3g} µm/s</b>. The recovered magnitude "
                "reads low where the flow shears inside a tile; the direction and "
                "the shape of the profile are what to check.</span>"
            )
        return "<p>" + "<br/>".join(rows) + "</p>"

    def export_csv(self, path: str) -> str:
        """Write the velocity field to *path* and return what was written."""
        if self._result is None:
            return ""
        return _core.write_csv(self._result, path, self.min_quality)

    # ── imaging-toolbox adapters ──
    def apply_setup_settings(self, payload: dict) -> None:
        """Adopt the shared imaging detector setup (photon streams)."""
        if not isinstance(payload, dict):
            return
        self.detectors = dict(payload.get("detectors") or {})
        for key in ("pixel_duration_us", "line_duration_ms",
                    "frame_duration_ms", "pixel_size_nm"):
            value = payload.get(key)
            if isinstance(value, (int, float)) and float(value) > 0:
                setattr(self, key, float(value))
        self.notify()

    def apply_pipeline_context(self, payload: dict) -> None:
        """Adopt the toolbox pipeline's current source file."""
        if not isinstance(payload, dict):
            return
        self.pipeline_hdf5 = str(payload.get("hdf5") or self.pipeline_hdf5)
        source = str(payload.get("source") or "")
        if source and source != self.filename:
            self.set_filename(source)
