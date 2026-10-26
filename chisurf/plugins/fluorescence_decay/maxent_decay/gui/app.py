"""Native MEM lifetime/FRET analysis with actual solver, L-curve and sampling jobs.

The decay with its IRF, a prior and the donor-only spectrum come from the Datasets workspace: one
Input section each (the manifest's ``accepts[].from_workspace``; :func:`receive_decays`,
:func:`receive_prior`, :func:`receive_donor`). Nothing asks for an input file.
"""

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
from emtk.i18n import mark, tr
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import (
    LabelColumn,
    action_button,
    action_caption,
    action_tooltip,
    button_row,
    group_by_width,
    labelled,
    layout_spec,
    window_size,
)

from .controller import MEMJobs
from .model import MEMForm, MEMModel, open_fits

HERE = Path(__file__).parent
#: Tour targets from the Qt era -> the button that answers them.
ALIASES = {"maxentBtnRefresh": "refresh", "maxentBtnRun": "run", "maxentBtnLcurve": "lcurve"}


class MaxentApp(ImApp):
    def __init__(self, model=None):
        self.model = model or MEMModel()
        self.mform = MEMForm(self.model)
        spec = json.loads((HERE / "maxent_emtk.view.json").read_text())
        self.window_size = window_size(spec, (1100, 720))
        panels = spec["panels"]
        self.panels = {n: layout_spec(copy.deepcopy(p)) for n, p in panels.items()}
        for name in ("fret", "sampling"):
            self.panels[name]["sections"] = group_by_width(
                self.panels[name]["sections"], toggles_join=False
            )
        self.forms = {n: FormState() for n in panels}
        self.columns = {n: LabelColumn() for n in panels}
        self.jobs = MEMJobs(self.model)
        self.fits = []
        self.fit_index = 0
        from chisurf.plugins.curve_input import CurveInput

        #: The Input sections: the decay (and IRF), a prior, the donor-only spectrum.
        self.inputs = {
            name: CurveInput("maxent_decay", self, name=name, title="", height=height)
            for name, height in (("decays", 92.0), ("prior", 56.0), ("donor", 56.0))
        }
        #: The workspace dataset of the decay: the reconstruction is computed from it.
        self.source_uid = ""
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
            get_target_rect=lambda key: (
                self.item_rects.get(key) or self.item_rects.get(ALIASES.get(key, key))
            ),
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
        """List the fits of this session (the data itself comes from the Input sections)."""
        self.fits = open_fits()
        self.fit_index = min(self.fit_index, max(0, len(self.fits) - 1))

    def choose(self, action):
        """Ask for the folder a result or a sampling run is written to (outputs only)."""
        self.file_action = action
        title = {
            "export": "Save MEM result folder",
            "sample": "Sample MEM distribution into folder",
        }[action]
        # not-input: the folder the MEM result or the sampling chains are written to
        self.dialog = FileDialog(title, mode="folder", directory=self.last_dir or None)
        self.file_window = DialogWindow(title, size=(760, 540))

    def remember(self, name):
        rect = im.get_item_rect()
        self.item_rects[name] = rect
        for alias, target in ALIASES.items():  # the Qt-era tour names
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
            "clear_irf": m.clear_irf,
            "donor_fit": lambda: m.donor_from_fit(self.fits[self.fit_index]),
            "use_fit": lambda: m.load_fit(self.fits[self.fit_index]),
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
        if action_button(
            "example",
            enabled=idle,
            tooltip=tr(
                "Load a seeded bi-exponential decay (1.0 and 4.5 ns, 60:40) and reconstruct its "
                "lifetime distribution, so the peaks can be checked against the truth."
            ),
        ):
            self.error(self.load_example)
            self.tour.notify_used("load_example")
        self.item_rects["load_example"] = im.get_item_rect()
        self.buttons(
            [
                {
                    "label": "Run MEM",
                    "key": "run",
                    "enabled": idle and have_data and (not fret or m.donor is not None),
                    "tip": "Solve the maximum-entropy inversion in an isolated, cancellable process.",
                },
                {
                    "label": "L-curve",
                    "key": "lcurve",
                    "enabled": idle and have_data and (not fret or m.donor is not None),
                    "tip": "Run the 16-point nu sweep and pick the discrete corner.",
                },
                {
                    "label": "Sample",
                    "key": "sample",
                    "enabled": idle and m.result is not None,
                    "tip": "Run Q-MCMC sampling of the distribution and save chains, summaries and project metadata in a folder.",
                },
                {
                    "label": action_caption("save"),
                    "key": "save",
                    "enabled": idle and m.result is not None,
                    "tip": action_tooltip(
                        "save",
                        "Export the distribution, observed and fitted curves, IRF, weighted residuals and metadata.",
                    ),
                },
                {
                    "label": "Cancel job",
                    "key": "cancel",
                    "enabled": not idle and self.jobs.process is not None,
                    "tip": "Terminate the MEM or sampling process this window started.",
                },
            ]
        )
        self.buttons(
            [
                {
                    "label": "Refresh",
                    "key": "refresh",
                    "enabled": idle,
                    "tip": "List the fits of this running ChiSurf session (Live fit below).",
                },
                {
                    "label": "Clear IRF",
                    "key": "clear_irf",
                    "enabled": idle and m.irf is not None,
                    "tip": "Drop the measured IRF: use the response of the live fit, or an impulse.",
                },
                {
                    "label": "JSON",
                    "key": "settings",
                    "enabled": idle,
                    "tip": "Inspect and edit the declared preferences as JSON.",
                },
                {"label": action_caption("help"), "key": "help", "tip": action_tooltip("help")},
                {"label": action_caption("guide"), "key": "guide", "tip": action_tooltip("guide")},
            ]
        )
        self.draw_inputs(idle, fret)
        if self.fits:
            _, self.fit_index = im.combo(
                "Live fit", self.fit_index, [getattr(f, "name", "Fit") for f in self.fits]
            )
            im.set_item_tooltip(
                tr("Choose a fit for the observed data, the fit range and the instrument values.")
            )
            self.buttons(
                [
                    {
                        "label": "Fit",
                        "key": "use_fit",
                        "role": "default",
                        "enabled": idle,
                        "tip": "Take data, range, response and nuisance values from the selected live fit.",
                    },
                    {
                        "label": "Donor from fit",
                        "key": "donor_fit",
                        "enabled": idle and fret,
                        "tip": "Use the selected fit's lifetime components as the donor-only spectrum.",
                    },
                ]
            )
        im.separator()
        im.text_wrapped(m.source)
        im.text_wrapped("IRF: " + m.irf_source)
        prior = m.priors[s.mode]
        im.text_wrapped(
            ("Prior: " + ("loaded" if prior is not None else tr("default uniform")))
            if not fret
            else ("Distance prior: " + ("loaded" if prior is not None else "default flat"))
        )
        if fret:
            im.text_wrapped(
                f"Donor spectrum: {len(m.donor) // 2} components"
                if m.donor is not None
                else "Donor spectrum: required in FRET mode (Donor-only spectrum input, or Donor from fit)."
            )
        im.text_wrapped(m.status)
        if self.jobs.progress[1]:
            im.text(f"Progress: {self.jobs.progress[0]}/{self.jobs.progress[1]}")
            im.set_item_tooltip(tr("Iterations or sweep points done by the running job."))
        if self.jobs.output:
            im.text_disabled(self.jobs.output[-1][:90])
        im.separator()
        self.form("mode")
        self.form("fret" if fret else "lifetime")
        self.form("period")
        self.form("instrument")
        opened = im.collapsing_header("L-curve span and sampling")
        im.set_item_tooltip(
            tr("The decades the L-curve sweep covers and the Q-MCMC sampling options.")
        )
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
                        "pos": implot.get_plot_pos(),
                        "size": implot.get_plot_size(),
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
                tr("Amplitude"),
            )
            if arrays:
                implot.plot_line("MEM", arrays["axis"], arrays["p"])
                if implot.is_legend_entry_hovered("MEM"):
                    im.set_tooltip(
                        tr(
                            "Unnormalized amplitudes of the decay basis; these coefficients reconstruct the fitted signal."
                        )
                    )
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
                corner = curve.get("corner_index")
                if corner is not None:
                    # The corner the sweep picked (and wrote into nu): marked, as the guide promises.
                    implot.set_next_marker_style(implot.MARKER_DIAMOND, 9.0)
                    implot.plot_scatter(
                        "Corner",
                        np.asarray([curve["chi2r"][corner]], float),
                        np.asarray([curve["sol_norm"][corner]], float),
                    )
                self.plot_info["lcurve"] = [
                    implot.plot_to_pixels(float(x), float(y))
                    for x, y in zip(curve["chi2r"], curve["sol_norm"])
                ]
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

    def draw_inputs(self, idle, fret):
        """The Input sections: the decay and its IRF, a prior, and (FRET) the donor-only spectrum."""
        captions = {
            "decays": (
                mark("Decay and IRF"),
                mark(
                    "The measured decay, and its IRF: the curve named IRF (or prompt), else the "
                    "second one picked."
                ),
            ),
            "prior": (
                mark("Prior"),
                mark(
                    "A prior distribution for the current grid: lifetime (or distance) on x, "
                    "prior mass on y."
                ),
            ),
            "donor": (
                mark("Donor-only spectrum"),
                mark(
                    "FRET mode: a curve with lifetimes (ns) on x and amplitudes on y; or use "
                    "Donor from fit."
                ),
            ),
        }
        for name, section in self.inputs.items():
            if name == "donor" and not fret:
                continue
            caption, tip = captions[name]
            im.text_disabled(tr(caption))
            im.set_item_tooltip(tr(tip))
            im.begin_disabled(not idle)
            rects = {}
            section.draw(rects, on_used=self.tour.notify_used)
            im.end_disabled()
            for key, rect in rects.items():
                self.item_rects[key if name == "decays" else f"{name}.{key}"] = rect

    def load_example(self):
        """The demo decay enters the workspace, is handed over like the user's data, and solved."""
        from chisurf.plugins.curve_input import example_into_workspace

        from ..demo import make_demo, synthetic_decay

        make_demo()
        t, counts = synthetic_decay()
        example_into_workspace(
            [(t, counts, "maxent_demo")],
            receive_decays,
            self,
            key="decays",
            kind="decay",
            many=True,
            experiment="TCSPC",
        )
        if self.model.decay is not None:
            self.model.run()

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
                tr(
                    "Edit declared grids, nuisance controls, regularization and sampling preferences; live arrays are not persisted."
                )
            )
            if im.button(tr("Apply settings")):
                self.error(lambda: self.model.restore_preferences(json.loads(self.settings_text)))
                self.edit_settings = False
            im.set_item_tooltip(tr("Apply valid JSON preferences to the next MEM job."))
            if im.button(tr("Close settings")) or pressed == "close":
                self.edit_settings = False
            im.set_item_tooltip(tr("Close this settings editor."))
            self.settings_window.end()
        if self.dialog is not None:
            pressed = self.file_window.begin(box)
            result = self.dialog.draw()
            if result:
                action = self.file_action
                self.dialog = None
                self.last_dir = (
                    str(result[0])
                    if action in ("export", "sample")
                    else str(Path(result[0]).parent)
                )
                if action == "export":
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


