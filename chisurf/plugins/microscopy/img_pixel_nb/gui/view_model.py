"""Qt-free view-model backing the Number & Brightness imaging tool.

Computes the N&B maps (apparent B and N, molecular brightness ε and number n)
for **every** detector window of the step-0 setup, with the stack corrections,
detrending, dead-time / analog-detector corrections and moment smoothing the
settings select, and adds them to the standard imaging HDF5.

On top of the per-window maps it offers the two interactive readouts of an N&B
experiment: a **parameter plane** (e.g. brightness versus intensity) on which
gate regions pick out a population and back-map it onto the pixels, and **cross
N&B** between the displayed window and a second one.
"""

from __future__ import annotations

import pathlib
from typing import Any

import numpy as np

from chisurf.core.roi import RegionCollection
from chisurf.plugins.microscopy.imaging_common.base import ImagingMapViewModel

_VIEW_JSON = pathlib.Path(__file__).parent / "nb.view.json"

#: Map keys offered as axes of the parameter plane, with their display labels.
PLANE_AXES = {
    "mean": "intensity ⟨k⟩",
    "B": "apparent brightness B",
    "N": "apparent number N",
    "epsilon": "brightness ε",
    "n": "number n",
}

#: Value of the cross-window choice that switches cross N&B off.
CROSS_OFF = "(off)"


