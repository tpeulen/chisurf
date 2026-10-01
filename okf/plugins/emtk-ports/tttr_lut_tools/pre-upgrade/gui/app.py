"""Standalone, Qt-free native LUT computation and detector settings workspace."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from emtk import clipboard, im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkHelpWindow
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .controller import COLORS, LutWorkspace
from .translations import install, tr


class LutToolsApp(ImApp):
    def __init__(self, apply_callback=None, preferences_path=None):
        install()
        self.model = LutWorkspace(apply_callback)
        self.job = BackgroundJob()
        self.stage = 0
        self.dialog = None
        self.dialog_callback = None
        self.show_json = False
        self.item_rects = {}
        self.preferences_path = Path(preferences_path) if preferences_path else None
        self.help = EmTkHelpWindow(
            title=tr("LUT Tools — help"), resource=Path(__file__).parents[1] / "README.md"
        )
        self.dataset_picker = DatasetPicker(on_paths=self.add_files)
        self.docks = DockManager(Split("h", 0.30, Region("controls"), Region("plots")))
        self.docks.add_window("controls", tr("LUT controls"), self.draw_controls, dock="controls")
        self.docks.add_window("plots", tr("TAC histograms"), self.draw_plots, dock="plots")
        super().__init__(gui=self.render, continuous=True)
        if self.preferences_path and self.preferences_path.is_file():
            self.action(
                lambda: self.restore_settings(
                    json.loads(self.preferences_path.read_text(encoding="utf-8"))
                )
            )

    def action(self, callback, background=False):
        if self.job.running:
            return False
        if background:
            return self.job.start(
                callback, lambda _: None, lambda error: setattr(self.model, "message", str(error))
            )
        try:
            return callback()
        except Exception as error:
            self.model.message = str(error)
            return False

    def button(self, label, tip, callback, background=False):
        if im.button(tr(label)):
            self.action(callback, background)
        im.set_item_tooltip(tr(tip))
        self.item_rects[label] = im.get_item_rect()

    def check(self, label, value, tip):
        result = im.checkbox(tr(label), bool(value))
        im.set_item_tooltip(tr(tip))
        self.item_rects[label] = im.get_item_rect()
        return result

    def number(self, label, value, tip, integer=False):
        im.text(tr(label))
        im.set_next_item_width(-1)
        result = (
            im.input_int("##" + label, int(value), step=0)
            if integer
            else im.input_float("##" + label, float(value), step=0)
        )
        im.set_item_tooltip(tr(tip))
        self.item_rects[label] = im.get_item_rect()
        return result

    def choose(self, label, value, values, tip):
        values = values or [""]
        im.text(tr(label))
        im.set_next_item_width(-1)
        changed, index = im.combo(
            "##" + label,
            values.index(value) if value in values else 0,
            [tr(str(v)) for v in values],
        )
        im.set_item_tooltip(tr(tip))
        return changed, values[index]

    def browse(
        self, callback, mode="open", multiple=False, lut=False, settings=False, corrected=False
    ):
        filters = "Photon data (*.pto *.spc *.ht3 *.ptu *.phu *.photonhdf5 *.t3r *.t2r)"
        if lut:
            filters = "LUT (*.json *.npy *.npz *.csv *.txt)"
        if corrected:
            filters = "Corrected microtimes (*.npy *.npz *.csv *.txt)"
        if settings:
            filters = "TTTR settings (*.json)"
        self.dialog = FileDialog(
            tr("Select file"), mode=mode, multiselect=multiple, filters=filters
        )
        self.dialog_callback = callback

    def add_files(self, paths):
        paths = (
            [*self.model.compute.files, *paths] if self.stage == 0 else [*self.model.files, *paths]
        )
        self.action(
            lambda: (
                self.model.load_compute(paths)
                if self.stage == 0
                else self.model.load_preview(paths)
            ),
            background=True,
        )

    def on_paths_dropped(self, paths):
        photons = []
        for path in paths:
            if Path(path).suffix.lower() in {".npy", ".npz", ".txt", ".csv", ".json"}:
                self.action(lambda path=path: self.model.import_lut(path))
            else:
                photons.append(path)
        if photons:
            self.add_files(photons)
        return True

    files_dropped = on_paths_dropped
    on_files_dropped = on_paths_dropped

    def remove_file(self, path):
        paths = self.model.compute.files if self.stage == 0 else self.model.files
        remaining = [value for value in paths if value != path]
        if self.stage == 0:
            self.action(
                lambda: (
                    self.model.load_compute(remaining) if remaining else self.model.compute.clear()
                ),
                background=True,
            )
        else:
            self.action(lambda: self.model.load_preview(remaining), background=True)

    def draw_files(self):
        self.button(
            "Add files",
            "Load uniform-illumination or preview TTTR files.",
            lambda: self.browse(self.add_files, multiple=True),
        )
        im.same_line()
        self.button(
            "Folder",
            "Load supported photon files recursively from a folder.",
            lambda: self.browse(self.add_files, mode="folder"),
        )
        self.button(
            "Database", "Select photon files from the MMFDB object store.", self.dataset_picker.open
        )
        im.same_line()
        self.button(
            "Clear files",
            "Unload input files; retain assigned LUTs.",
            lambda: self.model.compute.clear() if self.stage == 0 else self.model.load_preview([]),
        )
        files = self.model.compute.files if self.stage == 0 else self.model.files
        for index, path in enumerate(files):
            im.push_id(index)
            if im.small_button("×"):
                self.remove_file(path)
            im.set_item_tooltip(tr("Remove this input file."))
            im.same_line()
            im.text(Path(path).name)
            im.set_item_tooltip(path)
            im.pop_id()
        if not files:
            im.text_wrapped(tr("Drop photon files here or use Add files."))

    def draw_controls(self, box):
        stages = ["Compute LUT", "Assign LUTs and shifts"]
        changed, stage = self.choose(
            "Workflow",
            stages[self.stage],
            stages,
            "0: Compute per-channel LUTs. 1: Assign and preview correction.",
        )
        if changed:
            self.stage = stages.index(stage)
        im.text_wrapped(tr("Compute LUT") if self.stage == 0 else tr("Assign LUTs and shifts"))
        im.begin_disabled(self.job.running)
        self.draw_files()
        im.separator()
        if self.stage == 0:
            self.draw_compute_controls()
        else:
            self.draw_settings_controls()
        im.separator()
        self.button("Help", "Read the complete LUT workflow and scientific notes.", self.help.show)
        if self.model.apply_callback:
            im.same_line()
            self.button(
                "Apply to detector setup",
                "Send assigned LUTs and shifts to the connected detector setup.",
                self.model.apply,
            )
        im.end_disabled()
        if self.job.running:
            im.text(tr("Working…"))
        if self.model.message:
            im.text_wrapped(self.model.message)

    def draw_compute_controls(self):
        model = self.model.compute
        changed, channel = self.choose(
            "Preview channel",
            model.channel,
            model.channels_options(),
            "Select the routing channel to inspect and tune.",
        )
        if changed:
            model.channel = channel
            self.action(model.update, True)
        params = [
            ("linear_start", "Linear start", "First bin of the flat linear region.", True),
            ("linear_stop", "Linear stop", "First bin after the flat linear region.", True),
            ("ntac_required", "TAC channels required", "Number of corrected TAC bins.", True),
            ("noffset", "Offset", "Offset subtracted from corrected TAC indices.", True),
            (
                "preview_photons",
                "Preview photons",
                "Maximum photons used for the corrected preview.",
                True,
            ),
            (
                "threshold",
                "Low-count threshold",
                "Bins below this count are excluded from calibration.",
                False,
            ),
            ("seed", "RNG seed", "Seed for reproducible stochastic rebinning.", True),
            (
                "eps",
                "Wrap epsilon",
                "Epsilon used with floor rounding to suppress wrap spikes.",
                False,
            ),
        ]

        def draw_parameter(parameter):
            attr, label, tip, integer = parameter
            changed, value = self.number(label, getattr(model, attr), tip, integer)
            if changed:
                setattr(model, attr, value)
                self.action(model.compute, True)

        for parameter in params[:5]:
            draw_parameter(parameter)
        changed, value = self.check(
            "Normalize by region mean",
            model.normalize,
            "Normalize the displayed histogram by its plateau mean.",
        )
        if changed:
            model.normalize = value
            self.action(model.compute, True)
        advanced = im.collapsing_header(tr("Advanced"))
        im.set_item_tooltip(tr("Show advanced calibration parameters."))
        if advanced:
            for parameter in params[5:]:
                draw_parameter(parameter)
            changed, value = self.check(
                "Mitigate wrap spike",
                model.mitigate_wrap,
                "Use floor rounding and epsilon at the wrap boundary.",
            )
            if changed:
                model.mitigate_wrap = value
                self.action(model.compute, True)
        self.button(
            "Auto-detect region",
            "Find the flat calibration plateau automatically.",
            model.autodetect,
            True,
        )
        self.button(
            "Add all channels to setup",
            "Compute one LUT per routing channel and assign every result.",
            self.model.bridge,
            True,
        )
        self.button(
            "Save LUT",
            "Export the selected channel LUT as JSON, NumPy, CSV or text.",
            lambda: self.browse(
                lambda paths: self.action(lambda: model.save_lut(str(paths[0])), True),
                mode="save",
                lut=True,
            ),
        )
        self.button(
            "Export corrected",
            "Export corrected microtimes for all selected-channel photons.",
            lambda: self.browse(
                lambda paths: self.action(lambda: model.export_corrected(str(paths[0])), True),
                mode="save",
                corrected=True,
            ),
        )
        im.text_wrapped(model.info_text())

    def draw_settings_controls(self):
        model = self.model
        routines = ["Auto", "PTU", "HT3", "SPC-130", "SPC-600_256", "SPC-600_4096", "PHOTON-HDF5"]
        kinds = [None, 0, 1, 2, 3, 4, 5]
        index = kinds.index(model.reading_routine) if model.reading_routine in kinds else 0
        changed, value = self.choose(
            "Reading routine",
            routines[index],
            routines,
            "Select the TTTR container format; Auto detects it from the file.",
        )
        if changed:
            model.reading_routine = kinds[routines.index(value)]
            self.action(lambda: model.load_preview(model.files), True)
        self.button(
            "Load LUT",
            "Import a cumulative LUT from JSON, NumPy, CSV or text.",
            lambda: self.browse(lambda paths: model.import_lut(str(paths[0])), lut=True),
        )
        im.same_line()
        self.button(
            "Clear LUTs",
            "Remove all loaded and assigned LUTs; retain shifts.",
            model.clear_luts,
            True,
        )
        for name in list(model.loaded_luts):
            if im.selectable(name, name == model.selected_lut):
                model.selected_lut = name
            im.set_item_tooltip(tr("Select the LUT to assign to a channel."))
            self.item_rects["lut:" + name] = im.get_item_rect()
            if im.begin_popup_context_item("lut:" + name):
                if im.menu_item(tr("Remove LUT")):
                    self.action(lambda name=name: model.remove_lut(name))
                im.set_item_tooltip(tr("Remove this LUT from the import list; retain assignments."))
                im.end_popup()
        self.button(
            "Assign selected",
            "Assign the selected LUT to the active routing channel.",
            model.assign,
            True,
        )
        im.same_line()
        self.button(
            "Assign all",
            "Assign the selected LUT to every routing channel in the preview.",
            lambda: model.assign(True),
            True,
        )
        for channel in sorted(model.raw):
            im.push_id(channel)
            changed, visible = self.check(
                f"{tr('Show channel')} {channel}",
                channel in model.visible,
                "Show or hide this routing channel histogram.",
            )
            if changed:
                model.visible.add(channel) if visible else model.visible.discard(channel)
            if im.selectable(f"{tr('Channel')} {channel}", channel == model.active_channel):
                model.active_channel = channel
            im.set_item_tooltip(tr("Select the active channel for shifts and LUT inspection."))
            im.pop_id()
        changed, shift = self.number(
            "Shift",
            model.channel_shifts.get(model.active_channel, 0),
            "Photon-level shift of the active channel after LUT correction.",
            True,
        )
        if changed:
            self.action(lambda: model.set_shift(shift), True)
        _, model.show_lut = self.check(
            "Show LUT panel",
            model.show_lut,
            "Inspect the active channel cumulative LUT and bin increments.",
        )
        _, model.log_y = self.check(
            "Log counts", model.log_y, "Use a logarithmic histogram count axis."
        )
        self.button(
            "Show JSON",
            "Inspect the portable settings.tttr.json bundle.",
            lambda: setattr(self, "show_json", not self.show_json),
        )
        self.button(
            "Load JSON",
            "Restore per-channel LUTs, shifts and reading routine.",
            lambda: self.browse(
                lambda paths: self.action(lambda: model.import_settings(str(paths[0])), True),
                settings=True,
            ),
        )
        im.same_line()
        self.button(
            "Save JSON",
            "Save the portable TTTR correction settings.",
            lambda: self.browse(
                lambda paths: model.export_settings(str(paths[0])), mode="save", settings=True
            ),
        )

    def plot(self, title, ylabel, curves, height, log_y=False):
        if implot.begin_plot(tr(title), (-1, height)):
            implot.setup_axes(tr("Microtime (bins)"), tr(ylabel))
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

    def draw_plots(self, box):
        if self.job.running:
            im.text(tr("Working…"))
            return
        available = im.get_content_region_avail()
        height = max(150, available[1] / 2 - 35)
        if self.stage == 0:
            model = self.model.compute
            if model.counts is None:
                im.text_wrapped(tr("Load uniform-illumination files to inspect the TAC histogram."))
                return
            counts = model.counts.astype(float)
            if model.normalize:
                mean = counts[model.linear_start : model.linear_stop].mean()
                counts = counts / mean if mean > 0 else counts
            if implot.begin_plot(
                tr("Raw TAC — drag region boundaries, offset and threshold"), (-1, height)
            ):
                implot.setup_axes(tr("Microtime (bins)"), tr("Counts"))
                implot.set_next_fill_style((255, 160, 40), 0.16)
                implot.plot_shaded(
                    "##plateau",
                    np.array([model.linear_start, model.linear_stop]),
                    np.full(2, max(counts.max(), 1.0)),
                    yref=0.0,
                )
                implot.set_next_line_style((255, 210, 30), 2)
                implot.plot_line(tr("Raw TAC"), np.arange(len(counts)), counts)
                changed = False
                for attr, identifier, color in [
                    ("linear_start", 1, (255, 160, 40)),
                    ("linear_stop", 2, (255, 160, 40)),
                    ("noffset", 3, (220, 70, 70)),
                ]:
                    result = implot.drag_line_x(identifier, getattr(model, attr), color, 2)
                    if result.modified:
                        setattr(model, attr, max(0, min(len(counts), int(result.value))))
                        changed = True
                result = implot.drag_line_y(4, model.threshold, (70, 180, 80), 2)
                if result.modified:
                    model.threshold = max(0.0, result.value)
                    changed = True
                implot.end_plot()
                if changed:
                    self.action(model.compute, True)
            after = model.corrected_after_hist()
            if after:
                self.plot(
                    "Corrected TAC preview",
                    "Counts",
                    [("Corrected", after[1], (50, 195, 240))],
                    height,
                )
        else:
            model = self.model
            curves = []
            for index, channel in enumerate(sorted(model.raw)):
                if channel not in model.visible:
                    continue
                color = COLORS[index % len(COLORS)]
                for prefix, source in [("Raw", model.raw), ("Corrected", model.corrected)]:
                    counts = np.asarray(source.get(channel, []), dtype=float)
                    if model.log_y:
                        counts = np.maximum(counts, 1e-4)
                    curves.append(
                        (
                            f"{tr(prefix)} ch{channel}"
                            + (" *" if channel == model.active_channel else ""),
                            counts,
                            color,
                        )
                    )
            self.plot(
                "Channel correction preview",
                "Counts",
                curves,
                height if model.show_lut else max(150, available[1] - 30),
                log_y=model.log_y,
            )
            lut = model.channel_luts.get(model.active_channel)
            if model.show_lut and lut is not None:
                self.plot(
                    "Cumulative NTAC", "Cumulative NTAC", [("LUT", lut, (70, 70, 200))], height / 2
                )
                self.plot(
                    "Bin increments",
                    "ΔNTAC / bin",
                    [("LUT", np.diff(np.r_[0, lut]), (200, 70, 70))],
                    height / 2,
                )

    def render(self):
        self.job.poll()
        vp = im.get_main_viewport()
        self.docks.draw((0, 0, *vp.size))
        self.dataset_picker.render((0, 0, *vp.size))
        self.help.draw((0, 0, *vp.size))
        if self.dialog:
            if im.begin(tr("Select file")):
                result = self.dialog.draw()
                if result:
                    callback = self.dialog_callback
                    self.dialog = None
                    self.action(lambda: callback(result))
                elif result is False:
                    self.dialog = None
            im.end()
        if self.show_json:
            opened = im.begin(tr("Settings JSON preview"))
            if opened:
                self.button(
                    "Copy JSON",
                    "Copy the complete correction settings to the clipboard.",
                    lambda: clipboard.copy(json.dumps(self.model.bundle(), indent=2)),
                )
                im.same_line()
                self.button(
                    "Close", "Close the JSON preview.", lambda: setattr(self, "show_json", False)
                )
                im.text_wrapped(json.dumps(self.model.bundle(), indent=2))
            im.end()

    def export_settings(self):
        return {
            "workspace": self.model.get_state(),
            "stage": self.stage,
            "docks": self.docks.state(),
        }

    def restore_settings(self, state):
        self.model.set_state(state.get("workspace", state))
        self.stage = int(state.get("stage", 0))
        self.docks.restore(state.get("docks"))

    def close(self):
        self.job.close()
        self.dataset_picker.close()
        if self.preferences_path:
            self.preferences_path.write_text(
                json.dumps(self.export_settings(), indent=2), encoding="utf-8"
            )


def create_app(apply_callback=None, preferences_path=None):
    if preferences_path is None:
        from chisurf.core.settings import get_path

        preferences_path = get_path("settings") / "tttr_lut_tools_native.json"
    return LutToolsApp(apply_callback=apply_callback, preferences_path=preferences_path)
