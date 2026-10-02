"""EMTK app for Lazy Lifetime Analysis: one decay fitted by the LLTF command line, its log, results and plots.

The inputs and fitting options are the view spec ``lltf.view.json`` drawn by
emtk's view_form over :class:`~.model.LLTFModel` (the file rows are its custom
``lltf_files`` section); the Results panel of the same spec is drawn in the
Results tab. The fit runs as the LLTF CLI in a subprocess the model owns, so
the window keeps drawing while it streams its output.
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

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

from .model import LLTFModel

DATA_FILTERS = [("TCSPC data", ["*.dat", "*.txt", "*.csv"]), ("All files", ["*"])]
YAML_FILTERS = [("YAML", ["*.yml", "*.yaml"]), ("All files", ["*"])]
ERROR = (1.0, 0.45, 0.45, 1.0)
TAB_TIPS = {
    "Information": "Show workflow guidance.",
    "Analysis Output": "Inspect live stdout and stderr from the fitting process.",
    "Results": "Inspect fitted lifetimes, fit statistics and exports.",
}

#: The file rows: model attribute, caption, tooltip, browse action, browse caption, guide key of the browse button.
FILE_ROWS = (
    ("decay_file", "Decay File", "Measured two-column decay: time (ns) and counts.", "decay_file", "Load...",
     "Load..."),
    ("irf_file", "IRF File", "Measured two-column instrument response: time (ns) and counts.", "irf_file", "Load...",
     "load_irf"),
    ("config_file", "Config File", "The LLTF YAML configuration: fit range, background, IRF shift, starting values, "
     "pile-up. Edit… opens it; the next run uses the edited text.", None, "Edit...", "Edit..."),
    ("output_dir", "Output Directory", "Where <decay>_fit.json and <decay>_fit.png are written (the decay's folder "
     "when empty).", "output_dir", "Select...", "Select..."),
)


class LLTFApp(TourTarget, ImApp):
    """The Lazy Lifetime Analysis window."""

    def __init__(self, model=None):
        self.model = model or LLTFModel()
        self.tab = "Information"
        self.pending_tab = "Information"
        self.config_open = False
        self.config_window = DialogWindow("LLTF configuration", size=(820, 620))
        self.dialog = None
        self.file_window = None
        self.file_action = ""
        self.item_rects = {}
        self.arrays = None
        spec = json.loads((Path(__file__).parent / "lltf.view.json").read_text(encoding="utf-8"))
        self.controls_spec = {"sections": [p for p in spec["sections"] if p.get("title") != "Results"]}
        self.results_spec = {"sections": [p["sections"] for p in spec["sections"] if p.get("title") == "Results"][0]}
        self.form = FormState()
        self.form.custom["lltf_files"] = self.draw_files
        self.results_form = FormState()
        resources = Path(__file__).parent.parent
        self.help_window = EmTkHelpWindow(
            title="Lazy Lifetime Analysis — Help", resource=resources / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=resources / "guide.json",
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
            owner=self,
            wait_for_controls=True,
            on_step_change=self.reveal_step,
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(
            Split("h", 0.40, Region("inputs"), Split("v", 0.35, Region("details"), Region("plots")))
        )
        self.docks.add_window(
            "inputs", "LLTF inputs and options", self.controls, dock="inputs", closable=False
        )
        self.docks.add_window(
            "details",
            "Information, output and results",
            self.details,
            dock="details",
            closable=False,
        )
        self.docks.add_window(
            "plots", "Fit and residuals", self.plots, dock="plots", closable=False
        )
        self.native_layouts = {"main": self.docks}
        super().__init__(self.render, continuous=False)

    def reveal_step(self, index, step):
        key = EmTkGuidedTour._target_key(step.get("target"))
        if key == "Results":
            self.pending_tab = "Results"

    def error(self, action):
        try:
            return action()
        except Exception as exc:
            self.model.status = f"Error: {exc}"
            return None

    def choose(self, action):
        self.file_action = action
        mode = (
            "folder"
            if action == "output_dir"
            else "save"
            if action in ("save_config", "save_results")
            else "open"
        )
        title = {
            "decay_file": "Load decay",
            "irf_file": "Load IRF",
            "config_file": "Load configuration",
            "output_dir": "Output directory",
            "save_config": "Save configuration",
            "save_results": "Export fit results",
        }[action]
        filename = (
            "lltf-config.yml"
            if action == "save_config"
            else "lltf-results.json"
            if action == "save_results"
            else ""
        )
        filters = (
            YAML_FILTERS
            if "config" in action
            else [("JSON", ["*.json"])]
            if action == "save_results"
            else DATA_FILTERS
        )
        import chisurf

        directory = str(getattr(chisurf, "working_path", "") or "") or None
        self.dialog = FileDialog(
            title, mode=mode, filename=filename, filters=filters, directory=directory
        )
        self.file_window = DialogWindow(title, size=(760, 540))

    def start(self):
        """Start the fit (the model raises what is missing) and show its output."""
        self.model.start()
        self.pending_tab = "Analysis Output"
        self.arrays = None
        self.tour.notify_used("Fit")

    def controls(self, box):
        m = self.model
        if im.button("📖 Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through loading the inputs and running a real lifetime analysis.")
        self.remember("Guide")
        im.same_line()
        if im.button("❓ Help"):
            self.help_window.show()
        im.set_item_tooltip("What the fit decides by rule, what it reports, and what to check before believing it.")
        self.remember("help")
        im.separator()
        self.form.rects.clear()
        im.begin_disabled(m.running)
        draw_form(self.controls_spec, m, self.form)
        im.end_disabled()
        self.item_rects.update(self.form.rects)
        self.item_rects["Find Optimal"] = self.form.rects.get("find_optimal")      # the Qt tour's name for it
        ready = Path(m.decay_file).is_file() and Path(m.irf_file).is_file()
        im.begin_disabled(m.running or not ready)
        if im.button("▶ Fit"):
            self.error(self.start)
        im.set_item_tooltip("Run the LLTF command line in a background process with these inputs and options; "
                            "needs a decay and an IRF.")
        self.remember("Fit")
        im.end_disabled()
        im.same_line()
        im.begin_disabled(not m.running)
        if im.button("⏹ Stop"):
            self.model.stop()
        im.set_item_tooltip("Terminate the running fit; its captured output stays in Analysis Output.")
        self.remember("stop")
        im.end_disabled()
        if m.status.startswith("Error:") or "failed" in m.status:
            im.text_colored(ERROR, m.status)
        else:
            im.text_wrapped(m.status)

    def draw_files(self, section, model, state, width):
        """The four file rows of the Qt wizard: a path and its Load… / Edit… / Select… button."""
        m = self.model
        label_w = max(im.calc_text_size(row[1])[0] for row in FILE_ROWS) + 8.0
        button_w = max(im.calc_text_size(row[4])[0] for row in FILE_ROWS) + 2 * im.get_style().frame_padding[0]
        for attr, label, tip, action, button, key in FILE_ROWS:
            im.text(label)
            im.same_line(label_w)
            spacing = im.get_style().item_spacing[0]
            im.set_next_item_width(max(60.0, width - label_w - button_w - 2 * spacing - 8.0))
            flags = 0 if attr == "config_file" else im.InputTextFlags.READ_ONLY
            changed, value = im.input_text(f"##{attr}", getattr(m, attr) or "", flags=flags, elide_start=True)
            im.set_item_tooltip(tip)
            self.remember(attr)
            if changed and attr == "config_file":
                m.config_file, m.config_dirty = value, False
            im.same_line()
            if im.button(f"{button}##{attr}.browse", (button_w, 0)):     # not the field's id: it took the click
                self.tour.notify_used(key)
                if action is None:
                    self.edit_config()
                else:
                    self.choose(action)
            im.set_item_tooltip({"Edit...": "Open the configuration in the YAML editor (load another, edit, save).",
                                 "Select...": "Choose the output directory."}.get(button, f"Choose the {label.lower()}."))
            self.remember(key)

    def edit_config(self):
        """Open the YAML editor on the configuration file (or the buffer, if it was edited)."""
        m = self.model
        if m.config_file and Path(m.config_file).is_file() and not m.config_dirty:
            self.error(lambda: m.load_config(m.config_file))
        self.config_open = True

    def on_paths_dropped(self, paths):
        """A dropped YAML is the configuration, a folder the output directory, data files the decay, then the IRF."""
        m = self.model
        for path in map(str, paths):
            if Path(path).is_dir():
                m.output_dir = path
            elif path.lower().endswith((".yml", ".yaml")):
                self.error(lambda p=path: m.load_config(p))
            elif Path(path).is_file():
                if not m.decay_file:
                    m.decay_file = path
                else:
                    m.irf_file = path

    def details(self, box):
        m = self.model
        if im.begin_tab_bar("lltf_tabs"):
            for tab in ("Information", "Analysis Output", "Results"):
                flags = im.TabItemFlags.SET_SELECTED if self.pending_tab == tab else 0
                active = im.begin_tab_item(tab, flags=flags)
                im.set_item_tooltip(TAB_TIPS[tab])               # on every tab, not only the open one
                self.item_rects[tab] = im.get_item_rect()
                if active:
                    self.tab = tab
                    if tab == "Information":
                        im.text_wrapped(
                            "Load the measured decay and IRF, edit YAML settings if needed, choose a fixed or automatically selected lifetime count, then Fit. Analysis runs separately; inspect its output, fitted lifetimes and weighted residuals before interpreting the model."
                        )
                    elif tab == "Analysis Output":
                        if im.button("Clear output"):
                            m.clear_output()
                        im.set_item_tooltip(
                            "Clear displayed logs without interrupting the analysis."
                        )
                        im.text_unformatted("\n".join(m.output))
                    else:
                        if m.result is None:
                            im.text_wrapped(m.results_summary())
                        else:
                            draw_form(self.results_spec, m, self.results_form)    # the spec's Results panel
                            if im.button("💾 Export result JSON"):
                                self.choose("save_results")
                            im.set_item_tooltip(
                                "Copy the complete fit result and model arrays to a JSON file."
                            )
                    im.end_tab_item()
            im.end_tab_bar()
            self.pending_tab = None

    def plots(self, box):
        if self.arrays is None:
            im.text_wrapped("Fit plots appear after a successful analysis.")
            return
        a = self.arrays
        if im.begin_tab_bar("lltf_plot_tabs"):
            for title in ("Decay and fit", "Weighted residuals"):
                if im.begin_tab_item(title):
                    if implot.begin_plot(title, size=(-1.0, -1.0)):
                        implot.setup_axes(
                            "Time (ns)",
                            "Counts" if title == "Decay and fit" else "Weighted residual",
                        )
                        if title == "Decay and fit":
                            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
                            for name, x, y in [
                                ("Data", a["time"], a["decay"]),
                                ("Fit", a["model_time"], a["fit"]),
                                ("IRF (scaled)", a["irf_time"], a["irf"]),
                            ]:
                                implot.plot_line(name, x, np.where(np.asarray(y) > 0, y, np.nan))
                        else:
                            implot.plot_line("Weighted residuals", a["model_time"], a["residuals"])
                        for index, value in enumerate(a["range"]):
                            implot.drag_line_x(
                                index,
                                value,
                                flags=implot.DRAG_TOOL_FLAGS_NO_INPUTS
                                | implot.DRAG_TOOL_FLAGS_NO_FIT,
                            )
                        implot.end_plot()
                    im.end_tab_item()
                    im.set_item_tooltip("Show " + title.lower() + " and the analysis range.")
            im.end_tab_bar()

    def restore_settings(self, settings):
        self.model.restore_preferences(settings)

    def export_settings(self):
        return self.model.export_preferences()

    def close(self):
        self.model.close()

    def animating(self):
        return self.model.process is not None or super().animating()

    def render(self):
        self.item_rects.clear()
        if self.model.poll() and self.model.result is not None:
            self.arrays = self.error(self.model.plot_arrays)
            self.pending_tab = "Results"
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        im.begin_disabled(self.dialog is not None or self.config_open)
        self.docks.draw(box)
        im.end_disabled()
        if self.config_open:
            pressed = self.config_window.begin(box)
            changed, text = im.input_text_multiline(
                "YAML##lltf", self.model.config_text, size=(-1.0, 420.0)
            )
            im.set_item_tooltip(
                "Edit the complete LLTF YAML configuration; the next run uses this buffer."
            )
            if changed:
                self.model.config_text = text
                self.model.config_dirty = True
            if im.button("Save configuration"):
                self.choose("save_config")
            im.set_item_tooltip("Save the edited YAML configuration to a chosen file.")
            im.same_line()
            if im.button("Close editor") or pressed == "close":
                self.config_open = False
            im.set_item_tooltip("Close the editor; unsaved edits remain available to the next run.")
            self.config_window.end()
        if self.dialog is not None:
            pressed = self.file_window.begin(box)
            result = self.dialog.draw()
            if result:
                action = self.file_action
                self.dialog = None
                if action == "config_file":
                    self.error(lambda: self.model.load_config(result[0]))
                elif action == "save_config":
                    self.error(lambda: self.model.save_config(result[0]))
                elif action == "save_results":
                    self.error(
                        lambda: Path(result[0]).write_text(json.dumps(self.model.result, indent=2))
                    )
                else:
                    setattr(self.model, action, str(result[0]))
                    if action in ("decay_file", "irf_file", "output_dir"):
                        import chisurf

                        chisurf.working_path = (
                            Path(result[0]) if action == "output_dir" else Path(result[0]).parent
                        )
                    if action == "decay_file":
                        self.tour.notify_used("Load...")
            elif result is False or pressed == "close":
                self.dialog = None
            self.file_window.end()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)


def make_app():
    return LLTFApp()
