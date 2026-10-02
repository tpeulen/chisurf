"""Snapshot-safe native N&B operations; the estimator is shared with Qt."""

from __future__ import annotations

import copy
import threading

from chisurf.plugins.microscopy.img_pixel_intensity.gui.native_model import NativeIntensityModel

from .view_model import NBViewModel


class NativeNBModel(NBViewModel):
    save_hdf5 = NativeIntensityModel.save_hdf5
    save_container = NativeIntensityModel.save_container

    def __copy__(self):
        snapshot = NativeIntensityModel.__copy__(self)
        snapshot.gates = copy.deepcopy(self.gates)
        return snapshot

    def artifact_name(self):
        return "nb"

    def load_file(self, path):
        if str(path) != self.filename:
            self._by_window = {}
            self._columns = {}
            self._movie_cache = {}
            self._last_signature = None
            self.pipeline_hdf5 = ""
        self.filename = str(path)
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
            return

        def progress(fraction, text):
            if self._cancel.is_set():
                raise RuntimeError("N&B calculation cancelled.")
            self.results_text = f"{100 * fraction:.0f}% · {text}"
            self.notify("progress")

        if not self.compute(progress):
            raise RuntimeError(self.results_text)
        if self._cancel.is_set():
            raise RuntimeError("N&B calculation cancelled.")
        if not self._columns:
            raise RuntimeError("No detector-window maps were produced.")
        self._cross()
        self.notify("run")

    def compute_cross_job(self):
        if self._cancel.is_set():
            raise RuntimeError("N&B calculation cancelled.")
        self._cross()
        if self._cancel.is_set():
            raise RuntimeError("N&B calculation cancelled.")
        self.notify("run")

    def __init__(self):
        super().__init__()
        self._cancel = threading.Event()
