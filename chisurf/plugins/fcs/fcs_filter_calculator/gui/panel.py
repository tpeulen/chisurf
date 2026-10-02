"""The Qt-free view model behind the filter calculator window: what ``filter_emtk.view.json`` reads and calls.

The app owns the worker, the dialogs and the plots; this panel gives the spec forms the model's fields, the tables
(components, detectors, instrument, per-detector ranges, auto-fit parameters) as records, and the actions.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..gui_parts.instrument_options import InstrumentViewModel  # noqa: F401  (documented dependency of the rows below)

HERE = Path(__file__).parent
INSTRUMENT_ROWS = json.loads((HERE.parent / "gui_parts" / "instrument_options.view.json").read_text())["sections"][0]["options"]["rows"]
KINDS = ("lifetime", "fret")
KIND_LABELS = ("Lifetime species", "FRET states")


def _number(text):
    try:
        value = float(str(text).replace(",", ".").strip())
    except ValueError:
        return None
    return value if value == value and abs(value) != float("inf") else None


def describe(component) -> str:
    """One line per component, as the Qt list shows it: kind, main parameters and the IRF note."""
    source = component.source
    if isinstance(source, list):
        return f"measured, {len(source)} file(s)"
    model = source.get("model", "")
    if model == "lifetime":
        return f"synthetic, tau = {source.get('lifetime', 0):g} ns"
    if model == "lifetime_spectrum":
        return f"synthetic, {len(source.get('lifetimes', []))} lifetimes"
    if model == "gaussian_lifetime":
        return f"synthetic, tau = {source.get('mean_lifetime', 0):g} +- {source.get('sigma_lifetime', 0):g} ns"
    if model == "gaussian_distance":
        return f"synthetic, R = {source.get('mean_distance', 0):g} +- {source.get('sigma_distance', 0):g} A"
    if model == "fret_species":
        return f"FRET species ({source.get('state', 'da')})"
    return str(source.get("type", "component"))


class FilterPanel:
    """Fields, tables and actions of the window; edits are ignored while a computation runs (the model is then a snapshot)."""

    def __init__(self, app) -> None:
        object.__setattr__(self, "app", app)

    # -- fields -------------------------------------------------------------------------------------------- #
    @property
    def m(self):
        return self.app.model

    def __getattr__(self, name):
        return getattr(self.app.model, name)

    def __setattr__(self, name, value):
        if self.app.editing_blocked:
            return
        if name in ("fit_background", "scatter_irf"):
            setattr(self.m.options_model, name, bool(value))
        elif name in ("polarized", "stacked"):
            setattr(self.m, name, bool(value))
        elif name == "fit_start":
            lo, hi = self.m._fit_bounds
            self.m._fit_bounds = (max(0, min(int(value), hi - 1)), hi)
        elif name == "fit_stop":
            lo, hi = self.m._fit_bounds
            self.m._fit_bounds = (lo, max(int(value), lo + 1))
        elif name == "autofit_kind":
            self.m._auto_fit_settings["kind"] = value
        elif name == "autofit_components":
            self.m._auto_fit_settings["n_components"] = max(1, min(12, int(value)))
        elif name == "autofit_tau_min":
            self.m._auto_fit_settings["tau_min"] = max(0.01, float(value))
        elif name == "autofit_tau_max":
            self.m._auto_fit_settings["tau_max"] = max(0.02, float(value))
        elif name == "periodic":
            self.m.instrument_model.periodic = bool(value)
        else:
            setattr(self.m, name, value)

    @property
    def fit_background(self):
        return self.m.options_model.fit_background

    @property
    def scatter_irf(self):
        return self.m.options_model.scatter_irf

    @property
    def fit_start(self):
        return int(self.m._fit_bounds[0])

    @property
    def fit_stop(self):
        return int(self.m._fit_bounds[1])

    @property
    def autofit_kind(self):
        return self.m._auto_fit_settings["kind"]

    @property
    def autofit_components(self):
        return int(self.m._auto_fit_settings["n_components"])

    @property
    def autofit_tau_min(self):
        return float(self.m._auto_fit_settings["tau_min"])

    @property
    def autofit_tau_max(self):
        return float(self.m._auto_fit_settings["tau_max"])

    @property
    def periodic(self):
        return bool(self.m.instrument_model.periodic)

    def autofit_kinds(self):
        return list(zip(KINDS, KIND_LABELS))

    def mixed_label(self) -> str:
        return self.m.total_label or "No mixed decay loaded"

    def status_line(self) -> str:
        return self.app.status_text()

    def range_line(self) -> str:
        lo, hi = self.m._fit_bounds
        return f"Fit range: {lo}-{hi} TAC bins"

    def enabled(self, name: str) -> bool:
        running = self.app.job.running
        if name == "stop":
            return running
        if name in ("guide", "help"):
            return True
        if running:
            return False
        if name in ("save_project", "export_results", "export"):
            return name != "export_results" or bool(self.m.results())
        if name in ("edit_component", "duplicate_component", "remove_component"):
            return 0 <= self.app.selected_component < len(self.m.components)
        if name == "browse_irf":
            return self.app.selected_detector_row is not None
        if name in ("unlink_parameter",):
            return self.app.selected_parameter is not None and getattr(self.app.selected_parameter, "link", None) is not None
        if name == "link_parameter":
            return self.app.selected_parameter is not None
        return True

    # -- the components table ----------------------------------------------------------------------------------- #
    def component_columns(self):
        return [
            {"key": "enabled", "label": "Use", "width": 40, "description": "Include this component in the filter calculation. Click to tick or untick."},
            {"key": "name", "label": "Component", "description": "Name shown in the filter legends. Double click, type and press Enter to rename."},
            {"key": "kind", "label": "Definition", "editable": False, "description": "What the component is: a synthetic lifetime, spectrum, distribution, FRET species or measured reference files."},
        ]

    def component_rows(self):
        return [{"enabled": c.enabled, "name": c.name, "kind": describe(c), "_i": i} for i, c in enumerate(self.m.components)]

    def edit_component_row(self, record, key, value):
        if self.app.editing_blocked:
            return
        component = self.m.components[record["_i"]]
        if key == "enabled":
            component.enabled = bool(value)
        elif key == "name" and str(value).strip():
            component.name = str(value).strip()
            if isinstance(component.source, dict):
                component.source["name"] = component.name

    def select_component(self, record):
        self.app.selected_component = -1 if record is None else int(record["_i"])

    def component_editable(self, record, key):
        return not self.app.editing_blocked and key in ("enabled", "name")

    # -- the detectors table ----------------------------------------------------------------------------------- #
    def detector_columns(self):
        return [
            {"key": "use", "label": "Use", "width": 40, "description": "Include this detector in the total decay and the filter calculation."},
            {"key": "name", "label": "Detector", "editable": False, "description": "Detector of the active setup (with the parallel or perpendicular role when polarization is resolved)."},
            {"key": "width", "label": "Width", "format": "%.4g", "description": "Synthetic IRF full width at half maximum in ns, used when no IRF file is set."},
            {"key": "skew", "label": "Skew", "format": "%.4g", "description": "Shape (skew) of the synthetic generalised-normal IRF."},
            {"key": "shift", "label": "Shift", "format": "%.4g", "description": "Sub-bin time shift in ns, applied to measured and synthetic IRFs."},
            {"key": "irf", "label": "IRF", "description": "Measured IRF decay file (double click to type a path, or Browse IRF...). Empty uses Width, Skew and Shift."},
        ]

    def detector_rows(self):
        m = self.m
        rows = []
        for detector in m.detectors.names:
            for role in ("par", "perp") if m.polarized else ("",):
                rows.append({
                    "use": detector in m.detectors.selected,
                    "name": f"{detector} {role}".strip(),
                    "width": m.detectors.width(detector, role),
                    "skew": m.detectors.skew(detector, role),
                    "shift": m.detectors.shift(detector, role),
                    "irf": m.detectors.irf_path(detector, role),
                    "_detector": detector,
                    "_role": role,
                })
        return rows

    def edit_detector_row(self, record, key, value):
        if self.app.editing_blocked:
            return
        d, role, det = record["_detector"], record["_role"], self.m.detectors
        if key == "use":
            if value and d not in det.selected:
                det.selected.append(d)
            elif not value and d in det.selected and len(det.selected) > 1:
                det.selected.remove(d)  # at least one detector stays: the filters need a decay
        elif key == "irf":
            det.values["irf"][f"{d}|{role}"] = str(value).strip()
        else:
            number = _number(value)
            if number is None:
                return
            {"width": lambda v: det.set_width(d, max(0.0, v), role), "skew": lambda v: det.set_skew(d, v, role),
             "shift": lambda v: det.set_shift(d, v, role)}[key](number)

    def detector_editable(self, record, key):
        return not self.app.editing_blocked and key != "name"

    def select_detector_row(self, record):
        self.app.selected_detector_row = record

    # -- instrument and ranges ------------------------------------------------------------------------------- #
    def instrument_columns(self):
        return [
            {"key": "name", "label": "Name", "editable": False, "description": "Instrument or calibration parameter."},
            {"key": "value", "label": "Value", "format": "%.6g", "description": "Double click, type a number and press Enter. Pre-populated from the selected setup."},
        ]

    def instrument_rows(self):
        return [{"name": row["label"], "value": float(getattr(self.m.instrument_model, row["attr"])), "description": row["description"], "_attr": row["attr"]}
                for row in INSTRUMENT_ROWS]

    def edit_instrument(self, record, key, value):
        number = _number(value)
        if number is not None and not self.app.editing_blocked:
            setattr(self.m.instrument_model, record["_attr"], number)

    def instrument_editable(self, record, key):
        return key == "value" and not self.app.editing_blocked

    def range_columns(self):
        return [
            {"key": "detector", "label": "Detector", "editable": False, "description": "Detector the range belongs to."},
            {"key": "start", "label": "Start", "description": "First fitted TAC bin of this detector."},
            {"key": "stop", "label": "Stop", "description": "Exclusive last fitted TAC bin of this detector."},
        ]

    def range_rows(self):
        return [{"detector": d, "start": int(self.m._detector_fit_ranges.get(d, self.m._fit_bounds)[0]),
                 "stop": int(self.m._detector_fit_ranges.get(d, self.m._fit_bounds)[1])} for d in self.m.detectors.selected]

    def edit_range(self, record, key, value):
        number = _number(value)
        if number is None or self.app.editing_blocked:
            return
        lo, hi = self.m._detector_fit_ranges.get(record["detector"], self.m._fit_bounds)
        lo, hi = (int(number), hi) if key == "start" else (lo, int(number))
        self.m._detector_fit_ranges[record["detector"]] = (max(0, lo), max(lo + 1, hi))

    def range_editable(self, record, key):
        return key != "detector" and not self.app.editing_blocked

    def info_text(self) -> str:
        """The Qt Information box: the mixed decay, the fit range, the components and what each result holds."""
        m = self.m
        lo, hi = m._fit_bounds
        lines = ["== Mixed decay ==", f"source: {m.total_label or 'none'}", f"bins: {m._current_n_bins()}   bin width: {m._pattern_bin_width_ns():.6g} ns   micro-time binning: x{m._micro_time_binning}",
                 f"global fit range: {lo}-{hi} bins", f"detectors: {', '.join(m.detectors.selected)}", "", "== Components =="]
        lines += [f"{'[x]' if c.enabled else '[ ]'} {c.name}: {describe(c)}" for c in m.components]
        for entry in m.results():
            md = entry["result"].metadata
            lines += ["", f"== Result: {entry['detector']} ==", f"species: {md.get('n_species', '?')}   filters: {md.get('n_filters', '?')}   bins: {md.get('n_bins', '?')}",
                      f"rejected nuisance: {', '.join(md.get('nuisance_labels', []) or []) or 'none'}"]
        return "\n".join(lines)

    # -- auto-fit parameters ------------------------------------------------------------------------------------ #
    def parameter_columns(self):
        return [
            {"key": "name", "label": "Parameter", "editable": False, "description": "A fitted model parameter."},
            {"key": "value", "label": "Value", "format": "%.6g", "description": "Value the fit found; double click to type another."},
            {"key": "fixed", "label": "Fixed", "width": 52, "description": "Hold this parameter fixed in the next fit."},
            {"key": "link", "label": "Follows", "editable": False, "description": "The live parameter this one follows, if linked."},
        ]

    def parameter_rows(self):
        result = self.m._auto_fit_result
        fit = result.get("fit") if result else None
        parameters = getattr(getattr(fit, "model", None), "parameters_all", {})
        if isinstance(parameters, dict):
            parameters = list(parameters.values())
        rows = []
        for p in parameters or []:
            if getattr(p, "name", "") in {"dt", "start", "stop", "irf_start", "irf_stop"} or not isinstance(getattr(p, "value", None), (int, float)):
                continue
            link = getattr(p, "link", None)
            rows.append({"name": p.name, "value": float(p.value), "fixed": bool(getattr(p, "fixed", False)),
                         "link": getattr(link, "name", "") if link is not None else "", "_parameter": p})
        return rows

    def edit_parameter(self, record, key, value):
        p = record["_parameter"]
        if key == "fixed":
            p.fixed = bool(value)
        elif key == "value" and _number(value) is not None:
            p.value = _number(value)

    def parameter_editable(self, record, key):
        return key in ("value", "fixed") and not self.app.editing_blocked

    def select_parameter(self, record):
        self.app.selected_parameter = None if record is None else record["_parameter"]

    def chi2_line(self) -> str:
        result = self.m._auto_fit_result
        return f"Reduced chi2: {result.get('chi2_reduced', '?')}" if result else "No auto-fit yet."

    # -- actions ---------------------------------------------------------------------------------------------- #
    def load_mixed(self):
        self.app.choose("Mixed decay", self.app.load_total, multiple=True)

    def load_decay(self):
        self.load_mixed()

    def from_correlator(self):
        self.app.from_correlator()

    def compute(self):
        self.app.submit(lambda model: model.compute(), replace=False)

    def unmix(self):
        self.app.submit(lambda model: model.unmix())

    def autofit(self):
        self.app.submit(lambda model: model._auto_fit_components())

    def save_project(self):
        self.app.choose("Save project", lambda paths: self.app.submit(lambda model: model.save_project(paths[0])), mode="save", filters="Project (*.json)", filename="filter_project.json")

    def load_project(self):
        self.app.choose("Load project", lambda paths: self.app.submit(lambda model: model.load_project(paths[0])), filters="Project (*.json)")

    def export_results(self):
        self.app.choose("Export filters", lambda paths: self.app.submit(lambda model: model.export_results(paths[0])), mode="save", filters="Filters (*.json)", filename="filters.json")

    def example(self):
        self.app.submit(lambda model: (model.populate_example(), model.compute()))

    def stop(self):
        self.app.job.stop()

    def guide(self):
        self.app.tour.start()

    def help(self):
        self.app.help.show()

    def add_lifetime(self):
        self.app.new_component("lifetime")

    def add_spectrum(self):
        self.app.new_component("lifetime_spectrum")

    def add_fret(self):
        self.app.new_component("fret_species")

    def add_lifetime_distribution(self):
        self.app.new_component("gaussian_lifetime")

    def add_distance_distribution(self):
        self.app.new_component("gaussian_distance")

    def add_measured(self):
        self.app.choose("Species reference", self.app.add_measured, multiple=True)

    def edit_component(self):
        self.app.edit_selected_component()

    def duplicate_component(self):
        if 0 <= self.app.selected_component < len(self.m.components):
            self.m.add_component(self.m.components[self.app.selected_component].source)

    def remove_component(self):
        i = self.app.selected_component
        if 0 <= i < len(self.m.components):
            self.m.components.pop(i)
            self.app.selected_component = -1

    def browse_irf(self):
        row = self.app.selected_detector_row
        if row is not None:
            self.app.choose("IRF", lambda paths: self.app.set_irf(row["_detector"], row["_role"], paths[0]))

    def link_parameter(self):
        if self.app.selected_parameter is not None:
            self.app.choose_parameter_link(self.app.selected_parameter)

    def unlink_parameter(self):
        if self.app.selected_parameter is not None:
            self.app.selected_parameter.link = None

    def edited(self, *_):
        pass


def _spectrum_names(prefix, count):
    return [(f"{prefix}amp_{i}", f"{prefix}life_{i}") for i in range(count)]


class ComponentPanel:
    """A component definition (the source dict) as attributes, for a form built by :func:`component_spec`."""

    def __init__(self, source: dict, app) -> None:
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "app", app)
        object.__setattr__(self, "dirty", False)

    def _path(self, name):
        for prefix, key, idx in (("amp_", "amplitudes", 1), ("life_", "lifetimes", 1)):
            if name.startswith(prefix):
                return key, int(name[len(prefix):])
        for prefix, key in (("donamp_", "donor_spectrum"), ("donlife_", "donor_spectrum"), ("accamp_", "acceptor_spectrum"), ("acclife_", "acceptor_spectrum")):
            if name.startswith(prefix):
                return (key, 2 * int(name[len(prefix):]) + (0 if "amp" in prefix else 1))
        for prefix, key in (("dmean_", "mean"), ("dsigma_", "sigma"), ("damp_", "amplitude")):
            if name.startswith(prefix):
                return ("distance_rows", (int(name[len(prefix):]), key))
        if name.startswith("xt_"):
            return ("crosstalk", name[3:])
        return None

    def __getattr__(self, name):
        path = self._path(name)
        if path is None:
            return self.source.get(name, "" if name in ("name", "state", "fret_mode", "distance_distribution") else 0)
        key, idx = path
        if key == "crosstalk":
            return self.source.get("crosstalk", {}).get(idx, {"alpha": 0.0, "beta": 1.0, "gamma": 1.0, "delta": 0.0}[idx])
        if key == "distance_rows":
            i, field = idx
            return self.source.get("distance_rows", [])[i].get(field, 0.0)
        return self.source.get(key, [])[idx]

    def __setattr__(self, name, value):
        path = self._path(name)
        if path is None:
            self.source[name] = value
        else:
            key, idx = path
            if key == "crosstalk":
                self.source.setdefault("crosstalk", {})[idx] = float(value)
            elif key == "distance_rows":
                i, field = idx
                self.source["distance_rows"][i][field] = float(value)
            else:
                self.source[key][idx] = float(value)
        object.__setattr__(self, "dirty", True)
        self.source.pop("patterns_by_detector", None)  # the cached per-detector patterns describe the previous definition

    def edited(self, *_):
        pass

    def enabled(self, name):
        return True

    def add_spectrum_row(self):
        self.source.setdefault("amplitudes", []).append(1.0)
        self.source.setdefault("lifetimes", []).append(2.0)
        self.source.pop("patterns_by_detector", None)
        self.app.refresh_component_spec()

    def add_distance_row(self):
        self.source.setdefault("distance_rows", []).append({"mean": 50.0, "sigma": 5.0, "amplitude": 1.0})
        self.source.pop("patterns_by_detector", None)
        self.app.refresh_component_spec()

    def apply(self):
        self.app.commit_component()

    def cancel(self):
        self.app.editor = None


def _val(attr, label, kind, tip, **kw):
    d = {"type": "value", "attr": attr, "label": label, "kind": kind, "call": "edited", "description": tip}
    if kind == "float":
        d.setdefault("decimals", 4)
        d.setdefault("minimum", -1e9)
        d["maximum"] = 1e9
    else:
        d.setdefault("minimum", 0)
        d["maximum"] = 10 ** 9
    d.update(kw)
    return d


def component_spec(source: dict) -> dict:
    """The form of a component definition: the fields of its model, as the Qt component dialog offers them."""
    s = [_val("name", "Component name", "str", "Name shown in the filter legends and the component list."),
         _val("bin_width", "Bin width (ns)", "float", "Time represented by each TAC bin in nanoseconds."),
         _val("start_bin", "Start bin", "int", "Shift the synthetic decay by this many TAC bins."),
         _val("period_ns", "Laser period (ns)", "float", "Periodic convolution period; zero disables periodic wrapping.")]
    model = source.get("model")
    rows = []
    if model == "lifetime":
        s.append(_val("lifetime", "Lifetime (ns)", "float", "Exponential fluorescence lifetime in nanoseconds."))
    if model == "lifetime_spectrum":
        for i in range(min(len(source.get("amplitudes", [])), len(source.get("lifetimes", [])))):
            s.append(_val(f"amp_{i}", f"Amplitude {i + 1}", "float", "Pre-exponential amplitude of this lifetime component."))
            s.append(_val(f"life_{i}", f"Lifetime {i + 1} (ns)", "float", "Lifetime of this spectrum component in nanoseconds."))
        rows.append({"action": "add_spectrum_row", "label": "Add spectrum row", "description": "Add another amplitude and lifetime pair to the spectrum."})
    if model in ("gaussian_lifetime", "gaussian_distance"):
        fields = ((("mean_lifetime", "Mean lifetime (ns)"), ("sigma_lifetime", "Lifetime width (ns)")) if model == "gaussian_lifetime" else
                  (("donor_lifetime", "Donor lifetime (ns)"), ("forster_radius", "Foerster radius (A)"), ("mean_distance", "Mean distance (A)"), ("sigma_distance", "Distance width (A)")))
        for key, label in fields:
            s.append(_val(key, label, "float", "Mean or standard deviation of the sampled species distribution."))
        s.append(_val("n_samples", "Distribution samples", "int", "Number of quadrature samples resolving the distribution."))
    if model == "fret_species":
        s.append({"type": "choice", "attr": "state", "label": "State", "options": ["da", "d_only", "a_only"], "labels": ["Donor + acceptor", "Donor only", "Acceptor only"], "call": "edited", "description": "The fluorophore labeling state of this species."})
        s.append({"type": "choice", "attr": "fret_mode", "label": "FRET model", "options": ["efficiency", "distance"], "call": "edited", "description": "Specify the transfer efficiency or a distance (distribution)."})
        for key, label in (("transfer_efficiency", "Transfer efficiency"), ("distance", "Distance (A)"), ("forster_radius", "Foerster radius (A)"), ("kappa2", "kappa squared"), ("x_donly", "Donor-only fraction")):
            s.append(_val(key, label, "float", "Species FRET parameter used in the coupled detector decay generation."))
        for prefix, label, key in (("don", "Donor", "donor_spectrum"), ("acc", "Acceptor", "acceptor_spectrum")):
            for i in range(len(source.get(key, [])) // 2):
                s.append(_val(f"{prefix}amp_{i}", f"{label} amplitude {i + 1}", "float", "Pre-exponential fluorescence amplitude."))
                s.append(_val(f"{prefix}life_{i}", f"{label} lifetime {i + 1} (ns)", "float", "Fluorescence lifetime in nanoseconds."))
        if source.get("fret_mode") == "distance":
            for i in range(len(source.get("distance_rows", []))):
                for key, label in (("dmean", "Distance mean (A)"), ("dsigma", "Distance width (A)"), ("damp", "Distance amplitude")):
                    s.append(_val(f"{key}_{i}", f"{label} {i + 1}", "float", "Population weight and Gaussian distance distribution parameters."))
            rows.append({"action": "add_distance_row", "label": "Add distance population", "description": "Add a weighted distance-distribution population."})
            s.append({"type": "choice", "attr": "distance_distribution", "label": "Distance distribution", "options": ["gaussian", "gaussian_3d"], "call": "edited", "description": "A scalar Gaussian or the physical radial distribution of two 3-D Gaussian dye positions."})
        for key in ("alpha", "beta", "gamma", "delta"):
            s.append(_val(f"xt_{key}", key, "float", "Species leakage, excitation or detection correction factor."))
    s.append({"type": "toggle", "attr": "shot_noise", "label": "Simulate shot noise", "call": "edited", "description": "Sample the synthetic pattern using photon-count Poisson statistics."})
    if source.get("shot_noise"):
        s.append(_val("photon_count", "Pattern photons", "int", "Number of photons in the simulated reference pattern."))
        s.append(_val("noise_seed", "Random seed", "int", "Seed for reproducible pattern shot-noise generation."))
    buttons = rows + [{"action": "apply", "label": "Apply", "description": "Validate the definition and compute the filters."},
                      {"action": "cancel", "label": "Cancel", "description": "Discard the edit."}]
    return {"sections": [{"type": "panel", "title": "", "description": "The component definition.", "sections": s},
                         {"type": "button_row", "description": "Apply or discard the definition.", "buttons": buttons}]}
