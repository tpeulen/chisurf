"""Native emtk Region MLE tool (form from ``region_mle_emtk.view.json``).

The spec is drawn by :func:`emtk.view_form.draw_form`; the file lists, the
analysis-region editor, the region image and the decay plot are the spec's
``custom`` sections, drawn by callbacks registered in
:attr:`emtk.view_form.FormState.custom`. All state and work is in
:class:`~.model.RegionMleModel` (the plugin's view-model); the fit runs on a
:class:`chisurf.emtk.jobs.SnapshotJob`.

The three top-level sections of the spec become three docked windows:
*Analysis* (the form), *Regions* (list, fit summary and image with the region
overlay) and *Decay* (residuals above the log decay).
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.emtk.jobs import SnapshotJob
from chisurf.emtk.regions import RegionControls

from .model import PHOTON_FILE_FILTER, RegionMleModel

HERE = Path(__file__).parent

#: Dialog requests the model/regions can make -> (title, mode, filters, file name).
DIALOGS = {
    "add_files": ("Add imaging files", "open", PHOTON_FILE_FILTER, ""),
    "add_irf": ("Choose the IRF file", "open", PHOTON_FILE_FILTER, ""),
    "export": ("Export region table", "save", "Tables (*.tsv *.csv)", "regions.tsv"),
    "open_results": ("Open results", "open", "Tables (*.tsv *.csv);;All files (*)", ""),
    "save_regions": ("Save regions", "save", "Regions (*.json *.tif *.tiff *.npy)", "regions.json"),
    "load_regions": (
        "Load regions",
        "open",
        "Regions (*.json *.tif *.tiff *.npy);;All files (*)",
        "",
    ),
}

_BREAKS = re.compile(r"<\s*(?:br|p|div)\s*/?>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")


def plain_text(rich: str) -> str:
    """Flatten the view-model's small HTML summaries (``<b>``, ``<br>``) to text."""
    return html.unescape(_TAGS.sub("", _BREAKS.sub("\n", rich))).strip()


