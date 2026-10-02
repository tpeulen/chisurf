"""Native EMTK lifetime/FRET filter calculator, independent of Qt widgets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.dialog_window import DialogWindow
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .model import FilterModel
from .panel import ComponentPanel, FilterPanel, component_spec

HERE = Path(__file__).parent
SPEC = json.loads((HERE / "filter_emtk.view.json").read_text(encoding="utf-8"))
#: The guide's and the tests' names for the tables (a form records a table under its source).
#: The names the shared guide.json gives the toolbar actions.
TOUR_NAMES = {"load_mixed": "Mixed", "autofit": "Auto-fit", "unmix": "Unmix", "save_project": "Project"}
ALIASES = {"component_rows": "components", "detector_rows": "detectors", "instrument_rows": "instrument", "range_rows": "ranges", "parameter_rows": "fit_parameters"}


#: Lowest count drawn on the logarithmic decay axis: an IRF tail of 1e-298 would otherwise stretch the view over 300 decades.
FLOOR = 0.5
COMPONENT_COLOURS = ((56, 189, 248, 255), (251, 113, 133, 255), (74, 222, 128, 255), (250, 204, 21, 255), (192, 132, 252, 255), (251, 146, 60, 255))
#: Width the controls dock gets at least in a narrow window (its five tabs and the tables need it).
MIN_CONTROLS = 420.0


class FilterApp(TourTarget, ImApp):
    def __init__(self, workflow_context=None, parameter_linker=None):
        self.model = FilterModel()
        self.workflow_context = workflow_context
        self.parameter_linker = parameter_linker
        self.registry_owner = f"fcs_filter_calc_emtk_{id(self)}"
        self.job = BackgroundJob()
        self.job_replaces = False
        self.pending_restoration_compute = False
        self.dialog = None
        self.dialog_callback = None
        self.editor = None
        self.link_parameter = None
        self.editor_index = None
        self.selected_component = -1
        self.selected_detector_row = None
        self.selected_parameter = None
        self.component_panel = None
        self.component_spec = None
        self.file_window = DialogWindow("Choose input or output", size=(560.0, 420.0), key="filter_files")
        self.component_window = DialogWindow("Component definition", size=(520.0, 560.0), key="component_definition")
        self.item_rects = {}
        self.forms = {}
        self.panel = FilterPanel(self)
        self.setup = ChannelDefinitionWidget(settings=self.model._detector_settings, on_changed=self._setup_changed)
        self._setup_pending = None
        base = Path(__file__).parents[1] / "gui_parts"
        self.help = EmTkHelpWindow(title="Filtered FCS help", resource=base / "help.md", owner=self, on_start_guide=lambda: self.tour.start())
        self.tour = EmTkGuidedTour(steps=base / "guide.json", get_target_rect=self.item_rects.get, owner=self, wait_for_controls=True)
        self.docks = DockManager(
            Split(
                "h",
                0.34,
                Region("controls"),
                Split(
                    "v",
                    0.35,
                    Region("filters"),
                    Split("v", 0.65, Region("reconstruction"), Region("residuals")),
                ),
            )
        )
        for key, title, draw, dock in (
            ("sources", "Sources", self.draw_sources, "controls"),
            ("setup", "Detector setup", self.draw_setup, "controls"),
            ("autofit", "Auto-fit", self.draw_autofit, "controls"),
            ("instrument", "Instrument", self.draw_instrument, "controls"),
            ("info", "Info", self.draw_info, "controls"),
            ("filters", "Lifetime filters", self.draw_filters, "filters"),
            ("residuals", "Weighted residuals", self.draw_residuals, "residuals"),
            ("reconstruction", "Reconstruction", self.draw_reconstruction, "reconstruction"),
        ):
            self.docks.add_window(key, title, draw, dock=dock)
        super().__init__(gui=self.render, continuous=True)
        self.last_settings = self.settings_fingerprint()
        self.submit(lambda model: model.compute())

    def _used(self, name):
        """A named control was used: tell the guide, which knows the Qt toolbar's names too."""
        self.tour.notify_used(name)
        if name in TOUR_NAMES:
            self.tour.notify_used(TOUR_NAMES[name])

    def _setup_changed(self, settings):
        """The embedded detector editor edited the definition: adopt it once the pointer is up (called from inside a draw)."""
        self._setup_pending = settings

    def settings_fingerprint(self):
        model = self.model
        return json.dumps(
            {
                "components": [(c.source, c.enabled) for c in model.components],
                "detectors": model.detectors.selected,
                "irf": model.detectors.export_state(),
                "polarized": model.polarized,
                "stacked": model.stacked,
                "afterpulse": model.options_model.fit_background,
                "scatter": model.options_model.scatter_irf,
                "instrument": model._instrument(),
                "range": model._fit_bounds,
                "detector_ranges": model._detector_fit_ranges,
            },
            sort_keys=True,
        )

    #: What a plain recompute hands back to the live model (the inputs stay the live ones, edited while it ran).
    RESULT_FIELDS = ("_result", "_result_anisotropy", "_result_multi_detector", "_result_multi_anisotropy", "_unmix_result",
                     "_irf_by_detector", "_synthetic_scatter_fits", "message")

    @property
    def editing_blocked(self):
        """Whether the inputs may not be edited now: only while a job that replaces the model (load, auto-fit, unmix) runs."""
        return self.job.running and self.job_replaces

    def submit(self, operation, replace=True):
        if self.job.running:
            return False
        snapshot = self.model.snapshot()
        self.job_replaces = replace

        def work():
            operation(snapshot)
            return snapshot

        def publish(model):
            if replace:
                self.model = model
            else:
                for name in self.RESULT_FIELDS:
                    setattr(self.model, name, getattr(model, name))
            self.last_settings = self.settings_fingerprint()
            if model._auto_fit_result:
                from chisurf.core.registry.parameter_groups import register_parameter_group

                fit_model = getattr(model._auto_fit_result.get("fit"), "model", None)
                if fit_model is not None:
                    register_parameter_group(
                        fit_model, owner_id=self.registry_owner, label="FCS Filter Calc"
                    )

        return self.job.start(work, publish, lambda exc: setattr(self.model, "message", str(exc)))

    def choose(
        self,
        title,
        callback,
        mode="open",
        multiple=False,
        filters="Decay (*.pto *.txt *.dat *.csv *.spc *.ptu *.ht3 *.tttr *.bst);;All files (*)",
        filename="",
    ):
        if self.job.running:
            return
        self.dialog = FileDialog(title, mode=mode, multiselect=multiple, filters=filters, filename=filename)
        self.file_window.title = title
        self.file_window.show()
        self.dialog_callback = callback

    def button(self, label, tip, callback):
        if im.button(label):
            callback()
        im.set_item_tooltip(tip)
        self.item_rects[label] = im.get_item_rect()

    def number(self, label, value, tip, integer=False):
        changed, value = (
            im.input_int(label, int(value), step=0)
            if integer
            else im.input_float(label, float(value), step=0)
        )
        im.set_item_tooltip(tip)
        return changed, value

    def checkbox(self, label, value, tip):
        changed, value = im.checkbox(label, value)
        im.set_item_tooltip(tip)
        return changed, value

    def load_total(self, paths):
        def operation(model):
            model.set_total_paths(paths)
            model.compute()

        self.submit(operation)

    def from_correlator(self):
        ctx = self.workflow_context() if callable(self.workflow_context) else self.workflow_context
        if ctx is None:
            self.model.message = "No files are loaded in the Correlator (Files & Steps) step yet."
            return
        paths = list(getattr(ctx, "expanded_files", []) or getattr(ctx, "file_paths", []) or [])
        if not paths:
            self.model.message = "No files are loaded in the Correlator (Files & Steps) step yet."
            return

        def operation(model):
            model._micro_time_binning = max(1, int(getattr(ctx, "microtime_binning", 1)))
            model.set_total_paths(paths)
            model.compute()

        self.submit(operation)

    def new_component(self, kind="lifetime"):
        source = dict(
            type="synthetic",
            model=kind,
            name="New component",
            bin_width=self.model._pattern_bin_width_ns(),
            start_bin=0,
        )
        if kind == "lifetime":
            source["lifetime"] = 2.0
        elif kind == "lifetime_spectrum":
            source.update(amplitudes=[0.5, 0.5], lifetimes=[1.0, 4.0])
        elif kind == "gaussian_lifetime":
            source.update(mean_lifetime=2.0, sigma_lifetime=0.4, n_samples=81)
        elif kind == "gaussian_distance":
            source.update(
                donor_lifetime=4.0,
                forster_radius=52.0,
                mean_distance=50.0,
                sigma_distance=5.0,
                distance_distribution="gaussian",
                n_samples=81,
            )
        elif kind == "fret_species":
            source.update(
                state="da",
                donor_spectrum=[1.0, 4.0],
                acceptor_spectrum=[1.0, 2.0],
                fret_mode="efficiency",
                transfer_efficiency=0.5,
                crosstalk=self.model._calibration_seed(),
                forster_radius=52.0,
            )
        self.editor = source
        self.editor_index = None
        self.refresh_component_spec()

    def read_fit(self, fit):
        from chisurf.core.fluorescence.decay import (
            compute_detector_patterns_from_fit,
            lifetime_spectrum_from_model,
        )

        try:
            spectrum = lifetime_spectrum_from_model(
                getattr(getattr(fit, "selected_fit", fit), "model", None)
            )
            patterns = compute_detector_patterns_from_fit(
                fit, spectrum, detector_names=self.model.detectors.selected
            )
            source = dict(
                type="synthetic",
                model="lifetime_spectrum",
                name=str(getattr(fit, "name", "Fit spectrum")),
                amplitudes=spectrum[::2].tolist(),
                lifetimes=spectrum[1::2].tolist(),
                bin_width=self.model._pattern_bin_width_ns(),
                source_fit=str(getattr(fit, "name", "Fit")),
                patterns_by_detector={k: np.asarray(v).tolist() for k, v in patterns.items()},
            )
            routing = [
                f"routing_{c}"
                for det in self.model.detectors.selected
                for c in self.model._detector_settings.get("detectors", {})
                .get(det, {})
                .get("chs", [])
            ]
            ordered = [
                patterns[key]
                for key in sorted(
                    (k for k in patterns if k.startswith("detector_")),
                    key=lambda key: int(key.split("_")[-1]),
                )
            ]
            if len(routing) == len(ordered):
                source["patterns_by_detector"].update(
                    {key: np.asarray(value).tolist() for key, value in zip(routing, ordered)}
                )
            self.editor = source
            self.editor_index = None
            self.refresh_component_spec()
        except Exception as exc:
            self.model.message = str(exc)

    def commit_component(self):
        try:
            source = self.editor
            if not isinstance(source, (dict, list)):
                raise ValueError(
                    "Component must be a synthetic definition or a list of reference files."
                )
            if isinstance(source, dict) and source.get("model") == "fret_species":
                from chisurf.core.fluorescence.fret.species_decay import (
                    fret_species_detector_patterns,
                )

                patterns = fret_species_detector_patterns(
                    source,
                    self.model.detectors.selected,
                    self.model._current_n_bins(),
                    irf_for_detector=self.model._detector_irf,
                )
                source["patterns_by_detector"] = {
                    k: self.model._apply_pattern_shot_noise(v, source).tolist()
                    for k, v in patterns.items()
                }
            if self.editor_index is None:
                self.model.add_component(source)
            else:
                from .model import Component

                self.model.components[self.editor_index] = Component(
                    source,
                    source.get("name", "Component")
                    if isinstance(source, dict)
                    else "Measured reference",
                )
            self.editor = None
            self.submit(lambda model: model.compute())
        except Exception as exc:
            self.model.message = str(exc)

    def status_text(self):
        return self.model.message or ""

    def edit_selected_component(self):
        i = self.selected_component
        if 0 <= i < len(self.model.components):
            self.editor = json.loads(json.dumps(self.model.components[i].source)) if isinstance(self.model.components[i].source, dict) else None
            self.editor_index = i
            self.refresh_component_spec()

    def refresh_component_spec(self):
        if isinstance(self.editor, dict):
            self.component_panel = ComponentPanel(self.editor, self)
            self.component_spec = component_spec(self.editor)

    def add_measured(self, paths):
        self.model.add_component([str(p) for p in paths])
        self.submit(lambda model: model.compute())

    def set_irf(self, detector, role, path):
        self.model.detectors.values["irf"][f"{detector}|{role}"] = str(path)

    def form(self, name, spec=None, panel=None):
        state = self.forms.setdefault(name, FormState(on_used=self._used))
        state.rects.clear()
        draw_form((spec or SPEC[name]), panel or self.panel, state, titles=False)
        self.item_rects.update(state.rects)
        for source, alias in ALIASES.items():
            if source in state.rects:
                self.item_rects[alias] = state.rects[source]
        for action, tour_name in TOUR_NAMES.items():
            if action in state.rects:
                self.item_rects[tour_name] = state.rects[action]

    def draw_sources(self, box):
        self.form("toolbar")
        if self.job.running:
            im.text_disabled("Computing ...")
        elif self.model.message:
            im.text_wrapped(self.model.message)
        else:
            im.text_disabled(" ")
        self.form("inputs")
        im.text_unformatted("Detectors")
        self.form("detectors")
        self.form("mixed")
        im.text_unformatted("Components")
        self.form("components")
        self.form("component_buttons")
        import chisurf

        for fit in list(getattr(chisurf, "fits", []) or []):
            self.button(f"Read fit: {getattr(fit, 'name', 'Open fit')}", "Adopt the open fit's lifetime spectrum and detector-convolved patterns.", lambda fit=fit: self.read_fit(fit))
        self.remember("sources", tuple(box))
        self.item_rects["Decay sources"] = tuple(box)

    def refresh_saved_setups(self):
        self.setup.model.refresh_setups()

    def draw_setup(self, box):
        self.setup.draw()

    def apply_setup(self, settings=None):
        """The embedded editor changed the working definition: adopt its detectors and recompute."""
        settings = settings if settings is not None else self.setup.model.get_settings()
        if not settings.get("detectors"):
            return
        try:
            self.model.set_setup(settings)
            self.submit(lambda model: model.compute())
        except Exception as exc:
            self.model.message = str(exc)

    def draw_autofit(self, box):
        self.form("autofit")
        self.form("fit_parameters")

    def choose_parameter_link(self, parameter):
        if self.parameter_linker is not None:
            self.parameter_linker(parameter)
        else:
            self.link_parameter = parameter

    def draw_parameter_links(self):
        import chisurf
        from chisurf.core.registry.parameter_groups import iter_registered_parameter_groups

        groups = [(label, group) for _owner, label, group in iter_registered_parameter_groups()]
        groups += [
            (
                str(getattr(fit, "name", "Fit")),
                getattr(getattr(fit, "selected_fit", fit), "model", None),
            )
            for fit in (getattr(chisurf, "fits", []) or [])
        ]
        if im.begin("Link fitted parameter"):
            for label, group in groups:
                params = getattr(group, "parameters_all", []) or []
                if isinstance(params, dict):
                    params = list(params.values())
                for target in params:
                    if target is self.link_parameter:
                        continue
                    if im.selectable(
                        f"{label}: {getattr(target, 'name', 'Parameter')}##{id(target)}"
                    ):
                        try:
                            self.link_parameter.link = target
                            self.link_parameter = None
                        except Exception as exc:
                            self.model.message = str(exc)
                    im.set_item_tooltip(
                        "Follow this live parameter value; recursive links are rejected by the core model."
                    )
            self.button(
                "Cancel link",
                "Close parameter selection without changing links.",
                lambda: setattr(self, "link_parameter", None),
            )
        im.end()

    def draw_instrument(self, box):
        self.form("instrument")

    def draw_info(self, box):
        im.text_unformatted("Per-detector fit range (TAC bins)")
        self.form("ranges")
        im.text_unformatted("Information")
        im.text_wrapped(self.panel.info_text())

    @staticmethod
    def component_color(index):
        """One colour per component, in order (a hash of the name gave two components the same one)."""
        return COMPONENT_COLOURS[index % len(COMPONENT_COLOURS)]

    @staticmethod
    def stable_color(label):
        palette = [
            (56, 189, 248, 255),
            (251, 113, 133, 255),
            (74, 222, 128, 255),
            (250, 204, 21, 255),
            (192, 132, 252, 255),
            (251, 146, 60, 255),
        ]
        return palette[int(hashlib.sha1(label.encode()).hexdigest()[:8], 16) % len(palette)]

    def draw_filters(self, box):
        if implot.begin_plot("##lifetime_filters", (-1, -1)):
            implot.setup_axes("TAC bin", "Filter value")
            for entry in self.model.results():
                result = entry["result"]
                for role in ("", "par", "perp"):
                    filters = getattr(result, "filters" if not role else f"filters_{role}", None)
                    if filters is None:
                        continue
                    for i, weights in enumerate(filters):
                        names = [c.name for c in self.model.components if c.enabled]
                        rejected = i >= result.n_species
                        label = (
                            result.nuisance_labels[i - result.n_species]
                            if rejected and i - result.n_species < len(result.nuisance_labels or [])
                            else (names[i] if i < len(names) else f"filter {i}")
                        )
                        implot.plot_line(
                            f"{entry['detector']} {role} {label}"
                            + (" [rejected]" if rejected else ""),
                            np.arange(len(weights)),
                            weights,
                            spec=implot.PlotSpec(
                                line_color=(150, 150, 150, 255)
                                if rejected
                                else self.component_color(i),
                                dash=(5, 4) if rejected else None,
                            ),
                        )
            implot.end_plot()

    def draw_reconstruction(self, box):
        if implot.begin_plot("##reconstruction", (-1, -1)):
            implot.setup_axes("TAC bin", "Counts")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            peaks = [
                float(np.nanmax(getattr(entry["result"], attr)))
                for entry in self.model.results()
                for attr in ("total_decay", "total_decay_par", "total_decay_perp")
                if getattr(entry["result"], attr, None) is not None
            ]
            if peaks:
                # Frame the decay whenever its size or range changes (a limits request on an existing plot is ignored
                # unless it is COND_ALWAYS; the plot then showed the default 1e-6..1 window and none of the data).
                signature = (self.model._current_n_bins(), round(max(peaks), 3))
                if signature != getattr(self, "_recon_signature", None):
                    self._recon_signature = signature
                    implot.setup_axes_limits(
                        0, self.model._current_n_bins(), 1, max(max(peaks) * 1.2, 2), implot.COND_ALWAYS
                    )
            for entry in self.model.results():
                for role in ("", "par", "perp"):
                    result = entry["result"]
                    suffix = f"_{role}" if role else ""
                    total = getattr(result, "total_decay" + suffix, None)
                    recon = getattr(result, "reconstruction" + suffix, None)
                    if total is None:
                        continue
                    x = np.arange(len(total))
                    label = f"{entry['detector']} {role}"
                    implot.set_next_line_style((255, 255, 255, 255), 1.5)
                    implot.plot_line(label + " measured", x, np.clip(total, FLOOR, None))
                    implot.set_next_line_style((230, 40, 40, 255), 1.5)
                    implot.plot_line(label + " reconstruction", x, np.clip(recon, FLOOR, None))
                    irf = self.model._irf_by_detector.get(entry["detector"])
                    if irf is not None and np.max(irf) > 0:
                        implot.set_next_line_style((0, 200, 230, 255), 1.5)
                        implot.plot_line(
                            label + " IRF", np.arange(len(irf)), np.clip(irf / np.max(irf) * np.max(total), FLOOR, None)
                        )
            lo, hi = self.model._fit_bounds
            left = implot.drag_line_x(101, float(lo))
            right = implot.drag_line_x(102, float(hi))
            if not self.editing_blocked and (left.modified or right.modified):
                self.model._fit_bounds = (max(0, int(left.value)), max(1, int(right.value)))
            implot.end_plot()
        im.set_item_tooltip(
            "Drag the vertical lines to edit the fitted TAC range; Compute applies the new range."
        )

    def draw_residuals(self, box):
        if implot.begin_plot("##residuals", (-1, -1)):
            implot.setup_axes("TAC bin", "Weighted residuals σ")
            for entry in self.model.results():
                for role in ("", "par", "perp"):
                    values = getattr(
                        entry["result"], "weighted_residuals" + (f"_{role}" if role else ""), None
                    )
                    if values is not None:
                        implot.plot_line(
                            f"{entry['detector']} {role}", np.arange(len(values)), values
                        )
            implot.end_plot()

    def render(self):
        self.job.poll()
        self.setup.poll()
        if self._setup_pending is not None and not self.job.running:
            settings, self._setup_pending = self._setup_pending, None
            self.apply_setup(settings)
        if self.pending_restoration_compute and not self.job.running:
            self.pending_restoration_compute = False
            self.submit(lambda model: model.compute())
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        if not getattr(self, "_ratio_set", False):
            self._ratio_set = True  # a narrow window gives the controls room for their tabs; the bar still drags
            self.docks.layout.ratio = max(0.34, min(0.52, MIN_CONTROLS / max(float(vp.size[0]), 1.0)))
        self.docks.draw(frame)
        if self.help.open:
            self.help.draw(frame)
        if self.tour.active:
            self.tour.draw(*vp.size)
        if self.dialog:
            closed = self.file_window.begin(frame) == "close"
            result = self.dialog.draw()
            self.file_window.end()
            if closed or result is False:
                self.dialog = None
            elif result:
                callback, self.dialog = self.dialog_callback, None
                callback(result)
        elif self.file_window.open:
            self.file_window.hide()
        self.setup.draw_dialogs(frame)
        if self.editor is not None and self.component_spec is not None:
            self.component_window.show()
            closed = self.component_window.begin(frame) == "close"
            self.form("component_form", self.component_spec, self.component_panel)
            self.component_window.end()
            if closed:
                self.editor = None
        elif self.component_window.open:
            self.component_window.hide()
        if self.link_parameter is not None:
            self.draw_parameter_links()
        fingerprint = self.settings_fingerprint()
        if fingerprint != self.last_settings and not self.job.running:
            self.last_settings = fingerprint
            self.submit(lambda model: model.compute(), replace=False)

    def files_dropped(self, paths):
        self.on_paths_dropped(paths)

    def on_paths_dropped(self, paths):
        if paths:
            if len(paths) == 1 and str(paths[0]).lower().endswith(".json"):
                self.submit(lambda model: model.load_project(paths[0]))
            else:
                self.load_total(paths)

    def export_state(self):
        return self.model.export_state()

    def restore_state(self, state):
        self.job.stop()
        self.model.restore_state(state)
        self.last_settings = self.settings_fingerprint()
        self.pending_restoration_compute = True
        self.setup_json = json.dumps(self.model._detector_settings, indent=2)

    def close(self):
        self.setup.close()
        self.job.close()
        from chisurf.core.registry.parameter_groups import unregister_parameter_group

        unregister_parameter_group(self.registry_owner)


def create_app(workflow_context=None, parameter_linker=None):
    return FilterApp(workflow_context=workflow_context, parameter_linker=parameter_linker)
