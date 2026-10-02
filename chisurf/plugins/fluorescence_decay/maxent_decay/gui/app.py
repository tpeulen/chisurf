"""Native MEM lifetime/FRET analysis with actual solver, L-curve and sampling jobs."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.calculator.inputs import bounded_float, bounded_int

from .controller import MEMJobs
from .model import MEMModel, open_datasets, open_fits


class MaxentApp(ImApp):
    def __init__(self, model=None):
        self.model = model or MEMModel()
        self.jobs = MEMJobs(self.model)
        self.fits = []
        self.datasets = []
        self.fit_index = 0
        self.dataset_index = 0
        self.dialog = None
        self.file_window = None
        self.file_action = ""
        self.item_rects = {}
        self.edit_settings = False
        self.settings_text = ""
        self.settings_window = DialogWindow("MEM settings", size=(780, 600))
        self.help_window = EmTkHelpWindow(
            title="MaxEnt MEM — Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=lambda key: self.item_rects.get(key),
            owner=self,
            wait_for_controls=True,
        )
        self.docks = DockManager(
            Split(
                "h",
                0.31,
                Region("controls"),
                Split(
                    "v",
                    0.6,
                    Split("h", 0.65, Region("decay"), Region("distribution")),
                    Split("h", 0.65, Region("residuals"), Region("lcurve")),
                ),
            )
        )
        for key, title, draw in [
            ("controls", "MEM controls", self.controls),
            ("decay", "Decay, fit and IRF", self.decay_plot),
            ("distribution", "Lifetime / distance distribution", self.distribution_plot),
            ("residuals", "Weighted residuals", self.residuals_plot),
            ("lcurve", "L-curve diagnostics", self.lcurve_plot),
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
            title, mode=mode, filters="Data (*.txt *.dat *.csv);;All files (*)"
        )
        self.file_window = DialogWindow(title, size=(760, 540))

    def field(self, owner, attr, label, low, high, tip, integer=False, step=0.01):
        control = bounded_int if integer else bounded_float
        changed, value = control(
            label, getattr(owner, attr), minimum=low, maximum=high, step=1 if integer else step
        )
        im.set_item_tooltip(tip)
        self.item_rects[attr] = im.get_item_rect()
        if changed:
            setattr(owner, attr, value)

    def action(self, label, tip, call):
        aliases = {
            "Refresh live sources": "maxentBtnRefresh",
            "Run MEM": "maxentBtnRun",
            "L-curve": "maxentBtnLcurve",
        }
        if im.button(label):
            self.error(call)
            self.tour.notify_used(label)
            if label in aliases:
                self.tour.notify_used(aliases[label])
        im.set_item_tooltip(tip)
        self.item_rects[label] = im.get_item_rect()
        if label in aliases:
            self.item_rects[aliases[label]] = im.get_item_rect()

    def controls(self, box):
        m = self.model
        s = m.settings
        im.begin_disabled(self.jobs.process is not None)
        for label, tip, call in [
            (
                "Refresh live sources",
                "List datasets and individual fits from this running ChiSurf session.",
                self.refresh_sources,
            ),
            (
                "Load decay file",
                "Load a measured two-column time/counts decay.",
                lambda: self.choose("decay"),
            ),
            (
                "Load IRF file",
                "Load and resample a measured response onto the decay time axis.",
                lambda: self.choose("irf"),
            ),
            (
                "Clear IRF",
                "Use the current fit response or an impulse when no measured response is selected.",
                m.clear_irf,
            ),
        ]:
            self.action(label, tip, call)
        if self.fits:
            _, self.fit_index = im.combo(
                "Live fit", self.fit_index, [getattr(fit, "name", "Fit") for fit in self.fits]
            )
            im.set_item_tooltip("Choose a fit for observed data, fit range and instrument values.")
            self.action(
                "Use selected fit",
                "Copy data, current range and response from the selected live fit.",
                lambda: m.load_fit(self.fits[self.fit_index]),
            )
        if self.datasets:
            _, self.dataset_index = im.combo(
                "Dataset",
                self.dataset_index,
                [getattr(ds, "name", "Dataset") for ds in self.datasets],
            )
            im.set_item_tooltip("Choose an existing measured curve or IRF.")
            self.action(
                "Use dataset as decay",
                "Use the selected dataset counts and time axis.",
                lambda: m.load_dataset(self.datasets[self.dataset_index]),
            )
            self.action(
                "Use dataset as IRF",
                "Resample the selected response to the observed decay grid.",
                lambda: m.select_irf(self.datasets[self.dataset_index]),
            )
        im.text_wrapped(m.source)
        im.text_wrapped("IRF: " + m.irf_source)
        changed, index = im.combo("Mode", 0 if s.mode == "lifetime" else 1, ["Lifetime", "FRET"])
        im.set_item_tooltip("Invert a lifetime spectrum or a FRET-distance distribution.")
        if changed:
            s.mode = "lifetime" if index == 0 else "fret"
            m.reset_results()
        self.action(
            "Load prior",
            "Use a vector or axis/value prior for the current distribution grid.",
            lambda: self.choose("prior"),
        )
        self.action(
            "Load donor spectrum",
            "Load amplitude/lifetime pairs required for FRET inversion.",
            lambda: self.choose("donor"),
        )
        if self.fits:
            self.action(
                "Donor spectrum from fit",
                "Use the selected fit's active lifetime components as the donor-only spectrum.",
                lambda: m.donor_from_fit(self.fits[self.fit_index]),
            )
        im.text_wrapped(
            "Donor spectrum: "
            + (
                f"{len(m.donor) // 2} components"
                if m.donor is not None
                else "required in FRET mode"
            )
        )
        expanded = im.collapsing_header("MEM inversion", im.TreeNodeFlags.DEFAULT_OPEN)
        im.set_item_tooltip("Set regularization and the lifetime or distance grid.")
        if expanded:
            self.field(
                s,
                "nu",
                "Regularization nu",
                1e-8,
                1.0,
                "Entropy regularization weight.",
                step=0.001,
            )
            if s.mode == "lifetime":
                self.field(
                    s,
                    "tau_min",
                    "Minimum lifetime (ns)",
                    0.001,
                    1000.0,
                    "Smallest lifetime represented by the grid.",
                )
                self.field(
                    s,
                    "tau_max",
                    "Maximum lifetime (ns)",
                    0.001,
                    1000.0,
                    "Largest lifetime represented by the grid.",
                )
                self.field(
                    s,
                    "tau_bins",
                    "Lifetime grid points",
                    2,
                    10000,
                    "Evenly spaced lifetime-grid resolution.",
                    True,
                )
            else:
                for attr, label, low, high, tip in [
                    (
                        "tau0",
                        "Donor reference lifetime (ns)",
                        0.01,
                        100.0,
                        "Unquenched donor reference lifetime.",
                    ),
                    (
                        "R0",
                        "Forster radius (A)",
                        10.0,
                        100.0,
                        "Forster radius for converting FRET rates to distance.",
                    ),
                    (
                        "r_min_frac",
                        "Minimum R/R0",
                        0.001,
                        10.0,
                        "Lower distance boundary relative to R0.",
                    ),
                    (
                        "r_max_frac",
                        "Maximum R/R0",
                        0.001,
                        10.0,
                        "Upper distance boundary relative to R0.",
                    ),
                    (
                        "x_donly",
                        "Donor-only fraction",
                        0.0,
                        1.0,
                        "Unquenched donor fraction in the sample.",
                    ),
                ]:
                    self.field(s, attr, label, low, high, tip)
                self.field(
                    s,
                    "r_bins",
                    "Distance grid points",
                    2,
                    10000,
                    "Evenly spaced distance-grid resolution.",
                    True,
                )
                _, m.fix_x_donly = im.checkbox("Fix donor-only fraction", m.fix_x_donly)
                im.set_item_tooltip("Keep this fraction fixed during nuisance optimization.")
            _, m.use_periodic = im.checkbox("Periodic convolution", m.use_periodic)
            im.set_item_tooltip(
                "Include repeated excitation pulses rather than a single-shot decay."
            )
            self.field(
                s,
                "period",
                "Excitation period (ns)",
                0.1,
                1000.0,
                "Pulse separation used when periodic convolution is enabled.",
            )
            self.field(
                s,
                "fit_start_fraction",
                "Start fraction of peak",
                0.1,
                1.0,
                "Automatic fitting starts near this fraction of the decay peak.",
            )
            self.field(
                s,
                "max_iter",
                "MEM iterations",
                1,
                100000,
                "Maximum iterations of the actual compiled MEM solver.",
                True,
            )
        expanded = im.collapsing_header("Instrument / nuisance parameters")
        im.set_item_tooltip("Set or optimize response shift, backgrounds and donor-only fraction.")
        if expanded:
            _, s.optimize_nuisance = im.checkbox("Optimize nuisance", s.optimize_nuisance)
            im.set_item_tooltip("Fit all nuisance values whose Fix controls are off.")
            for attr, label, low, high, tip, fix in [
                (
                    "timeshift",
                    "Timeshift (channels)",
                    -100.0,
                    100.0,
                    "Response shift, in histogram channels.",
                    "fix_timeshift",
                ),
                (
                    "background",
                    "Background (counts)",
                    0.0,
                    1e9,
                    "Constant decay background.",
                    "fix_background",
                ),
                (
                    "irf_background",
                    "IRF background",
                    0.0,
                    1e9,
                    "Response baseline; zero selects automatic baseline estimation.",
                    "fix_irf_background",
                ),
            ]:
                if getattr(s, attr) is None:
                    setattr(s, attr, 0.0)
                self.field(s, attr, label, low, high, tip)
                _, value = im.checkbox("Fix " + label, getattr(m, fix))
                setattr(m, fix, value)
                im.set_item_tooltip("Hold this nuisance parameter at its configured value.")
            self.field(
                s,
                "lamp_scatter",
                "Lamp scatter",
                0.0,
                1000.0,
                "Fixed amplitude of scattered excitation light.",
            )
        expanded = im.collapsing_header("L-curve and sampling")
        im.set_item_tooltip(
            "Scan regularization or sample distribution uncertainty with the original Q-MCMC engine."
        )
        if expanded:
            for attr, label, low, high, tip, integer in [
                (
                    "lcurve_left",
                    "Decades below nu",
                    0.0,
                    6.0,
                    "Lower log10 span of the16-point regularization sweep.",
                    False,
                ),
                (
                    "lcurve_right",
                    "Decades above nu",
                    0.0,
                    6.0,
                    "Upper log10 span of the regularization sweep.",
                    False,
                ),
                ("sample_steps", "MCMC steps", 10, 1000000, "Total ensemble-sampling steps.", True),
                ("sample_thin", "Thinning", 1, 1000, "Keep every nth ensemble step.", True),
                (
                    "sample_walkers",
                    "Walkers (0 auto)",
                    0,
                    1000000,
                    "Number of walkers; zero uses the sampler default.",
                    True,
                ),
                (
                    "sample_substeps",
                    "Sampling chunk size",
                    1,
                    1000000,
                    "Steps per progress update and saved sampling chunk.",
                    True,
                ),
                (
                    "sample_nprocs",
                    "CPUs (0 auto)",
                    0,
                    64,
                    "Worker-process count; zero selects a platform default.",
                    True,
                ),
            ]:
                self.field(m, attr, label, low, high, tip, integer)
            _, m.sample_vectorized = im.checkbox("Vectorized sampling", m.sample_vectorized)
            im.set_item_tooltip("Evaluate ensemble log probabilities in vectorized batches.")
        self.action(
            "Run MEM",
            "Solve the maximum-entropy inversion in an isolated cancellable process.",
            lambda: self.jobs.start("run"),
        )
        self.action(
            "L-curve",
            "Run the16-point nu sweep and choose a discrete corner.",
            lambda: self.jobs.start("lcurve"),
        )
        self.action(
            "Sample distribution",
            "Run actual Q-MCMC and save chains, posterior summaries and project metadata.",
            lambda: self.choose("sample"),
        )
        self.action(
            "Save result",
            "Export distribution, observed/fit curves, IRF, weighted residuals and metadata.",
            lambda: self.choose("export"),
        )
        self.action(
            "Edit advanced settings",
            "Inspect and edit the declared JSON preferences.",
            self.open_settings,
        )
        im.end_disabled()
        self.action(
            "Cancel job", "Terminate only the owned MEM or sampling process.", self.jobs.cancel
        )
        self.action(
            "Help", "Explain maximum entropy, FRET priors and uncertainty.", self.help_window.show
        )
        self.action(
            "Guide", "Tour the actual input, regularization and run controls.", self.tour.start
        )
        im.text_wrapped(m.status)
        if self.jobs.progress[1]:
            im.text(f"Progress: {self.jobs.progress[0]}/{self.jobs.progress[1]}")
        if self.jobs.output:
            im.text_wrapped(self.jobs.output[-1])

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

    def restore_settings(self, settings):
        self.model.restore_preferences(settings)

    def export_settings(self):
        return self.model.parameters()

    def close(self):
        self.jobs.close()

    def animating(self):
        return self.jobs.process is not None or super().animating()

    def render(self):
        self.item_rects.clear()
        self.jobs.poll()
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
