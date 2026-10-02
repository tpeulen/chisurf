"""Native EMTK lifetime/FRET filter calculator, independent of Qt widgets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .model import FilterModel


#: Lowest count drawn on the logarithmic decay axis: an IRF tail of 1e-298 would otherwise stretch the view over 300 decades.
FLOOR = 0.5


class FilterApp(ImApp):
    def __init__(self, workflow_context=None, parameter_linker=None):
        self.model = FilterModel()
        self.workflow_context = workflow_context
        self.parameter_linker = parameter_linker
        self.registry_owner = f"fcs_filter_calc_emtk_{id(self)}"
        self.job = BackgroundJob()
        self.pending_restoration_compute = False
        self.dialog = None
        self.dialog_callback = None
        self.editor = None
        self.link_parameter = None
        self.editor_index = None
        self.selected_component = -1
        self.setup_store = None
        self.setup_json = json.dumps(self.model._detector_settings, indent=2)
        self.item_rects = {}
        base = Path(__file__).parents[1] / "gui_parts"
        self.help = EmTkHelpWindow(title="Filtered FCS help", resource=base / "help.md")
        self.tour = EmTkGuidedTour(steps=base / "guide.json", get_target_rect=self.item_rects.get)
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

    def submit(self, operation):
        if self.job.running:
            return False
        snapshot = self.model.snapshot()

        def work():
            operation(snapshot)
            return snapshot

        def publish(model):
            self.model = model
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
    ):
        if self.job.running:
            return
        self.dialog = FileDialog(title, mode=mode, multiselect=multiple, filters=filters)
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
        self.editor = json.dumps(source, indent=2)
        self.editor_index = None

    def draw_component_form(self):
        try:
            source = json.loads(self.editor)
        except ValueError:
            return
        if not isinstance(source, dict):
            return
        changed, name = im.input_text("Component name", source.get("name", "Component"))
        im.set_item_tooltip("Name shown in the filter legends and component list.")
        dirty = changed
        source["name"] = name
        for key, label, default, tip in (
            ("bin_width", "Bin width ns", 0.05, "Time represented by each TAC bin in nanoseconds."),
            ("start_bin", "Start bin", 0, "Shift the synthetic decay by this many TAC bins."),
            (
                "period_ns",
                "Laser period ns",
                0.0,
                "Periodic convolution period; zero disables periodic wrapping.",
            ),
        ):
            changed, value = self.number(
                label, source.get(key, default), tip, integer=key == "start_bin"
            )
            source[key] = value
            dirty |= changed
        if source.get("model") == "lifetime":
            changed, source["lifetime"] = self.number(
                "Lifetime ns",
                source.get("lifetime", 2.0),
                "Exponential fluorescence lifetime in nanoseconds.",
            )
            dirty |= changed
        if source.get("model") == "lifetime_spectrum":
            amplitudes = source.get("amplitudes", [1.0])
            lifetimes = source.get("lifetimes", [2.0])
            for i in range(min(len(amplitudes), len(lifetimes))):
                changed, amplitudes[i] = self.number(
                    f"Amplitude {i + 1}",
                    amplitudes[i],
                    "Pre-exponential amplitude of this lifetime component.",
                )
                dirty |= changed
                changed, lifetimes[i] = self.number(
                    f"Lifetime {i + 1} ns",
                    lifetimes[i],
                    "Lifetime of this spectrum component in nanoseconds.",
                )
                dirty |= changed
            if im.button("Add spectrum row"):
                amplitudes.append(1.0)
                lifetimes.append(2.0)
                dirty = True
            im.set_item_tooltip("Add another amplitude/lifetime pair to the spectrum.")
            source.update(amplitudes=amplitudes, lifetimes=lifetimes)
        if source.get("model") in {"gaussian_lifetime", "gaussian_distance"}:
            fields = (
                (
                    ("mean_lifetime", "Mean lifetime ns", 2.0),
                    ("sigma_lifetime", "Lifetime width ns", 0.4),
                )
                if source["model"] == "gaussian_lifetime"
                else (
                    ("donor_lifetime", "Donor lifetime ns", 4.0),
                    ("forster_radius", "Förster radius Å", 52.0),
                    ("mean_distance", "Mean distance Å", 50.0),
                    ("sigma_distance", "Distance width Å", 5.0),
                )
            )
            for key, label, default in fields:
                changed, source[key] = self.number(
                    label,
                    source.get(key, default),
                    "Mean or standard deviation of the sampled species distribution.",
                )
                dirty |= changed
            changed, source["n_samples"] = self.number(
                "Distribution samples",
                source.get("n_samples", 81),
                "Number of quadrature samples resolving the lifetime/distance distribution.",
                True,
            )
            dirty |= changed
        if source.get("model") == "fret_species":
            states = ["da", "d_only", "a_only"]
            changed, index = im.combo(
                "State",
                states.index(source.get("state", "da")),
                ["Donor + acceptor", "Donor only", "Acceptor only"],
            )
            im.set_item_tooltip("Choose the fluorophore labeling state of this species.")
            source["state"] = states[index]
            dirty |= changed
            modes = ["efficiency", "distance"]
            mode = source.get("fret_mode", "efficiency")
            changed, index = im.combo(
                "FRET model", modes.index(mode) if mode in modes else 0, modes
            )
            im.set_item_tooltip(
                "Specify transfer efficiency, a distance, or a distance distribution."
            )
            source["fret_mode"] = modes[index]
            dirty |= changed
            for key, label, default in (
                ("transfer_efficiency", "Transfer efficiency", 0.5),
                ("distance", "Distance Å", 50.0),
                ("forster_radius", "Förster radius Å", 52.0),
                ("kappa2", "κ²", 2.0 / 3.0),
                ("x_donly", "Donor-only fraction", 0.0),
            ):
                changed, source[key] = self.number(
                    label,
                    source.get(key, default),
                    "Species FRET parameter used in coupled detector decay generation.",
                )
                dirty |= changed
            for spectrum_key, label in (
                ("donor_spectrum", "Donor"),
                ("acceptor_spectrum", "Acceptor"),
            ):
                spectrum = list(source.get(spectrum_key, [1.0, 4.0 if label == "Donor" else 2.0]))
                for i in range(0, len(spectrum) - 1, 2):
                    changed, spectrum[i] = self.number(
                        f"{label} amplitude {i // 2 + 1}",
                        spectrum[i],
                        "Pre-exponential fluorescence amplitude.",
                    )
                    dirty |= changed
                    changed, spectrum[i + 1] = self.number(
                        f"{label} lifetime {i // 2 + 1} ns",
                        spectrum[i + 1],
                        "Fluorescence lifetime before energy transfer.",
                    )
                    dirty |= changed
                source[spectrum_key] = spectrum
            if source["fret_mode"] == "distance":
                rows = source.get(
                    "distance_rows",
                    [{"mean": source.get("distance", 50.0), "sigma": 0.0, "amplitude": 1.0}],
                )
                for i, row in enumerate(rows):
                    for key, label in (
                        ("mean", "Distance mean Å"),
                        ("sigma", "Distance width Å"),
                        ("amplitude", "Distance amplitude"),
                    ):
                        changed, row[key] = self.number(
                            f"{label} {i + 1}",
                            row.get(key, 0),
                            "Species population weight and Gaussian distance distribution parameters.",
                        )
                        dirty |= changed
                if im.button("Add distance population"):
                    rows.append({"mean": 50.0, "sigma": 5.0, "amplitude": 1.0})
                    dirty = True
                im.set_item_tooltip("Add a weighted distance-distribution population.")
                source["distance_rows"] = rows
                options = ["gaussian", "gaussian_3d"]
                changed, index = im.combo(
                    "Distance distribution",
                    options.index(source.get("distance_distribution", "gaussian")),
                    options,
                )
                im.set_item_tooltip(
                    "Use a scalar Gaussian or the physical radial distribution of two 3-D Gaussian dye positions."
                )
                source["distance_distribution"] = options[index]
                dirty |= changed
            crosstalk = source.get("crosstalk", {})
            for key, default in (("alpha", 0.0), ("beta", 1.0), ("gamma", 1.0), ("delta", 0.0)):
                changed, crosstalk[key] = self.number(
                    key,
                    crosstalk.get(key, default),
                    "Species leakage, excitation or detection correction factor.",
                )
                dirty |= changed
            source["crosstalk"] = crosstalk
        changed, source["shot_noise"] = self.checkbox(
            "Simulate shot noise",
            source.get("shot_noise", False),
            "Sample the synthetic pattern using photon-count Poisson statistics.",
        )
        dirty |= changed
        if source["shot_noise"]:
            changed, source["photon_count"] = self.number(
                "Pattern photons",
                source.get("photon_count", 100000),
                "Number of photons in the simulated reference pattern.",
                True,
            )
            dirty |= changed
            changed, source["noise_seed"] = self.number(
                "Random seed",
                source.get("noise_seed", 0),
                "Seed for reproducible pattern shot-noise generation.",
                True,
            )
            dirty |= changed
        if dirty:
            # Per-detector pattern caches describe the previous definition.
            # Rebuild them on Apply rather than silently retaining stale shapes.
            source.pop("patterns_by_detector", None)
            self.editor = json.dumps(source, indent=2)

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
            self.editor = json.dumps(source, indent=2)
            self.editor_index = None
        except Exception as exc:
            self.model.message = str(exc)

    def commit_component(self):
        try:
            source = json.loads(self.editor)
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

    def draw_sources(self, box):
        model = self.model
        im.begin_disabled(self.job.running)
        self.button(
            "Mixed…",
            "Open a measured mixed decay histogram or TTTR/BST files.",
            lambda: self.choose("Mixed decay", self.load_total, multiple=True),
        )
        self.button(
            "From correlator",
            "Adopt the sibling Correlator files and microtime binning.",
            self.from_correlator,
        )
        im.text_wrapped(model.total_label)
        changed, model.polarized = self.checkbox(
            "Polarized / MFD",
            model.polarized,
            "Resolve parallel and perpendicular routing channels separately for every detector.",
        )
        _, model.stacked = self.checkbox(
            "Global stacked detectors",
            model.stacked,
            "Use inter-detector relative species brightness in one global filter solve.",
        )
        _, model.options_model.fit_background = self.checkbox(
            "Afterpulse / constant",
            model.options_model.fit_background,
            "Add and reject a constant dark-count/afterpulse nuisance filter.",
        )
        _, model.options_model.scatter_irf = self.checkbox(
            "Scatter / IRF",
            model.options_model.scatter_irf,
            "Add and reject the measured or synthetic detector IRF nuisance filter.",
        )
        _, start = self.number("Fit start", model._fit_bounds[0], "First included TAC bin.", True)
        _, stop = self.number(
            "Fit stop", model._fit_bounds[1], "Exclusive upper TAC bin of the filter fit.", True
        )
        model._fit_bounds = (max(0, start), max(1, stop))
        for i, c in enumerate(model.components):
            _, c.enabled = self.checkbox(
                f"##component{i}", c.enabled, "Include this component in filter calculation."
            )
            im.same_line()
            if im.selectable(f"{c.name}##species{i}", i == self.selected_component):
                self.selected_component = i
            im.set_item_tooltip(
                "Right-click to edit, remove or duplicate the component definition."
            )
            if im.begin_popup_context_item(f"component-menu{i}"):
                if im.menu_item("Edit component"):
                    self.editor = json.dumps(c.source, indent=2)
                    self.editor_index = i
                im.set_item_tooltip(
                    "Edit the complete lifetime, lifetime-spectrum, FRET or measured-reference definition."
                )
                if im.menu_item("Duplicate component"):
                    model.add_component(c.source)
                im.set_item_tooltip("Copy the selected component, preserving every model field.")
                if im.menu_item("Remove component"):
                    model.components.pop(i)
                im.set_item_tooltip("Remove this basis component without deleting files.")
                im.end_popup()
        for kind, label in [
            ("lifetime", "Add lifetime"),
            ("lifetime_spectrum", "Add spectrum"),
            ("fret_species", "Add FRET species"),
            ("gaussian_lifetime", "Add lifetime distribution"),
            ("gaussian_distance", "Add distance distribution"),
        ]:
            self.button(
                label,
                "Create a synthetic component; its complete definition is editable.",
                lambda kind=kind: self.new_component(kind),
            )
        import chisurf

        fits = list(getattr(chisurf, "fits", []) or [])
        if fits:
            for fit in fits:
                self.button(
                    f"Read fit: {getattr(fit, 'name', 'Open fit')}",
                    "Adopt the open fit's lifetime spectrum and detector-convolved patterns.",
                    lambda fit=fit: self.read_fit(fit),
                )
        self.button(
            "Add measured pattern…",
            "Load one or more reference decay files as a component.",
            lambda: self.choose(
                "Species reference", lambda paths: self.add_measured(paths), multiple=True
            ),
        )
        self.button(
            "Compute filters",
            "Solve the selected component filters over the fit range.",
            lambda: self.submit(lambda model: model.compute()),
        )
        self.button(
            "Unmix",
            "Fit non-negative component intensities and compute filters.",
            lambda: self.submit(lambda model: model.unmix()),
        )
        self.button(
            "Save project…",
            "Save inputs, definitions, detector IRFs, options and computed filters.",
            lambda: self.choose(
                "Save project",
                lambda paths: self.submit(lambda model: model.save_project(paths[0])),
                mode="save",
                filters="Project (*.json)",
            ),
        )
        self.button(
            "Load project…",
            "Restore existing Qt or native Filter Calculator projects.",
            lambda: self.choose(
                "Load project",
                lambda paths: self.submit(lambda model: model.load_project(paths[0])),
                filters="Project (*.json)",
            ),
        )
        self.button(
            "Export results…",
            "Export single, multi-detector or MFD filters and reconstruction metadata.",
            lambda: self.choose(
                "Export filters",
                lambda paths: self.submit(lambda model: model.export_results(paths[0])),
                mode="save",
                filters="Filters (*.json)",
            ),
        )
        self.button(
            "Example",
            "Restore the detector-convolved synthetic 70/30 example.",
            lambda: self.submit(lambda model: (model.populate_example(), model.compute())),
        )
        im.end_disabled()
        self.button(
            "Help", "Read the lifetime filter workflow and scientific assumptions.", self.help.show
        )
        self.button("Guide", "Walk through the built-in example.", self.tour.start)
        if self.job.running:
            self.button(
                "Stop",
                "Discard pending computation results; file exports already writing may finish.",
                self.job.stop,
            )
        im.text_wrapped(model.message)

    def add_measured(self, paths):
        self.model.add_component([str(p) for p in paths])
        self.submit(lambda model: model.compute())

    def refresh_saved_setups(self):
        if self.job.running:
            return
        from chisurf.core.setup_channel_definition import ChannelDefinition

        def work():
            store = ChannelDefinition()
            store.refresh_setups()
            return store

        def publish(store):
            self.setup_store = store
            self.model.message = f"Loaded {len(store.setups)} saved detector setups."

        self.job.start(work, publish, lambda exc: setattr(self.model, "message", str(exc)))

    def select_saved_setup(self, name):
        self.setup_store.select_setup(name)
        self.model.set_setup(self.setup_store.get_settings())
        self.setup_json = json.dumps(self.model._detector_settings, indent=2)
        self.submit(lambda model: model.compute())

    def draw_setup(self, box):
        model = self.model
        im.begin_disabled(self.job.running)
        self.button(
            "Refresh saved setups",
            "Read saved Detector Definition setups from the authoritative MMFDB or JSON store.",
            self.refresh_saved_setups,
        )
        if self.setup_store is not None and self.setup_store.setups:
            names = sorted(self.setup_store.setups)
            current = self.setup_store.current_name
            changed, index = im.combo(
                "Saved detector setup", names.index(current) if current in names else -1, names
            )
            im.set_item_tooltip(
                "Use a saved detector definition, routing channels and calibration."
            )
            if changed:
                self.select_saved_setup(names[index])
        for detector in model.detectors.names:
            changed, value = self.checkbox(
                detector,
                detector in model.detectors.selected,
                "Include this detector in total decay and filter calculations.",
            )
            if changed:
                if value:
                    model.detectors.selected.append(detector)
                elif detector in model.detectors.selected:
                    model.detectors.selected.remove(detector)
            for role in ("par", "perp") if model.polarized else ("",):
                im.push_id(f"{detector}|{role}")
                im.text(f"{detector} {role}")
                _, path = im.input_text("IRF path", model.detectors.irf_path(detector, role))
                im.set_item_tooltip(
                    "Measured instrument response; empty uses Width/Skew/Shift to build a synthetic IRF."
                )
                model.detectors.values["irf"][f"{detector}|{role}"] = path
                self.button(
                    "Browse IRF…",
                    "Choose a measured IRF decay histogram.",
                    lambda d=detector, r=role: self.choose(
                        "IRF", lambda paths: self.set_irf(d, r, paths[0])
                    ),
                )
                _, width = self.number(
                    "Width ns",
                    model.detectors.width(detector, role),
                    "Synthetic IRF full width at half maximum in nanoseconds.",
                )
                _, skew = self.number(
                    "Skew",
                    model.detectors.skew(detector, role),
                    "Synthetic generalized-normal IRF shape.",
                )
                _, shift = self.number(
                    "Shift ns",
                    model.detectors.shift(detector, role),
                    "Sub-bin time alignment, applied to both measured and synthetic IRFs.",
                )
                model.detectors.set_width(detector, max(0, width), role)
                model.detectors.set_skew(detector, skew, role)
                model.detectors.set_shift(detector, shift, role)
                im.pop_id()
        _, self.setup_json = im.input_text_multiline(
            "Detector setup JSON", self.setup_json, (-1, 180)
        )
        im.set_item_tooltip(
            "Detector routing channels and calibration setup, compatible with the authoritative Detector Definition tool."
        )
        self.button(
            "Apply detector setup",
            "Validate and adopt routing, detector names and calibration.",
            self.apply_setup,
        )
        self.button(
            "Load detector setup…",
            "Open a detector setup JSON file.",
            lambda: self.choose("Detector setup", self.load_setup, filters="Setup (*.json)"),
        )
        im.end_disabled()

    def set_irf(self, detector, role, path):
        self.model.detectors.values["irf"][f"{detector}|{role}"] = str(path)

    def apply_setup(self):
        try:
            self.model.set_setup(json.loads(self.setup_json))
            self.submit(lambda model: model.compute())
        except Exception as exc:
            self.model.message = str(exc)

    def load_setup(self, paths):
        self.setup_json = Path(paths[0]).read_text()
        self.apply_setup()

    def draw_autofit(self, box):
        model = self.model
        im.begin_disabled(self.job.running)
        settings = model._auto_fit_settings
        changed, index = im.combo(
            "Type", 1 if settings["kind"] == "fret" else 0, ["Lifetime species", "FRET states"]
        )
        im.set_item_tooltip(
            "Fit lifetime components, or FRET distances against the Förster radius."
        )
        if changed:
            settings["kind"] = "fret" if index else "lifetime"
        _, n = self.number(
            "Components / states",
            settings["n_components"],
            "Number of lifetime components or FRET states, 1–12.",
            True,
        )
        _, lo = self.number(
            "Lifetime min ns", settings["tau_min"], "Lower fitted lifetime bound in nanoseconds."
        )
        _, hi = self.number(
            "Lifetime max ns",
            settings["tau_max"],
            "Upper lifetime bound; donor lifetime for FRET fitting.",
        )
        settings.update(
            n_components=max(1, min(12, n)), tau_min=max(0.01, lo), tau_max=max(0.02, hi)
        )
        self.button(
            "Fit components",
            "Fit the mixed decay, jointly fitting the synthetic IRF when no measured IRF is loaded.",
            lambda: self.submit(lambda model: model._auto_fit_components()),
        )
        result = model._auto_fit_result
        if result:
            im.text_wrapped(f"Reduced χ²: {result.get('chi2_reduced', '?')}")
            fit = result.get("fit")
            parameters = getattr(getattr(fit, "model", None), "parameters_all", {})
            if isinstance(parameters, dict):
                parameters = list(parameters.values())
            for parameter in parameters or []:
                if getattr(parameter, "name", "") in {
                    "dt",
                    "start",
                    "stop",
                    "irf_start",
                    "irf_stop",
                }:
                    continue
                name = getattr(parameter, "name", "parameter")
                value = getattr(parameter, "value", None)
                if isinstance(value, (int, float)):
                    changed, value = self.number(
                        name,
                        value,
                        "Edit this fitted model parameter; use linking to share a fit parameter.",
                    )
                    if changed:
                        parameter.value = value
                    changed, fixed = self.checkbox(
                        f"Fixed##{id(parameter)}",
                        bool(getattr(parameter, "fixed", False)),
                        "Hold this parameter fixed during fitting.",
                    )
                    if changed:
                        parameter.fixed = fixed
                    self.button(
                        f"Link {name}##{id(parameter)}",
                        "Choose a parameter from open fits or registered plugin models to follow.",
                        lambda p=parameter: self.choose_parameter_link(p),
                    )
                    if getattr(parameter, "link", None) is not None:
                        self.button(
                            f"Unlink {name}##{id(parameter)}",
                            "Detach this follower while retaining its current scalar value.",
                            lambda p=parameter: setattr(p, "link", None),
                        )
        im.end_disabled()

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
        im.begin_disabled(self.job.running)
        view = json.loads(
            (Path(__file__).parents[1] / "gui_parts/instrument_options.view.json").read_text()
        )
        for row in view["sections"][0]["options"]["rows"]:
            _, value = self.number(
                row["label"], getattr(self.model.instrument_model, row["attr"]), row["description"]
            )
            setattr(self.model.instrument_model, row["attr"], value)
        _, self.model.instrument_model.periodic = self.checkbox(
            "Periodic convolution",
            self.model.instrument_model.periodic,
            "Wrap the previous laser pulse decay tail into the current microtime window.",
        )
        im.end_disabled()

    def draw_info(self, box):
        im.begin_disabled(self.job.running)
        im.text_wrapped(
            f"{len(self.model.components)} components; detectors: {', '.join(self.model.detectors.selected)}; bin width {self.model._pattern_bin_width_ns():.6g} ns"
        )
        for detector in self.model.detectors.selected:
            im.push_id(detector)
            lo, hi = self.model._detector_fit_ranges.get(detector, self.model._fit_bounds)
            changed_start, lo = self.number(
                f"{detector} start", lo, "Per-detector first fitted TAC bin.", True
            )
            changed_stop, hi = self.number(
                f"{detector} stop", hi, "Per-detector exclusive last fitted TAC bin.", True
            )
            if changed_start or changed_stop:
                self.model._detector_fit_ranges[detector] = (max(0, lo), max(lo + 1, hi))
            im.pop_id()
        for entry in self.model.results():
            im.text_wrapped(f"{entry['detector']}: {entry['result'].metadata}")

        im.end_disabled()

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
                                else self.stable_color(label),
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
            if not self.job.running and (left.modified or right.modified):
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
        if self.pending_restoration_compute and not self.job.running:
            self.pending_restoration_compute = False
            self.submit(lambda model: model.compute())
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        self.docks.draw(frame)
        if self.help.open:
            self.help.draw(frame)
        if self.tour.active:
            self.tour.draw(*vp.size)
        if self.dialog:
            if im.begin("Choose input or output"):
                result = self.dialog.draw()
                if result:
                    callback = self.dialog_callback
                    self.dialog = None
                    callback(result)
                elif result is False:
                    self.dialog = None
            im.end()
        if self.editor is not None:
            im.begin_disabled(self.job.running)
            if im.begin("Component definition"):
                self.draw_component_form()
                _, self.editor = im.input_text_multiline("Definition JSON", self.editor, (-1, 300))
                im.set_item_tooltip(
                    "All lifetime/spectrum/FRET source fields are editable; preserve per-detector patterns unless regenerating them."
                )
                self.button(
                    "Apply component",
                    "Validate and compute the edited species model.",
                    self.commit_component,
                )
                self.button(
                    "Cancel component",
                    "Discard the current definition edit.",
                    lambda: setattr(self, "editor", None),
                )
            im.end()
            im.end_disabled()
        if self.link_parameter is not None:
            self.draw_parameter_links()
        fingerprint = self.settings_fingerprint()
        if fingerprint != self.last_settings and not self.job.running:
            self.last_settings = fingerprint
            self.submit(lambda model: model.compute())

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
        self.job.close()
        from chisurf.core.registry.parameter_groups import unregister_parameter_group

        unregister_parameter_group(self.registry_owner)


def create_app(workflow_context=None, parameter_linker=None):
    return FilterApp(workflow_context=workflow_context, parameter_linker=parameter_linker)
