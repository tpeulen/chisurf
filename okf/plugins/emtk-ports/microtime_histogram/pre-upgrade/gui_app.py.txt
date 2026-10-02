"""Native EMTK TTTR/BID histogram workflow with the full shared setup editor."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .model import HistogramModel


class HistogramApp(ImApp):
    def __init__(self, reader=None, add_dataset=None):
        self.model = HistogramModel()
        self.reader = reader
        self.add_dataset = add_dataset
        self.help = EmTkHelpWindow(
            title="Scientific workflow help", resource=Path(__file__).with_name("help.md")
        )
        self.guide = EmTkGuidedTour(steps=Path(__file__).with_name("guide.json"))
        self.job = BackgroundJob()
        self.progress = (0, 0)
        self.dialog = None
        self.dialog_callback = None
        self.editor = ChannelDefinitionWidget(on_changed=self.definition_changed)
        self.dataset_picker = DatasetPicker(on_paths=self.add_files)
        self.log_y = False
        self.show_vv = self.show_vh = self.show_combined = True
        self.plot_signature = None
        self.input_signature = self.fingerprint()
        self.docks = DockManager(
            Split("h", 0.34, Region("setup"), Split("v", 0.48, Region("files"), Region("plot")))
        )
        self.docks.add_window("setup", "Detector definition", self.draw_setup, dock="setup")
        self.docks.add_window("files", "Files and histogram options", self.draw_files, dock="files")
        self.docks.add_window("plot", "Microtime decay", self.draw_plot, dock="plot")
        super().__init__(gui=self.render, continuous=True)

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

    def button(self, label, tip, callback):
        if im.button(label):
            callback()
        im.set_item_tooltip(tip)

    def numeric(self, label, value, tip, integer=False):
        im.text(label + ":")
        im.set_next_item_width(-1)
        changed, value = (
            im.input_int("##" + label, int(value), step=0)
            if integer
            else im.input_float("##" + label, float(value), step=0)
        )
        im.set_item_tooltip(tip)
        return changed, value

    def choose(self, title, callback, mode="open", multiple=False, bids=False):
        if self.job.running or self.editor._future is not None:
            return
        filters = (
            "Burst indices (*.bst *.bur)"
            if bids
            else "Photon data (*.pto *.ptu *.ht3 *.ht2 *.spc *.phu *.tttr);;All files (*)"
        )
        if mode == "save":
            filters = "Decay (*.dat *.txt)"
        self.dialog = FileDialog(title, mode=mode, multiselect=multiple, filters=filters)
        self.dialog_callback = callback

    def add_files(self, paths):
        if not self.job.running:
            self.model.add_paths(paths)

    def add_bids(self, paths):
        if not self.job.running:
            self.model.add_paths(paths, bids=True)
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

    def draw_queue(self, label, paths, enabled):
        im.text(label)
        for index, path in enumerate(list(paths)):
            changed, use = im.checkbox(f"##{label}{index}", enabled.get(path, True))
            im.set_item_tooltip("Include this file in the histogram calculation.")
            if changed:
                enabled[path] = use
                self.model.update_output_filename()
            im.same_line()
            im.selectable(f"{Path(path).name}##{label}file{index}")
            im.set_item_tooltip(path + " — right-click to remove the input.")
            if im.begin_popup_context_item(f"{label}menu{index}"):
                if im.menu_item("Remove input"):
                    paths.remove(path)
                    self.model.update_output_filename()
                im.set_item_tooltip("Remove this input without deleting its source file.")
                im.end_popup()

    def draw_files(self, box):
        im.text_wrapped(self.model.message)
        if self.job.running:
            im.text(f"{self.progress[0]}/{self.progress[1]} files")
            self.button(
                "Stop",
                "Stop between file reads and discard pending results; an autosave already writing may finish.",
                self.job.stop,
            )
        im.begin_disabled(
            self.job.running or self.dialog is not None or self.dataset_picker.is_open
        )
        self.button(
            "Photon files…",
            "Queue TTTR/PTO photon streams, with per-file inclusion controls.",
            lambda: self.choose("TTTR inputs", self.add_files, multiple=True),
        )
        self.button(
            "Photon folder…",
            "Queue photon files recursively from a folder.",
            lambda: self.choose("TTTR folder", self.add_files, mode="folder"),
        )
        self.button(
            "Database…",
            "Select raw photon data from the MMFDB object store.",
            self.dataset_picker.open,
        )
        self.button(
            "BID/BUR files…",
            "Queue inclusive photon-index burst selections and find corresponding sources.",
            lambda: self.choose("Burst indices", self.add_bids, multiple=True, bids=True),
        )
        self.button(
            "Burstwise folder…",
            "Expand a folder to its .bst/.bur photon-index files.",
            lambda: self.choose("Burstwise folder", self.add_bids, mode="folder", bids=True),
        )
        self.button(
            "Find corresponding TTTR",
            "Search four parent directories for sources matching BID/BUR names.",
            self.find_sources,
        )
        self.button(
            "Clear inputs",
            "Clear photon files, burst selections and existing histogram results.",
            self.clear,
        )
        self.draw_queue("Photon files", self.model.files, self.model.enabled)
        self.draw_queue("Burst selections", self.model.bid_files, self.model.bid_enabled)
        detectors = list(self.model.setup.get("detectors", {}))
        if detectors:
            im.text("Detector:")
            im.set_next_item_width(-1)
            changed, index = im.combo(
                "##detector",
                detectors.index(self.model.detector) if self.model.detector in detectors else 0,
                detectors,
            )
            im.set_item_tooltip(
                "Use this detector interleaved parallel/perpendicular routing channels and G-factor."
            )
            if changed:
                self.model.select_detector(detectors[index])
        _, self.model.polarized = im.checkbox("Polarization resolved", self.model.polarized)
        im.set_item_tooltip(
            "Split detector channels into alternating VV/VH routes; unchecked produces one unpolarized stream."
        )
        for attr, label in (("parallel", "VV channels"), ("perpendicular", "VH channels")):
            im.text(label + ":")
            im.set_next_item_width(-1)
            _, text = im.input_text("##" + label, ",".join(map(str, getattr(self.model, attr))))
            im.set_item_tooltip(
                "Comma-separated routing channels; detector selection can populate these automatically."
            )
            try:
                setattr(
                    self.model,
                    attr,
                    [int(value.strip()) for value in text.split(",") if value.strip()],
                )
            except ValueError:
                pass
        windows = ["All windows"] + list(self.model.setup.get("windows", {}))
        im.text("Excitation window:")
        im.set_next_item_width(-1)
        changed, index = im.combo(
            "##excitation_window",
            windows.index(self.model.window) if self.model.window in windows else 0,
            windows,
        )
        im.set_item_tooltip(
            "Apply this inclusive excitation micro-time gate, or include all windows."
        )
        if changed:
            self.model.window = windows[index]
        formats = ["Auto", "PTU", "HT3", "SPC-130", "SPC-600_256", "SPC-600_4096", "PTO"]
        if self.model.filetype not in formats:
            formats.append(self.model.filetype)
        im.text("TTTR format:")
        changed, index = im.combo("##TTTR format", formats.index(self.model.filetype), formats)
        im.set_item_tooltip("Container reader override; Auto uses the file header.")
        if changed:
            self.model.filetype = formats[index]
        changed, value = self.numeric(
            "Binning", self.model.binning, "Group this many adjacent micro-time bins.", True
        )
        if changed:
            self.model.binning = max(1, value)
        changed, value = self.numeric(
            "Time step ns",
            self.model.dt_ns,
            "Nanoseconds per binned TAC channel; reading normally derives this from the header.",
        )
        if changed and value > 0:
            self.model.dt_ns = value
            self.model.dt_manual = True
            self.model.update_timeshifts()
        changed, self.model.dt_manual = im.checkbox("Manual time step", self.model.dt_manual)
        im.set_item_tooltip("Keep the entered time step instead of using file-header resolution.")
        for attr, label, tip in (
            ("g_factor", "G-factor", "Weight VH by 2G in the combined intensity."),
            (
                "vv_shift",
                "VV histogram shift",
                "Pad/clip VV histogram bins; this does not wrap photon times.",
            ),
            (
                "vh_shift",
                "VH histogram shift",
                "Pad/clip VH histogram bins; this does not wrap photon times.",
            ),
        ):
            changed, value = self.numeric(
                label, getattr(self.model, attr), tip, integer=attr != "g_factor"
            )
            if changed:
                setattr(self.model, attr, value)
                self.model.update_timeshifts()
        polarization = ["vv", "vh", "vm"]
        im.text("Transfer polarization:")
        im.set_next_item_width(-1)
        changed, index = im.combo(
            "##transfer_polarization", polarization.index(self.model.polarization), polarization
        )
        im.set_item_tooltip(
            "TCSPC reader polarization mode applied when transferring the saved decay."
        )
        if changed:
            self.model.polarization = polarization[index]
        im.text("Output decay file:")
        im.set_next_item_width(-1)
        _, self.model.output = im.input_text("##output", self.model.output)
        im.set_item_tooltip(
            "Single-column export: VV bins followed by VH bins, compatible with read_vv_vh."
        )
        _, self.model.auto_save = im.checkbox("Autosave after compute", self.model.auto_save)
        im.set_item_tooltip(
            "Preserve the original workflow: write the cumulative decay once computation succeeds."
        )
        self.button(
            "Compute histogram",
            "Read selected photons and burst gates in a background worker.",
            self.compute,
        )
        self.button(
            "Save histogram", "Write the current shifted cumulative VV/VH decay.", self.save
        )
        self.button(
            "Save as…",
            "Choose an alternative decay filename.",
            lambda: self.choose("Save decay", lambda paths: self.save(paths[0]), mode="save"),
        )
        self.button(
            "Transfer to ChiSurf",
            "Save and add a TCSPC dataset with current G-factor, time step and polarization.",
            self.transfer,
        )
        im.end_disabled()
        self.button(
            "Help", "Read histogram, burst-gate, shift and transfer conventions.", self.help.show
        )
        self.button(
            "Guide", "Walk through input/setup selection, calculation and export.", self.guide.start
        )

    def draw_plot(self, box):
        _, self.log_y = im.checkbox("Log counts", self.log_y)
        im.set_item_tooltip("Use a positive logarithmic intensity axis.")
        for attr, label in (("show_vv", "VV"), ("show_vh", "VH"), ("show_combined", "VV + 2G VH")):
            _, value = im.checkbox(label, getattr(self, attr))
            setattr(self, attr, value)
            im.set_item_tooltip("Show or hide this cumulative decay trace.")
            im.same_line()
        im.new_line()
        im.text(f"FWHM {self.model.fwhm_ns:.3g} ns ({self.model.fwhm_bins:g} bins)")
        if implot.begin_plot("##microtime_decay", (-1, -1)):
            implot.setup_axes("Time ns", "Counts")
            if self.log_y:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            vectors = [
                ("VV", self.model.cumulative_parallel, self.show_vv),
                ("VH", self.model.cumulative_perpendicular, self.show_vh),
                ("VV + 2G VH", self.model.combined, self.show_combined),
            ]
            existing = [
                np.asarray(vector)
                for _, vector, enabled in vectors
                if vector is not None and enabled
            ]
            if existing:
                peak = max(float(np.max(vector)) for vector in existing)
                n = max(map(len, existing))
                signature = (id(self.model.original_histograms), self.log_y, peak, self.model.dt_ns)
                implot.setup_axes_limits(
                    0,
                    max(self.model.dt_ns * n, self.model.dt_ns),
                    1 if self.log_y else 0,
                    max(2, peak * 1.1),
                    cond=implot.COND_ALWAYS
                    if signature != self.plot_signature
                    else implot.COND_ONCE,
                )
                self.plot_signature = signature
                for label, vector, enabled in vectors:
                    if vector is not None and enabled:
                        values = np.where(vector > 0, vector, np.nan) if self.log_y else vector
                        implot.plot_line(label, np.arange(len(vector)) * self.model.dt_ns, values)
            implot.end_plot()

    def render(self):
        self.job.poll()
        self.editor.poll()
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        self.docks.draw(frame)
        if self.help.open:
            self.help.draw(frame)
        if self.guide.active:
            self.guide.draw(*vp.size)
        self.dataset_picker.render(frame)
        self.editor.draw_dialogs(frame)
        if self.dialog:
            if im.begin("Histogram file chooser"):
                result = self.dialog.draw()
                if result:
                    callback = self.dialog_callback
                    self.dialog = None
                    callback(result)
                elif result is False:
                    self.dialog = None
            im.end()
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
