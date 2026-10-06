"""The emtk side of a per-pixel imaging tool (intensity, mean micro-time, phasor, N&B).

``PixelModelMixin`` goes in front of an :class:`~chisurf.plugins.microscopy.imaging_common.base.ImagingMapViewModel`
subclass (the analysis, shared unchanged with the Qt tool) and adds what a window without a toolbar and a status bar needs:
the action methods the spec's buttons call, the worker bodies, a status line, the file-dialog requests, the snapshot copy the
worker runs on and the imaging hub's adapters. Nothing here imports Qt.
"""

from __future__ import annotations

import copy
import pathlib
import threading
from typing import Any

from .model_base import EmtkModelMixin

#: Files the Open dialog lists (the Qt file field's photon-stream types).
PHOTON_FILE_FILTER = "Photon streams (*.ptu *.pto *.ht3 *.pt3 *.spc);;All files (*)"
HDF5_FILE_FILTER = "Imaging HDF5 (*.h5 *.hdf5);;All files (*)"


class PixelModelMixin(EmtkModelMixin):
    """Actions, worker bodies and hub adapters of a per-pixel map tool.

    Class attributes a tool sets
    ----------------------------
    TOOL_NAME : str
        What the status line calls a run ("Intensity", "N&B", ...).
    HDF5_CREATES : bool
        The HDF5 button creates the file (Intensity); otherwise it adds columns to the pipeline's file.
    SETTINGS : tuple of str
        Analysis settings saved by ``export_settings`` (the file and the results are never saved).
    """

    TOOL_NAME = "Pixel maps"
    HDF5_CREATES = False
    #: extra events a run announces (the tour waits for them)
    ndx_requested: bool = False
    _pending_path: str = ""

    # -- snapshot --------------------------------------------------------- #
    def __copy__(self):
        """What a worker runs on: the result containers and the detectors are its own, the rest is shared."""
        snapshot = type(self).__new__(type(self))
        snapshot.__dict__ = dict(self.__dict__)
        snapshot.detectors = copy.deepcopy(self.detectors)
        for name in ("_by_window", "_columns", "_movie_cache"):
            setattr(snapshot, name, dict(getattr(self, name)))
        snapshot._observers = list(self._observers)
        for name in self.COPIED:
            if hasattr(self, name):
                setattr(snapshot, name, copy.deepcopy(getattr(self, name)))
        return snapshot

    #: further mutable attributes a snapshot must not share (regions, ...)
    COPIED: tuple[str, ...] = ()

    @property
    def cancel_event(self) -> threading.Event:
        event = self.__dict__.get("_cancel_event")
        if event is None:
            event = self.__dict__["_cancel_event"] = threading.Event()
        return event

    def artifact_name(self) -> str:
        return self.WINDOW_KIND or self.TOOL_NAME.lower().replace(" ", "_")

    # -- choices and enabling ---------------------------------------------- #
    def enabled(self, name: str) -> bool:
        """Actions are greyed while a worker runs (its result replaces the model's state)."""
        if self.busy:
            return False
        if name == "next_step":
            return bool(getattr(self, "has_host", False))
        if name in ("request_hdf5", "save_container", "open_ndx"):
            return bool(self._columns)
        if name == "run_maps":
            return bool(self.filename)
        return True

    def colormap_choices(self) -> list[str]:
        return ["magma", "inferno", "viridis", "gray"]

    # -- the file ------------------------------------------------------------ #
    def open_file(self) -> None:
        self.request_dialog("open")

    def open_database(self) -> None:
        self.request_dialog("database")

    def open_path(self, path: str) -> None:
        """Select *path* (a dialog, a picker or a typed path): the maps are computed when Run is pressed, as in the Qt tool."""
        if not path:
            return
        self.remember_folder(path)
        self.select_file(str(path))

    def commit_filename(self, value: str) -> None:
        """A path typed into the field and committed."""
        value = str(value or "").strip()
        if value:
            self.select_file(value)

    def select_file(self, path: str) -> None:
        """Adopt a new source file and drop the previous result (the Qt file field only selected)."""
        if path != self.filename or not self._columns:
            self._by_window = {}
            self._columns = {}
            self._movie_cache = {}
            self._last_signature = None
            if path != self.filename:
                self.pipeline_hdf5 = ""
        self.filename = path
        self.results_text = f"{pathlib.Path(path).name} selected."
        self.status_line = "File selected. Press Run to compute the maps."
        self.notify("file")

    def on_paths_dropped(self, paths: list[str]) -> bool:
        """A dropped file is loaded and run, as the Qt tool did."""
        if not paths:
            return False
        self.select_file(str(paths[0]))
        self.run_maps()
        return True

    # -- running ------------------------------------------------------------- #
    def run_maps(self) -> None:
        """Compute every detector window in the background (the Qt Run)."""
        if not self.filename:
            self.results_text = "No file selected."
            self.status_line = "No file selected."
            return
        if not self.needs_recompute():
            self.status_line = "Nothing changed since the last run; the maps are up to date."
            self.notify("run")
            return
        self.cancel_event.clear()
        self.status_line = f"Computing {self.TOOL_NAME}..."
        self.run_job("compute_job")

    def cancel(self) -> None:
        """Stop at the next progress checkpoint and discard the unfinished result."""
        self.cancel_event.set()
        self.status_line = "Cancelling..."

    def compute_job(self) -> None:
        """The worker body: compute, then say what came out."""
        if not self.filename:
            raise ValueError("Choose a TTTR imaging file first.")
        if not self.needs_recompute():
            self.notify("run")
            return

        def progress(fraction, text):
            if self.cancel_event.is_set():
                raise RuntimeError(f"{self.TOOL_NAME} calculation cancelled.")
            self.results_text = f"{100 * float(fraction):.0f} % {text}"
            self.notify("progress")

        ok = self.compute(progress)
        if self.cancel_event.is_set():
            raise RuntimeError(f"{self.TOOL_NAME} calculation cancelled.")
        if not ok:
            raise RuntimeError(self.results_text)
        if not self._columns:
            raise RuntimeError("No detector-window maps were produced.")
        self.after_compute()
        self.status_line = ""
        self.notify("run")

    def after_compute(self) -> None:
        """A tool's own follow-up on the worker (N&B: the cross maps)."""

    # -- the outputs -------------------------------------------------------------- #
    def request_hdf5(self) -> None:
        """Write the columns to the imaging HDF5: the pipeline's file when there is one, otherwise a chosen one (the Qt HDF5 action)."""
        if not self._columns:
            self.status_line = "Nothing to add — press Run first."
            self.results_text = self.status_line
            return
        if self.pipeline_hdf5:
            self._pending_path = self.pipeline_hdf5
            self.status_line = "Writing the imaging HDF5..."
            self.run_job("hdf5_job")
            return
        self.request_dialog("hdf5")

    def dialog_filename(self, kind: str) -> str:
        if kind == "save_regions":
            return "regions.json"
        return pathlib.Path(self._default_hdf5_path() or f"{self.artifact_name()}.imaging.h5").name

    def write_hdf5(self, path: str) -> None:
        """A path chosen in the dialog."""
        self.remember_folder(path)
        self._pending_path = str(path)
        self.status_line = "Writing the imaging HDF5..."
        self.run_job("hdf5_job")

    def hdf5_job(self) -> None:
        """The worker body: write the file and remember it pipeline-wide (the Qt ``add_to_hdf5``)."""
        path = self._pending_path
        added = self._write_hdf5(path)
        self._register_hdf5_snapshot(path)
        self.pipeline_hdf5 = path
        if callable(self.pipeline_sink):
            self.pipeline_sink(source=self.filename or None, hdf5=path)
        self.results_text = f"added {len(added)} column(s) → {pathlib.Path(path).name}"
        self.status_line = self.results_text
        self.notify("saved")

    def save_container(self) -> None:
        """Write the maps into the source's container (the Qt tool did this when it closed)."""
        if not self._columns:
            self.status_line = "Nothing to save — press Run first."
            return
        self.status_line = "Writing the container..."
        self.run_job("container_job")

    def container_job(self) -> None:
        path = self.write_container()
        if not path:
            raise ValueError("Run a source image before saving the container.")
        self.results_text = f"Saved container → {path}"
        self.status_line = self.results_text
        self.notify("saved")

    def open_ndx(self) -> None:
        """Explore the live table in ndX (the Qt ndX action opened a window; the app shows it over the maps)."""
        table = self.to_table()
        if table is None:
            self.status_line = "Nothing to explore — press Run first."
            self.results_text = self.status_line
            return
        self.ndx_requested = True
        self.notify("ndx")

    #: set by the app, which owns the coordinator
    next_callback: Any = None

    def next_step(self) -> None:
        """Go on to the next analysis step (the app hands the file and the HDF5 to the coordinator)."""
        if callable(self.next_callback):
            self.next_callback()

    # -- the tab that is shown (a choice, because a row of ten tabs does not fit a window) -------------------- #
    view_tab: str = ""
    tab_titles_list: tuple = ()

    def tab_titles(self) -> list[str]:
        return list(self.tab_titles_list)

    def show_tab(self, value: str = "") -> None:
        """The View choice changed: the app brings that tab forward."""
        self.notify("view")

    # -- regions drawn on a plane (cursors, gates) ------------------------------------------ #
    #: name of the RegionCollection attribute (tools with a plane set it)
    REGIONS_ATTR = ""

    def save_regions(self, path: str) -> None:
        """Save the regions as JSON, with their flags and the combine rule (the dialog's handler)."""
        path = str(path)
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            getattr(self, self.REGIONS_ATTR).save(path)
        except Exception as exc:
            self.status_line = f"Could not save the regions: {exc}"
            return
        self.remember_folder(path)
        self.status_line = f"Wrote {path}"

    def load_regions(self, path: str) -> None:
        """Append the regions of a JSON file (the dialog's handler)."""
        from chisurf.core.roi import RegionCollection

        try:
            loaded = RegionCollection.load(str(path))
        except Exception as exc:
            self.status_line = f"Could not read the regions: {exc}"
            return
        collection = getattr(self, self.REGIONS_ATTR)
        for entry in loaded:
            collection.add(entry.roi, enabled=entry.enabled, invert=entry.invert)
        self.remember_folder(str(path))
        self.status_line = f"Loaded {len(loaded)} region(s) from {path}"
        self.regions_changed()

    def regions_changed(self) -> None:
        """The regions were edited: the views that depend on them are redrawn."""
        self.notify("regions")

    def clear_regions(self) -> None:
        getattr(self, self.REGIONS_ATTR).clear()
        self.regions_changed()

    # -- the tool's settings ---------------------------------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        state = super().export_settings()
        state.update(
            display_window=self.display_window,
            colormap=self.colormap,
            detectors=copy.deepcopy(self.detectors),
        )
        return state

    def restore_settings(self, state: dict[str, Any]) -> None:
        super().restore_settings(state)
        if not isinstance(state, dict):
            return
        if isinstance(state.get("colormap"), str) and state["colormap"] in self.colormap_choices():
            self.colormap = state["colormap"]
        if isinstance(state.get("detectors"), dict):
            self.detectors = copy.deepcopy(state["detectors"])
        if isinstance(state.get("display_window"), str):
            self.display_window = state["display_window"]

    # -- hub adapters ---------------------------------------------------------------------- #
    def apply_pipeline_context(self, payload: dict) -> None:
        """Adopt the toolbox pipeline's source and HDF5 (a new source is selected, not run: the hub starts the run)."""
        if not isinstance(payload, dict):
            return
        source = payload.get("source")
        if source and str(source) != self.filename:
            self.select_file(str(source))
        if payload.get("hdf5"):
            self.pipeline_hdf5 = str(payload["hdf5"])

    def apply_setup_settings(self, payload: dict) -> None:
        super().apply_setup_settings(payload)
        self.status_line = self.status_line or ""

    def window_rows(self) -> list[dict]:
        """The detector windows that are computed: name, channels, micro-time ranges."""
        return [
            {
                "window": name,
                "channels": ", ".join(str(c) for c in d.get("chs", [])),
                "micro_time_ranges": ", ".join(
                    f"{r[0]}-{r[1]}" for r in (d.get("micro_time_ranges") or [])
                ),
            }
            for name, d in self._windows().items()
        ]

    @property
    def summary_text(self) -> str:
        return self.results_text
