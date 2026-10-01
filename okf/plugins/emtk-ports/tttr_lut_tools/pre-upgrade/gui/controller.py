"""Qt-free LUT workspace state and correction pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..api import io, settings
from .view_model import LutComputeViewModel

EXTENSIONS = {".spc", ".ht3", ".ptu", ".phu", ".photonhdf5", ".t3r", ".t2r", ".pto"}
COLORS = [
    (31, 119, 180),
    (255, 127, 14),
    (44, 160, 44),
    (214, 39, 40),
    (148, 103, 189),
    (140, 86, 75),
    (227, 119, 194),
    (127, 127, 127),
    (188, 189, 34),
    (23, 190, 207),
]
PARAMETERS = (
    "linear_start",
    "linear_stop",
    "ntac_required",
    "noffset",
    "preview_photons",
    "seed",
    "normalize",
    "mitigate_wrap",
    "eps",
    "threshold",
)


class LutWorkspace:
    """Preserve compute/assign/import/export state independently of presentation."""

    def __init__(self, apply_callback=None):
        self.compute = LutComputeViewModel()
        self.files = []
        self.reading_routine = None
        self.channel_luts = {}
        self.channel_shifts = {}
        self.loaded_luts = {}
        self.selected_lut = ""
        self.active_channel = None
        self.visible = set()
        self.raw = {}
        self.corrected = {}
        self.log_y = True
        self.show_lut = False
        self.apply_callback = apply_callback
        self.message = ""

    @staticmethod
    def expand(paths):
        result = []
        for path in paths:
            path = Path(path)
            candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
            for candidate in candidates:
                if candidate.is_file() and candidate.suffix.lower() in EXTENSIONS:
                    name = str(candidate)
                    if name not in result:
                        result.append(name)
        return result

    def load_compute(self, paths):
        paths = self.expand(paths)
        if not paths:
            raise ValueError("No supported TTTR files.")
        self.compute.load_files(paths)

    def load_preview(self, paths):
        paths = self.expand(paths)
        if not paths:
            self.files, self.raw, self.corrected = [], {}, {}
            self.visible.clear()
            self.active_channel = None
            return
        # Same LUT-aware production read as all ChiSurf readers. Combine per-file
        # photon histograms, rather than pooling channels into a common TAC LUT.
        micro, routing = io.load_micro_and_routing(paths, self.reading_routine)
        bins = max(int(micro.max()) + 1, len(next(iter(self.channel_luts.values()), [])))
        channels = sorted(int(value) for value in np.unique(routing))
        self.raw = {
            ch: np.bincount(micro[routing == ch].astype(int), minlength=bins) for ch in channels
        }
        self.files = paths
        self.visible = set(channels)
        if self.active_channel not in channels:
            self.active_channel = channels[0] if channels else None
        self.refresh_corrected()

    def refresh_corrected(self):
        if not self.files:
            self.corrected = {}
            return
        micro_parts, route_parts = [], []
        for path in self.files:
            tttr = settings.apply_luts_to_tttr(
                path, self.channel_luts, self.channel_shifts, self.reading_routine
            )
            micro_parts.append(np.asarray(tttr.micro_times))
            route_parts.append(np.asarray(tttr.routing_channels))
        micro, routing = np.concatenate(micro_parts), np.concatenate(route_parts)
        bins = max((len(v) for v in self.raw.values()), default=1)
        bins = max(bins, int(micro.max()) + 1 if micro.size else 1)
        self.corrected = {
            ch: np.bincount(micro[routing == ch].astype(int), minlength=bins) for ch in self.raw
        }

    def receive_computed_lut(self, name, lut, channel=None):
        lut = np.asarray(lut, dtype=float)
        if lut.ndim != 1 or not lut.size or not np.all(np.isfinite(lut)):
            raise ValueError("Expected a nonempty, finite one-dimensional LUT.")
        self.loaded_luts[str(name)] = lut.copy()
        self.selected_lut = str(name)
        if channel is not None:
            self.channel_luts[int(channel)] = lut.copy()

    def bridge(self):
        luts = self.compute.compute_all_channels()
        if not luts:
            raise ValueError("Load a uniform-illumination file and compute a LUT first.")
        for channel, lut in luts.items():
            self.receive_computed_lut(f"ch{channel}_lut", lut, channel)
        self.refresh_corrected()
        return luts

    def import_lut(self, path):
        self.receive_computed_lut(Path(path).name, io.load_lut_file(str(path)))

    def remove_lut(self, name=None):
        self.loaded_luts.pop(name or self.selected_lut, None)
        self.selected_lut = next(iter(self.loaded_luts), "")

    def clear_luts(self):
        self.loaded_luts.clear()
        self.channel_luts.clear()
        self.selected_lut = ""
        self.refresh_corrected()

    def assign(self, all_channels=False):
        if self.selected_lut not in self.loaded_luts:
            raise ValueError("Select a loaded LUT first.")
        channels = sorted(self.raw) if all_channels else [self.active_channel]
        if not channels or channels == [None]:
            raise ValueError("Load preview files and select a routing channel.")
        for channel in channels:
            self.channel_luts[channel] = self.loaded_luts[self.selected_lut].copy()
        self.refresh_corrected()

    def set_shift(self, value):
        if self.active_channel is None:
            raise ValueError("Select a routing channel first.")
        self.channel_shifts[self.active_channel] = int(value)
        self.refresh_corrected()

    def bundle(self):
        return settings.build_settings_dict(
            self.channel_luts, self.channel_shifts, self.reading_routine, sorted(self.raw)
        )

    def import_settings(self, path):
        data = settings.load_settings(str(path))
        self.channel_luts = data["channel_luts"]
        self.channel_shifts = data["channel_shifts"]
        self.reading_routine = data["reading_routine"]
        for channel, lut in self.channel_luts.items():
            self.receive_computed_lut(f"ch{channel}_lut", lut)
        if self.files:
            self.load_preview(self.files)

    def export_settings(self, path):
        return settings.save_settings(str(path), self.bundle())

    def apply(self):
        data = self.bundle()
        if self.apply_callback is None:
            raise ValueError(
                "Open LUT tools from a detector setup to apply the correction; "
                "standalone users can save settings.tttr.json."
            )
        self.apply_callback(data)
        return data

    def get_state(self):
        return {
            "parameters": {key: getattr(self.compute, key) for key in PARAMETERS},
            "compute_files": self.compute.files,
            "files": self.files,
            "compute_channel": self.compute.channel,
            "log_y": self.log_y,
            "show_lut": self.show_lut,
            "active_channel": self.active_channel,
            "visible": sorted(self.visible),
            "selected_lut": self.selected_lut,
            "loaded_luts": {key: value.tolist() for key, value in self.loaded_luts.items()},
            "settings": settings.json_safe(self.bundle()),
        }

    def set_state(self, state):
        for key, value in state.get("parameters", {}).items():
            if key in PARAMETERS:
                setattr(self.compute, key, value)
        data = state.get("settings", {})
        self.reading_routine = data.get("reading_routine")
        self.channel_luts = {
            int(ch): np.asarray(lut, dtype=float)
            for ch, lut in data.get("channel_luts", {}).items()
        }
        self.channel_shifts = {int(ch): int(v) for ch, v in data.get("channel_shifts", {}).items()}
        for name, lut in state.get("loaded_luts", {}).items():
            self.receive_computed_lut(name, lut)
        self.selected_lut = state.get("selected_lut", self.selected_lut)
        self.log_y, self.show_lut = state.get("log_y", True), state.get("show_lut", False)
        if state.get("compute_files"):
            # Loading auto-detects a plateau. Restore the hand-tuned parameters
            # afterwards so reload does not silently erase the calibration.
            params = state.get("parameters", {})
            self.load_compute(state["compute_files"])
            self.compute.channel = state.get("compute_channel", self.compute.channel)
            self.compute._select_channel()
            for key in PARAMETERS:
                if key in params:
                    setattr(self.compute, key, params[key])
            self.compute.compute()
        if state.get("files"):
            self.load_preview(state["files"])
        self.active_channel = state.get("active_channel", self.active_channel)
        self.visible = set(state.get("visible", self.visible))

    def save_preferences(self, path):
        Path(path).write_text(json.dumps(self.get_state(), indent=2), encoding="utf-8")
