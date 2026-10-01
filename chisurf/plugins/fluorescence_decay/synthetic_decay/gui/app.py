"""Native synthetic TCSPC and polarized-decay generator."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.dialog_window import DialogWindow
from emtk.view_form import FormState, draw_form

from chisurf.emtk.datasets import register_synthetic_fit
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from .model import SyntheticDecayModel


class SyntheticDecayApp(ImApp):
    def __init__(self, model=None, fit_sink=None):
        self.model = model or SyntheticDecayModel()
        self.model.choose_file = self.request_file
        self.model.fit_sink = fit_sink or register_synthetic_fit
        self.dialog = None
        self.dialog_action = ""
        self.file_window = None
        self.form = FormState()
        self.item_rects = {}
        spec = json.loads(Path(__file__).with_name("synthetic_decay.view.json").read_text())
        self.spec = {"sections": [s for s in spec["sections"] if s["type"] not in ("plot", "info") and s["type"] != "button_row"]}
        def configure_panels(sections):
            for section in sections:
                if section.get("type") == "panel":
                    section["collapsible"] = True
                    section.setdefault("description", f"Expand or collapse {section['title']}.")
                    configure_panels(section.get("sections", []))
        configure_panels(self.spec["sections"])
        self._plain_labels(self.spec["sections"])
        self._bind_tables(self.spec["sections"])
        self.corrections = self.spec["sections"][3]["sections"][1]
        self.last_mode = None
        # File picking happens in a native overlay; the editable path still allows pasting.
        self.spec["sections"][2]["sections"][0]["kind"] = "str"
        self.help_window = EmTkHelpWindow(title="Synthetic decay — Help", resource=Path(__file__).with_name("help_emtk.md"), owner=self)
        self.tour = EmTkGuidedTour(steps=Path(__file__).with_name("guide_emtk.json"), get_target_rect=self.target_rect, owner=self, wait_for_controls=True, on_step_change=self.reveal_step)
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Split("h", .42, Region("settings"), Split("v", .66, Region("decay"), Region("anisotropy"))))
        self.docks.add_window("settings", "Generator settings", self.controls, dock="settings", closable=False)
        self.docks.add_window("decay", "Synthetic decay", self.decay_plot, dock="decay", closable=False)
        self.docks.add_window("anisotropy", "Anisotropy r(t)", self.anisotropy_plot, dock="anisotropy", closable=False)
        super().__init__(self.render, continuous=False)

    @staticmethod
    def _bind_tables(sections):
        """Native tables edit the model's own rows (``edited_call``); the Qt spec's ``update_call`` is not read."""
        for section in sections:
            if section.get("type") == "table" and section.get("update_call"):
                section["source"] = {"spectrum_source": "spectrum_records", "rotation_source": "rotation_records"}[section["source"]]
                section["edited_call"] = "edit_cell"
            if section.get("attr") == "photon_count":
                section["decimals"] = 0  # a count: the default float format would draw 1e+06
            SyntheticDecayApp._bind_tables(section.get("sections", []))

    @staticmethod
    def _plain_labels(sections):
        """The shared spec carries the Qt buttons' emoji; the native window shows plain labels."""
        for section in sections:
            for item in section.get("buttons", []):
                item["label"] = re.sub(r"^[^\w(]+\s*", "", str(item.get("label", "")))
            SyntheticDecayApp._plain_labels(section.get("sections", []))

    def reveal_step(self, index, step):
        target = EmTkGuidedTour._target_key(step.get("target"))
        def reveal(section):
            children = section.get("sections", [])
            found = target in (section.get("attr"), section.get("title"), section.get("source"))
            found = any(reveal(child) for child in children) or found
            if found and section.get("type") == "panel":
                self.form.folds[section["title"]] = True
            return found
        for section in self.spec["sections"]:
            reveal(section)

    def target_rect(self, name):
        alias = {"Lifetime spectrum": "spectrum_source", "Anisotropy": "polarization"}.get(name, name)
        return self.item_rects.get(alias) or self.form.rects.get(name + ".fold") or self.form.rects.get(alias)

    def request_file(self, mode, title, filename, filters):
        self.dialog = FileDialog(title, mode=mode, filename=filename, filters=filters)
        self.file_window = DialogWindow(title, size=(760, 540))
        self.dialog_action = "load_spectrum" if title == "Load lifetime spectrum" else "save"
        return None

    def browse_irf(self):
        self.dialog = FileDialog("Select instrument response", mode="open", filters="Data (*.txt *.dat *.npy)")
        self.dialog_action = "irf"
        self.file_window = DialogWindow("Select instrument response", size=(760, 540))

    def controls(self, box):
        actions = [
            ("Generate", "generate", "Generate the VM decay or VV/VH pair and the sample anisotropy curve.", self.model.generate),
            ("Save", "save", "Save CSV, text, NumPy, JSON or a VV/VH file with detection calibration.", self.model.save),
            ("Fit group", "send_to_fit", "Register the generated dataset and create its lifetime fit group with calibration and shared parameters.", self.model.send_to_fit),
            ("Browse IRF", "irf_path", "Choose an optional instrument response to convolve with the ideal decay.", self.browse_irf),
            ("Help", "help", "Explain lifetime spectra, anisotropy, convolution and noise.", self.help_window.show),
            ("Guide", "guide", "Walk through generation, export and creating a fit group.", self.tour.start),
        ]
        for index, (label, name, tip, action) in enumerate(actions):
            if im.button(label):
                try:
                    action()
                    self.tour.notify_used(name)
                    self.tour.notify_used(label)
                except Exception as exc:
                    self.model.status = f"Error: {exc}"
            im.set_item_tooltip(tip)
            self.item_rects[name] = im.get_item_rect()
            self.item_rects[label] = self.item_rects[name]
            if (index + 1) % 3 and index + 1 < len(actions):
                im.same_line()
        im.text_wrapped(self.model.status_text())
        draw_form(self.spec, self.model, self.form)

    def _plot(self, title, series, label, log=False):
        if implot.begin_plot(title, size=(-1., -1.)):
            implot.setup_axes("Micro-time (ns)", label)
            if log and series:  # an empty plot keeps linear axes: a log axis would invent a 1e-21 range
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            for curve in series:
                values = np.asarray(curve["y"], dtype=float)
                if log:
                    values = np.where(values > 0, values, np.nan)
                implot.plot_line(curve["name"], np.asarray(curve["x"]), values)
            implot.end_plot()

    def decay_plot(self, box):
        self._plot("Synthetic TCSPC decay", self.model.decay_series(), "Counts", log=True)

    def anisotropy_plot(self, box):
        self._plot("Sample anisotropy", self.model.aniso_series(), "r(t)")

    def render(self):
        if self.model.polarization != self.last_mode:
            self.last_mode = self.model.polarization
            self.form.folds.pop(self.corrections["title"], None)
            self.corrections["collapsed"] = not self.model.is_vv_vh()
        viewport = im.get_main_viewport()
        box = (*viewport.pos, *viewport.size)
        self.form.rects.clear()
        im.begin_disabled(self.dialog is not None)
        self.docks.draw(box)
        im.end_disabled()
        if self.dialog is not None:
            pressed = self.file_window.begin(box)
            result = self.dialog.draw()
            if result:
                action = self.dialog_action
                self.dialog = None
                try:
                    if action == "irf":
                        self.model.irf_path = str(result[0])
                        self.form.buffers.clear()
                    elif action == "load_spectrum":
                        self.model.load_spectrum(str(result[0]))
                    else:
                        self.model.save(str(result[0]))
                except Exception as exc:
                    self.model.status = f"File action failed: {exc}"
            elif result is False or pressed == "close":
                self.dialog = None
            self.file_window.end()
        self.help_window.draw(box)
        self.tour.draw(*viewport.size)


    # ── persistence ─────────────────────────────────────────────────────
    def export_settings(self):
        """The generator's inputs (not the generated curves)."""
        return self.model.export_settings()

    def restore_settings(self, settings):
        """Restore :meth:`export_settings`; invalid entries are ignored."""
        self.model.restore_settings(settings)
        self.form.buffers.clear()


def make_app():
    return SyntheticDecayApp()
