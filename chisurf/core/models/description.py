"""A model BFF describes in data, seen from ChiSurf.

BFF owns the model: its parameters, its topologies, the measurements it is
fitted against, its objective and its search, all built once from a family
description (``IMP.bff`` ``data/model_search/<family>.json``). This module owns
none of that. It is a *view* -- the parameters shown here are the model's own
ports, the curve drawn is the model's own output, a fit writes the model's own
ports in C++, and a model search leaves the model standing at its winner. There
is nothing to copy back because nothing was copied out.

No family is named here. What to call a parameter, how to group them, which
measurement is the fit's own and what a scalar defaults to is the description's
``presentation`` block and the parameters' ``group`` keys, read as data. A new
family is a new description file, not a new class.
"""

from __future__ import annotations

import json

import numpy as np

import chisurf.core.fitting.parameter
from chisurf import typing
from chisurf.core.fitting import factorgraph
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.models.model import ModelCurve

try:  # pragma: no cover - exercised wherever BFF is installed
    import IMP.bff as _bff
except ImportError:  # pragma: no cover
    _bff = None


class DescriptionParameter(FittingParameter):
    """One canonical parameter of a BFF model, read and written in place.

    The value is the port's, always -- never a copy cached for a run, because
    the optimiser and the search write the port from C++ and a view that did
    not see those writes would show the model as it was. Fixing and freeing
    are the model's locks and releases, so they hold for whichever topology is
    current and for whichever one a search reaches.
    """

    def __init__(self, view: "DescriptionModel", canonical_id: str, port, **kwargs):
        self.__dict__["_view"] = None
        super().__init__(port=port, name=kwargs.pop("name", canonical_id), **kwargs)
        self.canonical_id = canonical_id
        self.__dict__["_view"] = view

    @property
    def value(self) -> float:
        # A port that follows another (a link across fits) reads as a
        # one-element vector.
        pv = self._port.value
        return pv if type(pv) is float else float(np.atleast_1d(pv)[0])

    @value.setter
    def value(self, value: float):
        # A write to a fixed port is ignored by the port, and a user typing a
        # number into a fixed parameter means that number.
        was = self._port.fixed
        self._port.fixed = False
        self._port.value = float(value)
        self._port.fixed = was

    @property
    def fixed(self) -> bool:
        return bool(self._port.fixed)

    @fixed.setter
    def fixed(self, v: bool):
        view = self.__dict__.get("_view")
        if view is None:
            # Construction: the model, not the constructor, decides.
            return
        problem = view.problem
        if problem is None:
            return
        if bool(v):
            problem.set_parameter_locked(self.canonical_id, True)
        else:
            problem.set_parameter_locked(self.canonical_id, False)
            if self._port.fixed:
                problem.set_parameter_released(self.canonical_id, True)
        factorgraph.bump_structure_version()


class DescriptionGroup(FittingParameterGroup):
    """The parameters of one ``group`` a description declares."""

    def __init__(self, view: "DescriptionModel", key: str, parameters, **kwargs):
        super().__init__(parameters=list(parameters), **kwargs)
        self.name = kwargs.get("name", key)
        self.__dict__["_view"] = view
        self.key = key

    def visible_parameters(self):
        """The group's parameters the current topology reads, in registry order."""
        used = set(self._view.structure_parameter_ids())
        return [p for p in self.parameters_all if p.canonical_id in used]


class _Scalars:
    """``model.scalars.<name>``: a description's scalars as attributes.

    What lets a generic ``value`` or ``toggle`` section bind to a scalar by a
    dotted ``attr`` without the view knowing any scalar's name.
    """

    def __init__(self, view: "DescriptionModel"):
        object.__setattr__(self, "_view", view)

    def __getattr__(self, name: str):
        view = object.__getattribute__(self, "_view")
        if name not in view.scalar_names():
            raise AttributeError(name)
        return view.get_scalar(name)

    def __setattr__(self, name: str, value):
        view = object.__getattribute__(self, "_view")
        view.set_scalar(name, float(value))
        view.update()


