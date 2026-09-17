from __future__ import annotations

import numpy as np

import chisurf.core.fitting
import chisurf.core.settings
import chisurf.core.support.decorators
from chisurf import typing
from chisurf.core import base, parameter

# parameter_settings = chisurf.core.settings.parameter


class FittingParameter(chisurf.core.parameter.Parameter):
    """Fit parameter with bounds, fixed flag and optional scan results.

    This is the high-level parameter type used throughout the fitting
    machinery. It extends :class:`chisurf.core.parameter.Parameter` with
    attributes for error estimates and chi² scans.

    Examples
    --------
    Create a simple fitting parameter and change its value:

    >>> from chisurf.core.fitting.parameter import FittingParameter
    >>> p = FittingParameter(name="amp", value=1.0)
    >>> float(p)
    1.0
    >>> p.value = 2.5
    >>> float(p)
    2.5
    """

    def __init__(
        self,
        value: float = 1.0,
        link: chisurf.core.parameter.Parameter = None,
        lb: float = float("-inf"),
        ub: float = float("inf"),
        bounds_on: bool = False,
        fixed: bool = False,
        *args,
        **kwargs,
    ):
        """Initialize a fitting parameter.

        Parameters
        ----------
        value : float, optional
            Initial parameter value.
        link : Parameter, optional
            Link to another parameter.
        lb : float, optional
            Lower bound.
        ub : float, optional
            Upper bound.
        bounds_on : bool, optional
            Whether bounds are active.
        fixed : bool, optional
            Whether the parameter is fixed during optimization.
        """
        super().__init__(*args, value=value, link=link, ub=ub, lb=lb, bounds_on=bounds_on, **kwargs)
        self.fixed = fixed
        # Stored under its public name so the serialised form is unchanged: a
        # property is a data descriptor and wins over the instance dict, so the
        # accessors below still run while ``to_dict``/``__getstate__`` continue
        # to see a plain ``redundant`` entry as they always did.
        self.__dict__["redundant"] = False
        self._error_estimate = None
        self._chi2s = None
        self._values = None
        self._scan_result = None

    @property
    def redundant(self) -> bool:
        """Whether this parameter is fully determined by its siblings.

        A redundant parameter carries no degree of freedom of its own and is
        kept out of the optimiser. Distinct from :attr:`fixed`: a redundant
        parameter is still *written* -- its value follows from the others -- it
        simply is not varied (the last amplitude of a normalised set was the
        classic case).
        """
        return self.__dict__.get("redundant", False)

    @redundant.setter
    def redundant(self, v: bool):
        """Set the redundancy flag, invalidating cached free-parameter lists.

        Redundancy is one of the three tests that decide whether a parameter is
        free, so changing it changes the parameter vector -- exactly what the
        cached lists and the factor graph are keyed on.
        """
        was = bool(self.__dict__.get("redundant", False))
        self.__dict__["redundant"] = bool(v)
        if was != bool(v):
            from chisurf.core.fitting import factorgraph

            factorgraph.bump_structure_version()

    @property
    def parameter_scan(self) -> typing.Tuple[np.array, np.array]:
        """Return the stored parameter scan values and chi² curve.

        The return value is a pair ``(values, chi2s)`` or ``(None, None)``
        if no scan has been performed yet.
        """
        return self._values, self._chi2s

    @parameter_scan.setter
    def parameter_scan(self, v: typing.Tuple[np.array, np.array]):
        """Store the parameter scan values and chi² curve."""
        self._values, self._chi2s = v

    @property
    def error_estimate(self) -> float:
        """One-sigma error estimate associated with the parameter.

        If the parameter is linked, the error estimate of the link target is
        returned. If no estimate has been computed yet, ``NaN`` is returned.
        """
        if self.is_linked:
            return self._link.error_estimate
        else:
            if isinstance(self._error_estimate, float):
                return self._error_estimate
            else:
                return float("nan")

    @error_estimate.setter
    def error_estimate(self, v: float):
        """Set the stored error estimate (in the same units as ``value``)."""
        self._error_estimate = v

    @property
    def scan_result(self) -> typing.Union[typing.Dict, None]:
        """Return the full result dict from the last smart scan, or None."""
        return self._scan_result

    @scan_result.setter
    def scan_result(self, v: typing.Dict):
        """Store the full result dict from a smart scan."""
        self._scan_result = v

    def scan(self, fit: chisurf.core.fitting.fit.Fit, rel_range: float = None, **kwargs) -> None:
        """Trigger a chi² scan for this parameter on the given fit.

        This is a thin wrapper around :meth:`chisurf.core.fitting.fit.Fit.chi2_scan`
        which stores the resulting scan on the :class:`Fit` instance.
        """
        fit.chi2_scan(parameter_name=self.name, rel_range=rel_range, **kwargs)

    def adaptive_scan(
        self,
        fit: chisurf.core.fitting.fit.Fit,
        scan_range: typing.Tuple[float, float] = (None, None),
        p_value: float = 0.99,
        **kwargs,
    ) -> typing.Dict:
        """Trigger an adaptive F-test-driven chi² scan.

        This is a thin wrapper around
        :meth:`chisurf.core.fitting.fit.Fit.adaptive_chi2_scan`.
        """
        return fit.adaptive_chi2_scan(
            parameter_name=self.name, scan_range=scan_range, p_value=p_value, **kwargs
        )

    def update(self) -> None:
        """Update the UI controller for this parameter."""
        controller = getattr(self, "controller", None)
        if controller is not None and hasattr(controller, "finalize"):
            try:
                controller.finalize()
            except Exception as e:
                import chisurf.logging

                chisurf.logging.error(f"Failed to finalize parameter controller: {e}")

    def __getstate__(self):
        """Return a picklable representation of the fitting parameter."""
        state = super().__getstate__()
        return state

    def __setstate__(self, state):
        """Restore state from :meth:`__getstate__` output."""
        super().__setstate__(state)

    def __str__(self):
        """Return a human-readable description of the fitting parameter."""
        s = "\nVariable\n"
        s += f"name: {self.name}\n"
        s += f"value: {self.value:.6g}\n"
        try:
            ee = self.error_estimate
            if isinstance(ee, float) and not self.fixed:
                rel = (
                    abs(ee / (self.value + 1e-12) * 100.0)
                    if np.isfinite(self.value)
                    else float("nan")
                )
                src = "support plane" if self.scan_result is not None else "covariance"
                s += f"error: {ee:.4g} ({rel:.0f}%) [{src}]\n"
        except Exception:
            pass
        s += f"fixed: {self.fixed}\n"
        if self.bounds_on:
            bounds = getattr(self, "bounds", None)
            if isinstance(bounds, (tuple, list)) and len(bounds) == 2:
                s += f"bounds: [{bounds[0]:.4g}, {bounds[1]:.4g}]\n"
        if self.is_linked:
            s += f"linked to: {self.link.name}\n"
        return s


