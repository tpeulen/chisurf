r"""ndX's constants as ChiSurf fitting parameters.

ndX derives its FRET columns from a handful of scalar constants
(``gG/gR``, ``alpha``, ``beta``, ``r``, the backgrounds, ``PhiA``/``PhiD``,
``forster_radius``, ``tauD0``, …). Inside ndX they are numbers in a table:
typed in, not fitted, not shared, and invisible to the rest of ChiSurf.

This module turns them into real
:class:`~chisurf.core.fitting.parameter.FittingParameter`\\s in a
:class:`~chisurf.core.fitting.parameter.FittingParameterGroup`. That is what
makes them first-class in ChiSurf:

* they appear in the **Global View** alongside every fit parameter, because the
  group is published in the out-of-fit parameter registry;
* they carry a process-wide ``unique_identifier``, so a fit parameter can be
  **linked** to one — one number, one owner, many consumers;
* they can be bounded, fixed, freed and given priors like any other parameter.

The group is a *view* of one window: :meth:`NdxConstants.pull` reads the window's
constants into the parameters, :meth:`NdxConstants.push` writes them back and
makes ndX recompute. Which constants exist is read from the window rather
than hard-coded, so a setup with extra constants exposes those too.

Parameters are created **free**, so they show up in the Global View without
switches. Nothing optimizes them by itself — a registered group is not part of
any fit's model — so "free" here means *available*: a fit parameter linked to one
can be fitted, and until that happens the number simply sits there with its
bounds.
"""

from __future__ import annotations

import re

import numpy as np

from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup

__all__ = [
    "NdxConstants",
    "CONSTANT_BOUNDS",
    "bind_ndx_parameters",
    "unbind_ndx_parameters",
    "bound_ndx_parameters",
]

#: Bounds per known ndX constant: ``name -> (lower, upper)``. Anything not
#: listed gets no bounds — the point is to keep a physical quantity physical
#: (a quantum yield cannot exceed 1), not to guess limits for unknown entries.
CONSTANT_BOUNDS: dict[str, tuple[float, float]] = {
    "gG/gR": (1e-6, 1e6),
    "alpha": (0.0, 1.0),  # donor leakage
    "beta": (0.0, 1.0),  # ndx "beta" is the direct-excitation coefficient
    "r": (1e-6, 1e6),  # scales I_AA in the stoichiometry (1/beta_Hellenkamp)
    "Bg": (0.0, 1e6),
    "Br": (0.0, 1e6),
    "By": (0.0, 1e6),
    "PhiA": (0.0, 1.0),
    "PhiD": (0.0, 1.0),
    "forster_radius": (1.0, 200.0),
    "tauD0": (1e-3, 1e3),
    "kappa2": (0.0, 4.0),
    "omega_r_um": (1e-3, 1e2),
    "T_K": (0.0, 1e4),
    "eta_Pa_s": (0.0, 1e3),
}


def _attribute_name(constant: str) -> str:
    """Return a Python attribute name for an ndX constant name.

    Constants like ``gG/gR`` are not identifiers; the parameter keeps the ndX
    spelling as its ``name`` (that is what a user recognises) while the attribute
    it is stored under is sanitized, because group discovery scans attributes.
    """
    return "_c_" + re.sub(r"[^0-9a-zA-Z_]", "_", str(constant))


