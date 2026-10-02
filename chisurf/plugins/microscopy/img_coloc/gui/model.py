"""Qt-free model of the emtk colocalization window (the analysis is :class:`~.view_model.ColocViewModel`, shared with the Qt tool).

Everything the Qt tool did on its thread pool (the run, and the recomputes after an edit of a gate or the painted region) runs on a worker here:
``compute`` called on the displayed model starts the worker, ``compute_job`` is the worker's body.
"""

from __future__ import annotations

import copy
import pathlib
import threading
from typing import Any

import numpy as np

from chisurf.core.roi import RegionCollection

from ...imaging_emtk.model_base import EmtkModelMixin
from .view_model import ColocViewModel

IMAGE_FILE_FILTER = "Images and photon streams (*.pto *.tif *.tiff *.png *.ptu *.ht3 *.spc);;All files (*)"


class ColocModel(EmtkModelMixin, ColocViewModel):
    """Two-channel colocalization plus the state of the emtk window."""

    SETTINGS = ("channel_a", "channel_b", "frame", "channel_axis_mode", "auto_background", "background_quantile", "background_a", "background_b",
                "auto_threshold", "threshold_a", "threshold_b", "gate_enabled", "gate_a_min", "gate_a_max", "gate_b_min", "gate_b_max", "bins",
                "log_histogram", "costes_test", "costes_block", "costes_randomizations", "costes_seed", "ccf_max_shift", "profile_bins", "object_analysis",
                "object_min_size", "object_smoothing", "object_split", "object_distance", "brush_size", "colormap")

    def __init__(self) -> None:
        ColocViewModel.__init__(self)
        self.status_line = ""
        self.paint_roi = False
        self.paint_gate = False
        self.erase = False
        self.view_tab = ""
        self.tab_titles_list: tuple = ()
        self._direct = False
        self._cancel_event = threading.Event()
        self.dirty_roi = False
        self.dirty_gate = False
        self.mask_version = 0

    # -- snapshot ------------------------------------------------------------------------- #
    def __copy__(self):
        snapshot = type(self).__new__(type(self))
        snapshot.__dict__ = dict(self.__dict__)
        for name in ("detectors", "gates", "roi_mask", "gate_paint"):
            setattr(snapshot, name, copy.deepcopy(getattr(self, name)))
        snapshot._observers = list(self._observers)
        return snapshot

    def _windows(self) -> dict:
        return self.detectors

    # -- the computation, on a worker ------------------------------------------------------ #
    def compute(self, progress=None) -> bool:  # type: ignore[override]
        """The Qt ``compute`` called from the window runs on a worker; the worker's own call (``compute_job``) runs it."""
        if progress is None and not self._direct and self.runner is not None:
            if not self.filename:
                return False
            self.status_line = "Computing colocalization..."
            return bool(self.run_job("compute_job"))
        return ColocViewModel.compute(self, progress)

    def compute_job(self) -> None:
        self._direct = True
        try:
            ok = ColocViewModel.compute(self, progress=self._progress)
        finally:
            self._direct = False
        self.status_line = "" if ok else self.results_text
        self.notify("computed")

    def run_coloc(self) -> None:
        """Compute the selected channel pair (the Qt Run)."""
        if not self.filename:
            self.status_line = "Choose an image first."
            return
        self.compute()

    def cancel(self) -> None:
        pass

    def enabled(self, name: str) -> bool:
        if self.busy:
            return False
        if name in ("run_coloc", "estimate_background"):
            return bool(self.filename)
        if name == "request_export":
            return bool(self._metrics)
        return True

    # -- the file --------------------------------------------------------------------------- #
    def open_file(self) -> None:
        self.request_dialog("open")

    def open_database(self) -> None:
        self.request_dialog("database")

    def open_path(self, path: str) -> None:
        """A file chosen in a dialog, the picker or typed: it is loaded and run, as in the Qt tool."""
        if not path:
            return
        self.remember_folder(path)
        self.set_filename(str(path))
        self.compute()

    def commit_filename(self, value: str) -> None:
        value = str(value or "").strip()
        if value:
            self.open_path(value)

    def on_paths_dropped(self, paths: list[str]) -> bool:
        if not paths:
            return False
        self.open_path(str(paths[0]))
        return True

    def apply_pipeline_context(self, payload: dict) -> None:
        source = (payload or {}).get("source")
        if source and str(source) != self.filename:
            self.open_path(str(source))

    def apply_setup_settings(self, payload: dict) -> None:
        super().apply_setup_settings(payload)
        if self.filename:
            self.compute()

    # -- the Qt actions that recompute ------------------------------------------------------- #
    def clear_roi(self) -> None:
        """Drop the painted region and analyse the whole image again."""
        if self.roi_mask is not None:
            self.roi_mask = np.zeros_like(np.asarray(self.roi_mask))
        self.mask_version += 1
        self.compute()

    def gates_edited(self) -> None:
        """A gate region was added, moved or removed: the typed box follows its ``box`` region, the gate is on while there is one, and the result is recomputed."""
        box = self.gates.get("box")
        if box is not None and hasattr(box.roi, "x0"):
            self.gate_a_min, self.gate_b_min = float(box.roi.x0), float(box.roi.y0)
            self.gate_a_max, self.gate_b_max = float(box.roi.x1), float(box.roi.y1)
        elif box is None and len(self.gates):
            self.gate_a_max = self.gate_a_min
            self.gate_b_max = self.gate_b_min
        self.gate_enabled = bool(len(self.gates))
        self.notify("gate")
        self.compute()

    # the region editor's contract (shared with the other imaging tools)
    REGIONS_ATTR = "gates"

    def regions_changed(self) -> None:
        self.gates_edited()

    def clear_regions(self) -> None:
        self.clear_gate()

    def save_regions(self, path: str) -> None:
        path = str(path)
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            self.gates.save(path)
        except Exception as exc:
            self.status_line = f"Could not save the regions: {exc}"
            return
        self.remember_folder(path)
        self.status_line = f"Wrote {path}"

    def load_regions(self, path: str) -> None:
        try:
            loaded = RegionCollection.load(str(path))
        except Exception as exc:
            self.status_line = f"Could not read the regions: {exc}"
            return
        for entry in loaded:
            self.gates.add(entry.roi, enabled=entry.enabled, invert=entry.invert)
        self.remember_folder(str(path))
        self.status_line = f"Loaded {len(loaded)} region(s) from {path}"
        self.gates_edited()

    # -- painting ------------------------------------------------------------------------------ #
    def paint(self, target: str, y: int, x: int) -> None:
        """One brush dab on the painted region (``roi_mask``, pixels) or the painted gate (``gate_paint``, histogram bins)."""
        mask = getattr(self, target)
        if mask is None:
            return
        half = max(int(self.brush_size), 1) // 2
        mask[max(0, y - half):y + half + 1, max(0, x - half):x + half + 1] = 0 if self.erase else 1
        self.mask_version += 1
        self.dirty_roi |= target == "roi_mask"
        self.dirty_gate |= target == "gate_paint"

    def end_stroke(self) -> None:
        """The pointer was released after painting: recompute with the painted region / gate."""
        if self.dirty_roi:
            self.dirty_roi = False
            self.compute()
        if self.dirty_gate:
            self.dirty_gate = False
            self.on_gate_painted()

    # -- the export ------------------------------------------------------------------------------ #
    def request_export(self) -> None:
        self.request_dialog("export")

    def dialog_filename(self, kind: str) -> str:
        if kind == "save_regions":
            return "regions.json"
        return pathlib.Path(self.filename).with_suffix(".coloc.csv").name if self.filename else "colocalization.csv"

    def write_export(self, path: str) -> None:
        try:
            self.export_csv(str(path))
        except OSError as exc:
            self.status_line = f"Could not write {path}: {exc}"
            return
        self.remember_folder(path)
        self.status_line = f"Wrote {path}"

    # -- views ------------------------------------------------------------------------------------ #
    def tab_titles(self) -> list[str]:
        return list(self.tab_titles_list)

    def show_tab(self, value: str = "") -> None:
        self.notify("view")

    @property
    def summary_text(self) -> str:
        return self.results_text

    def export_settings(self) -> dict[str, Any]:
        state = super().export_settings()
        state.update(gates=self.gates.to_dict(), detectors=copy.deepcopy(self.detectors), setup_name=self.setup_name)
        return state

    def restore_settings(self, state: dict) -> None:
        super().restore_settings(state)
        if not isinstance(state, dict):
            return
        if isinstance(state.get("gates"), dict):
            try:
                self.gates = RegionCollection.from_dict(state["gates"])
            except Exception:
                pass
        if isinstance(state.get("detectors"), dict):
            self.detectors = copy.deepcopy(state["detectors"])
        if isinstance(state.get("setup_name"), str):
            self.setup_name = state["setup_name"]

    def channel_axis_mode_choices(self) -> list[str]:
        return ["auto", "first axis"]

    def colormap_choices(self) -> list[str]:
        return ["magma", "inferno", "viridis", "gray"]
