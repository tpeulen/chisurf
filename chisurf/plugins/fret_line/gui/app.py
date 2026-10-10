"""Native mixture FRET-line generator: spec forms for the mixture and the sweep, a live model editor and two plots.

The three left tabs (components, sweep, lines), the action bar and the notice are the view spec
``fret_line_emtk.view.json`` drawn by :func:`emtk.view_form.draw_sections` over :class:`~.model.FretLineModel`. Drawn here
because a spec cannot express them: the live model editor of the selected component (its parameters are the model's own),
the two plots, the Help / Guide buttons and the file chooser for Save CSV and measured input curves.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.i18n import tr
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.typed_field import typed_number_field
from chisurf.plugins.emtk_layout import action_button, cap_widths, window_size

from .model import FretLineModel, hex_rgba

HERE = Path(__file__).parent
COMPONENTS_TABLE, LINES_TABLE = "component_rows", "line_rows"


class FRETLineApp(ImApp):
    """Build a mixture, sweep one parameter or fraction, overlay the lines, without a Qt host."""

    window_title = "ChiSurf FRET Line Generator"

    def __init__(self, push_callback=None, model: FretLineModel | None = None) -> None:
        self.window_title = tr("ChiSurf FRET Line Generator")
        self.model = model or FretLineModel(push_callback)
        self.model.on_open_advanced = self.show_advanced
        spec = json.loads((HERE / "fret_line_emtk.view.json").read_text(encoding="utf-8"))
        self.window_size = window_size(spec, (640, 480))
        cap_widths(spec["sections"])
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.dialog_form = FormState()
        self.item_rects: dict[str, tuple] = {}
        self.error = ""
        self._number_buffers: dict[str, str] = {}
        self.reference_index = 0
        self.input_selection: dict = {}
        self.loaded_curves: list = []
        self.file_dialog: FileDialog | None = None
        self.file_purpose: tuple = ()
        self.file_window = DialogWindow(tr("File"), size=(700.0, 540.0), key="fret_line_file")
        self.message_window = DialogWindow(tr("FRET lines"), size=(480.0, 170.0), key="fret_line_notice", fit_height=True)
        self.help_window = EmTkHelpWindow(title=tr("FRET line - Help"), resource=HERE / "help.md", owner=self)
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json", owner=self, wait_for_controls=True, on_step_change=self._tour_step,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key))
        self.help_window.on_start_guide = self.tour.start
        self.form.on_used = self.tour.notify_used
        self._last_component = self.model.component_index
        self._pending: dict = {}
        self._initial_layout_selected = False
        self.docks = DockManager(Split("v", 0.9, Split("v", 0.58, Split("h", 0.4, Region("controls"), Region("editor")),
                                                       Split("h", 0.5, Region("efficiency"), Region("lifetime"))), Region("actions")))
        self.docks.add_window("your_dyes", tr("Your dyes"), self.draw_your_dyes, dock="controls", closable=False)
        for key, title, draw in (("components", tr("Components"), self.draw_components), ("sweep", tr("Sweep"), self.draw_sweep),
                                 ("lines", tr("FRET lines"), self.draw_lines)):
            self.docks.add_window(key, title, draw, dock="controls", closable=False)
        self.docks.add_window("editor", tr("Live model editor"), self.draw_editor, dock="editor", closable=False)
        self.docks.add_window("efficiency", tr("FRET line"), lambda box: self.plot("e_fret", "E_FRET"), dock="efficiency", closable=False)
        self.docks.add_window("lifetime", tr("τ_X(τ_F)"), lambda box: self.plot("tau_x", tr("τ_X (ns)")), dock="lifetime", closable=False)
        self.docks.add_window("actions", tr("Actions"), self.draw_actions, dock="actions", closable=False)
        for key in ("components", "sweep", "lines", "editor"):
            self.docks.windows[key].visible = False
        super().__init__(self.render)

    def _tour_step(self, index: int, step: dict) -> None:
        """Reveal the tab owning a tour target before its rectangle is measured."""
        target = step.get("target", {})
        key = target.get("name") or target.get("attr")
        if key == "Advanced.fold":
            self.docks.focus("your_dyes")
            return
        for panel_name in ("your_dyes", "components", "sweep", "lines", "editor"):
            pending = list(self._sections(panel_name))
            while pending:
                section = pending.pop()
                options = section.get("options", {})
                keys = {section.get("attr"), section.get("action"), options.get("source")}
                keys.update(button.get("action") for button in section.get("buttons", []))
                if key and key in keys:
                    self.docks.focus(panel_name)
                    return
                pending.extend(section.get("sections", []))

    # -- the model's state, for the tests and the tour ------------------------------------------------ #
    @property
    def lines(self) -> list:
        return self.model.lines

    # -- one frame --------------------------------------------------------------------------------- #
    def render(self) -> None:
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        if not self._initial_layout_selected:
            self._initial_layout_selected = True
            if vp.size[0] < 900:
                compact = Split("v", 0.9, Split("v", 0.58, Region("controls"),
                    Split("h", 0.5, Region("efficiency"), Region("lifetime"))), Region("actions"))
                self.docks.configure_default_layout(compact, {"editor": "controls"})
        self.form.rects.clear()
        self.item_rects.clear()
        self.docks.draw(box)
        self._sync_tables()
        self._requests()
        self._draw_notice(box)
        self._draw_file_dialog(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _sync_tables(self) -> None:
        binding = self.form.tables.get(COMPONENTS_TABLE)
        if binding is not None:
            wanted = self.model.component_index
            if binding.control.selected_key != wanted:
                binding.control.select_key(wanted)
        binding = self.form.tables.get(LINES_TABLE)
        if binding is not None and self.model.lines:
            wanted_line = self.model.lines[self.model.line_index]["name"] if 0 <= self.model.line_index < len(self.model.lines) else None
            if binding.control.selected_key != wanted_line:
                binding.control.select_key(wanted_line)
        for name in (COMPONENTS_TABLE, LINES_TABLE):
            if name in self.form.rects:
                self.item_rects[name] = self.form.rects[name]

    # -- the spec windows -------------------------------------------------------------------------- #
    def _sections(self, name: str) -> list:
        return self.panels[name]["sections"]


    def draw_your_dyes(self, box: Any) -> None:
        """Draw the declared pair starter and folded expert navigation."""
        draw_sections(self._sections("your_dyes"), self.model, self.form, titles=False)

    def show_advanced(self, key: str) -> None:
        """Reveal the original expert panel without changing its scientific state."""
        if key not in ("components", "sweep", "lines", "editor"):
            raise ValueError(key)
        self.docks.focus(key)
        self.request_frame()

    def draw_components(self, box: Any) -> None:
        draw_sections(self._sections("components"), self.model, self.form, titles=False)

    def draw_sweep(self, box: Any) -> None:
        draw_sections(self._sections("sweep"), self.model, self.form, titles=False)

    def draw_lines(self, box: Any) -> None:
        draw_sections(self._sections("lines"), self.model, self.form, titles=False)

    def draw_actions(self, box: Any) -> None:
        draw_sections(self._sections("actions"), self.model, self.form, titles=False)
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if action_button("guide"):
            self.tour.start()
        self.item_rects["guide"] = im.get_item_rect()

    # -- requests of the model: the file chooser -------------------------------------------------- #
    def _requests(self) -> None:
        request, self.model.request = self.model.request, ""
        if request == "save" and self.file_dialog is None:
            self.file_dialog = FileDialog(tr("Save FRET lines"), mode="save", filename="fret_lines.csv", filters=tr("CSV (*.csv)"))
            self.file_purpose = ("save",)
            self.file_window.title = tr("Save FRET lines")
            self.file_window.show()

    def choose_input(self, slot: str) -> None:
        self.file_dialog = FileDialog(tr("Load {slot}").format(slot=slot), mode="open",
                                      filters=tr("Curves (*.csv *.txt *.dat *.tsv *.pto);;All files (*)"))
        self.file_purpose = ("input", self.model.selected["model"], slot)
        self.file_window.title = tr("Load {slot}").format(slot=slot)
        self.file_window.show()

    def _draw_file_dialog(self, box: Any) -> None:
        if self.file_dialog is None:
            return
        pressed = self.file_window.begin(box)
        result = self.file_dialog.draw()
        self.file_window.end()
        if result:
            purpose, self.file_dialog = self.file_purpose, None
            self.file_window.hide()
            try:
                if purpose[0] == "save":
                    self.model.write_csv(result[0])
                else:
                    from chisurf.core.data import DataCurve

                    curve = DataCurve(filename=str(result[0]))
                    self.model.bind_input(purpose[2], curve, model=purpose[1])
                    self.loaded_curves.append(curve)
                    self.error = ""
            except Exception as exc:
                self.error = str(exc)
                self.model.message = tr("Failed: {error}").format(error=exc)
        elif result is False or pressed == "close":
            self.file_dialog = None
            self.file_window.hide()

    def _draw_notice(self, box: Any) -> None:
        window = self.message_window
        if self.model.dialog_open and not window.open:
            window.show()
        if not self.model.dialog_open and window.open:
            window.hide()
        if not window.open:
            return
        window.title = self.model.dialog_title
        pressed = window.begin(box)
        draw_sections(self._sections("dialog"), self.model, self.dialog_form, titles=False)
        window.end()
        if pressed == "close":
            self.model.dialog_ok()

    # -- the live model editor ------------------------------------------------------------------------ #
    def draw_inputs(self, model: Any) -> None:
        slots = model.dataset_slots()
        expanded = im.collapsing_header(tr("Input curves"))
        im.set_item_tooltip(tr("Load or unload measured IRF, background and correction curves for this model."))
        if not expanded:
            return
        curves = self.input_curves()
        for slot in slots:
            im.push_id(slot)
            source = getattr(model.datasets, slot, None)
            im.text_wrapped(slot + ": " + (getattr(source, "name", tr("Measured curve")) if source is not None else tr("not loaded")))
            if curves:
                index = min(self.input_selection.get(slot, 0), len(curves) - 1)
                _, index = im.combo(tr("Reference curve"), index, [getattr(c, "name", tr("Curve {number}").format(number=i + 1)) for i, c in enumerate(curves)])
                self.input_selection[slot] = index
                im.set_item_tooltip(tr("Select an already imported experimental curve for this model input."))
                if im.button(tr("Use selected curve")):
                    self._guarded(self.model.bind_input, slot, curves[index])
                im.set_item_tooltip(tr("Bind this experimental curve to the model input."))
            if im.button(tr("Load curve file")):
                self.choose_input(slot)
            im.set_item_tooltip(tr("Read a measured curve with the ChiSurf DataCurve loader."))
            im.same_line()
            im.begin_disabled(source is None)
            if im.button(tr("Unload curve")):
                self.model.unload_input(slot)
            im.set_item_tooltip(tr("Remove this measured input; unloading an IRF restores the modelled response."))
            im.end_disabled()
            im.pop_id()

    def input_curves(self) -> list:
        import chisurf

        curves = list(self.loaded_curves)
        for group in getattr(chisurf, "imported_datasets", []):
            if not isinstance(group, (list, tuple)) and hasattr(group, "x") and hasattr(group, "y"):
                curves.append(group)
            else:
                try:
                    curves.extend(c for c in group if hasattr(c, "x") and hasattr(c, "y"))
                except TypeError:
                    pass
        return curves

    def _guarded(self, call, *args) -> None:
        try:
            call(*args)
            self.error = ""
        except Exception as exc:
            self.error = str(exc)

    def draw_editor(self, box: Any) -> None:
        m = self.model
        component = m.selected
        im.text_wrapped(f"C{m.component_index}: {component['model_name']}")
        self.item_rects["editor"] = im.get_item_rect()
        model = component["model"]
        self.draw_inputs(model)
        references = m.donor_references()
        if not references:
            im.begin_disabled()
            im.combo(tr("Donor reference"), 0, [tr("No live donor references")])
            im.set_item_tooltip(tr("Open a donor-only fit or register a lifetime working model to populate the reference list."))
            im.end_disabled()
        else:
            self.reference_index = min(self.reference_index, len(references) - 1)
            _, self.reference_index = im.combo(tr("Donor reference"), self.reference_index, [r[0] for r in references])
            im.set_item_tooltip(tr("Use a donor / lifetime spectrum from a live fit or registered model as the donor-only reference."))
            if im.button(tr("Apply donor reference")):
                self._guarded(m.apply_donor_reference, references[self.reference_index][1])
            im.set_item_tooltip(tr("Copy the reference amplitudes and lifetimes into this component; the source stays unchanged."))
        subcomponents_open = True
        if im.get_main_viewport().size[0] < 900:
            subcomponents_open = im.collapsing_header(tr("Subcomponents"))
            im.set_item_tooltip(tr("Add or remove donor lifetimes, distance distributions and rotational components."))
            self.item_rects["subcomponents"] = im.get_item_rect()
        if subcomponents_open:
            for group_name, group in model._groups.items():
                if group.component_parameters():
                    im.push_id(group_name)
                    im.text_unformatted(tr(group_name))
                    if im.button(tr("Add subcomponent")):
                        model.change_components(group_name, 1)
                    im.set_item_tooltip(tr("Add an independent {group} component.").format(group=group_name))
                    im.same_line()
                    if im.button(tr("Remove subcomponent")):
                        model.remove_component(group_name)
                    im.set_item_tooltip(tr("Remove the last {group} component; one stays.").format(group=group_name))
                    im.pop_id()
        settings_open = im.collapsing_header(tr("Model settings"))
        im.set_item_tooltip(tr("Scalar settings that define the model's topology and numerical evaluation."))
        if settings_open:
            for name in model.scalar_names():
                value = model.get_scalar(name)
                if value is None:
                    continue
                new, problem = typed_number_field(
                    f"scalar.{m.component_index}.{name}", float(value), self._number_buffers, integer=False, label=name
                )
                self.item_rects[f"scalar.{name}"] = im.get_item_rect()
                im.set_item_tooltip(tr("{name}: scalar configuration of the model.").format(name=name))
                if problem:
                    self.error = f"{name}: {problem}"
                if new is not None:
                    self.error = ""
                    self._set_scalar(model, name, float(value), new)
        if self.error:
            im.text_wrapped(self.error)
        draw_sections(self._sections("editor"), m, self.form, titles=False)

    def _set_scalar(self, model: Any, name: str, previous: float, new: float) -> None:
        """Apply a typed scalar; a value the model rejects (e.g. a negative threshold) is rolled back and reported.

        The native model validates lazily, so an unchecked bad value would make the editor window fail to
        draw on every following frame.
        """
        model.set_scalar(name, new)
        try:
            model.problem  # builds the model with the new value
        except Exception as exc:  # noqa: BLE001 - the native library raises its own exception type
            model.set_scalar(name, previous)
            self.error = f"{name}: {str(exc).rsplit(': ', 1)[-1]}"

    # -- the plots ---------------------------------------------------------------------------------- #
    def plot(self, key: str, label: str) -> None:
        if implot.begin_plot(label, (-1, -1)):
            implot.setup_axes(tr("τ_F (ns)"), label)
            implot.setup_legend()
            for line in self.model.lines:
                if line["visible"]:
                    implot.set_next_line_style(hex_rgba(line["color"]), 2.0)
                    implot.plot_line(line["name"], line["result"]["tau_f"], line["result"][key])
            if key == "tau_x":  # the diagonal tau_X = tau_F: the lifetime of a species that does not exchange
                ref = float(self.model.tau_d0) or 1.0
                implot.set_next_line_style((170, 170, 170, 255), 1.0)
                implot.plot_line(tr("τ_X = τ_F"), [0.0, ref], [0.0, ref])
            implot.end_plot()
            im.set_item_tooltip(tr("The computed lines; hide or remove them in the FRET lines tab."))
        self.item_rects["plot_" + key] = im.get_item_rect()

    # -- settings and the tour ----------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        return self.model.export_state()

    def restore_settings(self, settings: dict) -> None:
        self.model.restore_state(settings)

    def close(self) -> None:
        self.model.close()


def make_app(**kwargs) -> FRETLineApp:
    """Build the app (the manifest's ``entrypoints.emtk``); ``push_callback`` is the host's ndX
    connection, by default every open ndX window (:func:`~.model.push_to_ndx`)."""
    from chisurf.emtk.i18n import install

    from .model import push_to_ndx

    install()
    return FRETLineApp(push_callback=kwargs.get("push_callback", push_to_ndx))
