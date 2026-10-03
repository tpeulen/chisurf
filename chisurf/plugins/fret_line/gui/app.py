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
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import cap_widths

from .model import FretLineModel, hex_rgba

HERE = Path(__file__).parent
COMPONENTS_TABLE, LINES_TABLE = "component_rows", "line_rows"


class FRETLineApp(ImApp):
    """Build a mixture, sweep one parameter or fraction, overlay the lines, without a Qt host."""

    window_title = "ChiSurf FRET Line Generator"

    def __init__(self, push_callback=None, model: FretLineModel | None = None) -> None:
        self.model = model or FretLineModel(push_callback)
        spec = json.loads((HERE / "fret_line_emtk.view.json").read_text(encoding="utf-8"))
        cap_widths(spec["sections"])
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.dialog_form = FormState()
        self.item_rects: dict[str, tuple] = {}
        self.error = ""
        self.reference_index = 0
        self.input_selection: dict = {}
        self.loaded_curves: list = []
        self.file_dialog: FileDialog | None = None
        self.file_purpose: tuple = ()
        self.file_window = DialogWindow("File", size=(700.0, 540.0), key="fret_line_file")
        self.message_window = DialogWindow("FRET lines", size=(480.0, 170.0), key="fret_line_notice", fit_height=True)
        self.help_window = EmTkHelpWindow(title="FRET line - Help", resource=HERE / "help.md", owner=self)
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json", owner=self, wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key))
        self.help_window.on_start_guide = self.tour.start
        self.form.on_used = self.tour.notify_used
        self._last_component = self.model.component_index
        self._pending: dict = {}
        # the Qt tool's arrangement: mixture / sweep / lines and the editor on top, the two plots below, the action bar under all
        self.docks = DockManager(Split("v", 0.9, Split("v", 0.58, Split("h", 0.4, Region("controls"), Region("editor")),
                                                       Split("h", 0.5, Region("efficiency"), Region("lifetime"))), Region("actions")))
        for key, title, draw in (("components", "Components", self.draw_components), ("sweep", "Sweep", self.draw_sweep),
                                 ("lines", "FRET lines", self.draw_lines)):
            self.docks.add_window(key, title, draw, dock="controls", closable=False)
        self.docks.add_window("editor", "Live model editor", self.draw_editor, dock="editor", closable=False)
        self.docks.add_window("efficiency", "FRET line", lambda box: self.plot("e_fret", "E_FRET"), dock="efficiency", closable=False)
        self.docks.add_window("lifetime", "τ_X(τ_F)", lambda box: self.plot("tau_x", "τ_X (ns)"), dock="lifetime", closable=False)
        self.docks.add_window("actions", "Actions", self.draw_actions, dock="actions", closable=False)
        super().__init__(self.render)

    # -- the model's state, for the tests and the tour ------------------------------------------------ #
    @property
    def lines(self) -> list:
        return self.model.lines

    # -- one frame --------------------------------------------------------------------------------- #
    def render(self) -> None:
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
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
            wanted = self.model.lines[self.model.line_index]["name"] if 0 <= self.model.line_index < len(self.model.lines) else None
            if binding.control.selected_key != wanted:
                binding.control.select_key(wanted)
        for name in (COMPONENTS_TABLE, LINES_TABLE):
            if name in self.form.rects:
                self.item_rects[name] = self.form.rects[name]

    # -- the spec windows -------------------------------------------------------------------------- #
    def _sections(self, name: str) -> list:
        return self.panels[name]["sections"]

    def draw_components(self, box: Any) -> None:
        draw_sections(self._sections("components"), self.model, self.form, titles=False)

    def draw_sweep(self, box: Any) -> None:
        draw_sections(self._sections("sweep"), self.model, self.form, titles=False)

    def draw_lines(self, box: Any) -> None:
        draw_sections(self._sections("lines"), self.model, self.form, titles=False)

    def draw_actions(self, box: Any) -> None:
        draw_sections(self._sections("actions"), self.model, self.form, titles=False)
        im.same_line()
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain static, dynamic, WLC and mixture FRET lines.")
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through a static line and a two-state dynamic line.")
        self.item_rects["guide"] = im.get_item_rect()

    # -- requests of the model: the file chooser -------------------------------------------------- #
    def _requests(self) -> None:
        request, self.model.request = self.model.request, ""
        if request == "save" and self.file_dialog is None:
            self.file_dialog = FileDialog("Save FRET lines", mode="save", filename="fret_lines.csv", filters="CSV (*.csv)")
            self.file_purpose = ("save",)
            self.file_window.title = "Save FRET lines"
            self.file_window.show()

    def choose_input(self, slot: str) -> None:
        self.file_dialog = FileDialog("Load " + slot, mode="open",
                                      filters="Curves (*.csv *.txt *.dat *.tsv *.pto);;All files (*)")
        self.file_purpose = ("input", self.model.selected["model"], slot)
        self.file_window.title = "Load " + slot
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
                self.model.message = f"Failed: {exc}"
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
        expanded = im.collapsing_header("Input curves")
        im.set_item_tooltip("Load or unload measured IRF, background and correction curves for this model.")
        if not expanded:
            return
        curves = self.input_curves()
        for slot in slots:
            im.push_id(slot)
            source = getattr(model.datasets, slot, None)
            im.text_wrapped(slot + ": " + (getattr(source, "name", "Measured curve") if source is not None else "not loaded"))
            if curves:
                index = min(self.input_selection.get(slot, 0), len(curves) - 1)
                _, index = im.combo("Reference curve", index, [getattr(c, "name", f"Curve {i + 1}") for i, c in enumerate(curves)])
                self.input_selection[slot] = index
                im.set_item_tooltip("Select an already imported experimental curve for this model input.")
                if im.button("Use selected curve"):
                    self._guarded(self.model.bind_input, slot, curves[index])
                im.set_item_tooltip("Bind this experimental curve to the model input.")
            if im.button("Load curve file"):
                self.choose_input(slot)
            im.set_item_tooltip("Read a measured curve with the ChiSurf DataCurve loader.")
            im.same_line()
            im.begin_disabled(source is None)
            if im.button("Unload curve"):
                self.model.unload_input(slot)
            im.set_item_tooltip("Remove this measured input; unloading an IRF restores the modelled response.")
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
            im.combo("Donor reference", 0, ["No live donor references"])
            im.set_item_tooltip("Open a donor-only fit or register a lifetime working model to populate the reference list.")
            im.end_disabled()
        else:
            self.reference_index = min(self.reference_index, len(references) - 1)
            _, self.reference_index = im.combo("Donor reference", self.reference_index, [r[0] for r in references])
            im.set_item_tooltip("Use a donor / lifetime spectrum from a live fit or registered model as the donor-only reference.")
            if im.button("Apply donor reference"):
                self._guarded(m.apply_donor_reference, references[self.reference_index][1])
            im.set_item_tooltip("Copy the reference amplitudes and lifetimes into this component; the source stays unchanged.")
        for group_name, group in model._groups.items():
            if group.component_parameters():
                im.push_id(group_name)
                im.text_unformatted(group_name)
                if im.button("Add subcomponent"):
                    model.change_components(group_name, 1)
                im.set_item_tooltip(f"Add an independent {group_name} component.")
                im.same_line()
                if im.button("Remove subcomponent"):
                    model.remove_component(group_name)
                im.set_item_tooltip(f"Remove the last {group_name} component; one stays.")
                im.pop_id()
        settings_open = im.collapsing_header("Model settings")
        im.set_item_tooltip("Scalar settings that define the model's topology and numerical evaluation.")
        if settings_open:
            for name in model.scalar_names():
                value = model.get_scalar(name)
                if value is None:
                    continue
                changed, new = im.input_float(name, float(value), step=1.0)
                im.set_item_tooltip(f"{name}: scalar configuration of the model.")
                if changed:
                    model.set_scalar(name, new)
        if self.error:
            im.text_wrapped(self.error)
        draw_sections(self._sections("editor"), m, self.form, titles=False)

    # -- the plots ---------------------------------------------------------------------------------- #
    def plot(self, key: str, label: str) -> None:
        if implot.begin_plot(label, (-1, -1)):
            implot.setup_axes("τ_F (ns)", label)
            implot.setup_legend()
            for line in self.model.lines:
                if line["visible"]:
                    implot.set_next_line_style(hex_rgba(line["color"]), 2.0)
                    implot.plot_line(line["name"], line["result"]["tau_f"], line["result"][key])
            if key == "tau_x":  # the diagonal tau_X = tau_F: the lifetime of a species that does not exchange
                ref = float(self.model.tau_d0) or 1.0
                implot.set_next_line_style((170, 170, 170, 255), 1.0)
                implot.plot_line("τ_X = τ_F", [0.0, ref], [0.0, ref])
            implot.end_plot()
            im.set_item_tooltip("The computed lines; hide or remove them in the FRET lines tab.")
        self.item_rects["plot_" + key] = im.get_item_rect()

    # -- settings and the tour ----------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        return self.model.export_state()

    def restore_settings(self, settings: dict) -> None:
        self.model.restore_state(settings)

    def close(self) -> None:
        self.model.close()


def make_app(**kwargs) -> FRETLineApp:
    """Build the app (the manifest's ``entrypoints.emtk``); ``push_callback`` is the host's ndX connection."""
    from chisurf.emtk.i18n import install

    install()
    return FRETLineApp(push_callback=kwargs.get("push_callback"))
