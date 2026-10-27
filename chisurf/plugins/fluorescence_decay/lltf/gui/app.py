"""EMTK app for Lazy Lifetime Analysis: one decay fitted by the LLTF command line, its log, results and plots.

The decay and IRF are picked from the Datasets workspace in the generated Input section (the
manifest's ``accepts[].from_workspace``; :func:`receive_decays`). The fitting options are the view
spec ``lltf.view.json`` drawn by emtk's view_form over :class:`~.model.LLTFModel` (the file rows,
read-only, are its custom ``lltf_files`` section); the Results panel of the same spec is drawn in the
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
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form

from chisurf.core.plugin.workspace_input import (
    WorkspaceInputMixin,
    input_section,
    register_result,
    resolve_dataset,
    spec_for,
)
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import action_button, window_size

from .model import LLTFModel

YAML_FILTERS = [("YAML", ["*.yml", "*.yaml"]), ("All files", ["*"])]
ERROR = (1.0, 0.45, 0.45, 1.0)
TAB_TIPS = {
    "Information": "Show workflow guidance.",
    "Analysis Output": "Inspect live stdout and stderr from the fitting process.",
    "Results": "Inspect fitted lifetimes, fit statistics and exports.",
}

#: The file rows: model attribute, caption, tooltip, button action, button caption, guide key of the button.
#: The data rows show what the Input section handed over (no button: data comes from the workspace);
#: the two VH rows are drawn in VV/VH mode only.
FILE_ROWS = (
    (
        "decay_file",
        "Decay File",
        "Measured two-column decay: time (ns) and counts; picked in the Input section.",
        None,
        "",
        "",
    ),
    (
        "vh_file",
        "VH File (optional)",
        "The VH channel as a two-column file (time, counts) when the decay file holds only VV. "
        "Empty for a stacked VV/VH or a three-column (time, VV, VH) decay file; a picked curve "
        "named VH fills it.",
        None,
        "",
        "",
    ),
    (
        "irf_file",
        "IRF File",
        "Measured two-column instrument response: time (ns) and counts; the picked curve named "
        "IRF (or the second one picked).",
        None,
        "",
        "",
    ),
    (
        "irf_vh_file",
        "VH IRF (optional)",
        "The VH channel's instrument response; empty: the IRF file serves both channels.",
        None,
        "",
        "",
    ),
    (
        "config_file",
        "Config File",
        "The LLTF YAML configuration: fit range, background, IRF shift, starting values, "
        "pile-up. Edit… opens it; the next run uses the edited text.",
        "edit_config",
        "Edit...",
        "Edit...",
    ),
    (
        "output_dir",
        "Output Directory",
        "Where <decay>_fit.json and <decay>_fit.png are written (the decay's folder when empty).",
        "output_dir",
        "Select...",
        "Select...",
    ),
)


#: The rows of FILE_ROWS that are data from the workspace (read-only).
DATA_ROWS = ("decay_file", "vh_file", "irf_file", "irf_vh_file")


class _Input(WorkspaceInputMixin):
    """The Input section's model: the workspace's decays, a pick handed to :func:`receive_decays`."""

    workspace_input_plugin = "lltf"


def _input_spec() -> dict:
    """The generated Input section of the manifest's ``accepts[].from_workspace``."""
    manifest = Path(__file__).resolve().parents[1] / "manifest.json"
    found = spec_for(json.loads(manifest.read_text(encoding="utf-8")))
    return {"sections": [input_section(found[1])]} if found else {"sections": []}


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
        self.window_size = window_size(spec, (1100, 720))
        self.controls_spec = {
            "sections": [p for p in spec["sections"] if p.get("title") != "Results"]
        }
        self.results_spec = {
            "sections": [p["sections"] for p in spec["sections"] if p.get("title") == "Results"][0]
        }
        self.form = FormState()
        self.form.custom["lltf_files"] = self.draw_files
        #: The Input section: which decay and IRF of the workspace are fitted.
        self.input = _Input()
        self.input.workspace_input_app = self
        self.input_spec = _input_spec()
        self.input_form = FormState()
        #: The workspace dataset of the decay: the fit registers as its child.
        self.source_uid = ""
        #: The workspace address picked for each role (``decay``, ``vh``, ``irf``, ``irf_vh``);
        #: the files the fit reads are written from these.
        self.input_addresses: dict[str, str] = {}
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
        self.input_form.on_used = self.tour.notify_used
        self.input.workspace_input_on_used = self.tour.notify_used
        self.docks = DockManager(
            Split("h", 0.40, Region("inputs"), Split("v", 0.46, Region("details"), Region("plots")))
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
        """Ask where an output goes: the output directory, a saved configuration or the results.

        The decay and IRF are never asked for: they come from the workspace (the Input section).
        """
        self.file_action = action
        title = {
            "output_dir": "Output directory",
            "save_config": "Save configuration",
            "save_results": "Export fit results",
        }[action]
        import chisurf

        directory = str(getattr(chisurf, "working_path", "") or "") or None
        if action == "output_dir":
            # not-input: where the fit's JSON and plot are written
            self.dialog = FileDialog(title, mode="folder", directory=directory)
        else:
            self.dialog = FileDialog(
                title,
                mode="save",
                filename="lltf-config.yml" if action == "save_config" else "lltf-results.json",
                filters=YAML_FILTERS if action == "save_config" else [("JSON", ["*.json"])],
                directory=directory,
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
        if action_button("guide"):
            self.tour.start()
        self.remember("Guide")
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        self.remember("help")
        # The actions come first: in VV/VH mode the options outgrow a small window,
        # and Fit must stay reachable without scrolling.
        if action_button(
            "example",
            enabled=not m.running,
            tooltip=tr(
                "Simulate a VV/VH pair whose answer is known (lifetimes 1 and 4 ns, ρ = 1.5 ns, "
                "r0 = 0.35, G = 1.2), select it in VV/VH mode with the example IRF."
            ),
        ):
            self.error(lambda: m.load_example())
            self.tour.notify_used("load_example")
        self.remember("load_example")
        im.same_line()
        ready = Path(m.decay_file).is_file() and Path(m.irf_file).is_file()
        im.begin_disabled(m.running or not ready)
        if im.button(tr("▶  Fit"), role="primary"):
            self.error(self.start)
        im.set_item_tooltip(
            tr(
                "Run the LLTF command line in a background process with these inputs and options; "
                "needs a decay and an IRF."
            )
        )
        self.remember("Fit")
        im.end_disabled()
        im.same_line()
        im.begin_disabled(not m.running)
        if im.button(tr("⏹  Stop"), role="danger"):
            self.model.stop()
        im.set_item_tooltip(
            tr("Terminate the running fit; its captured output stays in Analysis Output.")
        )
        self.remember("stop")
        im.end_disabled()
        if m.status.startswith("Error:") or "failed" in m.status:
            im.text_colored(ERROR, m.status)
        else:
            im.text_wrapped(m.status)
        im.separator()
        self.input_form.rects.clear()
        im.begin_disabled(m.running)
        draw_form(self.input_spec, self.input, self.input_form)
        im.end_disabled()
        self.item_rects.update(self.input_form.rects)
        self.form.rects.clear()
        im.begin_disabled(m.running)
        draw_form(self.controls_spec, m, self.form)
        im.end_disabled()
        self.item_rects.update(self.form.rects)
        self.item_rects["Find Optimal"] = self.form.rects.get(
            "find_optimal"
        )  # the Qt tour's name for it

    def draw_files(self, section, model, state, width):
        """The file rows of the Qt wizard, each as its caption and, under it, the path and -- for the
        configuration and the output directory -- its Edit... / Select... button.

        The path takes the dock's width less the button, so a long path stays readable in a narrow dock instead of
        being cut to a few characters beside a caption.
        """
        m = self.model
        button_w = (
            max(im.calc_text_size(row[4])[0] for row in FILE_ROWS)
            + 2 * im.get_style().frame_padding[0]
        )
        spacing = im.get_style().item_spacing[0]
        for attr, label, tip, action, button, key in FILE_ROWS:
            if attr in ("vh_file", "irf_vh_file") and not m.polarized:
                continue
            im.text(label)
            im.set_next_item_width(max(60.0, width - button_w - spacing - 4.0))
            flags = 0 if attr == "config_file" else im.InputTextFlags.READ_ONLY
            if action is None:  # data from the workspace: the path, the full width
                im.set_next_item_width(max(60.0, width - 4.0))
            changed, value = im.input_text(
                f"##{attr}", getattr(m, attr) or "", flags=flags, elide_start=True
            )
            im.set_item_tooltip(tip)
            self.remember(attr)
            if changed and attr == "config_file":
                m.config_file, m.config_dirty = value, False
            if action is None:
                continue
            im.same_line()
            if im.button(
                f"{button}##{attr}.browse", (button_w, 0)
            ):  # not the field's id: it took the click
                self.tour.notify_used(key)
                if action == "edit_config":
                    self.edit_config()
                else:
                    self.choose(action)
            im.set_item_tooltip(
                {
                    "Edit...": "Open the configuration in the YAML editor (load another, edit, save).",
                    "Select...": "Choose the output directory.",
                }.get(button, f"Choose the {label.lower()}.")
            )
            self.remember(key)

    def edit_config(self):
        """Open the YAML editor on the configuration file (or the buffer, if it was edited)."""
        m = self.model
        if m.config_file and Path(m.config_file).is_file() and not m.config_dirty:
            self.error(lambda: m.load_config(m.config_file))
        self.config_open = True

    def details(self, box):
        m = self.model
        if im.begin_tab_bar("lltf_tabs"):
            for tab in ("Information", "Analysis Output", "Results"):
                flags = im.TabItemFlags.SET_SELECTED if self.pending_tab == tab else 0
                active = im.begin_tab_item(tab, flags=flags)
                im.set_item_tooltip(TAB_TIPS[tab])  # on every tab, not only the open one
                self.item_rects[tab] = im.get_item_rect()
                if active:
                    self.tab = tab
                    if tab == "Information":
                        im.text_wrapped(
                            tr(
                                "Pick the measured decay and its IRF in the Input section (data dropped on the ChiSurf window is listed there), edit YAML settings if needed, choose a fixed or automatically selected lifetime count, then Fit. Analysis runs separately; inspect its output, fitted lifetimes and weighted residuals before interpreting the model. In VV/VH mode a polarized pair is fitted jointly: shared lifetimes, rotational correlation times and r0. Load example simulates one whose answer is known."
                            )
                        )
                    elif tab == "Analysis Output":
                        if im.button(tr("Clear output"), role="danger"):
                            m.clear_output()
                        im.set_item_tooltip(
                            tr("Clear displayed logs without interrupting the analysis.")
                        )
                        im.text_unformatted("\n".join(m.output))
                    else:
                        if m.result is None:
                            im.text_wrapped(m.results_summary())
                        else:
                            if im.button(tr("💾  Export result JSON")):
                                self.choose("save_results")
                            im.set_item_tooltip(
                                tr("Copy the complete fit result and model arrays to a JSON file.")
                            )
                            self.remember("export_json")
                            draw_form(
                                self.results_spec, m, self.results_form
                            )  # the spec's Results panel
                    im.end_tab_item()
            im.end_tab_bar()
            self.pending_tab = None

    def _range_lines(self, a):
        for index, value in enumerate(a["range"]):
            implot.drag_line_x(
                index,
                value,
                flags=implot.DRAG_TOOL_FLAGS_NO_INPUTS | implot.DRAG_TOOL_FLAGS_NO_FIT,
            )

    def polarized_plots(self, a):
        """VV and VH with their fits, both channels' weighted residuals, and r(t) data against fit."""
        tips = {
            "VV and VH": "Both channels and their joint fit, log scale, with the analysis range.",
            "Weighted residuals": "Weighted residuals of VV and VH over the analysis range.",
            "r(t)": "Anisotropy of the data and of the fit (both reconvolved, Schaffer-corrected).",
        }
        if im.begin_tab_bar("lltf_plot_tabs"):
            for title, tip in tips.items():
                opened = im.begin_tab_item(title)
                self.item_rects[title] = im.get_item_rect()  # the tour points at r(t)
                if opened:
                    if implot.begin_plot(title, size=(-1.0, -1.0)):
                        y_label = {"VV and VH": "Counts", "r(t)": "r(t)"}.get(
                            title, "Weighted residual"
                        )
                        implot.setup_axes("Time (ns)", y_label)
                        if title == "VV and VH":
                            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
                            for name, x, y in [
                                ("VV", a["time"], a["vv"]),
                                ("VH", a["time"], a["vh"]),
                                ("VV fit", a["model_time"], a["fit_vv"]),
                                ("VH fit", a["model_time"], a["fit_vh"]),
                            ]:
                                implot.plot_line(name, x, np.where(np.asarray(y) > 0, y, np.nan))
                            self._range_lines(a)
                        elif title == "r(t)":
                            implot.setup_axis_limits(implot.AXIS_Y1, -0.1, 0.5)
                            implot.plot_line("r(t) data", a["r_time"], a["r_data"])
                            implot.plot_line("r(t) fit", a["r_time"], a["r_model"])
                        else:
                            implot.plot_line("VV", a["model_time"], a["residuals_vv"])
                            implot.plot_line("VH", a["model_time"], a["residuals_vh"])
                            self._range_lines(a)
                        implot.end_plot()
                    im.end_tab_item()
                im.set_item_tooltip(tr(tip))
            im.end_tab_bar()

    def plots(self, box):
        if self.arrays is None:
            im.text_wrapped(tr("Fit plots appear after a successful analysis."))
            return
        a = self.arrays
        if a.get("polarized"):
            self.polarized_plots(a)
            return
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
            self._register_fit()
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
                tr("Edit the complete LLTF YAML configuration; the next run uses this buffer.")
            )
            if changed:
                self.model.config_text = text
                self.model.config_dirty = True
            if im.button(tr("Save configuration")):
                self.choose("save_config")
            im.set_item_tooltip(tr("Save the edited YAML configuration to a chosen file."))
            im.same_line()
            if im.button(tr("Close editor")) or pressed == "close":
                self.config_open = False
            im.set_item_tooltip(
                tr("Close the editor; unsaved edits remain available to the next run.")
            )
            self.config_window.end()
        if self.dialog is not None:
            pressed = self.file_window.begin(box)
            result = self.dialog.draw()
            if result:
                action = self.file_action
                self.dialog = None
                if action == "save_config":
                    self.error(lambda: self.model.save_config(result[0]))
                elif action == "save_results":
                    self.error(
                        lambda: Path(result[0]).write_text(json.dumps(self.model.result, indent=2))
                    )
                elif action == "output_dir":
                    import chisurf

                    self.model.output_dir = str(result[0])
                    chisurf.working_path = Path(result[0])
            elif result is False or pressed == "close":
                self.dialog = None
            self.file_window.end()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)


    def _register_fit(self) -> None:
        """The fitted decay enters the workspace, a child of the decay it was fitted to."""
        a = self.arrays
        if not a or a.get("polarized"):
            return
        try:
            from chisurf.core.data import DataCurve

            curve = DataCurve(
                x=np.asarray(a["model_time"], float),
                y=np.asarray(a["fit"], float),
                name=f"LLTF fit · {Path(self.model.decay_file).stem}",
                load_filename_on_init=False,
            )
            curve.data_kind = "decay"
            register_result(curve, result_of=self.source_uid, name=curve.name)
        except Exception:  # noqa: BLE001 - the fit stands; the workspace row is a convenience
            import logging

            logging.getLogger(__name__).exception("registering the LLTF fit failed")