def _measurement(coordinates, y, ey=None, mask=None):
    """A ChiSurf measurement as a bff one, every coordinate under its own name."""
    dataset = _bff.FitDataset()
    dataset.set_values_array(np.ascontiguousarray(np.asarray(y, dtype=float)))
    if coordinates is not None and not isinstance(coordinates, dict):
        coordinates = {"x": coordinates}
    for k, (name, values) in enumerate((coordinates or {}).items()):
        values = np.asarray(values, dtype=float).ravel()
        if values.size == len(y):
            dataset.set_coordinate_array(k, str(name), np.ascontiguousarray(values))
    if ey is not None:
        dataset.set_noise_family(_bff.FIT_NOISE_FAMILY_STORED)
        dataset.set_stored_variance_array(
            np.ascontiguousarray(np.asarray(ey, dtype=float) ** 2))
    if mask is not None:
        dataset.set_mask_array(np.ascontiguousarray(np.asarray(mask, dtype=float)))
    return dataset


def _coordinates_of(curve) -> typing.Optional[dict]:
    coordinates = getattr(curve, "coordinates", None)
    if isinstance(coordinates, dict) and coordinates:
        return coordinates
    x = getattr(curve, "x", None)
    return None if x is None else {"x": x}


def _read_catalogue(path) -> dict:
    """A ChiSurf equation catalogue (YAML or JSON) as plain data."""
    import pathlib
    import yaml

    text = pathlib.Path(path).read_text()
    data = yaml.safe_load(text) or {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict) and v.get("equation")}


