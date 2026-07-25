"""Qt-free view-model backing the colocalization imaging tool.

Holds the analysis settings the AutoForm binds to, runs the Qt-free compute, and
exposes the maps / histogram / metric rows the ``coloc.view.json`` sections read.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Callable

import numpy as np

from .. import core as _core

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "coloc.view.json"


class ColocViewModel:
    """State + logic for the interactive two-channel colocalization tool (no Qt)."""

    def __init__(self) -> None:
        #: The authored view spec (also the anchor for view-relative resources).
        self._view_json = _VIEW_JSON
        # ── AutoForm-bound settings ──
        #: Detector setup whose named windows become the image channels ("" = raw).
        self.setup_name: str = ""
        self.filename: str = ""
        self.channel_a: str = ""
        self.channel_b: str = ""
        #: Frame index; ``-1`` sums every frame of the stack.
        self.frame: int = -1
        #: Images with unlabelled axes: how to read the extra axis.
        self.channel_axis_mode: str = "auto"
        self.auto_background: bool = True
        self.background_quantile: float = 0.05
        self.background_a: float = 0.0
        self.background_b: float = 0.0
        self.auto_threshold: bool = False
        self.threshold_a: float = 0.0
        self.threshold_b: float = 0.0
        self.gate_enabled: bool = False
        self.gate_a_min: float = 0.0
        self.gate_a_max: float = 0.0
        self.gate_b_min: float = 0.0
        self.gate_b_max: float = 0.0
        self.bins: int = 128
        self.log_histogram: bool = True
        self.costes_test: bool = False
        self.costes_block: int = 4
        self.costes_randomizations: int = 200
        self.costes_seed: int = 0
        self.ccf_max_shift: int = 0
        self.profile_bins: int = 30
        self.object_analysis: bool = False
        self.object_min_size: int = 4
        self.object_smoothing: float = 0.0
        self.object_split: bool = False
        self.object_distance: float = 3.0
        self.brush_size: int = 9
        self.colormap: str = "magma"
        # ── detector windows from the selected setup ──
        #: ``{window: {"chs": [...], "micro_time_ranges": [...]}}`` (empty = raw channels).
        self.detectors: dict[str, dict] = {}
        #: Painted region the analysis is restricted to (``None`` = whole image).
        self.roi_mask = None
        # ── runtime state ──
        self._stack = None
        self._result = None
        self._metrics: dict = {}
        self.results_text: str = (
            "Load a TIFF stack or photon-stream image (or drop one) and press Run."
        )
        self._observers: list[Callable[[str], None]] = []

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
                logger.debug("colocalization observer failed", exc_info=True)

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    # ── file / channels ──
    def set_filename(self, path: str) -> None:
        """Adopt a new source file and drop the previous result."""
        path = str(path or "")
        if path == self.filename:
            return
        self.filename = path
        self._stack = None
        self._result = None
        self._metrics = {}
        if not (self.detectors and self._uses_windows()):
            # Channel identities came from the previous file; with a setup selected
            # the named windows stay valid across files.
            self.channel_a = ""
            self.channel_b = ""
        self.results_text = f"Loaded {pathlib.Path(path).name}. Press Run."
        self.notify("file")

    def apply_setup_settings(self, payload: dict) -> None:
        """Adopt the detector windows of a picked setup as the image channels.

        The shared hook every imaging step implements: the setup's named windows
        (green / red / …, each a channel set plus optional micro-time gates) become
        the channels offered for the colocalization pair, instead of the raw
        routing-channel numbers found in the file. An empty payload clears them.

        Parameters
        ----------
        payload : dict
            ``{"name": <setup>, "detectors": {...}}`` from the setup picker.
        """
        from chisurf.core.fluorescence.imaging import windows_from_payload

        name = str((payload or {}).get("name", "") or "")
        try:
            windows = windows_from_payload(payload or {})
        except Exception:
            logger.debug("apply_setup_settings failed", exc_info=True)
            windows = {}
        if name == self.setup_name and windows == self.detectors:
            return
        self.setup_name = name
        self.detectors = windows
        # The channel identities changed; drop the stale pair and result.
        self.channel_a = ""
        self.channel_b = ""
        self._stack = None
        self._result = None
        self._metrics = {}
        self.notify("setup")

    def window_names(self) -> list[str]:
        """Return the detector-window names of the selected setup (may be empty)."""
        return list(self.detectors.keys())

    def channel_names(self) -> list[str]:
        """Return the pickable channel names.

        The selected setup's detector windows when one is chosen (available
        immediately, before any file is read), otherwise the channels of the
        loaded stack.
        """
        if self.detectors and self._uses_windows():
            return self.window_names()
        return list(self._stack.channel_names) if self._stack is not None else []

    def _uses_windows(self) -> bool:
        """Return whether detector windows apply (photon streams only)."""
        if not self.filename:
            return True
        from chisurf.core.fluorescence.imaging import is_photon_stream

        return is_photon_stream(self.filename)

    def refresh_display(self, value=None) -> None:
        """Re-render after a channel pick (AutoForm calls bound methods as ``fn(value)``)."""
        self.notify("run")

    def _channel_axis(self):
        """Return the ``channel_axis`` override implied by :attr:`channel_axis_mode`."""
        return {"auto": None, "first axis": 0}.get(self.channel_axis_mode, None)

    def _gate(self):
        """Return the scatter-plane gate rectangle, or ``None`` when disabled."""
        if not self.gate_enabled:
            return None
        if self.gate_a_max <= self.gate_a_min or self.gate_b_max <= self.gate_b_min:
            return None
        return (self.gate_a_min, self.gate_a_max, self.gate_b_min, self.gate_b_max)

    # ── spatial ROI (painted on the channel-A map) ──
    def _roi(self):
        """Return the painted region as a :class:`MaskROI`, or ``None``.

        Returning a ROI rather than a bare array means the painted region
        composes with the other selections (``roi & ThresholdROI(...)``) and
        serialises, like every other region in ChiSurf.
        """
        if self.roi_mask is None:
            return None
        mask = np.asarray(self.roi_mask) > 0
        if not mask.any():
            return None
        from chisurf.core.roi import MaskROI

        return MaskROI(mask, name="painted")

    def brush_kernel(self):
        """Return the paint kernel for the ROI brush (a square of ``brush_size``)."""
        size = max(int(self.brush_size), 1)
        return np.ones((size, size))

    def on_roi_drawn(self) -> None:
        """Recompute after the ROI brush stroke finished."""
        self.compute()

    def clear_roi(self) -> None:
        """Drop the painted ROI and recompute over the whole image."""
        if self.roi_mask is not None:
            self.roi_mask = np.zeros_like(np.asarray(self.roi_mask))
        self.compute()

    # ── compute ──
    def compute(self, progress: Callable[[float, str], None] | None = None) -> bool:
        """Load the image (if needed) and evaluate every colocalization coefficient.

        Parameters
        ----------
        progress : callable, optional
            Called as ``progress(fraction, text)`` while working.

        Returns
        -------
        bool
            Whether the computation produced a result.
        """
        if not self.filename:
            return False
        if progress:
            progress(0.1, "Loading image…")
        try:
            names = self.channel_names()
            channel_a = self.channel_a or (names[0] if names else 0)
            channel_b = self.channel_b or (names[1] if len(names) > 1 else 1)
            out = _core.compute_colocalization(
                self.filename,
                channel_a=channel_a,
                channel_b=channel_b,
                frame=None if int(self.frame) < 0 else int(self.frame),
                windows=self.detectors if (self.detectors and self._uses_windows()) else None,
                channel_axis=self._channel_axis(),
                auto_background=bool(self.auto_background),
                background_quantile=float(self.background_quantile),
                background_a=float(self.background_a),
                background_b=float(self.background_b),
                threshold_a=float(self.threshold_a),
                threshold_b=float(self.threshold_b),
                auto_threshold=bool(self.auto_threshold),
                gate=self._gate(),
                bins=int(self.bins),
                costes_test=bool(self.costes_test),
                costes_block=int(self.costes_block),
                costes_randomizations=int(self.costes_randomizations),
                costes_seed=int(self.costes_seed),
                ccf_max_shift=int(self.ccf_max_shift),
                ccf_2d=bool(self.ccf_max_shift),
                profiles=True,
                profile_bins=int(self.profile_bins),
                roi=self._roi(),
                object_analysis=bool(self.object_analysis),
                object_min_size=int(self.object_min_size),
                object_smoothing=float(self.object_smoothing),
                object_split=bool(self.object_split),
                object_distance=float(self.object_distance),
            )
        except Exception as exc:
            logger.debug("colocalization compute failed", exc_info=True)
            self.results_text = f"Failed: {exc}"
            self.notify("run")
            return False
        if progress:
            progress(0.9, "Computing coefficients…")
        self._stack = out["stack"]
        self._result = out["result"]
        self._metrics = out["metrics"]
        # The brush overlay needs a mask of the image's shape to paint into.
        shape = np.asarray(out["image_a"]).shape
        if self.roi_mask is None or np.asarray(self.roi_mask).shape != shape:
            self.roi_mask = np.zeros(shape, dtype=float)
        names = self.channel_names()
        if names:
            self.channel_a = str(channel_a) if str(channel_a) in names else names[0]
            self.channel_b = (
                str(channel_b) if str(channel_b) in names else names[min(1, len(names) - 1)]
            )
        if self.auto_background:
            self.background_a = self._metrics.get("background_a", self.background_a)
            self.background_b = self._metrics.get("background_b", self.background_b)
        if self.auto_threshold:
            self.threshold_a = self._metrics.get("threshold_a", self.threshold_a)
            self.threshold_b = self._metrics.get("threshold_b", self.threshold_b)
        ny, nx = out["shape"]
        pcc = self._metrics.get("pearson", float("nan"))
        self.results_text = (
            f"{pathlib.Path(self.filename).name} · {nx}×{ny} px · "
            f"{self.channel_a} vs {self.channel_b} · PCC = {pcc:.3f}"
        )
        if self._metrics.get("warning"):
            self.results_text += f"\n⚠ {self._metrics['warning']}"
        self.notify("run")
        return True

    def estimate_background(self) -> None:
        """Set both backgrounds from the current images' low quantile and recompute."""
        if self._result is None:
            self.auto_background = True
            self.compute()
            return
        from chisurf.core.fluorescence.imaging import estimate_background as _estimate

        raw_a = self._result.image_a + self.background_a
        raw_b = self._result.image_b + self.background_b
        self.background_a = _estimate(raw_a, self.background_quantile)
        self.background_b = _estimate(raw_b, self.background_quantile)
        self.auto_background = False
        self.compute()

    def clear_gate(self) -> None:
        """Disable the scatter gate and recompute."""
        self.gate_enabled = False
        self.compute()

    # ── AutoForm accessors ──
    # (:attr:`results_text` is shown in the host's status bar, not in a panel.)
    def metric_rows(self) -> list[dict]:
        """Return the coefficient table rows (``name`` / ``value``)."""
        return _core.metric_rows(self._metrics) if self._metrics else []

    def image_a(self):
        """Return the background-subtracted map of channel A (or ``None``)."""
        return None if self._result is None else self._result.image_a

    def image_b(self):
        """Return the background-subtracted map of channel B (or ``None``)."""
        return None if self._result is None else self._result.image_b

    def coloc_mask_image(self):
        """Return the colocalized-pixel mask as a 0/1 map (or ``None``).

        Pixels inside the scatter gate are marked ``2`` so the gated population is
        visible against the merely above-threshold pixels.
        """
        if self._result is None:
            return None
        mask = self._result.coloc_mask.astype(float)
        if self.gate_enabled:
            mask = mask + self._result.mask.astype(float)
        return mask

    def histogram_image(self):
        """Return the 2-D intensity joint histogram (log-scaled when enabled)."""
        if self._result is None:
            return None
        hist = self._result.histogram.get("histogram")
        if hist is None:
            return None
        return np.log1p(hist) if self.log_histogram else hist

    def ccf_map_image(self):
        """Return the 2-D cross-correlation plane (or ``None``)."""
        if self._result is None or not self._result.ccf_map:
            return None
        return self._result.ccf_map.get("map")

    def profile_series(self) -> list[dict]:
        """Return the intensity-resolved correlation profiles as plot series.

        Three curves — Pearson versus channel A, versus channel B and versus the
        A/B intensity ratio — so a correlation that only exists in bright pixels,
        or that collapses at high intensity, is visible instead of averaged away.
        """
        if self._result is None or not self._result.profiles:
            return []
        labels = {"a": "vs channel A", "b": "vs channel B", "ratio": "vs A/B ratio"}
        colours = {"a": "#2ca02c", "b": "#d62728", "ratio": "#7f7f7f"}
        series = []
        for key, profile in self._result.profiles.items():
            x = np.asarray(profile["x"], dtype=float)
            y = np.asarray(profile["pearson"], dtype=float)
            good = np.isfinite(x) & np.isfinite(y)
            if not good.any():
                continue
            series.append(
                {
                    "x": x[good],
                    "y": y[good],
                    "name": labels.get(key, key),
                    "color": colours.get(key),
                }
            )
        return series

    def object_map_image(self):
        """Return a categorical map of the segmented objects (or ``None``).

        ``1`` = channel-A object only, ``2`` = channel-B object only, ``3`` = both,
        so coincidence is visible directly instead of via two separate masks.
        """
        if self._result is None or not self._result.objects:
            return None
        objects = self._result.objects
        mask_a = objects["objects_a"].mask
        mask_b = objects["objects_b"].mask
        return mask_a.astype(float) + 2.0 * mask_b.astype(float)

    def object_distance_series(self) -> list[dict]:
        """Return the nearest-neighbour object-distance histograms as plot series.

        A peak at short distance is real coincidence; a broad distribution centred
        on the mean inter-object spacing is what chance looks like.
        """
        if self._result is None or not self._result.objects:
            return []
        from chisurf.core.fluorescence.imaging import object_distance_histogram

        objects = self._result.objects
        series = []
        for key, name, colour in (
            ("distances_a", "A → nearest B", "#2ca02c"),
            ("distances_b", "B → nearest A", "#d62728"),
        ):
            histogram = object_distance_histogram(objects[key], bins=20)
            if not np.any(histogram["counts"]):
                continue
            series.append(
                {
                    "x": np.asarray(histogram["x"], dtype=float),
                    "y": np.asarray(histogram["counts"], dtype=float),
                    "name": name,
                    "color": colour,
                }
            )
        return series

    def ccf_series(self) -> list[dict]:
        """Return the van Steensel shift profile as an AutoForm plot series."""
        if self._result is None or not self._result.ccf:
            return []
        ccf = self._result.ccf
        return [
            {"x": np.asarray(ccf["shift"], dtype=float), "y": np.asarray(ccf["ccf"]), "name": "CCF"}
        ]

    # ── scatter gate (driven by the histogram's rectangle ROI) ──
    def gate_rect(self):
        """Return the gate rectangle in histogram-bin coordinates (or ``None``)."""
        if self._result is None or not self.gate_enabled:
            return None
        edges_a = self._result.histogram.get("edges_a")
        edges_b = self._result.histogram.get("edges_b")
        if edges_a is None or edges_b is None or len(edges_a) < 2:
            return None
        return (
            self._to_bin(self.gate_a_min, edges_a),
            self._to_bin(self.gate_b_min, edges_b),
            self._to_bin(self.gate_a_max, edges_a),
            self._to_bin(self.gate_b_max, edges_b),
        )

    def set_gate_from_rect(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """Adopt a rectangle drawn on the histogram (bin coordinates) as the gate."""
        if self._result is None:
            return
        edges_a = self._result.histogram.get("edges_a")
        edges_b = self._result.histogram.get("edges_b")
        if edges_a is None or edges_b is None or len(edges_a) < 2:
            return
        self.gate_a_min = self._to_value(min(x0, x1), edges_a)
        self.gate_a_max = self._to_value(max(x0, x1), edges_a)
        self.gate_b_min = self._to_value(min(y0, y1), edges_b)
        self.gate_b_max = self._to_value(max(y0, y1), edges_b)
        self.gate_enabled = True
        self.compute()

    @staticmethod
    def _to_value(bin_index: float, edges) -> float:
        """Map a (fractional) histogram bin index to an intensity."""
        edges = np.asarray(edges, dtype=float)
        lo, hi = float(edges[0]), float(edges[-1])
        n = len(edges) - 1
        return float(lo + (hi - lo) * (float(bin_index) / n)) if n > 0 else lo

    @staticmethod
    def _to_bin(value: float, edges) -> float:
        """Map an intensity to a (fractional) histogram bin index."""
        edges = np.asarray(edges, dtype=float)
        lo, hi = float(edges[0]), float(edges[-1])
        n = len(edges) - 1
        if hi <= lo or n <= 0:
            return 0.0
        return float((float(value) - lo) / (hi - lo) * n)

    # ── export ──
    def export_csv(self, path: str) -> str:
        """Write the coefficient table to *path* as CSV and return the path."""
        import csv

        with open(path, "w", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["source", self.filename])
            writer.writerow(["channel_a", self.channel_a])
            writer.writerow(["channel_b", self.channel_b])
            writer.writerow([])
            writer.writerow(["metric", "value"])
            for key, value in self._metrics.items():
                writer.writerow([key, value])
        return path