def make_app():
    return LLTFApp()


def _curve_file(address: str, folder: Path) -> str:
    """A file the LLTF command line reads for the workspace curve *address*: the file it was read
    from, else its points written as two columns into *folder* (a curve that lives in the session)."""
    dataset = resolve_dataset(address)
    if dataset is None:
        if Path(address).is_file():
            return address
        raise FileNotFoundError(f"{address} is not in the workspace")
    for source in (getattr(dataset, "filename", ""), getattr(dataset, "address", "")):
        if source and Path(str(source)).is_file():
            return str(source)
    name = str(getattr(dataset, "name", "") or "curve").replace("/", "_")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{Path(name).stem or 'curve'}.dat"
    np.savetxt(target, np.column_stack([np.asarray(dataset.x), np.asarray(dataset.y)]), delimiter="\t")
    return str(target)


def receive_decays(app: LLTFApp, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``decays``): the decay and IRF to fit.

    ``decays`` are addresses of workspace curves (``@<uid>`` for one read into the session), in the
    order picked: one named *IRF* (or *prompt*) is the instrument response, else the second; a
    curve named *VH* fills the VH row of a VV/VH fit. A decay alone replaces the decay and keeps the
    IRF; an IRF alone replaces the IRF.
    """
    import tempfile

    addresses = [str(a) for a in payload.get("decays") or []]
    uids = [str(u) for u in payload.get("datasets") or []]
    if not addresses:
        raise ValueError("no decay picked")
    folder = Path(tempfile.gettempdir()) / "chisurf-lltf-input"
    picked = []
    for index, address in enumerate(addresses):
        dataset = resolve_dataset(address)
        label = str(getattr(dataset, "name", "") or Path(address).name).lower()
        picked.append((address, label, uids[index] if index < len(uids) else ""))

    def is_irf(label: str) -> bool:
        return "irf" in label or "prompt" in label

    def is_vh(label: str) -> bool:
        return "vh" in label.replace("vv_vh", "").replace("vvvh", "")

    irfs = [p for p in picked if is_irf(p[1])]
    decays = [p for p in picked if not is_irf(p[1])]
    if not irfs and len(decays) >= 2:
        irfs = [decays.pop(1)]
    m = app.model
    # What the tool works on is the workspace address of each curve; a curve read into the session
    # is written to a file only because the fit runs on files (``decay_file`` and friends).
    addresses_by_role = app.input_addresses
    if decays:
        main = next((p for p in decays if not is_vh(p[1])), decays[0])
        m.decay_file = _curve_file(main[0], folder)
        addresses_by_role["decay"] = main[0]
        app.source_uid = main[2]
        vh = next((p for p in decays if p is not main and is_vh(p[1])), None)
        if vh is not None:
            m.vh_file = _curve_file(vh[0], folder)
            addresses_by_role["vh"] = vh[0]
    if irfs:
        irf = next((p for p in irfs if not is_vh(p[1])), irfs[0])
        m.irf_file = _curve_file(irf[0], folder)
        addresses_by_role["irf"] = irf[0]
        irf_vh = next((p for p in irfs if p is not irf and is_vh(p[1])), None)
        if irf_vh is not None:
            m.irf_vh_file = _curve_file(irf_vh[0], folder)
            addresses_by_role["irf_vh"] = irf_vh[0]
    app.arrays = None
