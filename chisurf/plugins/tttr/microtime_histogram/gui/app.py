"""Native EMTK TTTR/BID histogram workflow with the full shared setup editor.

Two dock tabs on the left as in the Qt wizard (Inputs and options, Detector definition) and the decay on the right.
The options are the view spec ``histogram.view.json`` drawn by emtk's view_form over :class:`HistogramFields` (a proxy of
the model whose text fields, choices and actions the spec names); the detector definition is the shared
channel-definition editor, not a copy. Computing runs on a worker, so the window draws only while something moves.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import LabelColumn, button_row, labelled, layout_spec
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .model import HistogramModel

HERE = Path(__file__).parent
FORMATS = ["Auto", "PTU", "HT3", "SPC-130", "SPC-600_256", "SPC-600_4096", "PTO"]
PHOTON_FILTERS = [("Photon data", ["*.pto", "*.ptu", "*.ht3", "*.ht2", "*.spc", "*.phu", "*.tttr"]),
                  ("All files", ["*"])]
BURST_FILTERS = [("Burst indices", ["*.bst", "*.bur"]), ("All files", ["*"])]
DECAY_FILTERS = [("Decay", ["*.dat", "*.txt"]), ("All files", ["*"])]


class HistogramFields:
    """What the option spec edits: attributes of the app's current model, plus the actions the buttons name.

    The channel lists are shown as comma-separated text (``parallel_text``); changing a detector, a channel list or the
    time step keeps the model's derived values (output name, shifted histograms) in step, as the Qt wizard's signals did.
    """

    TEXT = {"parallel_text": "parallel", "perpendicular_text": "perpendicular"}

    def __init__(self, app):
        object.__setattr__(self, "_app", app)

    def __getattr__(self, name):
        app = self._app
        if name in self.TEXT:
            return ", ".join(map(str, getattr(app.model, self.TEXT[name])))
        if name == "detector_options":
            return lambda: list(app.model.setup.get("detectors", {}))
        if name == "window_options":
            return lambda: ["All windows"] + list(app.model.setup.get("windows", {}))
        if name == "format_options":
            return lambda: FORMATS + ([app.model.filetype] if app.model.filetype not in FORMATS else [])
        if name.startswith("_"):
            raise AttributeError(name)
        if name in ("compute", "save", "save_as", "transfer"):       # the app's actions, not the model's same-named methods
            return getattr(app, name)
        if hasattr(app.model, name):
            return getattr(app.model, name)
        return getattr(app, name)

    def __setattr__(self, name, value):
        app, model = self._app, self._app.model
        if name in self.TEXT:
            try:
                parsed = [int(v.strip()) for v in str(value).replace(";", ",").split(",") if v.strip()]
            except ValueError:
                model.message = "Channels are comma-separated integers."
                return
            setattr(model, self.TEXT[name], parsed)
            model.update_output_filename()
        elif name == "detector":
            model.select_detector(value)
        elif name == "dt_ns":
            if float(value) > 0:
                model.dt_ns, model.dt_manual = float(value), True
                model.update_timeshifts()
        elif name == "binning":
            model.binning = max(1, int(value))
        elif name in ("g_factor", "vv_shift", "vh_shift"):
            setattr(model, name, float(value) if name == "g_factor" else int(value))
            model.update_timeshifts()
        else:
            setattr(model, name, value)
        app.tour.notify_used(name)

    def enabled(self, name):
        app = self._app
        model = app.model
        if name in ("compute",):
            return bool(model.selected_files()) and not app.job.running
        if name == "save":
            return model.cumulative_ps is not None and not app.job.running
        if name == "save_as":
            return model.cumulative_ps is not None and not app.job.running
        if name == "transfer":
            return bool(model.selected_files() or model.cumulative_ps is not None) and not app.job.running
        if name == "detector":
            return bool(model.setup.get("detectors"))
        return True

    def bounds(self, name):
        return None


class HistogramApp(TourTarget, ImApp):
    def __init__(self, reader=None, add_dataset=None):
        self.model = HistogramModel()
        self.reader = reader
        self.add_dataset = add_dataset
        self.item_rects = {}
        self.fields = HistogramFields(self)
        spec = layout_spec(json.loads((HERE / "histogram.view.json").read_text(encoding="utf-8")))
        self.run_spec = {"sections": [p for p in spec["sections"] if p.get("title") == "Run"]}      # always on top
        self.spec = {"sections": [p for p in spec["sections"] if p.get("title") != "Run"]}
        for section in self.walk(self.spec["sections"]):
            if section.get("kind") == "text":
                section.pop("width", None)                  # a text field takes the dock's width, never more
        self.labels = LabelColumn()
        self.form = FormState()
        self.help = EmTkHelpWindow(
            title="Micro-time histogram — Help", resource=HERE / "help.md", owner=self,
            on_start_guide=self.start_guide, size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
            owner=self, wait_for_controls=True, on_step_change=self.reveal_step,
        )
        self.form.on_used = self.tour.notify_used
        self.job = BackgroundJob()
        self.progress = (0, 0)
        self.dialog = None
        self.dialog_callback = None
        self.dialog_window = DialogWindow("Choose a file", size=(640.0, 420.0), key="microtime-histogram-file")
        self.editor = ChannelDefinitionWidget(on_changed=self.definition_changed)
        self.dataset_picker = DatasetPicker(on_paths=self.add_files)
        self.selected = {"photon": None, "burst": None}
        self.log_y = True
        self.show_vv = self.show_vh = self.show_combined = True
        self.plot_signature = None
        self.input_signature = self.fingerprint()
        self.docks = DockManager(Split("h", 0.40, Region("left"), Region("plot")))
        self.docks.add_window("inputs", "Inputs and options", self.draw_inputs, dock="left", closable=False)
        self.docks.add_window("setup", "Detector definition", self.draw_setup, dock="left", closable=False)
        self.docks.add_window("plot", "Microtime decay", self.draw_plot, dock="plot", closable=False)
        self.native_layouts = {"main": self.docks}
        super().__init__(gui=self.render, continuous=False)

    @staticmethod
    def walk(sections):
        for section in sections:
            yield section
            yield from HistogramApp.walk(section.get("sections", ()))

    def animating(self):
        return self.job.running or self.editor._future is not None or super().animating()

    def start_guide(self):
        self.tour.start()

    def reveal_step(self, index, step):
        self.docks.focus("inputs")

    def enabled(self, name):
        return self.fields.enabled(name)

    def fingerprint(self):
        return json.dumps(
            {
                key: getattr(self.model, key)
                for key in (
                    "files",
                    "enabled",
                    "bid_files",
                    "bid_enabled",
                    "setup",
                    "detector",
                    "parallel",
                    "perpendicular",
                    "polarized",
                    "window",
                    "filetype",
                    "binning",
                )
            },
            sort_keys=True,
        )

    def definition_changed(self, settings):
        self.model.set_setup(settings)
        self.plot_signature = None

    def button(self, label, tip, callback, key=None):
        """A button that tells the guide it was pressed, remembered under *key* (or its label)."""
        key = key or label
        pressed = im.button(label)
        im.set_item_tooltip(tip)
        self.remember(key)
        if pressed:
            self.tour.notify_used(key)
            callback()

    def choose(self, title, callback, mode="open", multiple=False, filters=None, filename=""):
        if self.job.running or self.editor._future is not None:
            return
        self.dialog = FileDialog(title, mode=mode, multiselect=multiple, filters=filters or PHOTON_FILTERS,
                                 filename=filename)
        self.dialog_callback = callback
        self.dialog_window.title = title
        self.dialog_window.show()

    def add_files(self, paths):
        if not self.job.running:
            self.model.add_paths(paths)

    def add_bids(self, paths):
        if not self.job.running:
            self.model.add_paths(paths, bids=True)
            self.model.message = f"{len(self.model.bid_files)} burst selection(s) queued."
            self.find_sources()

    def run(self, operation, on_complete=None):
        if self.job.running or self.editor._future is not None:
            return False
        model = self.model.snapshot()

        def work():
            operation(model)
            return model

        def publish(model):
            self.model = model
            self.plot_signature = None
            self.input_signature = self.fingerprint()
            if on_complete:
                on_complete()

        return self.job.start(work, publish, lambda exc: setattr(self.model, "message", str(exc)))

    def compute(self, transfer=False):
        def work(model):
            model.compute(
                reader=self.reader,
                cancel_cb=self.job.cancelled.is_set,
                progress_cb=lambda index, count: setattr(self, "progress", (index, count)),
            )
            if transfer:
                model.save(model.output)
            return model

        if self.job.running or self.editor._future is not None:
            return False
        model = self.model.snapshot()

        def publish(model):
            self.model = model
            self.plot_signature = None
            self.input_signature = self.fingerprint()
            if transfer:
                self.transfer_loaded()

        return self.job.start(
            lambda: work(model), publish, lambda exc: setattr(self.model, "message", str(exc))
        )

    def load_bid_folder(self, folder, setup_name=None, auto_transfer=False):
        if self.job.running or self.editor._future is not None:
            return False
        snapshot = self.model.snapshot()

        def work():
            if setup_name:
                from chisurf.core.setup_channel_definition import ChannelDefinition

                store = ChannelDefinition()
                store.refresh_setups()
                if setup_name not in store.setups:
                    raise ValueError(f"Unknown detector setup: {setup_name}")
                snapshot.set_setup(store.setups[setup_name])
            snapshot.bid_files = []
            snapshot.bid_enabled = {}
            snapshot.add_paths([folder], bids=True)
            snapshot.find_corresponding_files()
            snapshot.compute(reader=self.reader, cancel_cb=self.job.cancelled.is_set)
            if auto_transfer:
                snapshot.save(snapshot.output)
            return snapshot

        def publish(model):
            self.model = model
            self.input_signature = self.fingerprint()
            if auto_transfer:
                self.transfer_loaded()

        return self.job.start(work, publish, lambda exc: setattr(self.model, "message", str(exc)))

    def find_sources(self):
        self.run(lambda model: model.find_corresponding_files())

    def save(self, path=None):
        if self.model.cumulative_ps is None:
            self.model.message = "Compute a histogram before saving."
            return False
        target = str(path or self.model.output)

        def operation(model):
            model.save(target)
            model.message = f"Saved {target}"

        return self.run(operation)

    def save_as(self):
        self.choose("Save decay", lambda paths: self.save(paths[0]), mode="save", filters=DECAY_FILTERS,
                    filename=Path(self.model.output).name)

    def transfer(self):
        if self.model.cumulative_ps is None:
            self.compute(transfer=True)
        else:
            self.run(lambda model: model.save(model.output), on_complete=self.transfer_loaded)

    def transfer_loaded(self):
        params = {
            "is_vv_vh": self.model.polarized,
            "use_header": False,
            "matrix_columns": [],
            "g_factor": self.model.g_factor,
            "polarization": self.model.polarization,
            "rep_rate": 10.0,
            "rebin": (1, 1),
            "dt": self.model.dt_ns,
        }
        try:
            if self.add_dataset:
                self.add_dataset(Path(self.model.output), params)
            else:
                from chisurf.core.actions import dispatch

                dispatch(name="experiment.set", payload={"name": "TCSPC"})
                dispatch(name="setup.params.set", payload={"params": params})
                dispatch(
                    name="dataset.add",
                    payload={"filename": self.model.output, "experiment_reader": None},
                )
            self.model.message = "Added histogram to ChiSurf."
        except Exception as exc:
            self.model.message = f"Transfer failed: {exc}"

    def clear(self):
        self.job.stop()
        self.model.files = []
        self.model.bid_files = []
        self.model.invalidate()
        self.model.message = "Inputs cleared."

    def draw_setup(self, box):
        im.begin_disabled(self.job.running)
        self.editor.draw()
        im.end_disabled()

    def draw_queue(self, caption, key, paths, enabled, pickers):
        """One input list: its pickers, a checkable row per file (right-click removes), and All / None / Remove / Clear."""
        pad = " " if key == "burst" else ""          # the two lists' buttons need different ids (the caption is the id)
        if caption:
            im.text(caption)
        im.begin_disabled(self.job.running or self.dialog is not None or self.dataset_picker.is_open)
        got = button_row([dict(label=label + pad, key=f"{key}_{name}", tip=tip)
                          for name, label, tip, _ in pickers],
                         remember=self.remember)
        for name, label, tip, action in pickers:
            if got == f"{key}_{name}":
                self.tour.notify_used(got)
                action()
        im.end_disabled()
        top = im.get_cursor_screen_pos()
        for index, path in enumerate(list(paths)):
            changed, use = im.checkbox(f"##{key}check{index}", enabled.get(path, True))
            im.set_item_tooltip("Include this file in the histogram calculation.")
            self.remember(f"{key}_check_{index}")
            if changed:
                enabled[path] = use
                self.model.update_output_filename()
            im.same_line()
            if im.selectable(f"{Path(path).name}##{key}file{index}", self.selected[key] == path):
                self.selected[key] = path
            im.set_item_tooltip(path + " — right-click to remove the input.")
            self.remember(f"{key}_row_{index}")
            if im.begin_popup_context_item(f"{key}menu{index}"):
                if im.menu_item("Remove input"):
                    self.remove_input(key, path)
                im.set_item_tooltip("Remove this input without deleting its source file.")
                im.end_popup()
        if not paths:
            im.text_disabled("Nothing queued.")
        self.remember(f"{key}_list", (top[0], top[1], max(1.0, im.get_content_region_avail()[0]),
                                      max(im.get_text_line_height(), im.get_cursor_screen_pos()[1] - top[1])))
        im.begin_disabled(self.job.running)
        row = button_row([
            dict(label="All" + pad, key=f"{key}_all", tip="Include every file of this list."),
            dict(label="None" + pad, key=f"{key}_none", tip="Exclude every file of this list."),
            dict(label="Remove" + pad, key=f"{key}_remove", tip="Remove the selected file from the list (it stays on disk).",
                 enabled=self.selected[key] in paths),
            dict(label="Clear" + pad, key=f"{key}_clear", tip="Remove every file of this list and the computed histogram.",
                 enabled=bool(paths)),
        ], remember=self.remember)
        im.end_disabled()
        if row == f"{key}_all":
            enabled.update({path: True for path in paths})
        elif row == f"{key}_none":
            enabled.update({path: False for path in paths})
        elif row == f"{key}_remove":
            self.remove_input(key, self.selected[key])
        elif row == f"{key}_clear":
            paths.clear()
            enabled.clear()
            self.model.invalidate()
            self.model.message = "Inputs cleared."
        if row:
            self.model.update_output_filename()
            self.tour.notify_used(row)

    def remove_input(self, key, path):
        paths = self.model.files if key == "photon" else self.model.bid_files
        if path in paths:
            paths.remove(path)
        self.selected[key] = None
        self.model.update_output_filename()

    def draw_inputs(self, box):
        self.item_rects.clear()
        self.button("📖  Guide", "A walk through queueing files, choosing the detector, computing and exporting.",
                    self.start_guide, key="guide")
        im.same_line()
        self.button("❓  Help", "Histogram, burst-gate, shift and transfer conventions.", self.help.show, key="help")
        im.separator()
        im.text_wrapped(self.model.message or "Queue photon files, then Compute.")
        if self.job.running:
            im.text(f"{self.progress[0]}/{self.progress[1]} files")
            self.button("⏹  Stop", "Stop between file reads and discard pending results; an autosave already "
                        "writing may finish.", self.job.stop, key="stop")
        im.begin_disabled(self.job.running or self.dialog is not None or self.dataset_picker.is_open)
        self.form.rects.clear()
        draw_form(self.run_spec, self.fields, self.form)
        self.item_rects.update(self.form.rects)
        im.end_disabled()
        im.text(f"FWHM (VV + 2G VH): {self.model.fwhm_ns:.3g} ns ({self.model.fwhm_bins:g} channels)")
        self.remember("fwhm")
        self.draw_photon_list()
        open_bursts = im.collapsing_header("Burst selections (BID/BUR)", 32 if self.model.bid_files else 0)
        im.set_item_tooltip("Restrict the photons to bursts: queue .bst/.bur photon-index files (inclusive bounds).")
        self.remember("burst_header")
        if open_bursts:
            self.draw_burst_list()
        if not self.labels.ready:
            self.labels.measure([f["label"] for f in labelled(self.spec["sections"] + self.run_spec["sections"])])
            self.labels.pad(self.spec["sections"])
        im.begin_disabled(self.job.running or self.dialog is not None or self.dataset_picker.is_open)
        self.form.rects.clear()
        draw_form(self.spec, self.fields, self.form)
        self.item_rects.update(self.form.rects)
        im.end_disabled()

    def draw_photon_list(self):
        pickers = [
            ("files", "➕  Files…", "Queue TTTR/PTO photon files, with per-file inclusion controls.",
             lambda: self.choose("TTTR inputs", self.add_files, multiple=True)),
            ("folder", "📁  Folder…", "Queue photon files recursively from a folder.",
             lambda: self.choose("TTTR folder", self.add_files, mode="folder")),
            ("database", "🗄  Database…", "Select raw photon data from the MMFDB object store.",
             self.dataset_picker.open),
        ]
        self.draw_queue("Photon files", "photon", self.model.files, self.model.enabled, pickers)

    def draw_burst_list(self):
        pickers = [
            ("files", "➕  Files…", "Queue inclusive photon-index burst selections (BID/BUR).",
             lambda: self.choose("Burst indices", self.add_bids, multiple=True, filters=BURST_FILTERS)),
            ("folder", "📁  Folder…", "Expand a folder to its .bst/.bur photon-index files.",
             lambda: self.choose("Burstwise folder", self.add_bids, mode="folder", filters=BURST_FILTERS)),
            ("find", "🔍  Find TTTR", "Search four parent directories for the photon files the burst selections "
             "were made on.", self.find_sources),
        ]
        self.draw_queue("", "burst", self.model.bid_files, self.model.bid_enabled, pickers)

    def draw_plot(self, box):
        flags = [("log_y", "Log counts", "Use a positive logarithmic intensity axis."),
                 ("show_vv", "VV", "Show or hide the cumulative parallel decay."),
                 ("show_vh", "VH", "Show or hide the cumulative perpendicular decay."),
                 ("show_combined", "VV + 2G VH", "Show or hide the combined decay.")]
        for i, (attr, label, tip) in enumerate(flags):
            if i:
                im.same_line()
            _, value = im.checkbox(label, getattr(self, attr))
            setattr(self, attr, value)
            im.set_item_tooltip(tip)
            self.remember(attr)
        if implot.begin_plot("##microtime_decay", (-1, -1)):
            implot.setup_axes("Time (ns)", "Counts")
            if self.log_y:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            vectors = [
                ("VV", self.model.cumulative_parallel, self.show_vv),
                ("VH", self.model.cumulative_perpendicular, self.show_vh),
                ("VV + 2G VH", self.model.combined, self.show_combined),
            ]
            existing = [np.asarray(v) for _, v, on in vectors if v is not None and on]
            if existing:
                peak = max(float(np.max(v)) for v in existing)
                n = max(map(len, existing))
                signature = (id(self.model.original_histograms), self.log_y, peak, self.model.dt_ns)
                implot.setup_axes_limits(0, max(self.model.dt_ns * n, self.model.dt_ns), 1 if self.log_y else 0,
                                         max(2, peak * 1.1),
                                         cond=implot.COND_ALWAYS if signature != self.plot_signature
                                         else implot.COND_ONCE)
                self.plot_signature = signature
                for label, vector, on in vectors:
                    if vector is not None and on:
                        values = np.where(vector > 0, vector, np.nan) if self.log_y else vector
                        implot.plot_line(label, np.arange(len(vector)) * self.model.dt_ns, values)
            elif not self.model.original_histograms:
                implot.setup_axes_limits(0, 12.5, 0, 100, cond=implot.COND_ONCE)
            pos, size = implot.get_plot_pos(), implot.get_plot_size()
            implot.end_plot()
            self.remember("plot", (pos[0], pos[1], size[0], size[1]))

    def render(self):
        self.job.poll()
        self.editor.poll()
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        self.docks.draw(frame)
        self.dataset_picker.render(frame)
        self.editor.draw_dialogs(frame)
        if self.dialog is not None:
            pressed = self.dialog_window.begin(frame)
            result = self.dialog.draw()
            self.dialog_window.end()
            if result:
                callback, self.dialog = self.dialog_callback, None
                callback(result)
            elif result is False or pressed == "close":
                self.dialog = None
        self.help.draw(frame)
        self.tour.draw(*vp.size)
        signature = self.fingerprint()
        if signature != self.input_signature and not self.job.running:
            self.model.invalidate()
            self.input_signature = signature

    def on_paths_dropped(self, paths):
        photons = []
        bursts = []
        for path in paths:
            if Path(path).suffix.lower() in {".bst", ".bur"}:
                bursts.append(path)
            else:
                photons.append(path)
        if photons:
            self.add_files(photons)
        if bursts:
            self.add_bids(bursts)

    def export_settings(self):
        return self.model.export_settings()

    def restore_settings(self, state):
        self.job.stop()
        self.model.restore_settings(state)
        from chisurf.core.setup_channel_definition import ChannelDefinition

        self.editor.model = ChannelDefinition(self.model.setup)
        self.editor.model.on_changed = self.definition_changed

    def close(self):
        self.job.close()
        self.editor.close()
        self.dataset_picker.close()


def create_app(reader=None, add_dataset=None):
    return HistogramApp(reader=reader, add_dataset=add_dataset)
