r"""A finished calibration as ChiSurf fitting parameters.

A calibration produces numbers other analyses need: :math:`\alpha`,
:math:`\beta`, :math:`\gamma`, :math:`\delta`, :math:`R_0`, and the efficiency
and distance of each population it found. Until now those lived only in this
window's tables, so every downstream fit took them as numbers somebody typed in
again — with nothing recording that the two came from the same calibration, and
nothing to update when the calibration was re-run.

Publishing them as :class:`~chisurf.core.fitting.parameter.FittingParameter`\\s
puts them in the **Global View** beside the fits, where a fit parameter can be
*linked* to one of them. One number, one owner: change the calibration and every
follower moves with it.

They are read-outs, not free parameters. Nothing optimizes them — a registered
group belongs to no fit's model — and :meth:`AccurateFretParameters.adopt`
overwrites them from the next calibration. Re-registering under the same
``owner_id`` updates the group in place, so links survive a re-run.

Mirrors :mod:`chisurf.plugins.core.lightpath_simulator.core.parameters`, which
publishes the optical path the same way; the two sit side by side in the Global
View, which is the point — an optical *prediction* of γ next to the value the
data produced.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup

__all__ = [
    "AccurateFretParameters",
    "register_calibration_parameters",
    "unregister_calibration_parameters",
    "registered_calibration_parameters",
]

#: The correction factors, in the order the paper introduces them.
_FACTORS = ("alpha", "beta", "gamma", "delta", "r0")

#: Per-factor units, for the Global View's parameter rows.
_UNITS = {"r0": "Angstrom"}


class AccurateFretParameters(FittingParameterGroup):
    """The correction factors and the populations of one calibration.

    Parameters
    ----------
    result : CalibrationResult, optional
        A finished calibration; ``None`` creates the group with the factors at
        their neutral values and no populations.
    name : str, optional
        Group name shown in the Global View.

    Attributes
    ----------
    population_labels : list of str
        Labels of the populations currently published, in order.
    """

    def __init__(self, result=None, name: str = "Accurate FRET", **kwargs):
        """Create the group, optionally filled from *result*."""
        super().__init__(name=name, **kwargs)
        self.population_labels: list[str] = []
        neutral = {"alpha": 0.0, "beta": 1.0, "gamma": 1.0, "delta": 0.0, "r0": 52.0}
        for key in _FACTORS:
            self._add(key, neutral[key], unit=_UNITS.get(key, ""))
        if result is not None:
            self.adopt(result)

    # -- construction ---------------------------------------------------

    def _add(self, key: str, value: float, *, unit: str = "") -> FittingParameter:
        """Create (or return) one named parameter of this group."""
        attribute = f"_{key}"
        existing = getattr(self, attribute, None)
        if isinstance(existing, FittingParameter):
            return existing
        parameter = FittingParameter(value=float(value), name=key, fixed=True, unit=unit)
        setattr(self, attribute, parameter)
        return parameter

    def parameter(self, key: str) -> FittingParameter | None:
        """Return one parameter by name, or ``None``."""
        value = getattr(self, f"_{key}", None)
        return value if isinstance(value, FittingParameter) else None

    def value(self, key: str, default: float = float("nan")) -> float:
        """Return one parameter's value, or *default*."""
        parameter = self.parameter(key)
        return float(parameter.value) if parameter is not None else float(default)

    # -- refresh --------------------------------------------------------

    def adopt(self, result) -> None:
        """Take the numbers of a finished calibration.

        In place, so links into this group survive a re-run: a follower points
        at a parameter's identity, and replacing the group would leave it
        pointing at a dead one.

        A population that the new calibration did not find keeps its parameter
        at NaN rather than being deleted, for the same reason — deleting is what
        breaks a link, and a calibration that finds two populations today and
        three tomorrow is normal.
        """
        factors = dict(getattr(result, "factors", None) or {})
        for key in _FACTORS:
            parameter = self._add(key, 0.0, unit=_UNITS.get(key, ""))
            value = float(factors.get(key, float("nan")))
            if np.isfinite(value):
                parameter.value = value

        populations = list(getattr(getattr(result, "calibration", None), "populations", None) or [])
        seen: list[str] = []
        for population in populations:
            label = str(population.get("label", len(seen)))
            seen.append(label)
            for field, key in (("E", f"E_{label}"), ("distance", f"R_{label}")):
                unit = "Angstrom" if field == "distance" else ""
                parameter = self._add(key, 0.0, unit=unit)
                value = float(population.get(field, float("nan")))
                if np.isfinite(value):
                    parameter.value = value
        for label in self.population_labels:
            if label in seen:
                continue
            for key in (f"E_{label}", f"R_{label}"):
                parameter = self.parameter(key)
                if parameter is not None:
                    parameter.value = float("nan")
        self.population_labels = seen


#: Strong references to registered groups (the registry holds weakly).
_REGISTERED: dict[str, AccurateFretParameters] = {}


def register_calibration_parameters(
    result,
    *,
    owner_id: str = "accurate_fret",
    label: str = "Accurate FRET",
) -> AccurateFretParameters:
    """Publish a finished calibration in the Global View.

    Re-registering the same ``owner_id`` refreshes the existing group rather
    than creating a second one, so re-running a calibration updates every
    parameter linked to it.

    Parameters
    ----------
    result : CalibrationResult
        The finished calibration.
    owner_id : str, optional
        Registry slot.
    label : str, optional
        Label shown in the Global View.

    Returns
    -------
    AccurateFretParameters
        The registered group.
    """
    from chisurf.core.registry.parameter_groups import register_parameter_group

    group = _REGISTERED.get(owner_id)
    if group is None:
        group = AccurateFretParameters(result, name=label)
        _REGISTERED[owner_id] = group
        register_parameter_group(group, owner_id=owner_id, label=label)
    else:
        group.adopt(result)
    return group


def unregister_calibration_parameters(owner_id: str = "accurate_fret") -> None:
    """Remove a registered calibration from the Global View."""
    from chisurf.core.registry.parameter_groups import unregister_parameter_group

    _REGISTERED.pop(owner_id, None)
    try:
        unregister_parameter_group(owner_id)
    except Exception:
        pass


def registered_calibration_parameters(
    owner_id: str = "accurate_fret",
) -> AccurateFretParameters | None:
    """Return the registered group for *owner_id*, or ``None``."""
    return _REGISTERED.get(owner_id)
