"""Standalone, Qt-free native LUT computation and detector settings workspace.

The form (header, files, tab 1 parameters, tab 2 assignment, status) is the view spec
``lut_tools_emtk.view.json`` drawn by :func:`emtk.view_form.draw_sections` over
:class:`~.model.LutToolModel`. Only what a spec cannot express is drawn here: the two
plots (the raw TAC histogram with a draggable plateau region, offset and threshold, and
the corrected preview), the file dialogs and the JSON preview window. Slow work runs on a
:class:`~chisurf.emtk.jobs.SnapshotJob`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from emtk import clipboard, i18n, im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob

from .controller import COLORS
from .model import LutToolModel
from .translations import install, tr

HERE = Path(__file__).parent

#: Colour of the plateau region, offset line and threshold line (they carry meaning).
ORANGE, RED, GREEN = (255, 165, 0), (220, 70, 70), (70, 180, 80)
PHOTON_FILTERS = "Photon data (*.pto *.spc *.ht3 *.ptu *.phu *.photonhdf5 *.t3r *.t2r)"
FILTERS = {
    "save_lut": "LUT (*.npy *.npz *.json *.csv *.txt)",
    "load_lut": "LUT (*.json *.npy *.npz *.csv *.txt)",
    "export_corrected": "Corrected microtimes (*.npy *.npz *.csv *.txt)",
    "load_json": "TTTR settings (*.json)",
    "save_json": "TTTR settings (*.json)",
}
JSON_PREVIEW_LINES = 60
_TRANSLATED_KEYS = ("label", "title", "description", "tooltip", "text", "placeholder")


def _translate(node, locale):
    """Copy of a spec node with its user-visible strings looked up in the LUT catalog."""
    if isinstance(node, list):
        return [_translate(item, locale) for item in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, value in node.items():
        if key in _TRANSLATED_KEYS and isinstance(value, str):
            out[key] = tr(value)
        else:
            out[key] = _translate(value, locale)
    options = node.get("options")
    if node.get("type") == "choice" and isinstance(options, list) and "labels" not in node:
        out["labels"] = [tr(str(option)) for option in options]
    return out


class LutToolsApp(ImApp):
    """The LUT Tools window: tab 1 computes LUTs, tab 2 saves and loads settings."""

    def __init__(self, apply_callback=None, preferences_path=None):
        install()
        self.model = LutToolModel(apply_callback)
        self.job = SnapshotJob(self.model)
        self._spec_source = json.loads((HERE / "lut_tools_emtk.view.json").read_text("utf-8"))
        self._spec_locale = None
        self.panels = {}
        self.form = FormState()
        self.dialog = None
        self.dialog_kind = None
        self._reported_error = ""
        self._json_text = None
        self.json_dialog = DialogWindow(
            tr("Settings JSON preview"), size=(520.0, 420.0), key="lut_json"
        )
        self.preferences_path = Path(preferences_path) if preferences_path else None
        self.help_window = EmTkHelpWindow(
            title=tr("LUT Tools — help"), resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self.dataset_picker = DatasetPicker(on_paths=self.model.add_files)
        self.docks = DockManager(Split("h", 0.36, Region("controls"), Region("plots")))
        self.docks.add_window("controls", tr("LUT controls"), self.draw_controls, dock="controls")
        self.docks.add_window("plots", tr("TAC histograms"), self.draw_plots, dock="plots")
        super().__init__(gui=self.render, continuous=True)
        if self.preferences_path and self.preferences_path.is_file():
            try:
                self.restore_settings(json.loads(self.preferences_path.read_text(encoding="utf-8")))
            except Exception as error:  # noqa: BLE001 - a stale preference must not stop the tool
                self.model.message = f"Could not restore the last session: {error}"

    # -- spec ------------------------------------------------------------------- #
    def _sync_spec(self):
        locale = i18n.get_locale()
        if locale != self._spec_locale:
            spec = _translate(self._spec_source, locale)
            self.panels = {panel["name"]: panel["sections"] for panel in spec["sections"]}
            self._spec_locale = locale

    def section(self, name):
        """Draw the spec panel *name* (no caption)."""
        draw_sections(self.panels[name], self.model, self.form, titles=False)

    # -- requests the model made -------------------------------------------------- #
    def _service(self):
        """Run what the model asked for: a file dialog, a job, the help, the tour."""
        model = self.model
        model.busy = self.job.busy
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            model.message = self.job.error
        if model.help_requested:
            model.help_requested = False
            self.help_window.show()
        if model.guide_requested:
            model.guide_requested = False
            self.tour.start()
        request = model.dialog_request
        if request and self.dialog is None:
            model.dialog_request = None
            if request["kind"] == "database":
                self.dataset_picker.open()
            else:
                kind = request["kind"]
                self.dialog_kind = kind
                self.dialog = FileDialog(
                    tr("Select file"),
                    mode=request.get("mode", "open"),
                    multiselect=bool(request.get("multiselect")),
                    filters=FILTERS.get(kind, PHOTON_FILTERS),
                )
        if model.job_request and not self.job.busy:
            method, args = model.job_request
            model.job_request = None
            self._reported_error = ""
            self.job.start(method, *args)
            model.busy = True

    def on_files_dropped(self, paths):
        """Dropped photon files are added; dropped LUT / settings files are imported."""
        photons = []
        for path in paths:
            suffix = Path(path).suffix.lower()
            if suffix in {".npy", ".npz", ".txt", ".csv"}:
                self.model.finish_dialog("load_lut", [path])
            elif suffix == ".json":
                self.model.finish_dialog("load_json", [path])
            else:
                photons.append(path)
        if photons:
            self.model.add_files(photons)
        return True

    files_dropped = on_paths_dropped = on_files_dropped

    # -- windows --------------------------------------------------------------------- #
    def draw_controls(self, box):
        """The controls window: header, files, the shown tab, status."""
        self._sync_spec()
        self.section("header")
        self.section("files")
        self.section("compute" if self.model.stage == 0 else "assign")
        self.section("status")
        if self.model.busy:
            im.text(tr("Working…"))

    def _plot(self, title, x_label, y_label, curves, height, log_y=False):
        """A plain line plot; with no curve the axes and title still show (empty state)."""
        empty = not curves
        if implot.begin_plot(tr(title) + ("##empty" if empty else ""), (-1, height)):
            implot.setup_axes(tr(x_label), tr(y_label))
            if empty:
                implot.setup_axes_limits(0, 1, 1 if log_y else 0, 10 if log_y else 1)
            if log_y:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            for label, values, color in curves:
                implot.set_next_line_style(
                    color,
                    3 if label.endswith("*") else 1.5,
                    dash=(5, 3) if label.startswith(tr("Raw")) else None,
                )
                implot.plot_line(tr(label), np.arange(len(values)), values)
            implot.end_plot()

    def _raw_plot(self, height):
        """The raw TAC histogram with the draggable plateau region, offset and threshold."""
        model = self.model
        compute = model.ws.compute
        data = model.raw_plot()
        title = tr("Raw TAC histogram (drag the orange region)")
        if implot.begin_plot(title + ("##empty" if data is None else ""), (-1, height)):
            implot.setup_axes(tr("TAC bin"), tr(data[2] if data else "Counts"))
            top = 1.0
            if data is not None:
                x, y, _ = data
                top = max(float(np.max(y)) if y.size else 1.0, 1e-9)
                implot.set_next_line_style((255, 204, 0), 1.5)
                implot.plot_line(tr("Raw TAC"), x, y)
            else:
                implot.setup_axes_limits(
                    float(compute.linear_start), float(compute.linear_stop), 0.0, 1.0
                )
            changed = False
            region = implot.drag_rect(
                1,
                float(compute.linear_start),
                0.0,
                float(compute.linear_stop),
                top,
                ORANGE,
                implot.DRAG_TOOL_FLAGS_NO_FIT,
            )
            if region.modified:
                limit = int(compute.n_bins) if compute.n_bins else None
                start = max(0, int(round(min(region.x_min, region.x_max))))
                stop = max(start + 1, int(round(max(region.x_min, region.x_max))))
                if limit:
                    stop = min(stop, limit)
                    start = min(start, stop - 1)
                compute.linear_start, compute.linear_stop = start, stop
                changed = True
            result = implot.drag_line_x(3, float(compute.noffset), RED, 2)
            if result.modified:
                compute.noffset = max(0, int(round(result.value)))
                changed = True
            result = implot.drag_line_y(4, float(compute.threshold), GREEN, 2)
            if result.modified:
                compute.threshold = max(0.0, float(result.value))
                changed = True
            implot.end_plot()
            if changed and data is not None:
                model.param_changed()

    def _corrected_plot(self, height):
        """The corrected preview, on the equal-width NTAC axis."""
        model = self.model
        after = model.corrected_plot()
        ntac = int(model.ws.compute.ntac_required)
        title = tr("After linearization (corrected preview)")
        if implot.begin_plot(title + (f"##{ntac}" if after else "##empty"), (-1, height)):
            implot.setup_axes(tr("Equal-width NTAC bin"), tr("Counts"))
            if after is None:
                implot.setup_axes_limits(0, 1, 0, 1)
            else:
                implot.setup_axis_limits(implot.AXIS_X1, 0, ntac)
                implot.set_next_line_style((80, 200, 255), 1.5)
                implot.plot_line(tr("Corrected"), after[0], after[1])
            implot.end_plot()

    def draw_plots(self, box):
        """The plots window: tab 1 shows the raw and corrected TAC, tab 2 the channels."""
        available = im.get_content_region_avail()
        model = self.model
        if model.stage == 0:
            height = max(120, available[1] / 2 - 12)
            self._raw_plot(height)
            self._corrected_plot(height)
            return
        ws = model.ws
        curves = []
        for index, channel in enumerate(sorted(ws.raw)):
            if channel not in ws.visible:
                continue
            color = COLORS[index % len(COLORS)]
            for prefix, source in (("Raw", ws.raw), ("Corrected", ws.corrected)):
                counts = np.asarray(source.get(channel, []), dtype=float)
                if ws.log_y:
                    counts = np.maximum(counts, 1e-4)
                suffix = " *" if channel == ws.active_channel else ""
                curves.append((f"{tr(prefix)} ch{channel}{suffix}", counts, color))
        lut = ws.channel_luts.get(ws.active_channel)
        show_lut = ws.show_lut and lut is not None
        height = max(120, available[1] / 2 - 12) if show_lut else max(120, available[1] - 30)
        self._plot(
            "Channel correction preview",
            "Microtime (bins)",
            "Counts (log)" if ws.log_y else "Counts",
            curves,
            height,
            log_y=ws.log_y,
        )
        if show_lut:
            self._plot(
                "Cumulative NTAC",
                "Microtime (bins)",
                "Cumulative NTAC",
                [("LUT", lut, (70, 70, 200))],
                height / 2,
            )
            self._plot(
                "Bin increments",
                "Microtime (bins)",
                "ΔNTAC / bin",
                [("LUT", np.diff(np.r_[0, lut]), (200, 70, 70))],
                height / 2,
            )

    # -- one frame ------------------------------------------------------------------ #
    def render(self):
        """Draw one frame: poll the job, the windows, the dialogs, help and tour."""
        self.job.poll()
        self._service()
        self.form.rects.clear()
        vp = im.get_main_viewport()
        box = (0, 0, *vp.size)
        self.docks.draw(box)
        self.dataset_picker.render(box)
        self.help_window.draw(box)
        if self.dialog:
            if im.begin(tr("Select file")):
                result = self.dialog.draw()
                if result:
                    kind, self.dialog = self.dialog_kind, None
                    self.model.finish_dialog(kind, result if isinstance(result, list) else [result])
                elif result is False:
                    self.dialog = None
            im.end()
        if self.model.show_json:
            self._json_window(box)
        else:
            self._json_text = None
        self.tour.draw(*vp.size)

    def _json_window(self, frame):
        """The settings.tttr.json preview with Copy and Close (long arrays are cut)."""
        dialog = self.json_dialog
        dialog.open = self.model.show_json
        if not dialog.open:
            return
        if self._json_text is None:
            self._json_text = json.dumps(self.model.ws.bundle(), indent=2)
        lines = self._json_text.splitlines()
        shown = lines[:JSON_PREVIEW_LINES]
        if len(lines) > len(shown):
            shown.append(f"... {len(lines) - len(shown)} more lines (Copy JSON copies all)")
        pressed = dialog.begin(frame)
        if im.button(tr("Copy JSON")):
            clipboard.copy(self._json_text)
        im.set_item_tooltip(tr("Copy the complete correction settings to the clipboard."))
        self.form.rects["copy_json"] = im.get_item_rect()
        im.same_line()
        if im.button(tr("Close")):
            pressed = "close"
        im.set_item_tooltip(tr("Close the JSON preview."))
        self.form.rects["close_json"] = im.get_item_rect()
        avail = im.get_content_region_avail()
        im.begin_child(
            (*im.get_cursor_screen_pos(), max(100.0, avail[0]), max(60.0, avail[1])), clip=True
        )
        for line in shown:
            im.text(line)
        im.end_child()
        dialog.end()
        if pressed == "close":
            self.model.show_json = False

    # -- persistence ------------------------------------------------------------------ #
    def export_settings(self):
        """What the window remembers: the workspace, the shown tab, the dock layout."""
        state = self.model.get_state()
        state["docks"] = self.docks.state()
        state["folds"] = dict(self.form.folds)
        return state

    def restore_settings(self, state):
        """Restore :meth:`export_settings` (an older file holds the workspace under a key)."""
        self.model.set_state(state)
        self.docks.restore(state.get("docks"))
        folds = state.get("folds", {})
        if isinstance(folds, dict):
            self.form.folds.update({str(k): bool(v) for k, v in folds.items()})

    def close(self):
        """Let go of the dialogs and write the preferences."""
        self.dataset_picker.close()
        if self.preferences_path:
            self.preferences_path.write_text(
                json.dumps(self.export_settings(), indent=2), encoding="utf-8"
            )


def create_app(apply_callback=None, preferences_path=None):
    """Build the LUT Tools app (the manifest's ``entrypoints.emtk``)."""
    if preferences_path is None:
        from chisurf.core.settings import get_path

        preferences_path = get_path("settings") / "tttr_lut_tools_native.json"
    return LutToolsApp(apply_callback=apply_callback, preferences_path=preferences_path)


make_app = create_app
