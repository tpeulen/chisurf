"""Native snapshot-safe operations over the existing scientific view model."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from .view_model import MicroTimeViewModel


class NativeMicroTimeModel(MicroTimeViewModel):
    COLUMN_UNITS = {**MicroTimeViewModel.COLUMN_UNITS, "mean_micro_time": "nanoseconds"}

    def __copy__(self):
        snapshot = type(self).__new__(type(self))
        snapshot.__dict__ = dict(self.__dict__)
        snapshot.detectors = copy.deepcopy(self.detectors)
        for name in ("_by_window", "_columns", "_movie_cache"):
            setattr(snapshot, name, dict(getattr(self, name)))
        snapshot._observers = list(self._observers)
        return snapshot

    def compute(self, progress=None):
        if not super().compute(progress=progress):
            return False
        # tttrlib uses -1 for pixels below threshold; the imaging product uses
        # zero for discriminated pixels, never a physically negative arrival time.
        for maps in self._by_window.values():
            for key in ("mean_micro_time", "mt_frames"):
                if key in maps:
                    maps[key] = np.maximum(np.nan_to_num(maps[key]), 0.0)
        for window, maps in self._by_window.items():
            self._columns[f"mean_micro_time ({window})"] = maps["mean_micro_time"]
        return True

    def artifact_name(self):
        # Keep the legacy artifact identity; native class names are not data identifiers.
        return "mean_micro_time"

    def load_file(self, path):
        source = str(path)
        if source == self.filename:
            return
        self._by_window = {}
        self._columns = {}
        self._movie_cache = {}
        self._last_signature = None
        self.pipeline_hdf5 = ""
        self.filename = source
        self.results_text = "File selected. Press Run to compute pixel maps."
        self.notify("changed")

    def apply_pipeline_context(self, payload):
        source = payload.get("source")
        if source and str(source) != self.filename:
            self.load_file(source)
        super().apply_pipeline_context(payload)

    def compute_job(self):
        if not self.filename:
            raise ValueError("Choose a TTTR imaging file first.")
        if not self.needs_recompute():
            self.notify("run")
            return

        def progress(fraction, text):
            self.results_text = f"{float(fraction) * 100:.0f}% · {text}"
            self.notify("progress")

        if not self.compute(progress=progress):
            raise RuntimeError(self.results_text)
        if not self._columns:
            raise RuntimeError("No detector-window maps were produced.")
        self.notify("run")

    def save_hdf5(self, path):
        if not self._columns:
            raise ValueError("Run the mean-micro-time calculation first.")
        added = self._write_hdf5(str(path))
        self._register_hdf5_snapshot(str(path))
        self.pipeline_hdf5 = str(path)
        self.results_text = f"Created {len(added)} columns → {Path(path).name}"
        self.notify("saved")

    def save_container(self):
        path = self.write_container()
        if not path:
            raise ValueError("Run a source image before saving the container.")
        self.results_text = "Saved container → " + str(path)
        self.notify("saved")
