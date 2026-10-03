"""Native mixture FRET-line generator using the Qt-free backend API."""

import csv
from pathlib import Path

from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.core.registry.parameter_groups import (
    get_registered_parameter_group,
    iter_registered_parameter_groups,
    register_parameter_group,
    unregister_parameter_group,
)
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.calculator.export import install_csv_export
from chisurf.plugins.calculator.inputs import bounded_float, bounded_int
from chisurf.plugins.calculator.native_form import parameter_field, plain

from ..backend.client import FRETLineClient
from ..core.algorithms import (
    _build_component,
    _parameters_of,
    compute_fret_line_for_models,
    sweep_targets_for_models,
)


class FRETLineApp(ImApp):
    def __init__(self, push_callback=None):
        self.client = FRETLineClient()
        self.model_names = self.client.list_models()
        self.components = []
        self.weights = []
        self.reference_index = 0
        self.component_index = 0
        self.model_index = 0
        self.show_all_parameters = False
        self.sweep_filter = ""
        self.sweep_index = 0
        self.minimum = 20.0
        self.maximum = 100.0
        self.n_points = 100
        self.log_scale = False
        self.tau_d0 = 4.0
        self.lines = []
        self.error = ""
        self.input_dialog = None
        self.input_window = None
        self.input_target = None
        self.input_selection = {}
        self.loaded_curves = []
        self.push_callback = push_callback
        self.help_window = EmTkHelpWindow(
            title="FRET line — Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        self.item_rects = {}
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self,
            wait_for_controls=True,
        )
        self.add_component()
        targets = self.sweep_targets()
        self.sweep_index = next(
            (
                i
                for i, target in enumerate(targets)
                if target.get("name", "").startswith("distance.mean")
            ),
            0,
        )

        self.docks = DockManager(
            Split(
                "h",
                0.30,
                Region("controls"),
                Split(
                    "h",
                    0.50,
                    Region("editor"),
                    Split("v", 0.5, Region("efficiency"), Region("lifetime")),
                ),
            )
        )
        self.docks.add_window(
            "controls",
            "Mixture, sweep and FRET lines",
            self.controls,
            dock="controls",
            closable=False,
        )
        self.docks.add_window(
            "editor", "Live model editor", self.editor, dock="editor", closable=False
        )
        self.docks.add_window(
            "efficiency",
            "FRET line",
            lambda box: self.plot("e_fret", "E FRET"),
            dock="efficiency",
            closable=False,
        )
        self.docks.add_window(
            "lifetime",
            "τ_X(τ_F)",
            lambda box: self.plot("tau_x", "τ_X [ns]"),
            dock="lifetime",
            closable=False,
        )
        super().__init__(self.render, continuous=False)
        self.export = install_csv_export(self, "fret_lines.csv", self.write_csv)

    def add_component(self):
        name = self.model_names[self.model_index]
        model = _build_component(name)
        self.components.append(dict(model_name=name, n_components=1, model=model))
        self.weights.append(1.0)
        self.component_index = len(self.components) - 1
        self.sync_registry()

    def sync_registry(self):
        prefix = f"native_fret_line_{id(self)}_c"
        previous = getattr(self, "_registered", set())
        current = {prefix + str(i) for i in range(len(self.components))}
        for owner in previous - current:
            unregister_parameter_group(owner)
        for i, component in enumerate(self.components):
            owner = prefix + str(i)
            if (
                owner not in previous
                or get_registered_parameter_group(owner) is not component["model"]
            ):
                register_parameter_group(
                    component["model"],
                    owner_id=owner,
                    label=f"FRET Line C{i}: {component['model_name']}",
                )
        self._registered = current

    def close(self):
        for owner in getattr(self, "_registered", set()):
            unregister_parameter_group(owner)
        self._registered = set()

    @staticmethod
    def spectrum_of(model):
        values = {}
        for parameter in getattr(model, "parameters_all", []):
            key = getattr(parameter, "canonical_id", "")
            pieces = key.split(".")
            if (
                len(pieces) == 3
                and pieces[0] in ("donor", "lifetime")
                and pieces[1] in ("amplitude", "tau")
            ):
                values[(pieces[1], int(pieces[2]))] = parameter.value
        return values

    def donor_references(self):
        import chisurf

        sources = [(label, group) for _, label, group in iter_registered_parameter_groups()]
        for fit in getattr(chisurf, "fits", []):
            models = getattr(fit, "models", None) or [getattr(fit, "model", None)]
            sources.extend(
                (getattr(model, "name", "Fit donor"), model)
                for model in models
                if model is not None
            )
        own = {id(c["model"]) for c in self.components}
        return [
            (label, self.spectrum_of(model))
            for label, model in sources
            if id(model) not in own and self.spectrum_of(model)
        ]

    def apply_donor_reference(self, spectrum):
        model = self.components[self.component_index]["model"]
        group_name = "donor" if "donor" in model._groups else "lifetime"
        count = 1 + max(i for _, i in spectrum)
        from chisurf.core.fluorescence.fret.fret_line import find_parameter

        for _ in range(40):
            current = len(
                {
                    int(p.canonical_id.split(".")[-1])
                    for p in model._groups[group_name].component_parameters()
                }
            )
            if current == count:
                break
            if not model.change_components(group_name, 1 if current < count else -1):
                raise ValueError("This model cannot represent the reference spectrum.")
        for (kind, index), value in spectrum.items():
            find_parameter(model, f"{group_name}.{kind}.{index}").value = value

    def sweep_targets(self):
        targets = sweep_targets_for_models(
            [c["model"] for c in self.components],
            [c["model_name"] for c in self.components],
            relevant_only=not self.show_all_parameters,
        )
        signature = [
            (target.get("kind"), target.get("component"), target.get("name")) for target in targets
        ]
        previous = getattr(self, "_sweep_signature", [])
        key = getattr(self, "_sweep_key", None)
        if signature != previous and key in signature:
            self.sweep_index = signature.index(key)
        self.sweep_index = min(self.sweep_index, max(0, len(signature) - 1))
        self._sweep_signature = signature
        self._sweep_key = signature[self.sweep_index] if signature else None
        return targets

    def compute(self):
        targets = self.sweep_targets()
        if not targets:
            raise ValueError("No sweepable parameter is available.")
        sweep = targets[min(self.sweep_index, len(targets) - 1)]
        snapshots = [
            (parameter, parameter.value)
            for component in self.components
            for parameter in _parameters_of(component["model"])
        ]
        try:
            response = compute_fret_line_for_models(
                [c["model"] for c in self.components],
                sweep,
                self.minimum,
                self.maximum,
                self.n_points,
                self.weights,
                self.tau_d0 or None,
                self.log_scale,
            )
        finally:
            for parameter, value in snapshots:
                parameter.value = value
        if not response.get("ok"):
            raise ValueError(response.get("error", "FRET-line computation failed"))
        line = dict(
            name=f"Line {len(self.lines) + 1}",
            result=response["result"],
            sweep_label=sweep["label"],
            visible=True,
            log=self.log_scale,
            components="; ".join(
                f"{c['model_name']}(w={w:g})" for c, w in zip(self.components, self.weights)
            ),
        )
        self.lines.append(line)
        return line

    def write_csv(self, path):
        if not self.lines:
            raise ValueError("Add a FRET line before exporting.")
        with Path(path).open("w", newline="") as stream:
            stream.write(f"# {len(self.lines)} FRET line(s)\n")
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "line",
                    "sweep",
                    "log",
                    "components",
                    "parameter",
                    "tau_F_ns",
                    "tau_X_ns",
                    "E_FRET",
                ]
            )
            for line in self.lines:
                result = line["result"]
                for row in zip(
                    result["parameter_values"], result["tau_f"], result["tau_x"], result["e_fret"]
                ):
                    writer.writerow(
                        [line["name"], line["sweep_label"], line["log"], line["components"], *row]
                    )

    def controls(self, box):
        im.begin_disabled(self.input_dialog is not None)
        _, self.model_index = im.combo("New component model", self.model_index, self.model_names)
        self.item_rects["Components"] = im.get_item_rect()
        im.set_item_tooltip(
            "Choose Gaussian, worm-like-chain, discrete-distance or lifetime model for the next mixture component."
        )
        if im.button("Add component"):
            self.add_component()
        self.item_rects["+ Add"] = im.get_item_rect()
        im.set_item_tooltip("Append a new independently editable model to the mixture.")
        im.same_line()
        im.begin_disabled(len(self.components) <= 1)
        if im.button("Remove component"):
            self.components.pop(self.component_index)
            self.weights.pop(self.component_index)
            self.component_index = min(self.component_index, len(self.components) - 1)
            self.sync_registry()
        im.set_item_tooltip("Remove the selected component; retain at least one component.")
        im.end_disabled()
        _, self.component_index = im.combo(
            "Selected component",
            self.component_index,
            [f"C{i + 1}: {c['model_name']}" for i, c in enumerate(self.components)],
        )
        if im.is_item_clicked():
            self.tour.notify_used("Components")
        im.set_item_tooltip("Select the mixture component whose model parameters are edited below.")
        _, self.weights[self.component_index] = bounded_float(
            "Mixture weight", self.weights[self.component_index], minimum=0.0, maximum=1e6, step=0.1
        )
        im.set_item_tooltip(
            "Relative intensity weight; the mixture calculation normalizes all component weights."
        )
        targets = self.sweep_targets()
        self.sweep_index = min(self.sweep_index, max(0, len(targets) - 1))
        changed, self.show_all_parameters = im.checkbox("All parameters", self.show_all_parameters)
        if changed:
            targets = self.sweep_targets()
        im.set_item_tooltip(
            "Include instrument, anisotropy, timing, background and donor-only nuisance parameters in the sweep catalog."
        )
        _, self.sweep_filter = im.input_text("Filter sweep targets", self.sweep_filter)
        im.set_item_tooltip("Search model parameter names and mixing fractions by substring.")
        matches = [
            (i, target)
            for i, target in enumerate(targets)
            if self.sweep_filter.casefold() in target["label"].casefold()
        ]
        if matches:
            current = next(
                (i for i, (original, _) in enumerate(matches) if original == self.sweep_index), 0
            )
            changed, index = im.combo(
                "Sweep target", current, [target["label"] for _, target in matches]
            )
            im.set_item_tooltip(
                "Sweep a model parameter or mixing fraction while retaining the rest of the mixture."
            )
            if changed:
                self.sweep_index = matches[index][0]
        self.item_rects["Sweep"] = im.get_item_rect()
        if im.is_item_clicked():
            self.tour.notify_used("Sweep")
        _, self.minimum = im.input_float("Minimum", self.minimum, step=1.0)
        im.set_item_tooltip("First sweep value; must be positive for logarithmic spacing.")
        _, self.maximum = im.input_float("Maximum", self.maximum, step=1.0)
        im.set_item_tooltip("Last sweep value.")
        _, self.n_points = bounded_int("Points", self.n_points, minimum=2, maximum=100000)
        im.set_item_tooltip("Number of evaluated sweep points.")
        _, self.log_scale = im.checkbox("Logarithmic spacing", self.log_scale)
        im.set_item_tooltip("Use geometric spacing between positive sweep limits.")
        _, self.tau_d0 = bounded_float(
            "Donor τ₀ [ns]", self.tau_d0, minimum=0.0, maximum=1e6, step=0.1
        )
        im.set_item_tooltip(
            "Donor-only lifetime for efficiency; zero uses the component model lifetime."
        )
        if im.button("Add FRET line"):
            try:
                self.compute()
                self.tour.notify_used("Add FRET line")
            except Exception as exc:
                self.error = str(exc)
        self.item_rects["Add FRET line"] = im.get_item_rect()
        im.set_item_tooltip(
            "Compute and append a snapshot of this mixture and sweep; preserve previously computed lines."
        )
        if im.button("Save CSV"):
            self.export()
        im.set_item_tooltip(
            "Export every computed line with sweep values, lifetimes and efficiency."
        )
        im.begin_disabled(self.push_callback is None)
        if im.button("Push to ndX"):
            self.push_callback(self.lines)
        im.set_item_tooltip(
            "Send computed lines to the connected native ndX overlay panel; available when the host supplies an overlay connection."
        )
        im.end_disabled()
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain static, dynamic, WLC and mixture FRET lines.")
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through static and mixture FRET-line generation.")
        for i, line in enumerate(list(self.lines)):
            im.push_id(i)
            _, line["visible"] = im.checkbox(line["name"], line["visible"])
            im.set_item_tooltip(f"Show or hide {line['name']}: {line['sweep_label']}.")
            im.same_line()
            if im.button("Remove"):
                self.lines.remove(line)
            im.set_item_tooltip("Delete this computed line.")
            im.pop_id()
        if im.button("Show all"):
            for line in self.lines:
                line["visible"] = True
        im.set_item_tooltip("Show all computed lines on both plots.")
        im.same_line()
        if im.button("Hide all"):
            for line in self.lines:
                line["visible"] = False
        im.set_item_tooltip("Hide all computed lines while retaining the collection.")
        if im.button("Clear lines"):
            self.lines.clear()
        im.set_item_tooltip("Remove every computed line from this collection.")
        if self.error:
            im.text_wrapped(self.error)
        im.end_disabled()

    def input_curves(self):
        import chisurf

        curves = list(self.loaded_curves)
        for group in getattr(chisurf, "imported_datasets", []):
            if not isinstance(group, (list, tuple)) and hasattr(group, "x") and hasattr(group, "y"):
                curves.append(group)
            else:
                try:
                    curves.extend(
                        curve for curve in group if hasattr(curve, "x") and hasattr(curve, "y")
                    )
                except TypeError:
                    pass
        return curves

    def bind_input(self, slot, curve, model=None):
        import numpy as np

        x, y = np.asarray(curve.x, dtype=float), np.asarray(curve.y, dtype=float)
        if (
            x.ndim != 1
            or y.ndim != 1
            or not len(x)
            or len(x) != len(y)
            or not np.isfinite(x).all()
            or not np.isfinite(y).all()
        ):
            raise ValueError("Measured input curves need matching finite x/y arrays.")
        model = self.components[self.component_index]["model"] if model is None else model
        model.set_dataset(slot, curve)
        if slot == "response" and "generated_response" in model.scalar_names():
            model.set_scalar("generated_response", 0.0)

    def unload_input(self, slot):
        model = self.components[self.component_index]["model"]
        model.unset_dataset(slot)
        if slot == "response" and "generated_response" in model.scalar_names():
            model.set_scalar("generated_response", 1.0)

    def choose_input(self, slot):
        self.input_target = (self.components[self.component_index]["model"], slot)
        self.input_dialog = FileDialog(
            "Load " + slot,
            mode="open",
            filters="Curves (*.csv *.txt *.dat *.tsv *.pto);;All files (*)",
        )
        self.input_window = DialogWindow("Load " + slot, size=(700, 540), key="fret_input")
        self.input_window.show()

    def draw_inputs(self, model):
        slots = model.dataset_slots()
        expanded = im.collapsing_header("Input curves")
        im.set_item_tooltip(
            "Select or unload measured IRF, background and correction curves from experiment data or curve files."
        )
        if not expanded:
            return
        curves = self.input_curves()
        for slot in slots:
            im.push_id(slot)
            source = getattr(model.datasets, slot, None)
            im.text_wrapped(
                slot
                + ": "
                + (
                    getattr(source, "name", "Measured curve")
                    if source is not None
                    else "not loaded"
                )
            )
            if curves:
                index = self.input_selection.get(slot, 0)
                _, index = im.combo(
                    "Reference curve",
                    min(index, len(curves) - 1),
                    [
                        getattr(curve, "name", "Curve " + str(i + 1))
                        for i, curve in enumerate(curves)
                    ],
                )
                self.input_selection[slot] = index
                im.set_item_tooltip(
                    "Select an already imported experimental curve for this model input."
                )
                if im.button("Use selected curve"):
                    self.bind_input(slot, curves[index])
                im.set_item_tooltip("Bind this experimental curve to the selected model input.")
            if im.button("Load curve file"):
                self.choose_input(slot)
            im.set_item_tooltip("Read a measured curve with the existing ChiSurf DataCurve loader.")
            im.same_line()
            im.begin_disabled(source is None)
            if im.button("Unload curve"):
                self.unload_input(slot)
            im.set_item_tooltip(
                "Remove this measured input; unloading an IRF restores the modeled response."
            )
            im.end_disabled()
            im.pop_id()

    def editor(self, box):
        im.begin_disabled(self.input_dialog is not None)
        c = self.components[self.component_index]
        index = self.model_names.index(c["model_name"])
        changed, index = im.combo("Component model", index, self.model_names)
        im.set_item_tooltip(
            "Change the selected component model; preserve its mixture weight and reset its model parameters to the new defaults."
        )
        if changed:
            c["model_name"] = self.model_names[index]
            c["model"] = _build_component(c["model_name"])
            self.sync_registry()
        im.text_wrapped(c["model_name"])
        model = c["model"]
        self.draw_inputs(model)
        references = self.donor_references()
        if not references:
            im.begin_disabled()
            im.combo("Donor reference", 0, ["No live donor references"])
            im.set_item_tooltip(
                "Open a donor-only fit or register a lifetime working model to populate the reference catalog."
            )
            im.end_disabled()
        if references:
            self.reference_index = min(self.reference_index, len(references) - 1)
            _, self.reference_index = im.combo(
                "Donor reference", self.reference_index, [r[0] for r in references]
            )
            im.set_item_tooltip(
                "Use a donor/lifetime spectrum from a live fit or registered working model as the donor-only reference."
            )
            if im.button("Apply donor reference"):
                try:
                    self.apply_donor_reference(references[self.reference_index][1])
                except Exception as exc:
                    self.error = str(exc)
            im.set_item_tooltip(
                "Copy the reference amplitudes and lifetimes into this component; the source fit stays unchanged."
            )
        for group_name, group in model._groups.items():
            rows = group.component_parameters()
            if rows:
                im.push_id(group_name)
                im.text_unformatted(group_name)
                if im.button("Add subcomponent"):
                    model.change_components(group_name, 1)
                im.set_item_tooltip(
                    f"Add an independent {group_name} component while preserving other parameter groups."
                )
                im.same_line()
                if im.button("Remove subcomponent"):
                    model.remove_component(group_name)
                im.set_item_tooltip(f"Remove the last {group_name} component; keep at least one.")
                im.pop_id()
        if im.collapsing_header("Model settings"):
            im.set_item_tooltip(
                "Edit the scalar settings that define model topology and numerical evaluation."
            )
            for name in model.scalar_names():
                value = model.get_scalar(name)
                if value is None:
                    continue
                changed, new = im.input_float(name, float(value), step=1.0)
                im.set_item_tooltip(f"{name}: scalar configuration of the BFF model.")
                if changed:
                    model.set_scalar(name, new)
        if im.collapsing_header("Model parameters", im.TreeNodeFlags.DEFAULT_OPEN):
            self.item_rects["Editor"] = im.get_item_rect()
            im.set_item_tooltip(
                "Edit values, fixed states and bounds of every canonical model parameter."
            )
            for parameter in _parameters_of(model):
                parameter_field(parameter)
        im.end_disabled()

    def plot(self, key, label):
        if implot.begin_plot(label, (-1, -1)):
            implot.setup_axes("τ_F [ns]", label)
            implot.setup_legend()
            for line in self.lines:
                if line["visible"]:
                    implot.plot_line(line["name"], line["result"]["tau_f"], line["result"][key])
            implot.end_plot()
            im.set_item_tooltip(
                "Computed mixture FRET lines; use the legend or collection checkboxes to compare and hide snapshots."
            )

    def render(self):
        vp = im.get_main_viewport()
        self.docks.draw((0, 0, *vp.size))
        if self.help_window.open:
            self.help_window.draw((0, 0, *vp.size))
        if self.tour.active:
            self.tour.draw(*vp.size)
        if self.input_dialog:
            pressed = self.input_window.begin((0, 0, *vp.size))
            result = self.input_dialog.draw()
            if result:
                try:
                    from chisurf.core.data import DataCurve

                    curve = DataCurve(filename=str(result[0]))
                    model, slot = self.input_target
                    self.bind_input(slot, curve, model=model)
                    self.loaded_curves.append(curve)
                    self.input_dialog = None
                except Exception as exc:
                    self.error = str(exc)
            elif result is False or pressed == "close":
                self.input_dialog = None
            self.input_window.end()


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return FRETLineApp(push_callback=kwargs.get("push_callback"))