class DescriptionModel(ModelCurve):
    """A ChiSurf view on one BFF model family.

    Subclassed per family by :func:`for_family`, which is what the experiment
    configuration names by family -- ``chisurf.core.models.description.tcspc_lifetime``.
    """

    family: str = ""
    #: A ChiSurf equation catalogue this model is built from, if any.
    catalogue_path = None
    name = "BFF model"

    @property
    def _document(self) -> dict:
        """The description as BFF reads it now -- a catalogue's structures appear
        once the measurement that decides which variables are axes is bound."""
        return json.loads(self._spec.get_description_json())

    # --- equations ---------------------------------------------------------------
    @property
    def catalogue(self) -> dict:
        return dict(self._catalogue)

    @property
    def catalogue_names(self) -> typing.List[str]:
        return list(self._catalogue)

    @property
    def model_name(self) -> str:
        """The selected equation; before the model is built, the first one."""
        problem = self.__dict__.get("_spec") and self._spec.get_model_is_current() and self.problem
        if problem:
            return str(problem.get_active_structure())
        return self.__dict__.get("_selected_equation") or next(iter(self._catalogue), "")

    @model_name.setter
    def model_name(self, key: str) -> None:
        key = str(key)
        if key not in self._catalogue:
            raise KeyError(f"no equation named {key!r}")
        self.__dict__["_selected_equation"] = key
        if self.problem is not None:
            self.structure = key

    @property
    def func(self) -> str:
        """The selected equation's text."""
        return str((self._catalogue.get(self.model_name) or {}).get("equation", ""))

    @func.setter
    def func(self, text: str) -> None:
        """Typing an equation makes it the ``custom`` entry and selects it."""
        self.set_equation(text)
        self.model_name = "custom"

    def set_equation(self, text: str, key: str = "custom") -> None:
        """Add or replace one equation; parameters it shares by name keep their ports."""
        if not self._catalogue and not self._document.get("equations"):
            raise TypeError(f"{self.family!r} is not built from equations")
        entry = dict(self._catalogue.get(key, {}))
        entry["equation"] = str(text)
        self._catalogue[key] = entry
        self._spec.set_equations(json.dumps(self._catalogue))
        self._forget_discovery()

    def __init__(self, fit, family: typing.Optional[str] = None, **kwargs):
        if _bff is None:
            raise ImportError("a BFF-described model needs IMP.bff")
        catalogue_path = type(self).catalogue_path
        family = family or type(self).family or ("equations" if catalogue_path else "")
        if not family:
            raise ValueError("a DescriptionModel needs a family description or a catalogue")
        self.__dict__["_spec"] = _bff.ModelSearchSpec.from_name(family)
        self.__dict__["_catalogue"] = {}
        if catalogue_path:
            self.__dict__["_catalogue"] = _read_catalogue(catalogue_path)
            self._spec.set_equations(json.dumps(self._catalogue))
        self.__dict__["_bound_primary"] = None
        super().__init__(fit, **kwargs)
        self.family = family
        self.name = type(self).__dict__.get("name") or self._document.get("title", family)
        self.missing: typing.List[str] = []
        self._sources: typing.Dict[str, typing.Any] = {}
        self._scalars: typing.Dict[str, float] = {}
        self._groups: typing.Dict[str, DescriptionGroup] = {}

    # --- what the description says ------------------------------------------
    @property
    def presentation(self) -> dict:
        return self._document.get("presentation", {})

    @property
    def primary_dataset(self) -> str:
        for slot, info in self.presentation.get("datasets", {}).items():
            if info.get("primary"):
                return slot
        return list(self._spec.get_dataset_names())[0]

    def dataset_slots(self) -> typing.List[str]:
        """Every measurement slot, required then optional, primary excluded."""
        slots = list(self._spec.get_dataset_names())
        slots += list(self._document.get("optional_datasets", []))
        return [s for s in slots if s != self.primary_dataset]

    def scalar_names(self) -> typing.List[str]:
        names = list(self._spec.get_scalar_names())
        names += [n for n in self._document.get("optional_scalars", {}) if n not in names]
        return names

    # --- the model ------------------------------------------------------------
    def set_dataset(self, slot: str, curve) -> None:
        """Bind a curve (anything with ``x`` and ``y``) to a measurement slot."""
        if slot not in self.dataset_slots():
            raise KeyError(f"{self.family!r} has no measurement {slot!r}")
        self._sources[slot] = curve
        self._spec.set_dataset(slot, _measurement(_coordinates_of(curve), curve.y))
        self._forget_discovery()

    def unset_dataset(self, slot: str) -> None:
        """Forget a bound curve. The model rebuilds without it, or not at all."""
        self._sources.pop(slot, None)
        self._spec.unset_dataset(slot)
        self._forget_discovery()

    def set_scalar(self, name: str, value: float) -> None:
        if name not in self.scalar_names():
            raise KeyError(f"{self.family!r} has no value {name!r}")
        self._scalars[name] = float(value)
        self._spec.set_scalar(name, float(value))
        self._forget_discovery()

    def get_scalar(self, name: str) -> typing.Optional[float]:
        if name in self._scalars:
            return self._scalars[name]
        default = self.presentation.get("scalars", {}).get(name, {}).get("default")
        if default is None:
            default = self._document.get("optional_scalars", {}).get(name)
        if default is None:
            return None
        try:
            return float(default) if not isinstance(default, str) else float(self._spec.evaluate(default))
        except Exception:
            return None

    def _forget_discovery(self) -> None:
        """What the model consists of may have changed; rediscover on next read."""
        self.__dict__["_parameters"] = None

    def _bind_primary(self) -> None:
        fit = self.fit
        data = getattr(fit, "data", None)
        y = getattr(data, "y", None)
        if y is None or len(y) == 0:
            return
        ey = getattr(data, "ey", None)
        x = _coordinates_of(data)
        window = np.zeros(len(y))
        xmin = int(getattr(fit, "xmin", 0) or 0)
        xmax = getattr(fit, "xmax", None)
        xmax = len(y) if xmax is None else int(xmax)
        window[max(0, xmin):max(0, min(len(y), xmax))] = 1.0
        user_mask = getattr(fit, "mask", None)
        if user_mask is not None and np.size(user_mask) == len(y):
            window = window * (np.asarray(user_mask, dtype=float).ravel() != 0)
        # By content: a curve's arrays are not guaranteed to be the same objects
        # from one read to the next, and rebinding rebuilds the model's graphs.
        import hashlib
        digest = hashlib.blake2b(digest_size=16)
        for part in (y, ey, window, *((x or {}).values())):
            if part is not None:
                digest.update(np.ascontiguousarray(np.asarray(part, dtype=float)).tobytes())
        key = digest.hexdigest()
        if self._bound_primary == key:
            return
        self._spec.set_dataset(self.primary_dataset, _measurement(x, y, ey, window))
        self.__dict__["_bound_primary"] = key
        # A description that scales or normalises over the fit window names
        # it ``fit_start``/``fit_stop``; the window is the fit's, not the user's
        # to type twice.
        optional = self._document.get("optional_scalars", {})
        if "fit_start" in optional:
            self._spec.set_scalar("fit_start", float(max(0, xmin)))
        if "fit_stop" in optional:
            self._spec.set_scalar("fit_stop", float(max(0, min(len(y), xmax))))
        # Instrument numbers the data names (a pixel size) are held at its value.
        defaults = (getattr(data, "meta_data", None) or {}).get("parameter_defaults") or {}
        self.__dict__["_pending_defaults"] = {str(k): float(v) for k, v in defaults.items()}

    @property
    def problem(self):
        """The live BFF model, or ``None`` with :attr:`missing` saying why."""
        self._bind_primary()
        missing = []
        required = list(self._spec.get_dataset_names())
        # An optional measurement can still be needed: a description says
        # which switch makes it unnecessary (a modelled IRF instead of a
        # measured one), and while that switch is off it is missing.
        for slot, info in self.presentation.get("datasets", {}).items():
            unless = info.get("required_unless")
            if unless and slot not in required and not (self.get_scalar(unless) or 0.0):
                required.append(slot)
        for slot in required:
            if slot != self.primary_dataset and slot not in self._sources:
                missing.append(slot)
        for name in self._spec.get_scalar_names():
            if name not in self._scalars:
                value = self.get_scalar(name)
                if value is None:
                    missing.append(name)
                elif self.__dict__.setdefault("_defaults", {}).get(name) != value:
                    self._defaults[name] = value
                    self._spec.set_scalar(name, value)
        self.missing = missing
        if missing or self.__dict__.get("_bound_primary") is None:
            return None
        rebuilt = not self._spec.get_model_is_current()
        model = self._spec.get_model()
        if rebuilt:
            self._adopt(model)
        pending = self.__dict__.pop("_pending_defaults", None)
        if pending:
            ids = set(model.get_parameter_ids())
            for canonical, value in pending.items():
                if canonical in ids:
                    port = model.get_parameter(canonical)
                    port.fixed = False
                    port.value = value
                    model.set_parameter_locked(canonical, True)
        return model

    def _adopt(self, problem) -> None:
        """Wrap the model's ports once; a rebuild keeps them, so this is idempotent."""
        document = self._document
        labels = self.presentation.get("groups", {})
        by_group: typing.Dict[str, list] = {}
        known = {p.canonical_id: p for g in self._groups.values() for p in g.parameters_all}
        for canonical in problem.get_parameter_ids():
            entry = document["parameters"].get(canonical, {})
            port = problem.get_parameter(canonical)
            parameter = known.get(canonical)
            if parameter is None or parameter._port.uid != port.uid:
                parameter = DescriptionParameter(
                    self, canonical, port, name=entry.get("name", canonical))
            by_group.setdefault(entry.get("group", "equation"), []).append(parameter)
        for key, parameters in by_group.items():
            # A group named like something the model already has (its
            # ``parameters`` list, say) would shadow it; such a group is
            # reached under ``<name>_group`` instead.
            attribute = key if not hasattr(type(self), key) else f"{key}_group"
            group = DescriptionGroup(self, key, parameters,
                                     name=labels.get(key, key.replace("_", " ").capitalize()))
            self._groups[attribute] = group
            self.__dict__[attribute] = group
        self.__dict__["_adopting"] = True
        try:
            self.find_parameters()
        finally:
            self.__dict__.pop("_adopting", None)

    @property
    def scalars(self) -> _Scalars:
        return _Scalars(self)

    # --- editor ------------------------------------------------------------------
    def view_spec(self):
        """The editor, derived from the description's own presentation data.

        An authored ``views/<family>.view.json`` next to this module wins; it
        is layout only and names description ids, never ChiSurf attributes of
        a family class, because there is none.
        """
        import pathlib
        from chisurf.core.models import view_spec as vs

        authored = pathlib.Path(__file__).parent / "views" / f"{self.family}.view.json"
        if authored.is_file():
            return vs.load_view_spec(authored)
        presentation = self.presentation
        slot_info = presentation.get("datasets", {})
        scalar_info = presentation.get("scalars", {})
        sections = [
            vs.ChoiceSection(label="Equation" if self._catalogue else "Model", attr="structure",
                             options_source="structure_options",
                             rebuild_on_change=True),
            *((vs.ValueSection(label="Equation", kind="expression", attr="func"),)
              if self._catalogue else ()),
            vs.PanelSection(title="Measurements", sections=tuple(
                vs.CurveInputSection(
                    label=slot_info.get(slot, {}).get("label", slot),
                    select_action="model.set_dataset",
                    unload_action="model.unset_dataset",
                    index_key="idx", name_key="name",
                    action_fixed={"slot": slot})
                for slot in self.dataset_slots())),
        ]
        settings = []
        # A description that presents its scalars lists the ones a user sets;
        # the rest (a fit window the view fills itself) stay out of the editor.
        presented = set(scalar_info) if scalar_info else None
        for name in self.scalar_names():
            if presented is not None and name not in presented:
                continue
            info = scalar_info.get(name, {})
            if info.get("kind") == "flag":
                settings.append(vs.ToggleSection(label=info.get("label", name), attr=f"scalars.{name}"))
            else:
                settings.append(vs.ValueSection(label=info.get("label", name), kind="float", attr=f"scalars.{name}"))
        sections.append(vs.PanelSection(title="Settings", collapsed=True, sections=tuple(settings)))
        for attribute, group in self._groups.items():
            sections.append(vs.ParameterGroupTableSection(
                target=attribute, title=group.name,
                parameters_source="visible_parameters", collapsible=False))
        grid = (getattr(getattr(self.fit, "data", None), "meta_data", None) or {}).get("grid") or {}
        if len(tuple(grid.get("shape", ()) or ())) >= 2:
            # A measurement on a grid is shown as images; the accessors are
            # generic, reading the grid its reader recorded.
            module = "chisurf.core.models.grid_images"
            plots = (
                vs.PlotSpec("residual2d", {
                    "sources": {
                        "Residual": {"accessor": f"{module}:get_grid_residual_image",
                                     "accessor_kwargs": {"weighted": True, "frame_index": 0}},
                        "Data": {"accessor": f"{module}:get_grid_data_image",
                                 "accessor_kwargs": {"frame_index": 0}},
                        "Model": {"accessor": f"{module}:get_grid_model_image",
                                  "accessor_kwargs": {"frame_index": 0}},
                    },
                    "frame_kw": "frame_index",
                    "max_frames_accessor": f"{module}:get_grid_n_frames",
                    "frame_label": "Frame",
                }),
                vs.PlotSpec("fit_info"),
                vs.PlotSpec("parameter_scan"),
            )
        else:
            axis = presentation.get("axis", {})
            plots = [vs.PlotSpec("line", {"x_label": axis.get("x", "x"), "y_label": axis.get("y", "y"),
                                          **({"d_scaley": axis["scale_y"]} if "scale_y" in axis else {})}),
                     vs.PlotSpec("fit_table"), vs.PlotSpec("fit_info"), vs.PlotSpec("parameter_scan")]
            distributions = presentation.get("distributions", {})
            if distributions:
                plots.append(vs.PlotSpec("distribution", {"distribution_options": {
                    info.get("label", name): {
                        "attribute": name, "accessor": "interleaved_to_two_columns",
                        "accessor_kwargs": {"sort": True},
                        "curve_options": {"stepMode": False, "connect": False,
                                          "bar_mode": "sticks", "symbol": "o"}}
                    for name, info in distributions.items()}}))
            plots.append(vs.PlotSpec("residual"))
            plots = tuple(plots)
        return vs.ModelView(sections=tuple(sections), plots=plots)

    def find_parameters(self, parameter_type=FittingParameter) -> None:
        """Discover parameters, wrapping the model's ports first if it is complete.

        The parameters exist only once BFF has built the model, and discovery
        runs whenever ChiSurf asks -- often before the last measurement is
        bound. Asking for the model here is what makes the answer current.
        """
        if not self.__dict__.get("_adopting"):
            try:
                self.problem
            except Exception:
                pass
        super().find_parameters(parameter_type=parameter_type)

    # --- topology --------------------------------------------------------------
    def structure_options(self) -> typing.List[typing.Tuple[str, str]]:
        structures = self._document.get("structures", {})
        return [(k, structures.get(k, {}).get("label", k)) for k in self._spec.get_structure_keys()]

    @property
    def structure(self) -> str:
        problem = self.problem
        return "" if problem is None else str(problem.get_active_structure())

    @structure.setter
    def structure(self, key: str):
        problem = self.problem
        if problem is None:
            raise RuntimeError(f"the model is incomplete: missing {', '.join(self.missing)}")
        problem.select_structure(str(key))
        factorgraph.bump_structure_version()
        self.update()

    def structure_parameter_ids(self) -> typing.List[str]:
        problem = self.problem
        if problem is None:
            return []
        return list(problem.get_structure_parameter_ids(problem.get_active_structure()))

    # --- presented outputs -------------------------------------------------------
    def presented_distribution(self, name: str) -> np.ndarray:
        """A distribution the description presents, read from the live model now."""
        info = self.presentation.get("distributions", {}).get(name)
        problem = self.problem
        if info is None or problem is None:
            return np.zeros(0)
        active = problem.get_active_structure()
        node = f"{active}.{info['node']}"
        port = info.get("port", "@name")
        if port == "@name":
            return np.array(problem.get_structure_output(active, node), dtype=float)
        return np.array(problem.get_structure_port(active, node, port), dtype=float)

    def __getattr__(self, name: str):
        # Only the distributions a description names become attributes, so a
        # plot configured by attribute (``lifetime_spectrum``) reads the model.
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            document = object.__getattribute__(self, "_document")
        except Exception:
            raise AttributeError(name)
        if name in document.get("presentation", {}).get("distributions", {}):
            return self.presented_distribution(name)
        raise AttributeError(name)

    def _update_statistics(self) -> None:
        statistics = self.presentation.get("statistics", {})
        if not statistics:
            return
        import chisurf.core.fluorescence.general as general
        outputs = self.__dict__.get("_statistic_parameters")
        if outputs is None:
            outputs = {}
            for key, info in statistics.items():
                outputs[key] = FittingParameter(
                    value=0.0, name=info.get("label", key), fixed=True, is_output=True)
                # Not a parameter of the BFF model: derived from it, shown beside it.
                outputs[key].canonical_id = f"output.{key}"
            self.__dict__["_statistic_parameters"] = outputs
            self.__dict__["outputs"] = FittingParameterGroup(
                parameters=list(outputs.values()), name="Outputs")
            self._forget_discovery()
        for key, info in statistics.items():
            spectrum = self.presented_distribution(info["of"])
            function = getattr(general, info["statistic"], None)
            if function is None or spectrum.size < 2:
                continue
            try:
                outputs[key].value = float(function(spectrum))
            except Exception:
                pass

    def get_plot_reference_modes(self):
        from chisurf.core.plotting.reference_modes import modes_named

        return modes_named(self.presentation.get("reference_modes", []))

    # --- the curve -------------------------------------------------------------
    def _update_model(self, **kwargs):
        problem = self.problem
        x = getattr(self.fit.data, "x", None)
        if x is not None:
            self.x = np.asarray(x)
        if problem is None:
            self.y = np.zeros_like(np.asarray(self.x, dtype=float))
            return
        active = problem.get_active_structure()
        node = problem.get_structure_curve_node(active, self.primary_dataset)
        self.y = np.array(problem.get_structure_output(active, node), dtype=float)
        self._update_statistics()

    # --- persistence -----------------------------------------------------------
    def get_state(self) -> dict:
        problem = self.problem
        state = {
            "family": self.family,
            "scalars": dict(self._scalars),
            "datasets": {
                slot: {"x": np.asarray(getattr(c, "x", []), dtype=float).tolist(),
                       "y": np.asarray(c.y, dtype=float).tolist()}
                for slot, c in self._sources.items()
            },
        }
        if problem is not None:
            ids = list(problem.get_parameter_ids())
            state["structure"] = str(problem.get_active_structure())
            state["values"] = {i: float(problem.get_parameter(i).value) for i in ids}
            state["locked"] = [i for i in ids if problem.get_parameter_locked(i)]
            state["released"] = [i for i in ids if problem.get_parameter_released(i)]
        return state

    def set_state(self, state: dict) -> None:
        import chisurf.core.curve
        for name, value in state.get("scalars", {}).items():
            self.set_scalar(name, value)
        for slot, curve in state.get("datasets", {}).items():
            self.set_dataset(slot, chisurf.core.curve.Curve(x=np.asarray(curve["x"]), y=np.asarray(curve["y"])))
        problem = self.problem
        if problem is None or "values" not in state:
            return
        ids = set(problem.get_parameter_ids())
        for canonical in ids:
            problem.set_parameter_locked(canonical, canonical in state.get("locked", ()))
            problem.set_parameter_released(canonical, canonical in state.get("released", ()))
        if state.get("structure"):
            problem.select_structure(state["structure"])
        for canonical, value in state["values"].items():
            if canonical in ids:
                port = problem.get_parameter(canonical)
                was = port.fixed
                port.fixed = False
                port.value = float(value)
                port.fixed = was
        factorgraph.bump_structure_version()
        self.update()


