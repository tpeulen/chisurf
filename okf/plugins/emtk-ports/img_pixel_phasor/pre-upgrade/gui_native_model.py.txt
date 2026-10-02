"""Snapshot-safe phasor operations retaining the Qt scientific estimator."""

from __future__ import annotations

import copy
import threading

from chisurf.plugins.microscopy.img_pixel_intensity.gui.native_model import NativeIntensityModel

from .view_model import PhasorImgViewModel


class NativePhasorModel(PhasorImgViewModel):
    save_hdf5 = NativeIntensityModel.save_hdf5
    save_container = NativeIntensityModel.save_container
    load_file = NativeIntensityModel.load_file

    def __init__(self):
        super().__init__()
        self._cancel = threading.Event()

    def __copy__(self):
        snapshot = NativeIntensityModel.__copy__(self)
        snapshot.cursors = copy.deepcopy(self.cursors)
        return snapshot

    @property
    def gates(self):
        return self.cursors

    @gates.setter
    def gates(self, value):
        self.cursors = value

    plane_extent = PhasorImgViewModel.cursor_extent
    notify_gates = PhasorImgViewModel.notify_cursors
    gate_summary = PhasorImgViewModel.cursor_summary

    def clear_gates(self):
        from chisurf.core.roi import RegionCollection

        self.cursors = RegionCollection(combine="or", name="cursor")
        self.notify_cursors()

    def artifact_name(self):
        return "phasor"

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
                raise RuntimeError("Phasor calculation cancelled.")
            self.results_text = f"{100 * fraction:.0f}% · {text}"
            self.notify("progress")

        if not self.compute(progress):
            raise RuntimeError(self.results_text)
        if self._cancel.is_set():
            raise RuntimeError("Phasor calculation cancelled.")
        if not self._columns:
            raise RuntimeError("No detector-window maps were produced.")
        self.notify("run")