class RegionMleApp(ImApp):
    """Region MLE: fit one lifetime per detected region and inspect each decay."""

    def __init__(self, model: RegionMleModel | None = None) -> None:
        self.model = model or RegionMleModel()
        self.job = SnapshotJob(self.model)
        self.model.add_observer(self._on_event)
        self.spec = json.loads((HERE / "region_mle_emtk.view.json").read_text(encoding="utf-8"))
        self.windows = self.spec["sections"][0]["sections"]
        self.form = FormState()
        self.form.custom.update(
            path_list=self._draw_path_list,
            region_list=self._draw_region_list,
            image_browser=self._draw_image_browser,
            decay_panel=self._draw_decay_panel,
        )
        self.canvas = ImageCanvas("region_image")
        self.canvas.colormap = "inferno"
        self.controls = RegionControls(
            self.model, self._request_dialog, get_image=self.model.segmentation_image
        )
        self.picker = DatasetPicker(
            formats=["ptu", "pto", "ht3", "spc", "pt3"], on_paths=self._picked_paths
        )
        self.picker_target = "sel_files"
        self.dialog: FileDialog | None = None
        self.dialog_kind = ""
        self.item_rects: dict[str, tuple] = {}
        self.selected: dict[str, int] = {}
        self.region_filter = ""
        self.error = ""
        self._reported_error = ""
        self._job_method = ""
        self._view_key: Any = None
        self._view: dict[str, Any] = {}
        self._decay_key: Any = None
        self._decay_xlim = [0.0, 1.0]
        self.help_window = EmTkHelpWindow(
            title="Region MLE — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self._used
        self.docks = DockManager(
            Split("h", 0.34, Region("analysis"), Region("results"))
        )
        for key, section, draw in zip(
            ("analysis", "regions", "decay"),
            self.windows,
            (self._draw_analysis, self._draw_regions, self._draw_decay),
        ):
            # Regions and Decay are tabs of one region, as in the Qt tool: the image
            # needs the height its own controls leave, which a split cannot give it.
            dock = "analysis" if key == "analysis" else "results"
            self.docks.add_window(key, section["title"], draw, dock=dock, closable=False)
        super().__init__(self.render, continuous=False)

    # ── jobs ───────────────────────────────────────────────────────────
    def start_job(self, method: str) -> bool:
        """Run the model method *method* on a snapshot in a worker thread."""
        self.model.error_text = ""
        self._reported_error = ""
        started = self.job.start(method)
        if started:
            self._job_method = method
            self.model.busy = True
        return started

    def _on_event(self, event: str) -> None:
        """Turn the buttons' ``start_*`` announcements into work (draw thread only)."""
        if event == "start_run":
            self.start_job("run")
        elif event == "start_preview":
            self.start_job("preview_regions")
        elif event == "start_demo":
            self.start_job("load_demo")
        elif event == "start_export":
            self._request_dialog("export")

    def animating(self) -> bool:
        """Keep drawing while a worker runs, so its result appears."""
        return self.job.busy or self.picker.is_open or super().animating()

    # ── one frame ──────────────────────────────────────────────────────
    def render(self) -> None:
        was_busy = self.job.busy
        self.job.poll()
        self.model.busy = self.job.busy
        self.model.progress_text = self.job.progress if self.job.busy else ""
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            self.model.error_text = self.job.error
        if was_busy and not self.job.busy:
            self._job_finished()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self._open_requested_dialog()
        self._follow_tour()
        self.docks.draw(box)
        self._draw_dialog(box)
        self.picker.render(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _follow_tour(self) -> None:
        """Bring the Decay tab forward while the tour points at it."""
        if self.tour.active and self.tour.steps:
            target = self.tour.steps[self.tour.step_idx].get("target")
            if self.tour._target_key(target) == "Decay":
                self.docks.focus("decay")

    def _job_finished(self) -> None:
        """Release the tour's outcome steps: the demo is loaded, the regions measured."""
        if self.model.error_text:
            return
        if self._job_method in ("preview_regions", "run") and self.model.molecule_entries():
            self.docks.focus("regions")
        if self._job_method == "load_demo":
            self.tour.notify_used("Load demo")
        elif self._job_method in ("preview_regions", "run") and self.model.molecule_entries():
            self.tour.notify_used("Preview")

    def _used(self, name: str) -> None:
        self.tour.notify_used(name)

    # ── windows ────────────────────────────────────────────────────────
    def _collect_rects(self) -> None:
        """Name the controls by the labels the guide points at."""
        rects = self.form.rects
        for key, name in (
            ("Load demo", "request_demo"),
            ("Preview", "request_preview"),
            ("Regions", "Regions.fold"),
            ("Fit (Fit23)", "Fit (Fit23).fold"),
        ):
            if name in rects:
                self.item_rects[key] = rects[name]

    def _draw_analysis(self, box: Any) -> None:
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain what the fit does, what a region needs and how to read the decay.")
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through the demo: load it, preview the regions, run and read a decay.")
        self.item_rects["guide"] = im.get_item_rect()
        im.separator()
        # The analysis form: the panel of the first window, drawn in place.
        panel = self.windows[0]
        draw_sections(panel.get("sections") or [], self.model, self.form, 1, True)
        self._collect_rects()
        if self.error:
            im.text_wrapped(self.error)

    def _draw_regions(self, box: Any) -> None:
        draw_sections([self.windows[1]], self.model, self.form)

    def _draw_decay(self, box: Any) -> None:
        draw_sections([self.windows[2]], self.model, self.form)

    # ── custom section: a list of files ────────────────────────────────
    def _draw_path_list(self, section: dict, model: RegionMleModel, state: FormState,
                        width: float) -> None:
        """The CLSM or IRF file list with Add, Database, Remove and Clear."""
        target = section["target"]
        title = section.get("title", target)
        im.text_unformatted(title)
        im.set_item_tooltip(section.get("description", ""))
        start = im.get_item_rect()
        paths = list(getattr(model, target))
        index = min(self.selected.get(target, 0), max(len(paths) - 1, 0))
        if not paths:
            im.text_disabled("No file. Add or drop one.")
        for i, path in enumerate(paths):
            if im.selectable(f"{Path(path).name}##{target}{i}", index == i):
                self.selected[target] = index = i
            im.set_item_tooltip(path)
        self.item_rects[title] = state.rects[target] = start
        busy = model.busy or self.dialog is not None or self.picker.is_open
        room = im.get_content_region_avail()[0]
        used = 0.0
        for label, tip, needs_files, act in (
            ("Add files", "Choose photon files to add." if target == "sel_files"
             else "Choose the IRF measurement.", False,
             lambda: setattr(self.model, "dialog", section.get("options", {}).get("add", "add_files"))),
            ("Database", "Pick a registered photon dataset from the MMFDB catalogue.", False,
             lambda: self._open_picker(target)),
            ("Remove", "Remove the selected file from the list.", True,
             lambda: self._remove_path(target, index)),
            ("Clear", "Empty the list without deleting any file.", True,
             lambda: self._clear_paths(target)),
        ):
            width = im.calc_text_size(label)[0] + 16.0
            if used and used + 6.0 + width <= room:
                im.same_line()
            used = used + 6.0 + width if used and used + 6.0 + width <= room else width
            im.begin_disabled(busy or (needs_files and not paths))
            if im.button(f"{label}##{target}"):
                act()
            im.set_item_tooltip(tip)
            im.end_disabled()

    def _open_picker(self, target: str) -> None:
        self.picker_target = target
        self.picker.open()

    def _remove_path(self, target: str, index: int) -> None:
        paths = list(getattr(self.model, target))
        setattr(self.model, target, [p for i, p in enumerate(paths) if i != index])
        self.selected[target] = max(0, index - 1)
        self.model.notify("settings")

    def _clear_paths(self, target: str) -> None:
        setattr(self.model, target, [])
        self.selected[target] = 0
        self.model.notify("settings")

    def _picked_paths(self, paths: Any) -> None:
        self.model.add_paths(self.picker_target, [str(p) for p in paths])

    # ── custom section: the analysis region ────────────────────────────
    def _draw_region_list(self, section: dict, model: RegionMleModel, state: FormState,
                          width: float) -> None:
        """Named regions the fit is confined to (add, edit, combine, save, load)."""
        im.text_unformatted(section.get("title", "Analysis region"))
        im.set_item_tooltip(section.get("description", ""))
        im.begin_disabled(model.busy or self.dialog is not None)
        self.controls.draw()
        im.end_disabled()
        self.item_rects["Analysis region"] = state.rects["regions"] = im.get_item_rect()

    # ── custom section: the region image ───────────────────────────────
    def _view_of_results(self) -> dict[str, Any]:
        """Everything derived from the results, rebuilt only when they or the selection change."""
        model = self.model
        key = (tuple(id(r) for r in model.results), int(model.current_molecule))
        if key != self._view_key:
            self._view_key = key
            found = model.molecule_regions()
            labels = []
            for entry in found:
                roi = entry.roi
                labels.append({"text": str(entry.name).rsplit(" ", 1)[-1],
                               "x": float(roi.cx), "y": float(roi.cy)})
            self._view = dict(
                entries=model.molecule_entries(),
                image=model.segmentation_image(),
                marker=model.current_molecule_marker(),
                info=plain_text(model.current_molecule_info()),
                curves=model.current_region_curves(),
                found=found,
                labels=labels,
            )
            self.canvas.reset()
        return self._view

    def _draw_image_browser(self, section: dict, model: RegionMleModel, state: FormState,
                            width: float) -> None:
        """Filterable region list with its fit summary, and the image with region overlays."""
        view = self._view_of_results()
        entries = view["entries"]
        _, self.region_filter = im.input_text("Filter regions", self.region_filter,
                                              hint="Region name")
        im.set_item_tooltip("Show only regions whose name contains this text; the image is unchanged.")
        shown = [e for e in entries if self.region_filter.casefold() in e["label"].casefold()]
        if shown:
            current = next((i for i, e in enumerate(shown) if e["id"] == model.current_molecule), 0)
            changed, index = im.combo(
                "Region", current, [f"{e['label']}   {e['badge']}" for e in shown]
            )
            im.set_item_tooltip(section.get("description", ""))
            if changed:
                model.current_molecule = int(shown[index]["id"])
            self.item_rects["Regions.list"] = im.get_item_rect()
        else:
            im.text_disabled("No regions yet. Run or Preview, or open saved results.")
        im.text_wrapped(view["info"])
        editable = not model.busy and self.dialog is None and not self.picker.is_open
        self.canvas.draw(
            view["image"],
            markers=view["marker"],
            found=view["found"],
            labels=view["labels"],
            analysis=model.regions,
            on_change=model.apply_regions,
            pick_enabled=False,
            analysis_editable=editable,
        )
        self.item_rects["image"] = state.rects["segmentation_image"] = tuple(
            self.canvas.rect or (0, 0, 0, 0)
        )

    # ── custom section: the decay ──────────────────────────────────────
    def _draw_decay_panel(self, section: dict, model: RegionMleModel, state: FormState,
                          width: float) -> None:
        """Weighted residuals above the log decay, sharing the channel axis."""
        curves = self._view_of_results()["curves"]
        if curves is None:
            im.text_disabled("Select a region with a fitted decay.")
            self.item_rects["Decay"] = im.get_item_rect()
            return
        n = len(curves.channels)
        key = (id(curves), n)
        if key != self._decay_key:
            self._decay_key = key
            self._decay_xlim[:] = [-0.5, n - 0.5]
        height = max(120.0, im.get_content_region_avail()[1] - 6.0)
        x_label = section.get("options", {}).get("x_label", "channel")
        if implot.begin_aligned_plots("decay_aligned"):
            if implot.begin_plot("##decay_residuals", (-1.0, height * 0.30),
                                 implot.FLAGS_NO_LEGEND):
                implot.setup_axes("", "Residuals")
                implot.setup_axis_links(implot.AXIS_X1, self._decay_xlim)
                lo, hi = curves.residual_ylim
                implot.setup_axis_limits(implot.AXIS_Y1, float(lo), float(hi), implot.COND_ONCE)
                implot.plot_line("residuals", np.asarray(curves.channels, float),
                                 np.asarray(curves.residuals, float))
                implot.end_plot()
            self.item_rects["Decay"] = state.rects["current_region_curves"] = im.get_item_rect()
            im.set_item_tooltip(
                "Weighted residuals of the fit; a systematic trend lines up with the channel below."
            )
            if implot.begin_plot("##decay", (-1.0, height * 0.68)):
                implot.setup_axes(x_label, "Intensity")
                implot.setup_legend(implot.LOCATION_NORTH_EAST)
                implot.setup_axis_links(implot.AXIS_X1, self._decay_xlim)
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
                lo, hi = curves.decay_ylim
                implot.setup_axis_limits(implot.AXIS_Y1, float(lo), float(hi), implot.COND_ONCE)
                x = np.asarray(curves.channels, float)
                implot.plot_scatter("Data (VV|VH)", x, np.asarray(curves.data, float))
                implot.plot_line("Model (fit)", x, np.asarray(curves.model, float))
                for name, values in (("IRF", curves.irf), ("Background", curves.background)):
                    if values is not None:
                        implot.plot_line(name, np.arange(len(values), dtype=float),
                                         np.asarray(values, float))
                implot.end_plot()
            implot.end_aligned_plots()

    # ── file dialogs ───────────────────────────────────────────────────
    def _request_dialog(self, kind: str) -> None:
        """Ask for a dialog (the region editor's Save/Load use this)."""
        self.model.dialog = kind

    def _open_requested_dialog(self) -> None:
        """Turn the model's ``dialog`` request into a :class:`FileDialog`."""
        kind, self.model.dialog = self.model.dialog, ""
        if not kind or self.dialog is not None or kind not in DIALOGS:
            return
        if kind == "export" and not self.model.has_results():
            self.model.status_text = "No regions to export."
            return
        title, mode, filters, name = DIALOGS[kind]
        self.dialog = FileDialog(
            title,
            mode=mode,
            filename=name or None,
            filters=filters,
            multiselect=kind == "add_files",
            directory=self.model.folder or None,
        )
        self.dialog_kind = kind

    def _draw_dialog(self, box: Any) -> None:
        if self.dialog is None:
            return
        if im.begin(self.dialog.title):
            result = self.dialog.draw()
            if result:
                kind, self.dialog = self.dialog_kind, None
                self._dialog_done(kind, [str(p) for p in result])
            elif result is False:
                self.dialog = None
        im.end()

    def _dialog_done(self, kind: str, paths: list[str]) -> None:
        """Act on what a dialog returned; a failure is shown, never raised."""
        self.error = ""
        self.model.folder = str(Path(paths[0]).parent)
        try:
            if kind == "add_files":
                self.model.add_paths("sel_files", paths)
            elif kind == "add_irf":
                self.model.add_paths("sel_irf_files", paths)
            elif kind == "export":
                path = Path(paths[0])
                if path.suffix.lower() not in (".tsv", ".csv"):
                    path = path.with_suffix(".tsv")
                self.model.export_results(str(path))
            elif kind == "open_results":
                self.model.results_tsv = paths[0]
            elif kind == "save_regions":
                self.controls.save(paths[0])
            elif kind == "load_regions":
                self.controls.load(paths[0])
        except Exception as exc:  # noqa: BLE001 - shown in the window
            self.error = f"{Path(paths[0]).name}: {exc}"

    # ── files dropped on the window ────────────────────────────────────
    def on_paths_dropped(self, paths: Any) -> None:
        """Add dropped photon files to the imaging list (ignored while a worker runs)."""
        if not self.job.busy:
            self.model.add_paths("sel_files", [str(p) for p in paths])

    def files_dropped(self, paths: Any) -> bool:
        self.on_paths_dropped(paths)
        return bool(paths)

    on_files_dropped = files_dropped

    # ── persistence ────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """Settings to keep between sessions (model settings and the image colormap)."""
        state = self.model.export_settings()
        state["colormap"] = self.canvas.colormap
        return state

    def restore_settings(self, state: dict) -> None:
        """Adopt settings from :meth:`export_settings`."""
        self.model.restore_settings(state)
        if state.get("colormap") in ("magma", "inferno", "viridis", "gray"):
            self.canvas.colormap = state["colormap"]

    def close(self) -> None:
        """Nothing to release: workers are daemon threads and no file stays open."""


def make_app() -> RegionMleApp:
    """Factory named by the manifest's ``entrypoints.emtk``."""
    return RegionMleApp()
