"""Native synthetic TCSPC and polarized-decay generator."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.i18n import mark, tr
from emtk.view_form import FormState, draw_form

from chisurf.emtk.datasets import register_synthetic_fit
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import ACTIONS, action_button, window_size

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
        from chisurf.plugins.curve_input import CurveInput

        #: The Input sections: the IRF to convolve with, a lifetime spectrum for the table.
        self.inputs = {
            name: CurveInput("synthetic_decay", self, name=name, title="", height=74.0)
            for name in ("irf", "spectrum")
        }
        self.item_rects = {}
        spec = json.loads(Path(__file__).with_name("synthetic_decay.view.json").read_text())
        self.window_size = window_size(spec, (1100, 720))
        self.spec = {
            "sections": [
                s
                for s in spec["sections"]
                if s["type"] not in ("plot", "info") and s["type"] != "button_row"
            ]
        }

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
        self.help_window = EmTkHelpWindow(
            title="Synthetic decay — Help",
            resource=Path(__file__).with_name("help_emtk.md"),
            owner=self,
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide_emtk.json"),
            get_target_rect=self.target_rect,
            owner=self,
            wait_for_controls=True,
            on_step_change=self.reveal_step,
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(
            Split(
                "h",
                0.42,
                Region("settings"),
                Split("v", 0.66, Region("decay"), Region("anisotropy")),
            )
        )
        self.docks.add_window(
            "settings", "Generator settings", self.controls, dock="settings", closable=False
        )
        self.docks.add_window(
            "decay", "Synthetic decay", self.decay_plot, dock="decay", closable=False
        )
        self.docks.add_window(
            "anisotropy", "Anisotropy r(t)", self.anisotropy_plot, dock="anisotropy", closable=False
        )
        super().__init__(self.render, continuous=False)

    @staticmethod
    def _bind_tables(sections):
        """Tables edit the model's own rows (``edited_call``); the spec's ``update_call`` is not read."""
        for section in sections:
            if section.get("type") == "table" and section.get("update_call"):
                section["source"] = {
                    "spectrum_source": "spectrum_records",
                    "rotation_source": "rotation_records",
                }[section["source"]]
                section["edited_call"] = "edit_cell"
            if section.get("attr") == "polarization":
                section["style"] = "radio_list"
            if section.get("attr") == "photon_count":
                section["decimals"] = 0  # a count: the default float format would draw 1e+06
            SyntheticDecayApp._bind_tables(section.get("sections", []))

    @staticmethod
    def _plain_labels(sections):
        """Strip the emoji the shared spec puts before button labels: the window shows plain labels."""
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
        alias = {"Lifetime spectrum": "spectrum_source", "Anisotropy": "polarization"}.get(
            name, name
        )
        return (
            self.item_rects.get(alias)
            or self.form.rects.get(name + ".fold")
            or self.form.rects.get(alias)
        )

    def request_file(self, mode, title, filename, filters):
        """The model asks where a generated decay is saved (its inputs come from the workspace)."""
        self.dialog = FileDialog(title, mode="save", filename=filename, filters=filters)
        self.file_window = DialogWindow(title, size=(760, 540))
        self.dialog_action = "save"
        return None

    def clear_irf(self):
        """Convolve with no instrument response: the ideal decay."""
        self.model.irf_path = ""
        self.form.buffers.clear()

    def draw_inputs(self):
        """The Input sections: the instrument response, and a lifetime spectrum for the table."""
        for name, caption, tip in (
            (
                "irf",
                mark("IRF"),
                mark("An instrument response from the Datasets workspace to convolve with."),
            ),
            (
                "spectrum",
                mark("Lifetime spectrum"),
                mark("A curve with lifetimes (ns) on x and amplitudes on y fills the component table."),
            ),
        ):
            im.text_disabled(tr(caption))
            im.set_item_tooltip(tr(tip))
            rects = {}
            self.inputs[name].draw(rects, on_used=self.tour.notify_used)
            for key, rect in rects.items():
                self.item_rects[f"{name}.{key}"] = rect

    def controls(self, box):
        actions = [
            (
                "Generate",
                "generate",
                "Generate the VM decay or VV/VH pair and the sample anisotropy curve.",
                self.model.generate,
            ),
            (
                None,
                "save",
                "Save CSV, text, NumPy, JSON or a VV/VH file with detection calibration.",
                self.model.save,
            ),
            (
                "Fit group",
                "send_to_fit",
                "Register the generated dataset and create its lifetime fit group with calibration and shared parameters.",
                self.model.send_to_fit,
            ),
            (
                "Clear IRF",
                "clear_irf",
                "Convolve with no instrument response (the IRF input picks one).",
                self.clear_irf,
            ),
            (None, "help", None, self.help_window.show),
            (None, "guide", None, self.tour.start),
        ]
        # A None label is a shared action (name is its vocabulary key); its English label stays the
        # alias the tour targets.
        for index, (label, name, tip, action) in enumerate(actions):
            if label is None:
                label = ACTIONS[name].label
                pressed = action_button(name, tooltip=tip)
            else:
                pressed = im.button(label)
                im.set_item_tooltip(tip)
            if pressed:
                try:
                    action()
                    self.tour.notify_used(name)
                    self.tour.notify_used(label)
                except Exception as exc:
                    self.model.status = f"Error: {exc}"
            self.item_rects[name] = im.get_item_rect()
            self.item_rects[label] = self.item_rects[name]
            if (index + 1) % 3 and index + 1 < len(actions):
                im.same_line()
        im.text_wrapped(self.model.status_text())
        self.draw_inputs()
        draw_form(self.spec, self.model, self.form)

    def _plot(self, title, series, label, log=False):
        if implot.begin_plot(title, size=(-1.0, -1.0)):
            implot.setup_axes("Micro-time (ns)", label)
            if (
                log and series
            ):  # an empty plot keeps linear axes: a log axis would invent a 1e-21 range
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
                self.dialog = None
                try:
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


def _address(payload: dict, key: str) -> str:
    value = payload.get(key)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "")


def receive_irf(app: SyntheticDecayApp, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``irf``): the instrument response to convolve with.

    The generator reads one column of counts: a curve of the session is written as its counts
    alone (a time column would be flattened into the IRF); a file the workspace links to is used
    as it is.
    """
    import tempfile

    from chisurf.plugins.curve_input import curve_of

    address = _address(payload, "irf")
    if not address:
        return
    dataset = curve_of(address)
    try:
        counts = getattr(dataset, "y", None)
        if counts is not None and len(counts):
            folder = Path(tempfile.gettempdir()) / "chisurf-synthetic-decay-input"
            folder.mkdir(parents=True, exist_ok=True)
            stem = Path(str(getattr(dataset, "name", "") or "irf")).stem or "irf"
            target = folder / f"{stem}.txt"
            np.savetxt(target, np.asarray(counts, float))
            app.model.irf_path = str(target)
        elif Path(address).is_file():
            app.model.irf_path = address
        else:
            raise FileNotFoundError(f"{address} is not in the workspace")
    except Exception as exc:  # noqa: BLE001 - said in the status line
        app.model.status = f"IRF not taken: {exc}"
        return
    app.form.buffers.clear()
    app.tour.notify_used("irf_path")


def receive_spectrum(app: SyntheticDecayApp, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``spectrum``): a lifetime spectrum for the table,
    a curve with lifetimes on x and amplitudes on y."""
    from chisurf.plugins.curve_input import curve_of

    address = _address(payload, "spectrum")
    if not address:
        return
    dataset = curve_of(address)
    if dataset is None:
        app.model.load_spectrum(address)  # a file the session links to: the table formats
        return
    x, y = np.asarray(dataset.x, float), np.asarray(dataset.y, float)
    app.model.set_spectrum(np.column_stack([y, x]).ravel(), str(getattr(dataset, "name", "")))


def make_app():
    return SyntheticDecayApp()