class FittingParameterGroup(chisurf.core.parameter.ParameterGroup):
    """Group of :class:`FittingParameter` objects used by a model or fit.

    The group provides convenient access to bounds, names and values of all
    contained parameters and supports (de-)serialization via
    :meth:`to_dict` / :meth:`from_dict`.
    """

    @property
    def parameter_bounds(self) -> typing.List[typing.Tuple[float, float]]:
        """List of ``(lb, ub)`` bounds of all parameters (including fixed)."""
        frozen = self.__dict__.get("_frozen_structure")
        if frozen is not None:
            return frozen["parameter_bounds"]
        return [
            pi.bounds if getattr(pi, "bounds_on", True) else (float("-inf"), float("inf"))
            for pi in self.parameters
        ]

    @property
    def parameters_all(self) -> typing.List[chisurf.core.fitting.parameter.FittingParameter]:
        """List of all fitting parameters, including fixed and linked.

        Discovery is lazy. ``_parameters`` is ``None`` until :meth:`find_parameters`
        has walked the group once, and reading this property is what triggers that
        first walk. Discovery cannot run in ``__init__`` — a subclass attaches its
        parameters *after* ``super().__init__`` — so it used to happen only as a
        side effect of :meth:`chisurf.core.models.model.Model.update` and of
        :meth:`chisurf.core.fitting.fit.FitGroup.run`. A model that had not been
        through either reported **no parameters at all** to everything reading it
        from the outside (the RPC fit DTOs, and through them the parameter link
        menu and the Global View) while its own widgets, which hold their
        parameters directly, showed the full set.

        An empty *list* is a real answer — a group that owns no parameters — and is
        not re-walked. Only ``None`` means "never looked".
        """
        parameters = self.__dict__.get("_parameters")
        if parameters is None:
            # ``find_parameters`` reads attributes that may lead back here; the
            # in-progress walk answers with what it has rather than recursing.
            if self.__dict__.get("_finding_parameters"):
                return list()
            self.find_parameters()
            parameters = self.__dict__.get("_parameters")
            if parameters is None:  # a subclass that does not discover anything
                parameters = list()
                self._parameters = parameters
        return parameters

    @property
    def parameters(self) -> typing.List[chisurf.core.fitting.parameter.FittingParameter]:
        """List of *free* fitting parameters (not fixed, linked or redundant).

        Cached against the structure version. Deciding freedom costs three
        attribute reads per parameter, two of which cross into the underlying
        chinet port, and this property is consulted several times per objective
        evaluation -- it was the single largest cost of a sampling run, above
        the model evaluation itself. Every input to the filter (``fixed``,
        ``link``, ``redundant``, and rediscovery) bumps
        :func:`chisurf.core.fitting.factorgraph.structure_version`, so the cache
        cannot go stale.

        The cache is stored as a *tuple*, which
        :func:`chisurf.core.base.find_objects` does not descend into -- a list
        would make :meth:`find_parameters` rediscover these parameters through
        the cache itself. A fresh list is returned so callers may mutate it.
        """
        frozen = self.__dict__.get("_frozen_structure")
        if frozen is not None:
            # Inside a fit or sampling run the structure is fixed by contract
            # (see factorgraph.frozen_structure), so there is nothing to check.
            return frozen["parameters"]
        from chisurf.core.fitting import factorgraph

        all_parameters = self.parameters_all
        version = factorgraph.structure_version()
        cache = self.__dict__.get("_free_parameter_cache")
        if cache is not None and cache[0] == version and cache[1] is all_parameters:
            return list(cache[2])
        free = tuple(
            p
            for p in all_parameters
            if not (p.fixed or p.is_linked or getattr(p, "redundant", False))
        )
        self.__dict__["_free_parameter_cache"] = (version, all_parameters, free)
        return list(free)

    @property
    def parameters_all_dict(
        self,
    ) -> typing.Dict[str, chisurf.core.fitting.parameter.FittingParameter]:
        """Dictionary mapping parameter names to all parameters."""
        return dict([(p.name, p) for p in self.parameters_all])

    @property
    def parameters_dict(self):
        """Dictionary mapping parameter names to free parameters only."""
        return dict([(p.name, p) for p in self.parameters])

    @property
    def aggregated_parameters(self):
        """Nested :class:`FittingParameterGroup` instances discovered below.

        These are populated by :meth:`find_parameters` and used to implement
        hierarchical parameter collections.
        """
        a = list()
        for value in self.__dict__.values():
            if isinstance(value, FittingParameterGroup):
                a.append(value)
        seen = set()
        return [x for x in a if not (x in seen or seen.add(x))]

    @property
    def parameter_dict(self) -> typing.Dict[str, chisurf.core.fitting.parameter.FittingParameter]:
        """Alias for :attr:`parameters_dict` kept for backwards-compatibility."""
        re = dict()
        for p in self.parameters:
            re[p.name] = p
        return re

    @property
    def parameter_names(self) -> typing.List[str]:
        """Names of all free fitting parameters."""
        frozen = self.__dict__.get("_frozen_structure")
        if frozen is not None:
            return frozen["parameter_names"]
        return [p.name for p in self.parameters]

    @property
    def parameter_values(self) -> typing.List[float]:
        """Values of all free fitting parameters."""
        return [p.value for p in self.parameters]

    @parameter_values.setter
    def parameter_values(self, vs: typing.List[float]):
        """Set values of all free parameters.

        Parameters
        ----------
        vs : list of float
            New parameter values in the same order as :attr:`parameters`.
        """
        ps = self.parameters
        for i, v in enumerate(vs):
            ps[i].value = v

    def to_dict(
        self,
        remove_protected: bool = False,
        copy_values: bool = True,
        convert_values_to_elementary: bool = False,
        skip_qt_widgets: bool = False,
    ) -> typing.Dict:
        """Serialize the group and its parameters to a plain dictionary."""
        s = super().to_dict(
            remove_protected=remove_protected,
            copy_values=copy_values,
            convert_values_to_elementary=convert_values_to_elementary,
            skip_qt_widgets=skip_qt_widgets,
        )
        parameters = dict()
        s["parameter"] = parameters
        for p in self.parameters_all:
            parameters[p.name] = p.to_dict(
                remove_protected=remove_protected,
                copy_values=copy_values,
                convert_values_to_elementary=convert_values_to_elementary,
            )
        return s

    def from_dict(self, v: dict):
        """Restore parameter values from a dictionary created by :meth:`to_dict`."""
        self.find_parameters()
        parameter_target = self.parameters_all_dict
        parameter = v["parameter"]
        for parameter_name in parameter:
            pn = str(parameter_name)
            try:
                parameter_target[pn].from_dict(parameter[pn])
            except KeyError:
                chisurf.logging.warning(f"Key {pn} not found skipping")

    def find_parameters(self, parameter_type=FittingParameter) -> None:
        """Discover parameters and nested groups attached to this instance.

        This scans the attributes of the group, finds instances of
        :class:`FittingParameter` (or subclasses) and aggregates them into
        :attr:`_parameters` and :attr:`_aggregated_parameters`.
        """
        self._aggregated_parameters = None
        self._parameters = None
        self.__dict__["_finding_parameters"] = True
        try:
            d = [v for v in self.__dict__.values() if v is not self]
            ag = base.find_objects(search_iterable=d, searched_object_type=FittingParameterGroup)
            self._aggregated_parameters = ag

            ap = list()
            from chisurf.core.models.model import Model

            for o in ag:
                if not isinstance(o, Model):
                    o.find_parameters()
                    # Do NOT overwrite existing attributes with group names to avoid collisions
                    if o.name not in self.__dict__:
                        self.__dict__[o.name] = o
                    ap += o.parameters_all

            # Search using the base Parameter class for robustness.
            # FittingParameter is renamed by @register so isinstance against FittingParameter
            # can be unreliable; searching by base class always works.
            mp = base.find_objects(search_iterable=d, searched_object_type=parameter.Parameter)
            # Constructor-supplied parameters come first: they are the group's
            # own, and clearing ``_parameters`` above has just hidden them from
            # the ``__dict__`` walk.
            explicit = list(self.__dict__.get("_explicit_parameters") or ())
            seen = set()
            self._parameters = [x for x in (explicit + mp + ap) if not (x in seen or seen.add(x))]
        finally:
            self.__dict__.pop("_finding_parameters", None)

        # Rediscovery can change the parameter vector (order, membership), which
        # is exactly what a cached factor graph is indexed by.
        from chisurf.core.fitting import factorgraph

        factorgraph.bump_structure_version()

    def append_parameter(self, p: parameter.Parameter):
        """Append a new :class:`FittingParameter` to this group."""
        self.parameters_all.append(p)

    def finalize(self):
        """Finalize parameter controllers, if present.

        This is primarily used by GUI code so that widgets controlling
        parameters can release resources when the fit is closed.

        Having **no** controller is the ordinary case, not a fault: a headless
        run has no widgets at all, and a parameter drawn by a table or a
        rate-matrix section is edited through that section rather than through a
        controller of its own. This used to log a warning for every such
        parameter on every update -- six lines per model update for a two-state
        exchange scheme -- which is how a log stops being read.
        """
        for name, param in self.parameters_all_dict.items():
            controller = getattr(param, "controller", None)
            if controller is None:
                continue
            try:
                controller.finalize()
            except Exception as e:
                chisurf.logging.warning(f"Failed to finalize controller of parameter '{name}': {e}")

    # def __getattribute__(
    #         self,
    #         item_key
    # ):
    #     item = chisurf.core.base.Base.__getattribute__(
    #         self,
    #         item_key
    #     )
    #     if isinstance(
    #             item,
    #             chisurf.core.parameter.Parameter
    #     ):
    #         return item.value
    #     else:
    #         return item

    def __len__(self):
        """Return the total number of parameters in the group."""
        return len(self.parameters_all)

    def __getstate__(self) -> dict:
        """Return a picklable state for the group and all parameters."""
        d = super().__getstate__()
        for key, value in self.parameters_all_dict.items():
            d[key] = value.__getstate__()
        return d

    def __setstate__(self, state: dict):
        """Restore state from :meth:`__getstate__` output."""
        super().__setstate__(state)

    def get_state(self) -> typing.Dict:
        """Return a JSON-serializable snapshot of this parameter group.

        The returned structure focuses on the logical parameter content and
        intentionally avoids embedding live :class:`Parameter` objects so it
        can be safely stored in JSON (e.g. as part of a project file).

        The shape is::

            {"parameters": {name: parameter_state, ...}}

        where each ``parameter_state`` is produced by
        :meth:`chisurf.core.parameter.Parameter.get_state`.
        """
        try:
            params_state: typing.Dict[str, typing.Dict] = {}
            for name, p in self.parameters_all_dict.items():
                get_state = getattr(p, "get_state", None)
                if callable(get_state):
                    try:
                        s = get_state()
                    except Exception:
                        s = {}
                    if isinstance(s, dict):
                        params_state[name] = s
            return {"parameters": params_state}
        except Exception:
            return {}

    def set_state(self, state: typing.Dict) -> None:
        """Restore group/parameter state from :meth:`get_state` output.

        This updates only contained parameters (value, bounds, fixed, etc.)
        via their :meth:`set_state` methods and then asks them to
        :meth:`update` so any GUI controllers refresh.
        """
        if not isinstance(state, dict):
            return

        param_states = state.get("parameters") or {}
        if not isinstance(param_states, dict):
            return

        # Ensure our internal parameter list is up-to-date so that
        # ``parameters_all_dict`` reflects the current structure.
        try:
            self.find_parameters(chisurf.core.fitting.parameter.FittingParameter)
        except Exception:
            pass

        try:
            targets = self.parameters_all_dict
        except Exception:
            targets = {}

        for name, p_state in param_states.items():
            if not isinstance(p_state, dict):
                continue
            p = targets.get(name)
            if p is None:
                continue
            try:
                set_state = getattr(p, "set_state", None)
                if callable(set_state):
                    set_state(p_state)
                else:
                    # Minimal fallback for non-conforming parameters
                    from chisurf.core.parameter import Parameter as _P

                    if isinstance(p, _P):
                        if "bounds" in p_state:
                            b = p_state["bounds"]
                            if isinstance(b, (list, tuple)) and len(b) == 2:
                                p.bounds = (float(b[0]), float(b[1]))
                        if "bounds_on" in p_state:
                            p.bounds_on = bool(p_state["bounds_on"])
                        if "fixed" in p_state:
                            p.fixed = bool(p_state["fixed"])
                        if "value" in p_state:
                            p.value = float(p_state["value"])
            except Exception:
                continue

        # Ensure any attached controllers/widgets see the updated state.
        try:
            for p in targets.values():
                upd = getattr(p, "update", None)
                if callable(upd):
                    upd()
        except Exception:
            pass

    def __init__(
        self,
        fit: chisurf.core.fitting.fit.Fit = None,
        model: chisurf.core.models.Model = None,
        short: str = "",
        parameters: typing.List[chisurf.core.fitting.parameter.FittingParameter] = None,
        *args,
        **kwargs,
    ):
        """Initialize a fitting parameter group.

        Parameters
        ----------
        fit : Fit, optional
            The fit this group belongs to.
        model : Model, optional
            The model this group belongs to.
        short : str, optional
            Short label for the group.
        parameters : list of FittingParameter, optional
            Initial list of parameters.
        """
        super().__init__(*args, **kwargs)
        if chisurf.core.settings.cs_settings["verbose"]:
            print("---------------")
            print(f"Class: {self.__class__.name}")
            print(kwargs)
            print("---------------")

        self.short = short
        self.model = model
        self.fit = fit

        # ``None`` marks the group as not yet walked, which is what makes the
        # discovery in :attr:`parameters_all` happen on first read. An empty list
        # here would read as "walked, owns nothing" and never be filled.
        self._parameters = parameters
        self._aggregated_parameters = list()

        # Parameters handed to the constructor are owned by the group whether or
        # not they are also reachable as attributes. :meth:`find_parameters`
        # clears ``_parameters`` before it walks ``__dict__``, so without this
        # record a group built as ``FittingParameterGroup(parameters=[p])``
        # silently lost ``p`` the first time anything rediscovered it -- and
        # rediscovery is routine, since every model runs it. Kept as a *tuple*
        # so :func:`chisurf.core.base.find_objects` does not descend into it and
        # report the same parameters twice.
        self.__dict__["_explicit_parameters"] = tuple(parameters or ())

        # Copy parameters from provided ParameterGroup
        if len(args) > 0:
            p0 = args[0]
            if isinstance(p0, FittingParameterGroup):
                self.__dict__ = p0.__dict__
