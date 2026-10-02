"""Native MEM lifetime/FRET analysis with actual solver, L-curve and sampling jobs."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import LabelColumn, button_row, labelled, layout_spec

from .controller import MEMJobs
from .model import MEMForm, MEMModel, open_datasets, open_fits

HERE = Path(__file__).parent
#: Tour targets from the Qt era -> the button that answers them.
ALIASES = {"maxentBtnRefresh": "refresh", "maxentBtnRun": "run", "maxentBtnLcurve": "lcurve"}


class MaxentApp(ImApp):
    def __init__(self, model=None):
        self.model = model or MEMModel()
        self.mform = MEMForm(self.model)
        panels = json.loads((HERE / "maxent_emtk.view.json").read_text())["panels"]
        self.panels = {n: layout_spec(copy.deepcopy(p)) for n, p in panels.items()}
        self.forms = {n: FormState() for n in panels}
        self.columns = {n: LabelColumn() for n in panels}
        self.jobs = MEMJobs(self.model)
        self.fits = []
        self.datasets = []
        self.fit_index = 0
        self.dataset_index = 0
        self.dialog = None
        self.file_window = None
        self.file_action = ""
        self.item_rects = {}
        self.plot_info = {}
        self.last_dir = ""
        self.edit_settings = False
        self.settings_text = ""
        self.settings_window = DialogWindow("MEM settings", size=(780, 600))
        self.help_window = EmTkHelpWindow(
            title="MaxEnt MEM — Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=lambda key: self.item_rects.get(key) or self.item_rects.get(ALIASES.get(key, key)),
            owner=self,
            wait_for_controls=True,
        )
        for form in self.forms.values():
            form.on_used = self.tour.notify_used
        self.docks = DockManager(
            Split(
                "h",
                0.38,
                Region("controls"),
                Split(
                    "v",
                    0.6,
                    Split("h", 0.55, Region("decay"), Region("distribution")),
                    Split("h", 0.55, Region("residuals"), Region("lcurve")),
                ),
            )
        )
        for key, title, draw in [
            ("controls", "MEM controls", self.controls),
            ("decay", "Decay, fit and IRF", self.decay_plot),
            ("distribution", "Distribution", self.distribution_plot),
            ("residuals", "Residuals", self.residuals_plot),
            ("lcurve", "L-curve plot", self.lcurve_plot),
        ]:
            self.docks.add_window(key, title, draw, dock=key, closable=False)
        super().__init__(self.render, continuous=False)

    def error(self, action):
        try:
            return action()
        except Exception as exc:
            self.model.status = f"Error: {exc}"
            return None

    def refresh_sources(self):
        self.fits = open_fits()
        self.datasets = open_datasets()
        self.fit_index = min(self.fit_index, max(0, len(self.fits) - 1))
        self.dataset_index = min(self.dataset_index, max(0, len(self.datasets) - 1))

    def choose(self, action):
        self.file_action = action
        mode = "folder" if action in ("export", "sample") else "open"
        title = {
            "decay": "Load measured decay",
            "irf": "Load measured IRF",
            "prior": "Load distribution prior",
            "donor": "Load donor-only spectrum",
            "export": "Save MEM result folder",
            "sample": "Sample MEM distribution into folder",
        }[action]
        self.dialog = FileDialog(
            title, mode=mode, filters="Data (*.txt *.dat *.csv);;All files (*)", directory=self.last_dir or None
        )
        self.file_window = DialogWindow(title, size=(760, 540))

    def remember(self, name):
        rect = im.get_item_rect()
        self.item_rects[name] = rect
        for alias, target in ALIASES.items():          # the Qt-era tour names
            if target == name:
                self.item_rects[alias] = rect

    def form(self, name):
        """Draw the panel *name*; its captions share one column."""
        spec, column = self.panels[name], self.columns[name]
        if not column.ready:
            column.measure([f["label"] for f in labelled(spec["sections"])])
        column.pad(spec["sections"])
        draw_form(spec, self.mform, self.forms[name])

    def do(self, key):
        """Run what the button *key* does; its tour aliases are told."""
        m = self.model
        actions = {
            "refresh": self.refresh_sources,
            "load_decay": lambda: self.choose("decay"),
            "load_irf": lambda: self.choose("irf"),
            "clear_irf": m.clear_irf,
            "load_prior": lambda: self.choose("prior"),
            "load_donor": lambda: self.choose("donor"),
            "donor_fit": lambda: m.donor_from_fit(self.fits[self.fit_index]),
            "use_fit": lambda: m.load_fit(self.fits[self.fit_index]),
            "use_decay": lambda: m.load_dataset(self.datasets[self.dataset_index]),
            "use_irf": lambda: m.select_irf(self.datasets[self.dataset_index]),
            "run": lambda: self.jobs.start("run"),
            "lcurve": lambda: self.jobs.start("lcurve"),
            "sample": lambda: self.choose("sample"),
            "save": lambda: self.choose("export"),
            "cancel": self.jobs.cancel,
            "settings": self.open_settings,
            "help": self.help_window.show,
            "guide": self.tour.start,
        }
        self.error(actions[key])
        self.tour.notify_used(key)
        for alias, target in ALIASES.items():
            if target == key:
                self.tour.notify_used(alias)

    def buttons(self, rows):
        pressed = button_row(rows, remember=lambda name: self.remember(name))
        if pressed:
            self.do(pressed)

    def controls(self, box):
        m, s = self.model, self.model.settings
        m.busy = self.jobs.process is not None
        idle = self.jobs.process is None and self.dialog is None and not self.edit_settings
        have_data = m.decay is not None
        fret = s.mode == "fret"
        self.buttons([
            {"label": "Run MEM", "key": "run", "enabled": idle and have_data and (not fret or m.donor is not None),
             "tip": "Solve the maximum-entropy inversion in an isolated, cancellable process."},
            {"label": "L-curve", "key": "lcurve", "enabled": idle and have_data and (not fret or m.donor is not None),
             "tip": "Run the 16-point nu sweep and pick the discrete corner."},
            {"label": "Sample", "key": "sample", "enabled": idle and m.result is not None,
             "tip": "Run Q-MCMC sampling of the distribution and save chains, summaries and project metadata in a folder."},
            {"label": "Save", "key": "save", "enabled": idle and m.result is not None,
             "tip": "Export the distribution, observed and fitted curves, IRF, weighted residuals and metadata."},
            {"label": "Cancel job", "key": "cancel", "enabled": not idle and self.jobs.process is not None,
             "tip": "Terminate the MEM or sampling process this window started."},
        ])
        self.buttons([
            {"label": "Refresh", "key": "refresh", "enabled": idle,
             "tip": "List the datasets and fits of this running ChiSurf session."},
            {"label": "Load decay", "key": "load_decay", "enabled": idle,
             "tip": "Load a measured two-column time/counts decay from a file."},
            {"label": "IRF file", "key": "load_irf", "enabled": idle,
             "tip": "Load a measured instrument response and resample it onto the decay time axis."},
            {"label": "Clear IRF", "key": "clear_irf", "enabled": idle and m.irf is not None,
             "tip": "Drop the measured IRF: use the response of the live fit, or an impulse."},
            {"label": "Prior", "key": "load_prior", "enabled": idle,
             "tip": "Use a vector or axis/value prior for the current distribution grid."},
            {"label": "Donor", "key": "load_donor", "enabled": idle and fret,
             "tip": "Load the amplitude/lifetime pairs of the donor-only decay (FRET mode)."},
            {"label": "JSON", "key": "settings", "enabled": idle,
             "tip": "Inspect and edit the declared preferences as JSON."},
            {"label": "Help", "key": "help", "tip": "Explain maximum entropy, FRET priors and uncertainty."},
            {"label": "Guide", "key": "guide", "tip": "Tour the real input, regularization and run controls."},
        ])
        if self.fits or self.datasets:
            if self.fits:
                _, self.fit_index = im.combo("Live fit", self.fit_index, [getattr(f, "name", "Fit") for f in self.fits])
                im.set_item_tooltip("Choose a fit for the observed data, the fit range and the instrument values.")
                self.buttons([
                    {"label": "Fit", "key": "use_fit", "enabled": idle, "tip": "Take data, range, response and nuisance values from the selected live fit."},
                    {"label": "Donor from fit", "key": "donor_fit", "enabled": idle and fret,
                     "tip": "Use the selected fit's lifetime components as the donor-only spectrum."},
                ])
            if self.datasets:
                _, self.dataset_index = im.combo("Dataset", self.dataset_index, [getattr(d, "name", "Dataset") for d in self.datasets])
                im.set_item_tooltip("Choose an existing measured curve.")
                self.buttons([
                    {"label": "Use as decay", "key": "use_decay", "enabled": idle, "tip": "Use the selected dataset's counts and time axis as the decay."},
                    {"label": "Use as IRF", "key": "use_irf", "enabled": idle, "tip": "Resample the selected dataset to the decay grid as the response."},
                ])
        im.separator()
        im.text_wrapped(m.source)
        im.text_wrapped("IRF: " + m.irf_source)
        prior = m.priors[s.mode]
        im.text_wrapped(("Prior: " + ("loaded" if prior is not None else "default 1/tau")) if not fret
                        else ("Distance prior: " + ("loaded" if prior is not None else "default flat")))
        if fret:
            im.text_wrapped(f"Donor spectrum: {len(m.donor) // 2} components" if m.donor is not None
                            else "Donor spectrum: required in FRET mode (Donor).")
        im.text_wrapped(m.status)
        if self.jobs.progress[1]:
            im.text(f"Progress: {self.jobs.progress[0]}/{self.jobs.progress[1]}")
            im.set_item_tooltip("Iterations or sweep points done by the running job.")
        if self.jobs.output:
            im.text_disabled(self.jobs.output[-1][:90])
        im.separator()
        self.form("mode")
        self.form("fret" if fret else "lifetime")
        self.form("period")
        self.form("instrument")
        opened = im.collapsing_header("L-curve span and sampling")
        im.set_item_tooltip("The decades the L-curve sweep covers and the Q-MCMC sampling options.")
        if opened:
            self.form("lcurve")
            self.form("sampling")

    def open_settings(self):
        self.settings_text = json.dumps(self.model.parameters(), indent=2)
        self.edit_settings = True

    def decay_plot(self, box):
        m = self.model
        if implot.begin_plot("Measured decay and MEM fit", size=(-1.0, -1.0)):
            implot.setup_axes("Time (ns)", "Counts")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            if m.decay is not None:
                implot.plot_line("Observed", m.time, np.where(m.decay > 0, m.decay, np.nan))
                lamp = m.lamp()
                area = float(lamp.max())
                if area > 0:
                    scaled = lamp * float(m.decay.max()) / area
                    observed = m.decay[m.decay > 0]
                    floor = float(observed.min()) * 0.1 if observed.size else 1e-12
                    implot.plot_line(
                        "IRF scaled",
                        m.time,
                        np.where(scaled >= floor, scaled, np.nan),
                    )
                arrays = m.arrays()
                if arrays:
                    implot.plot_line(
                        "MEM fit",
                        arrays["time"],
                        np.where(arrays["fit"] > 0, arrays["fit"], np.nan),
                    )
                bounds = m.fitrange or (m.result["fitrange"] if m.result is not None else None)
                if bounds is not None:
                    low, high = [max(0, min(int(i), len(m.time) - 1)) for i in bounds]
                    positive = m.decay[m.decay > 0]
                    minimum = float(positive.min()) * 0.1 if positive.size else 1e-12
                    maximum = max(float(m.decay.max()), minimum) * 1.1
                    region = implot.drag_rect(
                        1,
                        m.time[low],
                        minimum,
                        m.time[high],
                        maximum,
                        flags=implot.DRAG_TOOL_FLAGS_NO_FIT,
                    )
                    if region.modified:
                        m.fitrange = tuple(
                            sorted(
                                int(np.argmin(abs(m.time - v)))
                                for v in (region.x_min, region.x_max)
                            )
                        )
                    mid = (minimum * maximum) ** 0.5
                    self.plot_info["decay"] = {
                        "pos": implot.get_plot_pos(), "size": implot.get_plot_size(),
                        "left": implot.plot_to_pixels(float(m.time[low]), mid),
                        "right": implot.plot_to_pixels(float(m.time[high]), mid),
                    }
            implot.end_plot()

    def distribution_plot(self, box):
        arrays = self.model.arrays()
        if implot.begin_plot("MEM distribution", size=(-1.0, -1.0)):
            implot.setup_axes(
                "Distance (A)"
                if self.model.result and "R" in self.model.result
                else "Lifetime (ns)",
                "Probability",
            )
            if arrays:
                implot.plot_line("MEM", arrays["axis"], arrays["p"])
            stats = self.model.samples
            if stats is not None:
                for key, label in (
                    ("p_mean", "Sample mean"),
                    ("p_lo", "16 percentile"),
                    ("p_hi", "84 percentile"),
                ):
                    implot.plot_line(label, stats["axis"], stats[key])
            implot.end_plot()

    def residuals_plot(self, box):
        arrays = self.model.arrays()
        if implot.begin_plot("Weighted residuals", size=(-1.0, -1.0)):
            implot.setup_axes("Time (ns)", "Residual / sigma")
            if arrays:
                implot.plot_line("Residuals", arrays["time"], arrays["wres"])
            implot.end_plot()

    def lcurve_plot(self, box):
        curve = self.model.lcurve
        if implot.begin_plot("L-curve", size=(-1.0, -1.0)):
            implot.setup_axes("Chi-square", "Solution norm")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            if curve is not None:
                implot.plot_line("Regularization sweep", curve["chi2r"], curve["sol_norm"])
                implot.plot_scatter("nu values", curve["chi2r"], curve["sol_norm"])
                self.plot_info["lcurve"] = [implot.plot_to_pixels(float(x), float(y))
                                            for x, y in zip(curve["chi2r"], curve["sol_norm"])]
                if implot.is_plot_hovered() and im.is_mouse_clicked(0):
                    mouse = implot.get_plot_mouse_pos()
                    if mouse.x > 0 and mouse.y > 0:
                        d = (np.log(np.maximum(curve["chi2r"], 1e-30)) - np.log(mouse.x)) ** 2 + (
                            np.log(np.maximum(curve["sol_norm"], 1e-30)) - np.log(mouse.y)
                        ) ** 2
                        index = int(np.argmin(d))
                        self.model.settings.nu = float(10.0 ** curve["log10_nu"][index])
                        self.model.status = (
                            f"Selected nu={self.model.settings.nu:.6g} from L-curve."
                        )
            implot.end_plot()

    def files_dropped(self, paths):
        """Host drop: the first file is the decay, the second the IRF, a ``.json`` loads preferences."""
        paths = [str(p) for p in paths]
        if not paths:
            return False
        slots = iter(("decay", "irf"))
        for path in paths:
            if path.lower().endswith(".json"):
                self.error(lambda p=path: self.model.restore_preferences(json.loads(Path(p).read_text())))
                continue
            slot = next(slots, None)
            if slot is None:
                break
            self.error(lambda p=path, irf=slot == "irf": self.model.load_file(p, irf=irf))
        return True

    on_files_dropped = files_dropped

    def restore_settings(self, settings):
        self.model.restore_preferences(settings)
        self.last_dir = str((settings or {}).get("last_dir", ""))

    def export_settings(self):
        return {**self.model.parameters(), "last_dir": self.last_dir}

    def close(self):
        self.jobs.close()

    def animating(self):
        return self.jobs.process is not None or super().animating()

    def render(self):
        self.item_rects.clear()
        for form in self.forms.values():
            form.rects.clear()
        self.jobs.poll()
        self.mform = MEMForm(self.model)
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        im.begin_disabled(self.dialog is not None or self.edit_settings)
        self.docks.draw(box)
        im.end_disabled()
        if self.edit_settings:
            pressed = self.settings_window.begin(box)
            _, self.settings_text = im.input_text_multiline(
                "JSON preferences", self.settings_text, size=(-1.0, 400.0)
            )
            im.set_item_tooltip(
                "Edit declared grids, nuisance controls, regularization and sampling preferences; live arrays are not persisted."
            )
            if im.button("Apply settings"):
                self.error(lambda: self.model.restore_preferences(json.loads(self.settings_text)))
                self.edit_settings = False
            im.set_item_tooltip("Apply valid JSON preferences to the next MEM job.")
            if im.button("Close settings") or pressed == "close":
                self.edit_settings = False
            im.set_item_tooltip("Close this settings editor.")
            self.settings_window.end()
        if self.dialog is not None:
            pressed = self.file_window.begin(box)
            result = self.dialog.draw()
            if result:
                action = self.file_action
                self.dialog = None
                self.last_dir = str(result[0]) if action in ("export", "sample") else str(Path(result[0]).parent)
                if action in ("decay", "irf"):
                    self.error(lambda: self.model.load_file(result[0], irf=action == "irf"))
                elif action == "prior":
                    self.error(lambda: self.model.load_prior(result[0]))
                elif action == "donor":
                    self.error(lambda: self.model.load_donor(result[0]))
                elif action == "export":
                    self.error(lambda: self.model.export_result(result[0]))
                else:
                    self.error(lambda: self.jobs.start("sample", result[0]))
            elif result is False or pressed == "close":
                self.dialog = None
            self.file_window.end()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)


def make_app():
    return MaxentApp()
