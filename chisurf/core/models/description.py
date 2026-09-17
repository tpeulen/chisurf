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

import functools
import json
import pathlib

import numpy as np

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

    def __init__(self, view: DescriptionModel, canonical_id: str, port, **kwargs):
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
    def bounds_on(self) -> bool:
        """Whether a bound applies: BFF marks every port bounded, an infinite pair bounds nothing."""
        if not self._port.bounded:
            return False
        low, high = self.bounds
        return not (np.isinf(float(low)) and np.isinf(float(high)))

    @bounds_on.setter
    def bounds_on(self, v: bool) -> None:
        self._port.bounded = bool(v)

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


def _component_index(canonical_id: str) -> typing.Optional[int]:
    """The component a parameter belongs to (``lifetime.tau.1`` -> 1), or ``None``."""
    head, _, tail = canonical_id.rpartition(".")
    return int(tail) if head and tail.isdigit() else None


def _component_base(canonical_id: str) -> str:
    """A per-component parameter's id without its index (``lifetime.tau``)."""
    return (
        canonical_id.rpartition(".")[0]
        if _component_index(canonical_id) is not None
        else canonical_id
    )


#: ChiSurf's editor layouts for described families: ``views/*.layout.json``.
_VIEWS = pathlib.Path(__file__).parent / "views"


@functools.cache
def _layout_for(family: str) -> typing.Optional[dict]:
    """The editor layout that applies to *family*, or ``None`` for the generic one."""
    for path in sorted(_VIEWS.glob("*.layout.json")):
        layout = json.loads(path.read_text(encoding="utf-8"))
        if any(family.startswith(prefix) for prefix in layout.get("applies_to", ())):
            return layout
    return None


class DescriptionGroup(FittingParameterGroup):
    """The parameters of one ``group`` a description declares.

    A group whose parameters carry a component index (``lifetime.amplitude.0``,
    ``lifetime.tau.0``, ...) is a list of components: the editor shows one row
    per component and adds or removes components through :meth:`append` and
    :meth:`pop`, which choose the topology with one more or one fewer.
    """

    def __init__(self, view: DescriptionModel, key: str, parameters, **kwargs):
        super().__init__(parameters=list(parameters), **kwargs)
        self.name = kwargs.get("name", key)
        self.__dict__["_view"] = view
        self.key = key

    def visible_parameters(self):
        """The group's parameters the current topology reads, in registry order."""
        used = set(self._view.structure_parameter_ids())
        return [p for p in self.parameters_all if p.canonical_id in used]

    # --- components ------------------------------------------------------------
    def component_bases(self) -> typing.List[str]:
        """The per-component parameter kinds, in description order (amplitude, tau)."""
        return list(
            dict.fromkeys(
                _component_base(p.canonical_id)
                for p in self.parameters_all
                if _component_index(p.canonical_id) is not None
            )
        )

    def component_parameters(self):
        """The per-component parameters the topology reads, one component after another."""
        bases = self.component_bases()
        rows = [
            p for p in self.visible_parameters() if _component_index(p.canonical_id) is not None
        ]
        return sorted(
            rows,
            key=lambda p: (
                _component_index(p.canonical_id),
                bases.index(_component_base(p.canonical_id)),
            ),
        )

    def static_parameters(self):
        """The group's parameters that are not per component (``anisotropy.g``)."""
        return [p for p in self.visible_parameters() if _component_index(p.canonical_id) is None]

    def append(self) -> None:
        """Add a component."""
        self._view.change_components(self.key, +1)

    def pop(self, index: typing.Optional[int] = None) -> None:
        """Remove component *index*, or the last one."""
        self._view.remove_component(self.key, index)

    # --- anisotropy diagnostics (the r(t) window) ---------------------------------
    def _channel_fits(self):
        """The fits of this model's group set to VV (1) and to VH (2), if both exist."""
        fit = getattr(self._view, "fit", None)
        members = list(getattr(fit, "group", None) or ()) or [fit]
        channels = {}
        for member in members:
            model = getattr(member, "model", None)
            try:
                code = float(model.get_scalar("polarization"))
            except Exception:
                continue
            channels.setdefault(code, member)
        return channels.get(1.0), channels.get(2.0)

    def _value_of(self, canonical: str, default: float) -> float:
        for parameter in self._view.parameters_all:
            if getattr(parameter, "canonical_id", None) == canonical:
                return float(parameter.value)
        return float(default)

    def _extract_vv_vh_raw_for_diag(self):
        """``(t, vv, vh, defaults)`` from the VV and VH fits of this group."""
        vv_fit, vh_fit = self._channel_fits()
        if vv_fit is None or vh_fit is None:
            return None, None, None, None
        vv = np.asarray(vv_fit.data.y, dtype=float)
        vh = np.asarray(vh_fit.data.y, dtype=float)
        n = min(vv.size, vh.size)
        t = np.asarray(vv_fit.data.x, dtype=float)[:n]
        defaults = {
            "g": self._value_of("anisotropy.g", 1.0),
            "l1": self._value_of("anisotropy.l1", 0.0),
            "l2": self._value_of("anisotropy.l2", 0.0),
            "bg_vv": float(vv_fit.model._value_of_instrument("instrument.background")),
            "bg_vh": float(vh_fit.model._value_of_instrument("instrument.background")),
            "shift_vv": float(vv_fit.model._value_of_instrument("instrument.timeshift")),
            "shift_vh": float(vh_fit.model._value_of_instrument("instrument.timeshift")),
        }
        return t, vv[:n], vh[:n], defaults

    def _extract_vv_vh_model_for_diag(self):
        """``(t, vv, vh)`` of the model curves of the VV and VH fits."""
        vv_fit, vh_fit = self._channel_fits()
        if vv_fit is None or vh_fit is None:
            return None, None, None
        vv = np.asarray(vv_fit.model.y, dtype=float)
        vh = np.asarray(vh_fit.model.y, dtype=float)
        n = min(vv.size, vh.size)
        return np.asarray(vv_fit.model.x, dtype=float)[:n], vv[:n], vh[:n]

    @staticmethod
    def _shift_trace_to_reference(t, trace, shift: float):
        """*trace* moved by *shift* along *t* (linear interpolation)."""
        t = np.asarray(t, dtype=float)
        trace = np.asarray(trace, dtype=float)
        return np.interp(t, t + float(shift), trace) if shift else trace

    @staticmethod
    def rt_from_channels(t, vv, vh, g: float, l1: float, l2: float):
        """``(t, r_uncorrected, r_corrected)`` -- see :func:`chisurf.core.fluorescence.anisotropy.rt.rt_curves`."""
        from chisurf.core.fluorescence.anisotropy.rt import rt_curves

        return rt_curves(t, vv, vh, g, l1, l2)