class NdxConstants(FittingParameterGroup):
    """The scalar constants of one ndX window, as fitting parameters.

    Parameters
    ----------
    constants : dict, optional
        Initial ``{name: value}`` mapping; usually the window's own constants.
    name : str, optional
        Group name shown in the Global View.

    Attributes
    ----------
    constant_names : list of str
        The ndX constant names currently exposed, in insertion order.
    """

    def __init__(self, constants: dict | None = None, name: str = "ndX"):
        """Create the group and one parameter per constant."""
        super().__init__(name=name)
        #: ndX constant name -> FittingParameter
        self._by_constant: dict[str, FittingParameter] = {}
        #: The window this group is a view of (set by :func:`bind_ndx_parameters`).
        self._window = None
        if constants:
            self.adopt(constants)
        self.find_parameters()

    def update(self, *args, **kwargs) -> None:
        """Refresh, and carry any edited value into the bound window.

        A parameter edited in the Global View writes straight into the parameter
        object; nothing tells ndX. Hooking the group's refresh means the
        two cannot drift: whenever ChiSurf refreshes this group, a value that no
        longer matches the window is pushed and the window recomputes. The
        comparison keeps it a no-op — and free — when nothing changed.
        """
        parent_update = getattr(super(), "update", None)
        if callable(parent_update):
            parent_update(*args, **kwargs)
        window = self._window
        if window is None:
            return
        current = getattr(window, "constants", None)
        if not isinstance(current, dict):
            return
        values = self.as_dict()
        if any(current.get(name) != value for name, value in values.items()):
            try:
                self.push(window)
            except Exception:
                pass

    # ── construction ──
    def adopt(self, constants: dict) -> list[str]:
        """Create or update a parameter for every numeric entry of *constants*.

        Parameters
        ----------
        constants : dict
            ``{name: value}`` as ndX holds them. Non-numeric entries are
            skipped.

        Returns
        -------
        list of str
            The constant names that were newly created.
        """
        created: list[str] = []
        for key, value in dict(constants or {}).items():
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(number):
                continue
            parameter = self._by_constant.get(str(key))
            if parameter is None:
                bounds = CONSTANT_BOUNDS.get(str(key))
                parameter = FittingParameter(
                    value=number,
                    name=str(key),
                    fixed=False,
                    lb=bounds[0] if bounds else float("-inf"),
                    ub=bounds[1] if bounds else float("inf"),
                    bounds_on=bounds is not None,
                )
                self._by_constant[str(key)] = parameter
                setattr(self, _attribute_name(key), parameter)
                created.append(str(key))
            else:
                parameter.value = number
        if created:
            self.find_parameters()
        return created

    @property
    def constant_names(self) -> list[str]:
        """The ndX constant names exposed by this group."""
        return list(self._by_constant)

    def parameter(self, constant: str) -> FittingParameter | None:
        """Return the parameter of one ndX constant (``None`` if absent)."""
        return self._by_constant.get(str(constant))

    def as_dict(self) -> dict:
        """Return the current values as an ndX constants mapping."""
        return {name: float(p.value) for name, p in self._by_constant.items()}

    # ── synchronisation with a window ──
    def pull(self, ndx) -> list[str]:
        """Read the window's constants into the parameters.

        Parameters
        ----------
        ndx : object
            In-process ndX window.

        Returns
        -------
        list of str
            Constants that appeared for the first time.
        """
        return self.adopt(getattr(ndx, "constants", {}) or {})

    def push(self, ndx, *, recompute: bool = True) -> dict:
        """Write the parameter values into the window and recompute it.

        Parameters
        ----------
        ndx : object
            In-process ndX window.
        recompute : bool, optional
            Recompute ndX's derived columns and refresh its plots.

        Returns
        -------
        dict
            The constants that were applied.
        """
        values = self.as_dict()
        constants = getattr(ndx, "constants", None)
        if not isinstance(constants, dict):
            constants = {}
            ndx.constants = constants
        constants.update(values)
        editor = getattr(ndx, "parameter_control", None)
        if editor is not None:
            try:
                editor.update(values)
            except Exception:
                pass
        if recompute:
            data_source = getattr(ndx, "data_source", None)
            if data_source is not None and hasattr(data_source, "compute_columns"):
                try:
                    data_source.compute_columns(
                        constants=ndx.constants, equations=getattr(ndx, "equations", None)
                    )
                except Exception:
                    pass
            update = getattr(ndx, "update_plots", None)
            if callable(update):
                try:
                    update()
                except Exception:
                    pass
        return values

    def as_calibration(self, calibration=None):
        """Return these constants as a Hellenkamp calibration group.

        ndX's names are not Hellenkamp's — its ``beta`` is the direct
        excitation δ and its ``r`` is ``1/β`` — so the two views are kept
        separate and converted explicitly.

        Parameters
        ----------
        calibration : CalibrationParameters, optional
            Group to fill in place; a fresh one is created when omitted.

        Returns
        -------
        CalibrationParameters
            The calibration view of the same numbers.
        """
        from chisurf.core.fluorescence.fret.calibration import calibration_from_ndx_constants

        return calibration_from_ndx_constants(self.as_dict(), calibration)


#: Strong references to the groups bound to live windows, keyed by owner id.
#: The Global View registry holds groups weakly, so something has to own them;
#: the binding does, and drops them when the window goes away.
_BOUND: dict[str, tuple[NdxConstants, object]] = {}


def bind_ndx_parameters(
    ndx, *, owner_id: str = "ndxplorer", label: str = "ndX constants"
) -> NdxConstants:
    """Expose a window's constants as fitting parameters in the Global View.

    Parameters
    ----------
    ndx : object
        In-process ndX window.
    owner_id : str, optional
        Registry slot; re-binding the same id replaces the previous group.
    label : str, optional
        Label shown in the Global View's owner column.

    Returns
    -------
    NdxConstants
        The bound group (already filled from the window).
    """
    from chisurf.core.registry.parameter_groups import register_parameter_group

    group = NdxConstants(name=label)
    group.pull(ndx)
    group._window = ndx
    _BOUND[owner_id] = (group, ndx)
    register_parameter_group(group, owner_id=owner_id, label=label)

    # Drop the binding when the window is destroyed, so the Global View does not
    # keep offering link targets that write into a dead window.
    destroyed = getattr(ndx, "destroyed", None)
    if destroyed is not None and hasattr(destroyed, "connect"):
        try:
            destroyed.connect(lambda *_: unbind_ndx_parameters(owner_id))
        except Exception:
            pass
    return group


def unbind_ndx_parameters(owner_id: str = "ndxplorer") -> None:
    """Remove a bound group from the Global View and drop its reference."""
    from chisurf.core.registry.parameter_groups import unregister_parameter_group

    _BOUND.pop(owner_id, None)
    try:
        unregister_parameter_group(owner_id)
    except Exception:
        pass


def bound_ndx_parameters(owner_id: str = "ndxplorer") -> NdxConstants | None:
    """Return the group bound to *owner_id* (``None`` when nothing is bound)."""
    entry = _BOUND.get(owner_id)
    return entry[0] if entry else None
