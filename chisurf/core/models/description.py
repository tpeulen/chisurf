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
        return float(self._port.value)

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


def _measurement(x, y, ey=None, mask=None):
    dataset = _bff.FitDataset()
    dataset.set_values_array(np.ascontiguousarray(np.asarray(y, dtype=float)))
    if x is not None and len(x) == len(y):
        dataset.set_coordinate_array(0, "x", np.ascontiguousarray(np.asarray(x, dtype=float)))
    if ey is not None:
        dataset.set_noise_family(_bff.FIT_NOISE_FAMILY_STORED)
        dataset.set_stored_variance_array(
            np.ascontiguousarray(np.asarray(ey, dtype=float) ** 2))
    if mask is not None:
        dataset.set_mask_array(np.ascontiguousarray(np.asarray(mask, dtype=float)))
    return dataset


class DescriptionModel(ModelCurve):
    """A ChiSurf view on one BFF model family.

    Subclassed per family by :func:`for_family`, which is what the experiment
    configuration names by family -- ``chisurf.core.models.description.tcspc_lifetime``.
    """

    family: str = ""
    name = "BFF model"

    def __init__(self, fit, family: typing.Optional[str] = None, **kwargs):
        if _bff is None:
            raise ImportError("a BFF-described model needs IMP.bff")
        family = family or type(self).family
        if not family:
            raise ValueError("a DescriptionModel needs a family description")
        self.__dict__["_spec"] = _bff.ModelSearchSpec.from_name(family)
        self.__dict__["_document"] = json.loads(self._spec.get_description_json())
        self.__dict__["_bound_primary"] = None
        super().__init__(fit, **kwargs)
        self.family = family
        self.name = self._document.get("title", family)
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
        self._spec.set_dataset(slot, _measurement(getattr(curve, "x", None), curve.y))
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
        x = getattr(data, "x", None)
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
        for part in (y, ey, x, window):
            if part is not None:
                digest.update(np.ascontiguousarray(np.asarray(part, dtype=float)).tobytes())
        key = digest.hexdigest()
        if self._bound_primary == key:
            return
        self._spec.set_dataset(self.primary_dataset, _measurement(x, y, ey, window))
        self.__dict__["_bound_primary"] = key

    @property
    def problem(self):
        """The live BFF model, or ``None`` with :attr:`missing` saying why."""
        self._bind_primary()
        missing = []
        required = list(self._spec.get_dataset_names())
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
            by_group.setdefault(entry.get("group", "parameters"), []).append(parameter)
        for key, parameters in by_group.items():
            group = DescriptionGroup(self, key, parameters, name=labels.get(key, key))
            self._groups[key] = group
            self.__dict__[key] = group
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
            vs.ChoiceSection(label="Model", attr="structure",
                             options_source="structure_options",
                             rebuild_on_change=True),
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
        for name in self.scalar_names():
            info = scalar_info.get(name, {})
            if info.get("kind") == "flag":
                settings.append(vs.ToggleSection(label=info.get("label", name), attr=f"scalars.{name}"))
            else:
                settings.append(vs.ValueSection(label=info.get("label", name), kind="float", attr=f"scalars.{name}"))
        sections.append(vs.PanelSection(title="Settings", collapsed=True, sections=tuple(settings)))
        for key, label in presentation.get("groups", {}).items():
            sections.append(vs.ParameterGroupTableSection(
                target=key, title=label, parameters_source="visible_parameters",
                collapsible=False))
        plots = (
            vs.PlotSpec("line", {"x_label": "x", "y_label": "y"}),
            vs.PlotSpec("fit_info"),
            vs.PlotSpec("parameter_scan"),
            vs.PlotSpec("residual"),
        )
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


__all__ = ["DescriptionGroup", "DescriptionModel", "DescriptionParameter", "for_family"]
