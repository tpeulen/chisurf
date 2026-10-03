"""EMTK app for the IRF & BG calibration step: per-detector IRF, fit/IRF windows and backgrounds.

The controls are the Calibration panel of ``calibration.view.json`` -- the spec
the Qt tool renders -- drawn by emtk's view_form over
:class:`~.view_model.CalibrationViewModel`; its ``path_list`` custom section is
the IRF file list drawn here. The spec's ``decay_conv`` section is the plot dock:
data and IRF decays with draggable fit (blue), IRF (green) and background (grey)
windows. The photon histograms are binned on a worker thread.
"""

from __future__ import annotations

import copy
import queue
import threading
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

from .view_model import CalibrationViewModel

HERE = Path(__file__).parent
ERROR = (1.0, 0.45, 0.45, 1.0)


def _controls_spec() -> dict:
    """The spec's Calibration panel (its plot section is the plot dock)."""
    import json

    spec = json.loads((HERE / "calibration.view.json").read_text(encoding="utf-8"))
    dock = spec["sections"][0]
    panel = next(s for s in dock["sections"] if s.get("title") == "Calibration")
    return {"sections": panel["sections"]}


def label(text):
    return tr(text, context="ImgCalibration")


class CalibrationApp(TourTarget, ImApp):
    """Edit independently cached detector calibrations and publish deep snapshots."""

    def __init__(self, model=None, coordinator=None, **kwargs):
        self.model = model or CalibrationViewModel()
        self.coordinator = coordinator
        if coordinator is not None:
            self.model.publish = coordinator.set_calibration
        self.busy = False
        self.error = ""
        self.apply_error = ""
        self._messages = queue.SimpleQueue()
        self._failed_signature = None
        self.dialog = None
        self.dialog_window = None
        self.dialog_action = ""
        self.file_selection = -1
        self.item_rects = {}
        self.spec = _controls_spec()
        self.form = FormState()
        self.form.custom["path_list"] = self.draw_irf_files
        self.dataset_picker = DatasetPicker(on_paths=self.add_irfs)
        self.plot_limits = None
        self.help = EmTkHelpWindow(
            title="IRF & BG — Help", resource=HERE / "help.md", owner=self, on_start_guide=self.start_guide
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
            owner=self, wait_for_controls=True,
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Split("h", 0.32, Region("controls"), Region("plot")))
        self.docks.add_window(
            "controls", label("Calibration"), self.controls, dock="controls", closable=False
        )
        self.docks.add_window("plot", label("Decay & IRF"), self.plot, dock="plot", closable=False)
        self.native_layouts = {"main": self.docks}
        super().__init__(self.render, continuous=False)

    def start_guide(self):
        self.tour.start()

    def choose(self, action):
        self.dialog_action = action
        self.dialog = FileDialog(
            label("Open TTTR" if action == "source" else "Add IRF"),
            mode="open",
            filters=[("Photon data", ["*.pto", "*.ptu", "*.ht3", "*.spc", "*.pt3"]), ("All files", ["*"])],
            multiselect=action == "irf",
        )
        self.dialog_window = DialogWindow(
            self.dialog.title, size=(700, 540), key="calibration_file"
        )
        self.dialog_window.show()

    def add_irfs(self, paths):
        if not self.model.display_detector:
            self.error = label("Choose a detector first")
            return False
        current = self.model.sel_irf_files
        for path in paths:
            path = str(path)
            if path not in current:
                current.append(path)
        self.model.sel_irf_files = current
        return True

    def files_dropped(self, paths):
        """Files dropped on the window (the hook the hosts call) go to this detector's IRF list."""
        self.add_irfs(paths) if paths else None

    def on_files_dropped(self, paths):
        """The hub's spelling of the same hook: the answer says whether the files were taken."""
        return self.add_irfs(paths) if paths else False

    def apply_setup_settings(self, payload):
        self.model.apply_setup_settings(copy.deepcopy(payload))
        self.model._hist_cache.clear()

    def apply_pipeline_context(self, payload):
        self.model.apply_pipeline_context(payload)

    def request_histograms(self):
        signature = (self.model._hist_key(), repr(self.model.detectors))
        if self.busy or not self.model.needs_histograms() or signature == self._failed_signature:
            return
        snapshot = copy.copy(self.model)
        snapshot.detectors = copy.deepcopy(self.model.detectors)
        snapshot.calibration = copy.deepcopy(self.model.calibration)
        snapshot._hist_cache = {}
        snapshot._observers = []
        key = snapshot._hist_key()
        self.busy = True
        self.error = ""

        def worker():
            try:
                result = snapshot.ensure_histograms()
                self._messages.put((key, signature, result, ""))
            except Exception as exc:
                self._messages.put((key, signature, None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        while not self._messages.empty():
            key, signature, hist, error = self._messages.get()
            self.busy = False
            # A setup/channel change can leave the same filename/detector key.
            # Cache only if the worker's complete detector definition still matches.
            if signature == (self.model._hist_key(), repr(self.model.detectors)):
                if hist is not None:
                    self.model._hist_cache[key] = hist
                self.error = error
                self._failed_signature = signature if error else None
        self.request_histograms()

    def retry(self):
        if not self.busy:
            self._failed_signature = None
            self.model._hist_cache.clear()
            self.request_histograms()

    def apply(self):
        """Publish through the model (it refuses an empty window or a negative background)."""
        ok = self.model.apply()
        # Its own field: a new histogram binning clears ``error`` (the worker's), and must not wipe a refusal.
        self.apply_error = "" if ok else self.model.status_text
        return ok

    def button_row(self, buttons):
        """Buttons side by side, wrapping onto a new line rather than running off a narrow dock."""
        pad = 2 * im.get_style().frame_padding[0] + im.get_style().item_spacing[0]
        for i, (text, action, tip, key) in enumerate(buttons):
            if i and im.get_line_avail() >= im.calc_text_size(label(text))[0] + pad:
                im.same_line()
            self.button(text, action, tip, key=key)

    def button(self, text, action, tip=None, key=None):
        pressed = im.button(label(text))
        im.set_item_tooltip(label(tip or text))
        if key:
            self.remember(key)
        if pressed:
            if key:
                self.tour.notify_used(key)
            action()

    def controls(self, box):
        self.remember("controls", tuple(box))             # the dock's box: what must hold the toolbar
        toolbar = (
            ("Guide", self.start_guide, "A walk through calibrating one detector.", "guide"),
            ("Help", self.help.show, "What the windows and backgrounds mean, and where they go.", "help"),
            ("Open TTTR…", lambda: self.choose("source"), "Open the source photon data whose decay is shown.",
             "open_source"),
            ("Refresh", self.retry, "Bin the histograms again after correcting the source files.", "refresh"),
        )
        self.button_row(toolbar)
        im.text_wrapped(self.model.filename or label("Choose source photon data"))
        im.separator()
        if not self.model.window_names():
            im.text_wrapped(label("Configure detector windows in Imaging Tools"))
        self.form.rects.clear()
        im.begin_disabled(not self.model.window_names())
        draw_form(self.spec, self.model, self.form)          # the spec the Qt tool renders
        im.end_disabled()
        self.item_rects.update(self.form.rects)
        if self.coordinator is not None:
            self.button("Next ▶", self.next_step, "Apply and advance the imaging pipeline.", key="next")
        if self.busy:
            im.text_disabled(label("Binning histograms…"))
        for message in (self.error, self.apply_error):       # shown while binning too
            if message:
                im.text_colored(ERROR, message)

    def draw_irf_files(self, section, model, state, width):
        """The spec's IRF file list: this detector's files, summed into its IRF."""
        im.text(str(section.get("title") or "IRF files"))
        self.button_row((
            ("Files…", lambda: self.choose("irf"), "Add IRF photon files for this detector; they are summed.",
             "add_irf"),
            ("Database…", self.dataset_picker.open, "Pick IRF files from the MMFDB object store.", "database_irf"),
            ("Remove", self.remove_irf, "Remove the selected IRF file.", "remove_irf"),
            ("Clear", lambda: setattr(self.model, "sel_irf_files", []), "Clear this detector's IRF files.",
             "clear_irf"),
        ))
        top = im.get_cursor_screen_pos()
        for index, path in enumerate(self.model.sel_irf_files):
            if im.selectable(Path(path).name + "##irf" + str(index), index == self.file_selection):
                self.file_selection = index
            im.set_item_tooltip(path)
        if not self.model.sel_irf_files:
            im.text_disabled(label("No IRF file: the raw data are used"))
        self.remember("path_list", (top[0], top[1] - 24.0, width, im.get_cursor_screen_pos()[1] - top[1] + 24.0))

    def remove_irf(self):
        files = self.model.sel_irf_files
        if 0 <= self.file_selection < len(files):
            files.pop(self.file_selection)
            self.model.sel_irf_files = files
            self.file_selection = -1

    def next_step(self):
        if self.apply():
            self.coordinator.advance_from("calibration")

    def plot(self, box):
        data = self.model.decay_data()
        if data is None:
            im.text_wrapped(label("Load photon data and configure a detector to view decay"))
            self.remember("decay_conv")
            return
        if implot.begin_plot(label("Decay & IRF"), (-1, -1)):
            implot.setup_axes(label("Microtime channel"), label("Photon counts / normalized IRF"))
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.setup_legend()
            top = max(float(np.max(data["data"])), 1.0) * 2.0
            limits = (0.0, float(data["n"]), 0.5, top)
            # ALWAYS when the data change, ONCE after (a first ONCE on a drawn plot is ignored -- known issue).
            implot.setup_axes_limits(*limits, cond=implot.COND_ALWAYS if limits != self.plot_limits else implot.COND_ONCE)
            self.plot_limits = limits
            x = np.arange(data["n"], dtype=float)
            implot.plot_line(label("Decay"), x, np.maximum(data["data"], 0.1))
            for name in ("irf_vv", "irf_vh"):
                if data[name] is not None:
                    scaled = (
                        data[name]
                        * max(float(np.max(data["data"])), 1)
                        / max(float(np.max(data[name])), 1e-12)
                    )
                    implot.plot_line(name.upper(), x, np.maximum(scaled, 0.1))
            tags = {}
            for index, (name, setter, color) in enumerate(
                (
                    ("conv", self.model.set_conv_range, (51, 153, 255, 255)),
                    ("irf_range", self.model.set_irf_range, (77, 204, 102, 255)),
                    ("bg_range", self.model.set_bg_range, (153, 153, 153, 255)),
                )
            ):
                start, stop = data[name]
                tag_names, tag_color = tags.setdefault(stop, ([], color))
                tag_names.append(("Fit", "IRF", "BG")[index])
                a = implot.drag_line_x(index * 2, start, color, 2)
                b = implot.drag_line_x(index * 2 + 1, stop, color, 2)
                if a.modified or b.modified:
                    setter(max(0, min(data["n"], a.value)), max(0, min(data["n"], b.value)))
                if a.hovered or b.hovered:
                    im.set_tooltip(label("Drag fit, IRF and background boundaries"))
            for value, (names, color) in tags.items():
                implot.tag_x(value, color, " / ".join(names))
            implot.end_plot()
            im.set_item_tooltip(label("Drag fit, IRF and background boundaries"))
        self.remember("decay_conv")

    def export_settings(self):
        return {
            "filename": self.model.filename,
            "detectors": copy.deepcopy(self.model.detectors),
            "calibration": copy.deepcopy(self.model.calibration),
            "display_detector": self.model.display_detector,
        }

    def restore_settings(self, data):
        self.model.filename = str(data.get("filename", ""))
        self.model.detectors = copy.deepcopy(data.get("detectors", {}))
        self.model.calibration = copy.deepcopy(data.get("calibration", {}))
        self.model.display_detector = data.get("display_detector", "")
        if self.model.display_detector not in self.model.detectors:
            self.model.display_detector = next(iter(self.model.detectors), "")
        self.model._hist_cache.clear()

    def close(self):
        """Close the dataset picker; the binning worker is a daemon thread whose result is dropped."""
        self.dialog = None
        self.dataset_picker.close()

    def animating(self):
        return super().animating() or self.busy

    def render(self):
        self.poll()
        vp = im.get_main_viewport()
        self.docks.draw((0, 0, *vp.size))
        if self.dialog:
            pressed = self.dialog_window.begin((0, 0, *vp.size))
            result = self.dialog.draw()
            if result:
                if self.dialog_action == "source":
                    self.model.apply_pipeline_context({"source": str(result[0])})
                else:
                    self.add_irfs(result)
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
            self.dialog_window.end()
        self.dataset_picker.render((0, 0, *vp.size))
        self.help.draw((0, 0, *vp.size))
        self.tour.draw(*vp.size)


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    from .locales import install_translations

    install()
    install_translations()
    return CalibrationApp(**kwargs)