class _Selection:
    """Named parameters of a model, as a table target (a layout panel's own list).

    Holds canonical ids, not parameters, so discovering the model's parameters
    never finds the same parameter twice through a panel.
    """

    def __init__(self, view: DescriptionModel, ids: typing.Tuple[str, ...]):
        self._view = view
        self.ids = ids
        self.name = ""

    @property
    def parameters_all(self):
        by_id = {getattr(p, "canonical_id", None): p for p in self._view.parameters_all}
        used = set(self._view.structure_parameter_ids())
        return [by_id[i] for i in self.ids if i in by_id and i in used]

    def visible_parameters(self):
        return self.parameters_all


class _Datasets:
    """The curves bound to a model's measurement slots, as attributes (for the editor)."""

    def __init__(self, view: DescriptionModel):
        self._view = view

    def __getattr__(self, slot: str):
        if slot.startswith("_") or slot not in self._view.dataset_slots():
            raise AttributeError(slot)
        return self._view.__dict__.get("_sources", {}).get(slot)


class _Scalars:
    """``model.scalars.<name>``: a description's scalars as attributes.

    What lets a generic ``value`` or ``toggle`` section bind to a scalar by a
    dotted ``attr`` without the view knowing any scalar's name.
    """

    def __init__(self, view: DescriptionModel):
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
        dataset.set_stored_variance_array(np.ascontiguousarray(np.asarray(ey, dtype=float) ** 2))
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
    #: An authored editor for this model class (a catalogue's own view file).
    view_file = None
    #: The catalogue equations this class offers (all of them when empty).
    catalogue_entries: typing.Tuple[str, ...] = ()
    #: Editor labels by parameter id, beside the layout's (a catalogue's own symbols).
    parameter_labels: typing.Dict[str, str] = {}
    #: Plot normalisations offered beside the description's own (see `for_catalogue`).
    reference_modes: typing.Tuple[str, ...] = ()
    name = "BFF model"

    @property
    def _document(self) -> dict:
        """The description as BFF reads it now -- a catalogue's structures appear
        once the measurement that decides which variables are axes is bound.
        """
        return json.loads(self._spec.get_description_json())

    # --- equations ---------------------------------------------------------------
    @property
    def catalogue(self) -> dict:
        return dict(self._catalogue)

    @property
    def catalogue_names(self) -> typing.List[str]:
        return list(self._catalogue)

    @property
    def description(self) -> str:
        """What the selected catalogue equation describes."""
        entry = self._catalogue.get(self.model_name) or {}
        text = entry.get("description") if isinstance(entry, dict) else None
        return str(text) if text else "No description!"

    def _parameters_equation(self) -> list:
        """The parameters the selected equation reads (the classic parse editor's table)."""
        group = next((g for g in self._groups.values() if g.key == "equation"), None)
        return group.visible_parameters() if group is not None else []

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
            catalogue = _read_catalogue(catalogue_path)
            entries = type(self).catalogue_entries
            if entries:
                catalogue = {k: v for k, v in catalogue.items() if k in entries}
            self.__dict__["_catalogue"] = catalogue
            self._spec.set_equations(json.dumps(self._catalogue))
        self.__dict__["_bound_primary"] = None
        super().__init__(fit, **kwargs)
        self.family = family
        self.name = type(self).__dict__.get("name") or self._document.get("title", family)
        self.missing: typing.List[str] = []
        self._sources: typing.Dict[str, typing.Any] = {}
        self._scalars: typing.Dict[str, float] = {}
        self._groups: typing.Dict[str, DescriptionGroup] = {}
        #: The models this one reads a published output of (a mixture's species).
        self._source_models: typing.List[DescriptionModel] = []
        self._source_names: typing.List[str] = []
        self._bound_ports: typing.List[str] = []
        # A port the description gives a default for (a MaxEnt prior) is bound
        # to it, so the model builds before anyone supplies one.
        for name, info in (self._document.get("ports") or {}).items():
            if isinstance(info, dict) and "default" in info:
                self.set_port_values(name, info["default"])
        # What the description presents as numbers (statistics, reports,
        # values) are the model's derived quantities: readable by name and
        # reported with an uncertainty like any other.
        presentation = self.presentation
        self.__dict__["derived_quantities"] = tuple(
            [
                *presentation.get("statistics", {}),
                *presentation.get("reports", {}),
                *presentation.get("values", {}),
            ]
        )
        self._assign_group_position(fit)

    def _assign_group_position(self, fit) -> None:
        """Set the scalar a family ties to a fit's place in its group.

        The description's ``presentation.group_position`` names the scalar and
        its values: ``single`` for a group of one, ``alternate`` by index
        otherwise -- how a VV/VH pair added together becomes a VV and a VH fit.
        Every view of this family in the group is re-set, since fits join a
        group one at a time.
        """
        rule = self.presentation.get("group_position")
        group = getattr(fit, "group", None)
        if (
            not rule
            or rule.get("scalar") not in self.scalar_names()
            or not isinstance(group, list)
            or not group
        ):
            return
        for index, member in enumerate(group):
            model = self if member is fit else member.__dict__.get("_model")
            if not isinstance(model, DescriptionModel) or model.family != self.family:
                continue
            value = (
                rule["single"]
                if len(group) == 1
                else rule["alternate"][index % len(rule["alternate"])]
            )
            model.set_scalar(rule["scalar"], float(value))

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

    def has_dataset(self, slot: str) -> bool:
        """Whether a curve is bound to the measurement slot."""
        return slot in self._sources

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
        if name in self.__dict__.get("_automatic_scalars", {}):
            return self._automatic_scalars[name]
        default = self.presentation.get("scalars", {}).get(name, {}).get("default")
        if default is None:
            default = self._document.get("optional_scalars", {}).get(name)
        if default is None:
            return None
        try:
            return (
                float(default)
                if not isinstance(default, str)
                else float(self._spec.evaluate(default))
            )
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
        window[max(0, xmin) : max(0, min(len(y), xmax))] = 1.0
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
        meta = getattr(data, "meta_data", None) or {}
        defaults = meta.get("parameter_defaults") or {}
        self.__dict__["_pending_defaults"] = {str(k): float(v) for k, v in defaults.items()}
        # Calibration a reader records on the data (a G factor) starts the
        # parameters the description maps it to; they stay the user's to change.
        starts = {}
        for key, canonical in self.presentation.get("meta_parameters", {}).items():
            if key.startswith("_"):
                continue
            try:
                starts[str(canonical)] = float(meta[key])
            except (KeyError, TypeError, ValueError):
                continue
        self.__dict__["_pending_starts"] = starts
        # Instrument settings a reader records on the data (the excitation
        # period of its laser) set the description's scalars until the user
        # sets them.
        automatic = self.__dict__.setdefault("_automatic_scalars", {})
        for key, scalar in self.presentation.get("meta_scalars", {}).items():
            if key.startswith("_") or scalar in self._scalars:
                continue
            try:
                automatic[str(scalar)] = float(meta[key])
            except (KeyError, TypeError, ValueError):
                continue

    @property
    def problem(self):
        """The live BFF model, or ``None`` with :attr:`missing` saying why."""
        self._bind_primary()
        missing = []
        required = list(self._spec.get_dataset_names())
        # An optional measurement can still be needed: a description says
        # which switch makes it unnecessary (a modelled IRF instead of a
        # measured one). Until the user sets that switch, it follows the
        # measurement -- on while nothing is loaded, off once something is --
        # which is what ChiSurf's lifetime model did with an unloaded IRF.
        # A switch the user set is theirs, and while it is off the
        # measurement is missing.
        automatic = self.__dict__.setdefault("_automatic_scalars", {})
        for slot, info in self.presentation.get("datasets", {}).items():
            unless = info.get("required_unless")
            if not unless or slot in required:
                continue
            if unless not in self._scalars:
                wanted = 0.0 if slot in self._sources else 1.0
                if automatic.get(unless) != wanted:
                    automatic[unless] = wanted
                    self._spec.set_scalar(unless, wanted)
                    self._forget_discovery()
                continue
            if not (self.get_scalar(unless) or 0.0):
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
        info = self.source_info
        if info:
            count = int(self.get_scalar(info["count"]) or 0)
            for i in range(max(1, count)):
                name = info["port"].format(i=i)
                if name not in self._bound_ports:
                    missing.append(name)
            axis_port = info.get("axis_port")
            if axis_port and axis_port not in self.__dict__.get("_value_ports", {}):
                missing.append(axis_port)
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
        starts = self.__dict__.pop("_pending_starts", None)
        if starts:
            ids = set(model.get_parameter_ids())
            for canonical, value in starts.items():
                if canonical in ids:
                    port = model.get_parameter(canonical)
                    held = port.fixed
                    port.fixed = False
                    port.value = value
                    port.fixed = held
        return model

    def _adopt(self, problem) -> None:
        """Wrap the model's ports once; a rebuild keeps them, so this is idempotent."""
        document = self._document
        labels = self.presentation.get("groups", {})
        layout = _layout_for(self.family) or {}
        symbols = {
            **layout.get("labels", {}),
            **layout.get("family_labels", {}).get(self.family, {}),
            **type(self).parameter_labels,
        }
        by_group: typing.Dict[str, list] = {}
        known = {p.canonical_id: p for g in self._groups.values() for p in g.parameters_all}
        for canonical in problem.get_parameter_ids():
            entry = document["parameters"].get(canonical, {})
            port = problem.get_parameter(canonical)
            parameter = known.get(canonical)
            if parameter is None or parameter._port.uid != port.uid:
                parameter = DescriptionParameter(
                    self, canonical, port, name=entry.get("name", canonical)
                )
                label = symbols.get(_component_base(canonical))
                if label:
                    index = _component_index(canonical)
                    parameter.__dict__["label_text"] = label.format(
                        n="" if index is None else index + 1
                    )
            by_group.setdefault(entry.get("group", "equation"), []).append(parameter)
        for key, parameters in by_group.items():
            # A group named like something the model already has (its
            # ``parameters`` list, say) would shadow it; such a group is
            # reached under ``<name>_group`` instead.
            attribute = key if not hasattr(type(self), key) else f"{key}_group"
            group = self._groups.get(attribute)
            if group is None:
                group = DescriptionGroup(
                    self, key, parameters, name=labels.get(key, key.replace("_", " ").capitalize())
                )
            else:
                # The same group object, so an editor holding it sees a component
                # a rebuild added (a fourth lifetime once the maximum rose).
                group._parameter[:] = parameters
                group.__dict__["_parameters"] = None
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

    @property
    def datasets(self) -> _Datasets:
        """``model.datasets.<slot>``: the curve bound to a measurement slot, or ``None``."""
        return _Datasets(self)

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
        if type(self).view_file:
            authored = pathlib.Path(type(self).view_file)
        if authored.is_file():
            return vs.load_view_spec(authored)
        layout = _layout_for(self.family)
        if layout is not None and self.problem is not None:
            sections = self._layout_sections(layout)
        else:
            sections = self._generic_sections()
        presentation = self.presentation
        grid = (getattr(getattr(self.fit, "data", None), "meta_data", None) or {}).get("grid") or {}
        if len(tuple(grid.get("shape", ()) or ())) >= 2:
            # A measurement on a grid is shown as images; the accessors are
            # generic, reading the grid its reader recorded.
            module = "chisurf.core.models.grid_images"
            plots = (
                vs.PlotSpec(
                    "residual2d",
                    {
                        "sources": {
                            "Residual": {
                                "accessor": f"{module}:get_grid_residual_image",
                                "accessor_kwargs": {"weighted": True, "frame_index": 0},
                            },
                            "Data": {
                                "accessor": f"{module}:get_grid_data_image",
                                "accessor_kwargs": {"frame_index": 0},
                            },
                            "Model": {
                                "accessor": f"{module}:get_grid_model_image",
                                "accessor_kwargs": {"frame_index": 0},
                            },
                        },
                        "frame_kw": "frame_index",
                        "max_frames_accessor": f"{module}:get_grid_n_frames",
                        "frame_label": "Frame",
                    },
                ),
                vs.PlotSpec("fit_info"),
                vs.PlotSpec("parameter_scan"),
            )
        else:
            axis = presentation.get("axis", {})
            plots = [
                vs.PlotSpec(
                    "line",
                    {
                        "x_label": axis.get("x", "x"),
                        "y_label": axis.get("y", "y"),
                        **({"d_scaley": axis["scale_y"]} if "scale_y" in axis else {}),
                    },
                ),
                vs.PlotSpec("fit_table"),
                vs.PlotSpec("fit_info"),
                vs.PlotSpec("parameter_scan"),
            ]
            distributions = presentation.get("distributions", {})
            if distributions:
                plots.append(
                    vs.PlotSpec(
                        "distribution",
                        {
                            "distribution_options": {
                                info.get("label", name): {
                                    "attribute": name,
                                    "accessor": "interleaved_to_two_columns",
                                    "accessor_kwargs": {"sort": True},
                                    "curve_options": {
                                        "stepMode": False,
                                        "connect": False,
                                        "bar_mode": "sticks",
                                        "symbol": "o",
                                    },
                                }
                                for name, info in distributions.items()
                            }
                        },
                    )
                )
            plots.append(vs.PlotSpec("residual"))
            plots = tuple(plots)
        return vs.ModelView(sections=tuple(sections), plots=plots)

    def _regularization_and_source_sections(self) -> list:
        """The L-curve panel of a regularised family and the models a mixture reads."""
        from chisurf.core.models import view_spec as vs

        sections = []
        if self.presentation.get("regularization"):
            sections.append(
                vs.PanelSection(
                    title="L-curve",
                    collapsed=True,
                    sections=(
                        vs.CustomSection(
                            key="lcurve",
                            target="l_curve",
                            options={
                                "compute_action": "compute_l_curve",
                                "select_action": "set_reg_from_lcurve_index",
                                "n_points": 16,
                            },
                        ),
                    ),
                )
            )
        sources = self.source_info
        if sources and sources.get("kind") != "values":
            sections.append(
                vs.PanelSection(
                    title=sources.get("label", "Models"),
                    sections=(vs.CustomSection(key="fit_mixer"),),
                )
            )
        return sections

    def _shown_with_sources(self, group) -> bool:
        """Whether *group* holds the per-source parameters the models section shows."""
        sources = self.source_info
        if not sources or sources.get("kind") == "values":
            return False
        prefix = sources.get("parameter", "").split("{")[0]
        return bool(prefix) and all(p.canonical_id.startswith(prefix) for p in group.parameters_all)

    def _generic_sections(self) -> list:
        """The editor for a family with no ChiSurf layout: slots, settings, one table per group."""
        from chisurf.core.models import view_spec as vs

        presentation = self.presentation
        slot_info = presentation.get("datasets", {})
        scalar_info = presentation.get("scalars", {})
        sections = [
            vs.ChoiceSection(
                label="Equation" if self._catalogue else "Model",
                attr="structure",
                options_source="structure_options",
                rebuild_on_change=True,
            ),
            *(
                (vs.ValueSection(label="Equation", kind="expression", attr="func"),)
                if self._catalogue
                else ()
            ),
            vs.PanelSection(
                title="Measurements",
                sections=tuple(
                    vs.CurveInputSection(
                        label=slot_info.get(slot, {}).get("label", slot),
                        select_action="model.set_dataset",
                        unload_action="model.unset_dataset",
                        index_key="idx",
                        name_key="name",
                        action_fixed={"slot": slot},
                        target="datasets",
                        name_attr=slot,
                    )
                    for slot in self.dataset_slots()
                ),
            ),
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
                settings.append(
                    vs.ToggleSection(label=info.get("label", name), attr=f"scalars.{name}")
                )
            else:
                settings.append(
                    vs.ValueSection(
                        label=info.get("label", name), kind="float", attr=f"scalars.{name}"
                    )
                )
        sections.append(vs.PanelSection(title="Settings", collapsed=True, sections=tuple(settings)))
        sections.extend(self._regularization_and_source_sections())
        for attribute, group in self._groups.items():
            if self._shown_with_sources(group):
                # Shown with its source by the models section.
                continue
            sections.append(
                vs.ParameterGroupTableSection(
                    target=attribute,
                    title=group.name,
                    parameters_source="visible_parameters",
                    collapsible=False,
                )
            )
        return sections

    def _layout_sections(self, layout: dict) -> list:
        """The editor a ``views/*.layout.json`` lays out (see ``tcspc.layout.json``).

        Each panel names measurement slots, scalar switches, choices and values,
        and parameters or whole groups; what the family does not have is left
        out, and a panel left empty is not drawn. ``"groups": "*"`` places every
        group no other panel claims, and ``"values": "*"`` every scalar left.
        A group of components becomes an add/del table, one row per component.
        """
        from chisurf.core.models import view_spec as vs

        presentation = self.presentation
        slot_info = presentation.get("datasets", {})
        scalar_info = presentation.get("scalars", {})
        group_labels = presentation.get("groups", {})
        slots = self.dataset_slots()
        scalars = self.scalar_names()
        visible = set(self.structure_parameter_ids())
        attribute_of = {group.key: attribute for attribute, group in self._groups.items()}
        claimed_groups = {
            g
            for panel in layout.get("panels", ())
            for g in (panel.get("groups") if isinstance(panel.get("groups"), list) else ())
        }
        claimed_groups |= {g for panel in layout.get("panels", ()) for g in panel.get("except", ())}
        claimed_scalars = {
            name
            for panel in layout.get("panels", ())
            for key in ("toggles", "values")
            if isinstance(panel.get(key), list)
            for name in panel[key]
        } | {name for panel in layout.get("panels", ()) for name in panel.get("choices", {})}
        selections = self.__dict__.setdefault("_selections", {})
        short = layout.get("scalar_labels", {})

        def scalar_label(name):
            return short.get(name) or scalar_info.get(name, {}).get("label", name)

        def curve(slot):
            return vs.CurveInputSection(
                label=slot_info.get(slot, {}).get("label", slot),
                select_action="model.set_dataset",
                unload_action="model.unset_dataset",
                index_key="idx",
                name_key="name",
                action_fixed={"slot": slot},
                target="datasets",
                name_attr=slot,
            )

        def group_sections(key):
            group = self._groups.get(attribute_of.get(key, ""))
            if group is None or not any(p.canonical_id in visible for p in group.parameters_all):
                return []
            out = []
            if group.static_parameters():
                out.append(
                    vs.ParameterGroupTableSection(
                        target=attribute_of[key],
                        parameters_source="static_parameters",
                        collapsible=False,
                        columns=(
                            "name",
                            "value",
                            "fixed",
                            "bounds_lo",
                            "bounds_hi",
                            "bounds_on",
                            "error",
                        ),
                    )
                )
            bases = group.component_bases()
            if bases:
                out.append(
                    vs.DynamicGroupSection(
                        target=attribute_of[key],
                        rows_source="component_parameters",
                        append_method="append",
                        remove_method="pop",
                        row_width=len(bases),
                        style="table",
                        collapsible=False,
                        min_rows=1,
                        columns=("value", "fixed", "bounds_lo", "bounds_hi", "bounds_on", "error"),
                    )
                )
            return out

        sections = []
        for panel in layout.get("panels", ()):
            children = []
            for slot in panel.get("datasets", ()):
                if slot in slots:
                    children.append(curve(slot))
            toggles = [
                name
                for name in panel.get("toggles", ())
                if name in scalars and scalar_info.get(name, {}).get("kind") == "flag"
            ]
            if toggles:
                children.append(
                    vs.ToggleRowSection(
                        items=tuple(
                            {"target": "scalars", "attr": name, "label": scalar_label(name)}
                            for name in toggles
                        )
                    )
                )
            for name, choice in panel.get("choices", {}).items():
                if name in scalars:
                    children.append(
                        vs.ChoiceSection(
                            label=choice.get("label", name),
                            attr=f"scalars.{name}",
                            options=tuple(choice.get("options", ())),
                            labels=tuple(choice.get("labels", ())),
                            rebuild_on_change=True,
                        )
                    )
            ids = [i for i in panel.get("parameters", ()) if i in visible]
            if ids:
                name = f"selection_{len(selections)}"
                for existing, selection in selections.items():
                    if selection.ids == tuple(ids):
                        name = existing
                        break
                selections[name] = _Selection(self, tuple(ids))
                children.append(
                    vs.ParameterGroupTableSection(
                        target=name,
                        collapsible=False,
                        columns=(
                            "name",
                            "value",
                            "fixed",
                            "bounds_lo",
                            "bounds_hi",
                            "bounds_on",
                            "error",
                        ),
                    )
                )
            groups = panel.get("groups", ())
            if groups == "*":
                sections.extend(self._regularization_and_source_sections())
                for group in self._groups.values():
                    key = group.key
                    if key in claimed_groups or self._shown_with_sources(group):
                        continue
                    content = group_sections(key)
                    if content:
                        sections.append(
                            vs.PanelSection(
                                title=group_labels.get(key, key.replace("_", " ").capitalize()),
                                sections=tuple(content),
                            )
                        )
                continue
            has_group = False
            for key in groups:
                content = group_sections(key)
                has_group = has_group or bool(content)
                children.extend(content)
            if groups and not has_group and not panel.get("choices"):
                continue
            values = panel.get("values", ())
            if values == "*":
                values = [n for n in scalars if n not in claimed_scalars]
            for name in values:
                if name not in scalars:
                    continue
                info = scalar_info.get(name, {})
                if info.get("kind") == "flag":
                    children.append(
                        vs.ToggleSection(label=scalar_label(name), attr=f"scalars.{name}")
                    )
                else:
                    children.append(
                        vs.ValueSection(
                            label=scalar_label(name), kind="float", attr=f"scalars.{name}"
                        )
                    )
            if panel.get("custom") and has_group:
                children.extend(
                    vs.CustomSection(key=key, target=attribute_of.get(groups[0], ""))
                    for key in panel["custom"]
                )
            if not children:
                continue
            collapsed = bool(panel.get("collapsed", False))
            switch = panel.get("collapsed_unless_scalar")
            if switch:
                collapsed = not (self.get_scalar(switch) or 0.0)
            sections.append(
                vs.PanelSection(
                    title=panel.get("title", ""), collapsed=collapsed, sections=tuple(children)
                )
            )
        return sections

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

    # --- models this one reads (a mixture's species) -----------------------------
    @property
    def source_info(self) -> dict:
        """What a description says about the models it reads, or ``{}``.

        ``count`` is the scalar holding how many, ``port`` the name each is
        bound under, ``output`` what each has to publish and ``parameter`` the
        parameter each comes with (a mixing fraction).
        """
        return dict(self.presentation.get("sources") or {})

    def _publishes(self, model) -> bool:
        output = self.source_info.get("output")
        return (
            isinstance(model, DescriptionModel)
            and model is not self
            and bool(output)
            and output in model._document.get("outputs", {})
        )

    @property
    def source_fits(self) -> list:
        """Every open fit whose model publishes what this model reads."""
        import chisurf

        found = []
        for group in list(getattr(chisurf, "fits", []) or []):
            for fit in list(group) if hasattr(group, "__iter__") else [group]:
                if self._publishes(getattr(fit, "model", None)):
                    found.append(fit)
        return found

    #: The name the mixture editor section reads.
    lifetime_fits = source_fits

    def append_model(self, model, name: typing.Optional[str] = None) -> None:
        """Read ``model``'s published output as one more source."""
        info = self.source_info
        if not info:
            raise TypeError(f"{self.name!r} reads no other models")
        if model is self:
            raise ValueError("a model cannot read its own output")
        if not self._publishes(model):
            raise TypeError(
                f"{type(model).__name__} publishes no {info['output']!r}; only a model "
                "BFF describes can be read here"
            )
        self._source_models.append(model)
        self._source_names.append(
            name
            or str(
                getattr(getattr(model, "fit", None), "name", "")
                or f"model {len(self._source_models)}"
            )
        )
        self._bind_sources()

    def append_values(self, values, name: typing.Optional[str] = None) -> None:
        """Bind a given array as one more source (a description with `kind: values`)."""
        info = self.source_info
        if info.get("kind") != "values":
            raise TypeError(f"{self.name!r} reads models, not given values")
        self._source_models.append(np.ascontiguousarray(np.asarray(values, dtype=float).ravel()))
        self._source_names.append(name or f"values {len(self._source_models)}")
        self._bind_sources()

    def set_port_values(self, name: str, values) -> None:
        """Bind a given array to a port the description reads (a distance axis)."""
        port = _bff.GraphPort(list(np.asarray(values, dtype=float).ravel()))
        self.__dict__.setdefault("_value_ports", {})[name] = port
        self._spec.set_port(name, port)
        self._forget_discovery()
        factorgraph.bump_structure_version()

    def clear_sources(self) -> None:
        self._source_models.clear()
        self._source_names.clear()
        self._bind_sources()

    def pop_model(self, idx: typing.Optional[int] = None):
        """Stop reading one source; the last one when ``idx`` is not given."""
        idx = len(self._source_models) - 1 if idx is None else int(idx)
        model = self._source_models.pop(idx)
        self._source_names.pop(idx)
        self._bind_sources()
        return model

    @property
    def source_models(self) -> list:
        return list(self._source_models)

    @property
    def model_names(self) -> typing.List[str]:
        return list(self._source_names)

    def _bind_sources(self) -> None:
        info = self.source_info
        for name in self._bound_ports:
            self._spec.unset_port(name)
        self._bound_ports = []
        for i, source in enumerate(self._source_models):
            name = info["port"].format(i=i)
            if info.get("kind") == "values":
                # A port of our own holding the array; kept, since the spec only
                # references it.
                port = _bff.GraphPort(list(source))
                self.__dict__.setdefault("_value_ports", {})[name] = port
                self._spec.set_port(name, port)
            else:
                problem = source.problem
                if problem is None:
                    raise ValueError(
                        f"{self._source_names[i]!r} is incomplete: missing "
                        + ", ".join(source.missing)
                    )
                self._spec.set_port(name, problem.get_output_port(info["output"]))
            self._bound_ports.append(name)
        self.set_scalar(info["count"], float(max(1, len(self._source_models))))
        self._forget_discovery()
        factorgraph.bump_structure_version()

    @property
    def _fractions(self) -> list:
        """The parameter each source comes with, in source order."""
        info = self.source_info
        if not info.get("parameter") or self.problem is None:
            return []
        by_id = {p.canonical_id: p for g in self._groups.values() for p in g.parameters_all}
        return [
            by_id[info["parameter"].format(i=i)]
            for i in range(len(self._source_models))
            if info["parameter"].format(i=i) in by_id
        ]

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

    def _component_counts(self, problem, structure: str) -> typing.Dict[str, int]:
        """How many components each group has in *structure*."""
        parameters = self._document.get("parameters", {})
        indices: typing.Dict[str, set] = {}
        for canonical in problem.get_structure_parameter_ids(structure):
            index = _component_index(canonical)
            if index is not None:
                group = parameters.get(canonical, {}).get("group", "equation")
                indices.setdefault(group, set()).add(index)
        return {group: len(found) for group, found in indices.items()}

    def _structure_with(self, problem, group: str, wanted: int, others: typing.Dict[str, int]):
        """A topology with *wanted* components in *group* and the others unchanged."""
        for key in self._spec.get_structure_keys():
            counts = self._component_counts(problem, key)
            if counts.get(group, 0) == wanted and all(
                counts.get(g, 0) == n for g, n in others.items() if g != group
            ):
                return key
        return None

    def change_components(self, group: str, delta: int) -> bool:
        """Add (``delta=+1``) or remove (``-1``) a component of *group*.

        The description lists the topologies it can build; this selects the one
        with the component count asked for and every other group unchanged.
        Where no listed topology has it, the count is bounded by a scalar --
        ``max_components`` above a lifetime list, ``donor_lifetimes`` fixing a
        FRET model's donor -- and that scalar is moved by *delta* when doing so
        yields the topology. Returns whether the model changed.
        """
        problem = self.problem
        if problem is None:
            raise RuntimeError(f"the model is incomplete: missing {', '.join(self.missing)}")
        counts = self._component_counts(problem, str(problem.get_active_structure()))
        wanted = counts.get(group, 0) + int(delta)
        if wanted < 1:
            return False
        key = self._structure_with(problem, group, wanted, counts)
        if key is None:
            key = self._widen_for(group, wanted, counts, int(delta))
        if key is None:
            from chisurf import logging

            logging.warning(f"{self.name}: no topology with {wanted} {group}")
            return False
        self.structure = key
        return True

    def _widen_for(self, group: str, wanted: int, counts, delta: int):
        """Move a scalar that bounds the component axes until the topology exists."""
        names = set(self.scalar_names())
        fixed, upper = [], []
        for axis in (self._document.get("axes") or {}).values():
            low, high = axis.get("from"), axis.get("to")
            if isinstance(high, str) and high in names:
                (fixed if low == high else upper).append(high)
        for name in dict.fromkeys([*fixed, *upper]):
            before = self.get_scalar(name)
            chosen = name in self._scalars
            if before is None or before + delta < 0:
                continue
            self.set_scalar(name, before + delta)
            problem = self.problem
            key = None if problem is None else self._structure_with(problem, group, wanted, counts)
            if key is not None:
                return key
            if chosen:
                self.set_scalar(name, before)
            else:
                self._scalars.pop(name, None)
                self._spec.set_scalar(name, float(before))
                self._forget_discovery()
        return None

    def remove_component(self, group: str, index: typing.Optional[int] = None) -> bool:
        """Remove component *index* of *group* (the last one when ``None``).

        A component in the middle is removed by moving the ones after it down
        a place -- value, fixed flag and bounds -- and dropping the last.
        """
        members = self._groups.get(group) or next(
            (g for g in self._groups.values() if g.key == group), None
        )
        if members is not None and index is not None:
            rows = members.component_parameters()
            bases = members.component_bases()
            width = max(1, len(bases))
            count = len(rows) // width
            by_id = {p.canonical_id: p for p in members.parameters_all}
            for j in range(int(index), count - 1):
                for base in bases:
                    here, after = by_id.get(f"{base}.{j}"), by_id.get(f"{base}.{j + 1}")
                    if here is None or after is None:
                        continue
                    here.value = after.value
                    here.bounds = after.bounds
                    here.fixed = after.fixed
        return self.change_components(group, -1)

    def _value_of_instrument(self, canonical: str) -> float:
        for parameter in self.parameters_all:
            if getattr(parameter, "canonical_id", None) == canonical:
                return float(parameter.value)
        return 0.0

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
        if name.startswith("selection_") and name in self.__dict__.get("_selections", {}):
            return self._selections[name]
        try:
            document = object.__getattribute__(self, "_document")
        except Exception:
            raise AttributeError(name)
        presentation = document.get("presentation", {})
        if name in presentation.get("distributions", {}):
            return self.presented_distribution(name)
        if any(name in presentation.get(kind, {}) for kind in ("statistics", "reports", "values")):
            return self._presented_number(name)
        raise AttributeError(name)

    def _update_statistics(self) -> None:
        statistics = self.presentation.get("statistics", {})
        # Reporting a description asks the application for (an efficiency
        # from a density): a Python function of parameters, called on demand
        # rather than evaluated by the graph on every fit iteration.
        reports = self.presentation.get("reports", {})
        # A number a node computes anyway (a second chi-square, an entropy),
        # read from its port.
        values = self.presentation.get("values", {})
        if not statistics and not reports and not values:
            return
        outputs = self.__dict__.get("_statistic_parameters")
        if outputs is None:
            outputs = {}
            for key, info in {**statistics, **reports, **values}.items():
                outputs[key] = FittingParameter(
                    value=0.0, name=info.get("label", key), fixed=True, is_output=True
                )
                # Not a parameter of the BFF model: derived from it, shown beside it.
                outputs[key].canonical_id = f"output.{key}"
            self.__dict__["_statistic_parameters"] = outputs
            self.__dict__["outputs"] = FittingParameterGroup(
                parameters=list(outputs.values()), name="Outputs"
            )
            self._forget_discovery()
        for key in (*statistics, *reports, *values):
            try:
                outputs[key].value = self._presented_number(key)
            except Exception:
                pass

    def _presented_number(self, key: str) -> float:
        """A statistic, report or value the description presents, computed now."""
        presentation = self.presentation
        if key in presentation.get("statistics", {}):
            import chisurf.core.fluorescence.general as general

            info = presentation["statistics"][key]
            # One distribution, or several a statistic compares (a FRET
            # efficiency is the contrast of two lifetime spectra).
            names = info["of"] if isinstance(info["of"], list) else [info["of"]]
            spectra = [self.presented_distribution(name) for name in names]
            if any(spectrum.size < 2 for spectrum in spectra):
                raise ValueError(f"{key!r}: a distribution it reads is empty")
            return float(getattr(general, info["statistic"])(*spectra))
        problem = self.problem
        if problem is None:
            raise ValueError(f"the model is incomplete: missing {', '.join(self.missing)}")
        if key in presentation.get("reports", {}):
            return float(self._call_report(problem, presentation["reports"][key]))
        return self._node_value(presentation["values"][key])

    def nuisance_parameter_names(self) -> typing.Set[str]:
        """The names of the parameters in the description's instrument groups.

        What a fit group keeps local to each curve when it links the rest:
        ``presentation.nuisance_groups``, or the ``instrument`` group.
        """
        groups = set(self.presentation.get("nuisance_groups", ["instrument"]))
        return {
            p.name
            for key, group in self._groups.items()
            if key in groups
            for p in group.parameters_all
        }

    def _node_value(self, info: dict) -> float:
        """A scalar a description names by node and port, from the live model."""
        problem = self.problem
        active = problem.get_active_structure()
        return float(
            np.atleast_1d(
                problem.get_structure_port(active, f"{active}.{info['node']}", info["port"])
            )[0]
        )

    # --- regularization ----------------------------------------------------------
    @property
    def l_curve(self):
        """The last regularization sweep (:meth:`compute_l_curve`), or None."""
        return self.__dict__.get("_l_curve")

    def compute_l_curve(
        self,
        n_points: int = 16,
        log10_min: typing.Optional[float] = None,
        log10_max: typing.Optional[float] = None,
    ) -> None:
        """Sweep the description's regularization parameter and record misfit against solution.

        ``presentation.regularization`` names the parameter (a log10 weight)
        and the node ports holding the misfit and the solution's norm; the
        parameter is put back afterwards.
        """
        import chisurf.core.math.regularization as regularization

        info = self.presentation.get("regularization")
        problem = self.problem
        if not info or problem is None:
            raise RuntimeError(f"{self.name!r} has no regularization to sweep")
        port = problem.get_parameter(info["parameter"])
        center = float(port.value)
        low = center - 2.0 if log10_min is None else float(log10_min)
        high = center + 2.0 if log10_max is None else float(log10_max)
        weights = np.linspace(low, high, max(2, int(n_points)))
        held = port.fixed
        misfit, solution = [], []
        try:
            port.fixed = False
            for weight in weights:
                port.value = float(weight)
                misfit.append(self._node_value(info["misfit"]))
                solution.append(abs(self._node_value(info["solution"])))
        finally:
            port.value = center
            port.fixed = held
        misfit, solution = np.asarray(misfit), np.asarray(solution)
        corner = None
        try:
            corner = int(regularization.discrete_lcurve_corner(misfit, solution))
        except Exception:
            pass
        self.__dict__["_l_curve"] = regularization.LCurveData(
            reg=10.0**weights, residual_norm=misfit, solution_norm=solution, corner_index=corner
        )
        self.__dict__["_l_curve_log10"] = weights

    def set_reg_from_lcurve_index(self, index: int) -> None:
        """Commit the swept weight at ``index`` to the regularization parameter."""
        weights = self.__dict__.get("_l_curve_log10")
        info = self.presentation.get("regularization")
        if weights is None or not info or self.problem is None:
            return
        port = self.problem.get_parameter(info["parameter"])
        held = port.fixed
        port.fixed = False
        port.value = float(weights[int(index)])
        port.fixed = held
        self.update()

    def _call_report(self, problem, info: dict):
        """A report's function on its arguments: `#parameter`, `@axis.<name>` or a number."""
        import importlib

        module_name, function_name = info["function"].split(":")
        function = getattr(importlib.import_module(module_name), function_name)
        axes = self._structure_axes(problem.get_active_structure())
        arguments = {}
        for name, reference in info.get("arguments", {}).items():
            if isinstance(reference, str) and reference.startswith("#"):
                arguments[name] = float(problem.get_parameter(reference[1:]).value)
            elif isinstance(reference, str) and reference.startswith("@axis."):
                arguments[name] = axes[reference[len("@axis.") :]]
            else:
                arguments[name] = reference
        return function(**arguments)

    def _structure_axes(self, key: str) -> dict:
        """The axis values of a structure key, read against the description's template key."""
        import re

        template = (self._document.get("template") or {}).get("key", "")
        names = re.findall(r"\{(\w+)\}", template)
        if not names:
            return {}
        pattern = re.escape(template)
        for name in names:
            pattern = pattern.replace(re.escape("{" + name + "}"), f"(?P<{name}>-?\\d+)")
        match = re.fullmatch(pattern, key)
        return {k: int(v) for k, v in match.groupdict().items()} if match else {}

    def get_plot_reference_modes(self):
        from chisurf.core.plotting.reference_modes import modes_named

        names = [*self.presentation.get("reference_modes", []), *type(self).reference_modes]
        return modes_named(dict.fromkeys(names), model=self)

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

    def get_curves(self, copy_curves: bool = False):
        """The model curve, and the curves the layout draws beside it (the IRF).

        A measured IRF is drawn as loaded, at its own height, as the classic
        lifetime model drew it; a modelled one is the node that models it.
        """
        from chisurf.core.curve import Curve

        curves = super().get_curves(copy_curves)
        for label, info in ((_layout_for(self.family) or {}).get("curves") or {}).items():
            source = self.__dict__.get("_sources", {}).get(info.get("dataset", ""))
            if source is not None:
                curves[label] = Curve(
                    x=np.asarray(source.x), y=np.asarray(source.y), copy_array=copy_curves
                )
                continue
            problem = self.problem
            node = info.get("node")
            if problem is None or not node:
                continue
            active = problem.get_active_structure()
            try:
                y = np.array(problem.get_structure_output(active, f"{active}.{node}"), dtype=float)
            except Exception:
                continue
            if y.size == np.asarray(self.x).size:
                curves[label] = Curve(x=np.asarray(self.x), y=y, copy_array=copy_curves)
        return curves

    def evaluate_lifetime_spectrum(self, lifetime_spectrum) -> np.ndarray:
        """The model's decay for an interleaved ``[a0, tau0, a1, tau1, ...]``.

        Evaluated at that spectrum with everything else as fitted -- instrument,
        background, scatter -- and then put back exactly as it was: the active
        structure, the lifetime parameters and the curve. The filter calculator
        uses this to turn a fit into detector patterns for a spectrum it chose.

        Raises
        ------
        ValueError
            If the family has no ``lifetime.components.{n}`` structure for the
            spectrum's number of components.
        """
        spectrum = np.asarray(lifetime_spectrum, dtype=float).ravel()
        n = spectrum.size // 2
        problem = self.problem
        key = f"lifetime.components.{n}"
        if problem is None or n == 0 or key not in set(problem.get_structure_keys()):
            raise ValueError(f"{type(self).__name__} has no {n}-component lifetime structure")
        ids = set(problem.get_parameter_ids())
        names = [f"lifetime.{kind}.{i}" for i in range(n) for kind in ("amplitude", "tau")]
        if not set(names) <= ids:
            raise ValueError(f"{type(self).__name__} does not name its lifetime components")
        active = str(problem.get_active_structure())
        saved = {name: float(problem.get_parameter(name).value) for name in names}
        saved_y = np.array(self.y, dtype=float, copy=True)
        try:
            problem.select_structure(key)
            for name, value in zip(names, spectrum):
                port = problem.get_parameter(name)
                was = port.fixed
                port.fixed = False
                port.value = float(value)
                port.fixed = was
            node = problem.get_structure_curve_node(key, self.primary_dataset)
            return np.array(problem.get_structure_output(key, node), dtype=float)
        finally:
            problem.select_structure(active)
            for name, value in saved.items():
                port = problem.get_parameter(name)
                was = port.fixed
                port.fixed = False
                port.value = value
                port.fixed = was
            self.y = saved_y

    # --- persistence -----------------------------------------------------------
    def get_state(self) -> dict:
        problem = self.problem
        state = {
            "family": self.family,
            "scalars": dict(self._scalars),
            # By name: a source is another fit, which a project restores itself.
            "source_fits": list(self._source_names),
            "datasets": {
                slot: {
                    "x": np.asarray(getattr(c, "x", []), dtype=float).tolist(),
                    "y": np.asarray(c.y, dtype=float).tolist(),
                }
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
            self.set_dataset(
                slot, chisurf.core.curve.Curve(x=np.asarray(curve["x"]), y=np.asarray(curve["y"]))
            )
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
        layout = _layout_for(family) or {}
        bases: typing.Tuple[type, ...] = (DescriptionModel,)
        if layout.get("classic_editor"):
            # The groups the classic editor's view files address (convolve,
            # generic, lifetimes, anisotropy, ...), over this view's parameters.
            from chisurf.core.models.tcspc.classic_editor import ClassicTCSPCEditor

            bases = (ClassicTCSPCEditor, DescriptionModel)
        name = layout.get("names", {}).get(family) or document.get("title", family)
        cls = type(
            f"DescriptionModel_{family}",
            bases,
            {"family": family, "name": name, "__module__": __name__},
        )
        _FAMILIES[family] = cls
        globals()[cls.__name__] = cls
    return cls


def for_catalogue(
    path,
    name: typing.Optional[str] = None,
    module: typing.Optional[str] = None,
    frame: str = "equations",
    reference_modes: typing.Sequence[str] = (),
    view=None,
    entries: typing.Sequence[str] = (),
    labels: typing.Optional[typing.Mapping[str, str]] = None,
    mixins: typing.Sequence[type] = (),
) -> type:
    """The model class ChiSurf lists for one equation catalogue.

    The catalogue is ChiSurf's (YAML beside the experiment's models); BFF
    builds every entry as a competing structure and knows nothing about what
    the equations describe. *frame* names the BFF frame the equations sit in:
    ``equations`` compares them to the data directly, ``equations_convolved``
    convolves them with a measured response and a counting instrument first.
    *reference_modes* names the plot normalisations of
    :mod:`chisurf.core.plotting.reference_modes` the curves support -- the
    catalogue's meaning is ChiSurf's, so they are declared here rather than
    in a BFF presentation.
    """
    import pathlib

    path = pathlib.Path(path).resolve()
    key = f"{frame}:{path}:{','.join(entries)}"
    cls = _FAMILIES.get(key)
    if cls is None:
        attributes = {
            "catalogue_path": path,
            "family": frame,
            "__module__": module or __name__,
            "reference_modes": tuple(reference_modes),
        }
        if name:
            attributes["name"] = name
        if view is not None:
            attributes["view_file"] = pathlib.Path(view).resolve()
        if entries:
            attributes["catalogue_entries"] = tuple(entries)
        if labels:
            attributes["parameter_labels"] = dict(labels)
        bases: typing.Tuple[type, ...] = (*mixins, DescriptionModel)
        if (_layout_for(frame) or {}).get("classic_editor"):
            from chisurf.core.models.tcspc.classic_editor import ClassicTCSPCEditor

            bases = (ClassicTCSPCEditor, *bases)
        cls = type(f"EquationModel_{path.parent.name}", bases, attributes)
        _FAMILIES[key] = cls
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


__all__ = [
    "DescriptionGroup",
    "DescriptionModel",
    "DescriptionParameter",
    "for_catalogue",
    "for_family",
]