_FAMILIES: typing.Dict[str, type] = {}


def for_family(family: str) -> type:
    """The model class ChiSurf lists for one described family."""
    cls = _FAMILIES.get(family)
    if cls is None:
        document = json.loads(_bff.ModelSearchSpec.from_name(family).get_description_json())
        cls = type(
            f"DescriptionModel_{family}",
            (DescriptionModel,),
            {"family": family, "name": document.get("title", family), "__module__": __name__},
        )
        _FAMILIES[family] = cls
        globals()[cls.__name__] = cls
    return cls


def for_catalogue(path, name: typing.Optional[str] = None, module: typing.Optional[str] = None,
                  frame: str = "equations") -> type:
    """The model class ChiSurf lists for one equation catalogue.

    The catalogue is ChiSurf's (YAML beside the experiment's models); BFF
    builds every entry as a competing structure and knows nothing about what
    the equations describe. *frame* names the BFF frame the equations sit in:
    ``equations`` compares them to the data directly, ``equations_convolved``
    convolves them with a measured response and a counting instrument first.
    """
    import pathlib

    path = pathlib.Path(path).resolve()
    cls = _FAMILIES.get(f"{frame}:{path}")
    if cls is None:
        attributes = {"catalogue_path": path, "family": frame, "__module__": module or __name__}
        if name:
            attributes["name"] = name
        cls = type(f"EquationModel_{path.parent.name}", (DescriptionModel,), attributes)
        _FAMILIES[f"{frame}:{path}"] = cls
    return cls


def __getattr__(name: str):
    """``chisurf.core.models.description.<family>`` is that family's model class.

    So a shipped description is listed in the experiment configuration by an
    ordinary dotted path, and every resolver that imports a class by name
    finds it without learning anything about descriptions.
    """
    if name.startswith("_") or _bff is None:
        raise AttributeError(name)
    if name in set(_bff.ModelSearchSpec.get_available_names()):
        return for_family(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["DescriptionGroup", "DescriptionModel", "DescriptionParameter", "for_catalogue", "for_family"]