def _curves(addresses):
    """``(name, x, y)`` of the workspace curves (or two-column files) at *addresses*."""
    from chisurf.plugins.curve_input import curve_of

    out = []
    for address in addresses:
        dataset = curve_of(address)
        if dataset is not None:
            out.append(
                (
                    str(getattr(dataset, "name", "") or address),
                    np.asarray(dataset.x, float),
                    np.asarray(dataset.y, float),
                )
            )
            continue
        try:
            values = np.loadtxt(address, ndmin=2)
        except ValueError:
            values = np.loadtxt(address, ndmin=2, delimiter=",")
        if values.shape[1] < 2:
            raise ValueError(f"{Path(address).name}: two columns (x, y) expected")
        out.append((Path(address).name, values[:, 0], values[:, 1]))
    return out


def _addresses(value):
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v)]
    return [str(value)] if value else []


def receive_decays(app: MaxentApp, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``decays``): the decay and its IRF.

    A picked curve named *IRF* (or *prompt*) is the instrument response, else the second one; the
    first other curve is the decay. A pick of only an IRF keeps the decay.
    """
    from types import SimpleNamespace

    curves = app.error(lambda: _curves(_addresses(payload.get("decays"))))
    uids = [str(u) for u in payload.get("datasets") or [] if str(u)]
    if not curves:
        return
    named_irf = [c for c in curves if any(w in c[0].lower() for w in ("irf", "prompt"))]
    others = [c for c in curves if c not in named_irf]
    irf = named_irf[0] if named_irf else (others[1] if len(others) > 1 else None)
    decay = others[0] if others else None
    m = app.model

    def load():
        if decay is not None:
            m.set_data(decay[1], decay[2], decay[0])
            app.source_uid = uids[curves.index(decay)] if curves.index(decay) < len(uids) else ""
        if irf is not None:
            m.select_irf(SimpleNamespace(x=irf[1], y=irf[2], name=irf[0]))

    app.error(load)


def receive_prior(app: MaxentApp, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``prior``): the prior distribution of the grid."""
    curves = app.error(lambda: _curves(_addresses(payload.get("prior"))))
    if curves:
        name, x, y = curves[0]

        def load():
            if not np.isfinite(y).all() or not y.size:
                raise ValueError("Prior must contain finite values.")
            app.model.priors[app.model.settings.mode] = (x, y)

        app.error(load)


def receive_donor(app: MaxentApp, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``donor``): the donor-only lifetime spectrum, a
    curve with lifetimes on x and amplitudes on y (interleaved as amplitude/lifetime pairs)."""
    curves = app.error(lambda: _curves(_addresses(payload.get("donor"))))
    if curves:
        from chisurf.core.fluorescence.decay import validate_lifetime_spectrum

        name, x, y = curves[0]

        def load():
            app.model.donor = validate_lifetime_spectrum(np.column_stack([y, x]).ravel())

        app.error(load)
