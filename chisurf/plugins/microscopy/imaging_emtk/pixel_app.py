"""The window shell of a per-pixel imaging tool (intensity, mean micro-time, phasor, N&B).

On top of :class:`~.app_base.ImagingToolApp` (settings form from a spec, dock windows, file dialogs, worker, help and guide)
this adds what the four photon-stream tools share: the imaging hub's contract (``coordinator``, ``start``, the setup / pipeline /
calibration adapters, ``Next``), the ndX explorer shown over the maps, the shared detector editor as a window of its own,
a Cancel button while a worker runs, and an MMFDB binding. The tools differ only in their spec and their maps.
"""

from __future__ import annotations

import copy
from typing import Any

from emtk import im

from chisurf.plugins.emtk_layout import layout_spec

from .app_base import ImagingToolApp
from .pixel_model import HDF5_FILE_FILTER, PHOTON_FILE_FILTER

#: Height of the bar that takes you back from ndX to the maps.
NDX_BAR = 40.0


class PixelToolApp(ImagingToolApp):
    """Base of the per-pixel map apps; subclasses name their spec, layout and hub role."""

    #: the role the imaging hub knows this tool by (``advance_from(ROLE)``)
    ROLE = ""
    CANCELLABLE = True
    #: show the shared detector editor as a window (the tools compute one map set per detector window)
    DETECTOR_EDITOR = True
    DIALOGS = {
        "open": ("Open photon image", "open", PHOTON_FILE_FILTER, "open_path"),
        "hdf5": ("Create imaging HDF5", "save", HDF5_FILE_FILTER, "write_hdf5"),
    }
    OUTCOMES = {"file": "filename", "run": "run_maps", "saved": "request_hdf5", "ndx": "open_ndx"}
    REGION_DIALOGS = {
        "save_regions": ("Save regions", "save", "JSON (*.json)", "save_regions"),
        "load_regions": ("Load regions", "open", "JSON (*.json)", "load_regions"),
    }

    def __init__(self, model: Any, coordinator: Any = None, ndx_callback: Any = None, **binding: Any) -> None:
        if any(binding.get(key) for key in ("mmfdb_db", "mmfdb_source_artifact_id", "mmfdb_principal")):
            if not all(binding.get(key) for key in ("mmfdb_db", "mmfdb_source_artifact_id", "mmfdb_principal")):
                raise ValueError("MMFDB imaging binding requires db, source artifact and principal.")
            model.bind_mmfdb(binding["mmfdb_db"], source_artifact_id=binding.get("mmfdb_source_artifact_id", ""),
                             sample_id=binding.get("mmfdb_sample_id", ""), principal=binding.get("mmfdb_principal"))
        self.coordinator = coordinator
        self.ndx_callback = ndx_callback
        self.ndx = None
        self.view_ndx = False
        self._painter = None
        self._ndx_box = (0.0, NDX_BAR, 1000.0, 700.0)
        self.editor = None
        self._editor_busy = False
        self.planes: dict[str, Any] = {}
        self.region_lists: dict[str, Any] = {}
        self._pending: dict[str, Any] = {}
        super().__init__(model)
        self.DIALOGS = {**type(self).DIALOGS, **self.REGION_DIALOGS}
        self.form.custom["plane"] = lambda section, m, st, w: self._draw_plane(section)
        self.form.custom["region_list"] = lambda section, m, st, w: self._draw_region_list(section)
        model.tab_titles_list = tuple(t for t, w in self.windows.items() if w.get("dock") == "views" and t != "Detectors") + (("Detectors",) if self.editor is not None or self.DETECTOR_EDITOR else ())
        model.view_tab = model.tab_titles_list[0] if model.tab_titles_list else ""
        model.has_host = coordinator is not None
        model.next_callback = self.next_step
        model.pipeline_sink = model.pipeline_sink if callable(model.pipeline_sink) else None
        if self.DETECTOR_EDITOR:
            self._make_editor()

    def prepare_spec(self, spec: dict) -> dict:
        """Capped field widths and one grid per kind of field (``emtk_layout``)."""
        return layout_spec(spec)

    # -- the shared detector editor -------------------------------------------------- #
    def _make_editor(self) -> None:
        """The detector / channel editor of the Setup tool, embedded as the "Detectors" window."""
        try:
            from chisurf.core.setup_channel_definition import ChannelDefinition
            from chisurf.emtk.channel_definition import ChannelDefinitionWidget
        except Exception:  # the editor is optional: the tool computes the channel-0 window without it
            return
        self.editor = ChannelDefinitionWidget(model=ChannelDefinition(self._editor_settings()), on_changed=self._editor_changed)
        self.editor.on_used = self.tour.notify_used
        self.docks.add_window("Detectors", "Detectors", lambda box: self._draw_editor(), dock="views", closable=False)
        self.windows["Detectors"] = {"title": "Detectors", "dock": "views"}

    def _editor_settings(self) -> dict:
        """What the editor shows: the detector windows this tool computes (the channel-0 window when none were set)."""
        detectors = {}
        for name, det in self.model._windows().items():
            detectors[name] = {"chs": list(det.get("chs", [0])), "micro_time_ranges": [list(r) for r in (det.get("micro_time_ranges") or [])],
                               "g_factor": 1.0, "l1": 0.0, "l2": 0.0}
        return {"windows": {}, "detectors": detectors,
                "tttr_reading": {"file_type": "PTU", "macro_time_resolution": 50.0, "micro_time_resolution": 50.0, "micro_time_binning": 1}}

    def _editor_changed(self, settings: dict) -> None:
        """A window or detector was edited: the tool computes the new windows on its next run."""
        if self._editor_busy:
            return
        self.model.apply_setup_settings(copy.deepcopy(settings))
        self.model.status_line = "Detector windows changed. Press Run to recompute."

    def _draw_editor(self) -> None:
        if self.editor is not None:
            self.editor.draw()
            self.item_rects.update({f"detectors.{k}": v for k, v in self.editor.item_rects.items()})
            if self.editor.item_rects.get("section_detectors"):
                self.item_rects["Detectors"] = self.editor.item_rects["section_detectors"]

    # -- planes and region lists ---------------------------------------------------------- #
    def add_plane(self, name: str, panel: Any, regions: Any = None) -> None:
        """Register a plane view (and the region list that edits what it shows) under the name a spec section refers to."""
        self.planes[name] = panel
        if regions is not None:
            self.region_lists[name] = regions

    def _draw_plane(self, section: dict) -> None:
        name = str(section.get("options", {}).get("name", section.get("title", "")))
        panel = self.planes[name]
        panel.draw(self.model.colormap)
        self.model.colormap = panel.canvas.colormap
        if panel.rect[2] > 0:
            self.item_rects[str(section.get("title", name))] = panel.rect

    def _draw_region_list(self, section: dict) -> None:
        from emtk import im as _im

        name = str(section.get("options", {}).get("name", section.get("title", "")))
        controls = self.region_lists[name]
        controls.draw()
        summary = getattr(self.model, str(section.get("options", {}).get("summary", "")), None)
        if callable(summary):
            _im.text_wrapped(summary())
        if section.get("options", {}).get("clear", True):
            if _im.button(f"Clear all##{name}"):
                self.model.clear_regions()
            _im.set_item_tooltip("Remove every region; all pixels are selected again.")
            self.item_rects[f"{name}.clear"] = _im.get_item_rect()

    # -- hub contract ----------------------------------------------------------------- #
    def start(self, method: str = "compute_job", *args: Any) -> bool:
        """The hub's ``autorun_role`` starts the run through this."""
        if method == "compute_job":
            self.model.cancel_event.clear()
        return self.start_job(method)

    def apply_setup_settings(self, payload: dict) -> None:
        """The hub's shared detector setup (applied after a running job has delivered)."""
        if self.job.busy or self.model.busy:
            self._pending["setup"] = copy.deepcopy(payload)
            return
        self.model.apply_setup_settings(payload)
        self._sync_editor(payload)
        self.request_frame()

    def _sync_editor(self, payload: dict | None = None) -> None:
        """Show the windows the model computes in the detector editor (without answering with a change)."""
        if self.editor is None:
            return
        self._editor_busy = True
        try:
            self.editor.load_definition(copy.deepcopy(payload) if payload else self._editor_settings())
        except Exception:  # an editor that cannot take the payload keeps its own windows
            pass
        finally:
            self._editor_busy = False

    def apply_pipeline_context(self, payload: dict) -> None:
        if self.job.busy or self.model.busy:
            self._pending["pipeline"] = dict(payload)
            return
        previous = self.model.filename
        self.model.apply_pipeline_context(payload)
        if self.model.filename != previous and self.model.filename:
            self.start("compute_job")
        self.request_frame()

    def apply_calibration(self, payload: dict) -> None:
        if self.job.busy or self.model.busy:
            self._pending["calibration"] = copy.deepcopy(payload)
            return
        self.model.apply_calibration(payload)
        self.request_frame()

    def _flush_pending(self) -> None:
        if self.job.busy or self.model.busy or not self._pending:
            return
        pending, self._pending = dict(self._pending), {}
        if "setup" in pending:
            self.apply_setup_settings(pending["setup"])
        if "calibration" in pending:
            self.model.apply_calibration(pending["calibration"])
        if "pipeline" in pending:
            self.apply_pipeline_context(pending["pipeline"])

    def next_step(self) -> None:
        """Remember the source and the HDF5 and advance the pipeline (the Qt ``Next``)."""
        if self.coordinator is None:
            self.model.status_line = "Open this tool inside the Imaging Tools pipeline to use Next."
            return
        self.coordinator.set_pipeline(source=self.model.filename or None, hdf5=self.model.pipeline_hdf5 or None)
        self.coordinator.advance_from(self.ROLE)

    def export_settings(self) -> dict:
        state = self.model.export_settings()
        state["panels"] = {name: {"colormap": p.canvas.colormap, "fps": getattr(p, "fps", 10), "loop": getattr(p, "loop", True)}
                           for name, p in self.panels.items()}
        state["docks"] = self.docks.state()
        return state

    def restore_settings(self, state: dict) -> None:
        if self.job.busy or not isinstance(state, dict):
            return
        self.model.restore_settings(state)
        self._sync_editor()
        for name, saved in (state.get("panels") or {}).items():
            panel = self._panel(name, lambda key: self._new_panel(key))
            if saved.get("colormap") in ("magma", "inferno", "viridis", "gray"):
                panel.canvas.colormap = saved["colormap"]
            if isinstance(saved.get("fps"), int):
                panel.fps = max(1, min(120, saved["fps"]))
            panel.loop = bool(saved.get("loop", True))
        if state.get("docks"):
            self.docks.restore(state["docks"])
        if self.model.filename and not self.model._columns:
            self.start("compute_job")

    def _new_panel(self, key: str):
        from .views import ImagePanel

        return ImagePanel(key)

    # -- ndX over the maps ---------------------------------------------------------------- #
    def _on_event(self, event: str) -> None:
        super()._on_event(event)
        if event == "view":
            if self.model.view_tab in self.windows:
                self.docks.focus(self.model.view_tab)
        elif event == "ndx":
            self.model.ndx_requested = False
            self.open_ndx()
        elif event in ("run", "saved") and self.ndx is not None:
            was_visible = self.view_ndx
            self._load_ndx()
            self.view_ndx = was_visible

    def open_ndx(self) -> None:
        table = self.model.to_table()
        if table is None:
            self.model.status_line = "Nothing to explore — press Run first."
            return
        if self.ndx_callback:
            self.ndx_callback(table)
            return
        self._load_ndx()
        self.view_ndx = self.ndx is not None

    def _load_ndx(self) -> None:
        table = self.model.to_table()
        if table is None:
            return
        try:
            if self.ndx is None:
                from chisurf.plugins.ndxplorer.gui.app import make_app

                self.ndx = make_app()
            from chisurf.plugins.microscopy.imaging_common.base import build_ndx_data_source

            self.ndx.model.set_source(build_ndx_data_source(table))
        except Exception as exc:
            self.ndx = None
            self.model.status_line = f"ndX failed: {exc}"

    def _draw_main(self, box: tuple) -> None:
        self._flush_pending()
        if self.view_ndx and self.ndx is not None:
            x, y, w, h = box
            im.set_next_window_pos((x, y), im.Cond.ALWAYS)
            im.set_next_window_size((w, NDX_BAR), im.Cond.ALWAYS)
            if im.begin(f"{self.TITLE} navigation", flags=im.WindowFlags.NO_TITLE_BAR):
                if im.button("Back to the maps"):
                    self.view_ndx = False
                im.set_item_tooltip("Return to the maps; ndX keeps its selection.")
                self.item_rects["ndx_back"] = im.get_item_rect()
            im.end()
            self._ndx_box = (x, y + NDX_BAR, w, max(1.0, h - NDX_BAR))
            if self._painter is not None:
                self.draw_child(self._painter, self.ndx, *self._ndx_box, local_coordinates=True)
        else:
            super()._draw_main(box)
        if self.editor is not None:
            self.editor.draw_dialogs(box)

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        super().draw(painter, x, y, w, h)
        self._painter = None

    def animating(self) -> bool:
        return bool(super().animating() or (self.view_ndx and self.ndx is not None and self.ndx.animating()))

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        super().pointer_press(x, y, button, modifiers, clicks)
        if self.view_ndx and self.ndx is not None and y >= self._ndx_box[1]:
            self.ndx.pointer_press(x - self._ndx_box[0], y - self._ndx_box[1], button, modifiers, clicks)

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        if self.view_ndx and self.ndx is not None:
            self.ndx.pointer_release(x - self._ndx_box[0], y - self._ndx_box[1], button, modifiers)

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if self.view_ndx and self.ndx is not None:
            self.ndx.pointer_move(x - self._ndx_box[0], y - self._ndx_box[1], buttons, modifiers)

    def wheel(self, x, y, steps, modifiers=0):
        super().wheel(x, y, steps, modifiers)
        if self.view_ndx and self.ndx is not None and y >= self._ndx_box[1]:
            self.ndx.wheel(x - self._ndx_box[0], y - self._ndx_box[1], steps, modifiers)

    def key(self, key, text="", modifiers=0):
        if self.view_ndx and self.ndx is not None:
            return self.ndx.key(key, text, modifiers)
        return super().key(key, text, modifiers)

    def close(self) -> None:
        """A computed session flushes its standard HDF5 and container (the Qt tool's contract); ndX closes."""
        try:
            self.model.flush_to_hdf5()
        except Exception:
            pass
        if self.ndx is not None and callable(getattr(self.ndx, "close", None)):
            self.ndx.close()
        super().close()