class NBViewModel(ImagingMapViewModel):
    """State + logic for the interactive N&B imaging tool (no Qt)."""

    HDF5_ACTION_LABEL = "➕ Add N&B to HDF5"
    WINDOW_KIND = "nb"
    OPERATION_TYPE = "number_and_brightness"
    #: Counts per pixel dwell; N and n are molecule numbers.
    COLUMN_UNITS = {
        "N": "dimensionless",
        "n": "dimensionless",
        "B": "counts",
        "epsilon": "counts",
        "mean": "counts",
        "variance": "counts",
    }

    def __init__(self) -> None:
        super().__init__(_VIEW_JSON)
        # ── stack corrections ──
        self.subtract: str = "none"
        self.add: str = "none"
        self.box_pixels: int = 3
        self.box_frames: int = 3
        self.background: float = 0.0
        self.detrend_segments: int = 0
        # ── detector ──
        self.dead_time_ns: float = 0.0
        self.pixel_dwell_us: float = 0.0
        self.gain: float = 1.0
        self.offset: float = 0.0
        self.read_variance: float = 0.0
        # ── estimator ──
        self.smoothing: str = "none"
        self.radius: float = 3.0
        self.median: bool = False
        self.gamma: float = 1.0
        # ── parameter plane / gating ──
        self.plane_x: str = "mean"
        self.plane_y: str = "B"
        self.plane_bins: int = 64
        self.log_histogram: bool = True
        #: Gate regions on the parameter plane (the shared region list).
        self.gates = RegionCollection(combine="or", name="gate")
        # ── cross N&B ──
        self.cross_window: str = CROSS_OFF
        self.colormap = "magma"

    # ── compute plumbing ──
    def _window_params(self) -> dict:
        """Return the N&B pipeline settings for the worker (``nb_pipeline`` keys)."""
        return {
            "subtract": str(self.subtract),
            "add": str(self.add),
            "box_pixels": int(self.box_pixels),
            "box_frames": int(self.box_frames),
            "background": float(self.background),
            "detrend_segments": int(self.detrend_segments),
            "dead_time": float(self.dead_time_ns),
            "pixel_dwell": float(self.pixel_dwell_us) * 1000.0,  # µs -> ns
            "smoothing": str(self.smoothing),
            "radius": float(self.radius),
            "median": bool(self.median),
            "gamma": float(self.gamma),
            "gain": float(self.gain),
            "offset": float(self.offset),
            "read_variance": float(self.read_variance),
        }

    def _extra_signature(self) -> tuple:
        """Settings that change the maps (for recompute dedup)."""
        return tuple(sorted(self._window_params().items()))

    def _summary(self, ny: int, nx: int) -> str:
        """File, windows and the median ε / n of every window."""
        lines = [super()._summary(ny, nx)]
        for win, maps in self._by_window.items():
            mean = maps.get("mean")
            eps = maps.get("epsilon")
            n = maps.get("n")
            if mean is None or eps is None or n is None:
                continue
            valid = np.asarray(mean) > 0
            if valid.any():
                lines.append(
                    f"{win}: median ε = {np.median(eps[valid]):.3g}, "
                    f"n = {np.median(n[valid]):.3g}, ⟨k⟩ = {np.mean(mean[valid]):.3g}"
                )
        return "\n".join(lines)

    # ── image accessors (view.json `image` sections; displayed window) ──
    def n_map(self):
        """Return the apparent-number (N) map of the displayed window."""
        return self._disp("N")

    def b_map(self):
        """Return the apparent-brightness (B) map of the displayed window."""
        return self._disp("B")

    def epsilon_map(self):
        """Return the molecular-brightness (ε) map of the displayed window."""
        return self._disp("epsilon")

    def number_map(self):
        """Return the molecule-number (n) map of the displayed window."""
        return self._disp("n")

    # ── parameter plane + gates ──
    def plane_axis_names(self) -> list[str]:
        """Keys selectable as parameter-plane axes."""
        return list(PLANE_AXES)

    def _plane_data(self):
        x = self._disp(self.plane_x)
        y = self._disp(self.plane_y)
        mean = self._disp("mean")
        if x is None or y is None or mean is None:
            return None
        return np.asarray(x, float), np.asarray(y, float), np.asarray(mean, float) > 0

    def plane_extent(self) -> tuple:
        """``(x0, x1, y0, y1)`` the parameter plane spans (outlier-trimmed ranges)."""
        data = self._plane_data()
        if data is None:
            return (0.0, 1.0, 0.0, 1.0)
        from chisurf.core.fluorescence.imaging import nb_default_ranges

        maps = {k: self._disp(k) for k in ("mean", "variance", self.plane_x, self.plane_y)}
        maps = {k: v for k, v in maps.items() if v is not None}
        ranges = nb_default_ranges(maps, keys=(self.plane_x, self.plane_y))
        (x0, x1), (y0, y1) = ranges[self.plane_x], ranges[self.plane_y]
        if self.plane_x == "mean":
            x0 = min(x0, 0.0)
        return (float(x0), float(x1), float(y0), float(y1))

    def plane_histogram(self):
        """2-D histogram of the displayed window on the parameter plane (row-major)."""
        data = self._plane_data()
        if data is None:
            return None
        from chisurf.core.fluorescence.imaging import nb_histogram_2d

        x, y, valid = data
        x0, x1, y0, y1 = self.plane_extent()
        hist = nb_histogram_2d(x, y, (x0, x1), (y0, y1), bins=int(self.plane_bins), mask=valid)
        return np.log1p(hist) if self.log_histogram else hist

    def gate_mask(self):
        """Pixels the gate regions select on the parameter plane (all valid pixels if none)."""
        data = self._plane_data()
        if data is None:
            return None
        from chisurf.core.fluorescence.imaging import nb_gate_mask

        x, y, valid = data
        return nb_gate_mask(x, y, self.gates.combined(), base_mask=valid)

    def gated_intensity_map(self):
        """Intensity of the gated pixels, zero elsewhere — the population, back on the image."""
        intensity = self._disp("intensity")
        mask = self.gate_mask()
        if intensity is None or mask is None:
            return intensity
        return np.where(mask, np.asarray(intensity, float), 0.0)

    def gate_summary(self) -> str:
        """One line: how many pixels the gates select and their median ε / n."""
        mask = self.gate_mask()
        mean = self._disp("mean")
        if mask is None or mean is None:
            return "Run first; then draw a gate on the parameter plane."
        valid = np.asarray(mean) > 0
        picked = int(mask.sum())
        total = int(valid.sum())
        if not picked:
            return f"0 of {total} px selected."
        eps = np.asarray(self._disp("epsilon"))[mask]
        n = np.asarray(self._disp("n"))[mask]
        return (
            f"{picked} of {total} px ({100.0 * picked / max(total, 1):.1f} %): "
            f"median ε = {np.median(eps):.3g}, n = {np.median(n):.3g}"
        )

    def results_html(self) -> str:
        """Status text plus, once gates exist, what they select."""
        text = self.results_text
        if len(self.gates) and self._by_window:
            text = f"{text}\nGates: {self.gate_summary()}"
        return f"<pre>{text}</pre>"

    def notify_gates(self) -> None:
        """Tell the views the gate set changed."""
        self.notify("gate")

    def clear_gates(self) -> None:
        """Drop every gate region."""
        self.gates.clear()
        self.notify_gates()

    # ── cross N&B ──
    def cross_window_names(self) -> list[str]:
        """Choices for the cross-N&B partner window."""
        return [CROSS_OFF] + [w for w in self.window_names() if w != self.display_window]

    def _cross(self) -> dict[str, Any] | None:
        if self.cross_window in ("", CROSS_OFF) or self.cross_window == self.display_window:
            return None
        a = self._disp("frames")
        b = (self._by_window.get(self.cross_window) or {}).get("frames")
        if a is None or b is None or np.shape(a) != np.shape(b):
            return None
        params = self._window_params()
        sig = (self.filename, self.display_window, self.cross_window, tuple(sorted(params.items())))

        def build():
            from chisurf.core.fluorescence.imaging import ccnb_maps, prepare_stack

            return ccnb_maps(
                prepare_stack(a, params),
                prepare_stack(b, params),
                dead_time=params["dead_time"],
                pixel_dwell=params["pixel_dwell"],
                smoothing=params["smoothing"],
                radius=params["radius"],
            )

        return self._cached_stack("cross_nb", sig, build)

    def cross_brightness_map(self):
        """Cross brightness ``B_cross = C/√(⟨a⟩⟨b⟩)`` of the displayed and the cross window."""
        cross = self._cross()
        return None if cross is None else cross["B_cross"]

    def cross_number_map(self):
        """Cross number ``N_cross = ⟨a⟩⟨b⟩/C`` of the displayed and the cross window."""
        cross = self._cross()
        return None if cross is None else cross["N_cross"]

    # ── analog detector calibration ──
    def calibrate_analog(self) -> None:
        """Set gain S and offset k₀ from the displayed window of a static-gradient file.

        Load a calibration measurement (a sample that does not fluctuate but spans
        a range of intensities), run, then press this: the per-pixel variance is
        fitted as a straight line against the mean, and the slope and the offset
        replace the detector settings. The read-noise variance is taken as set.
        """
        mean = self._disp("mean")
        variance = self._disp("variance")
        if mean is None or variance is None:
            self.results_text = "Calibration needs a computed map: load the gradient file and Run."
            self.notify("changed")
            return
        from chisurf.core.fluorescence.imaging import analog_calibration

        try:
            cal = analog_calibration(mean, variance, read_variance=float(self.read_variance))
        except ValueError as exc:
            self.results_text = f"Calibration failed: {exc}"
            self.notify("changed")
            return
        self.gain = cal["gain"]
        self.offset = cal["offset"]
        self.results_text = (
            f"Analog calibration from {pathlib.Path(self.filename).name} ({self.display_window}): "
            f"S = {cal['gain']:.4g}, offset = {cal['offset']:.4g} (R² = {cal['r2']:.3f}). "
            "Load the measurement and Run."
        )
        self.notify("changed")

    # ── demo ──
    def load_demo(self) -> dict:
        """Write (or reuse) the monomer/dimer demo photon stream and load it."""
        from chisurf.plugins.microscopy.img_pixel_nb.demo import create_demo

        info = create_demo()
        self.detectors = {}
        self.display_window = "ch0"
        self.load_file(info["path"])
        return info
