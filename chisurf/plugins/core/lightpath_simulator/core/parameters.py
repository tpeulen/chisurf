r"""The simulated optical path as ChiSurf fitting parameters.

The light-path simulator computes two probability matrices from the optics: how
strongly each laser excites each dye, and what fraction of each dye's emission
reaches each detector. Those numbers are where the FRET correction factors come
from — ``gamma``, ``alpha`` and ``delta`` are *consequences* of them, not free
inventions (see the accurate-FRET concept page).

This module publishes them as
:class:`~chisurf.core.fitting.parameter.FittingParameter`\\s so the optical model
sits in the **Global View** next to the fits that depend on it. Three things
follow:

* the derived ``gamma``/``alpha``/``delta`` are visible beside the fitted ones,
  so an optical prediction and its data-optimized posterior can be compared at a
  glance;
* a fit parameter can be **linked** to an optical quantity — a quantum yield, a
  detection efficiency — so one number has one owner;
* the whole group can be handed to
  :func:`~chisurf.core.fluorescence.fret.calibration.set_priors_from_lightpath`
  as the prior of a calibration.

Parameters are created **free** so the optical model is visible in the Global
View without switches; nothing optimizes them by itself, since a registered group
is not part of any fit's model. Note that ``gamma``/``alpha``/``delta`` are
*derived*: :meth:`LightPathParameters.update_factors` recomputes them from the
probabilities whenever the optics change, so treat them as read-outs rather than
as quantities to fit.
"""

from __future__ import annotations

import re

import numpy as np

from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup

__all__ = ["LightPathParameters", "register_lightpath_parameters",
           "unregister_lightpath_parameters", "registered_lightpath_parameters"]


def _attribute_name(prefix: str, *parts: str) -> str:
    """Return a Python attribute name for a labelled optical quantity."""
    tail = "_".join(re.sub(r"[^0-9a-zA-Z_]", "_", str(p)) for p in parts)
    return f"_{prefix}_{tail}"


def _payload_entries(payload) -> tuple[list[str], list[str], np.ndarray]:
    """Split a light-path matrix payload into rows, columns and values."""
    if not isinstance(payload, dict):
        return [], [], np.zeros((0, 0))
    rows = [str(r) for r in payload.get("rows", [])]
    columns = [str(c) for c in payload.get("columns", [])]
    values = np.asarray(payload.get("values", []), dtype=float)
    if values.ndim != 2:
        values = values.reshape(len(rows), len(columns)) if rows and columns else np.zeros((0, 0))
    return rows, columns, values


class LightPathParameters(FittingParameterGroup):
    """Excitation/emission probabilities and the factors they imply.

    Parameters
    ----------
    matrices : dict, optional
        A ``get_crosstalk_matrices()`` payload (``{"excitation": …,
        "emission": …}``).
    name : str, optional
        Group name shown in the Global View.
    quantum_yields : dict, optional
        ``{dye: QY}``; dyes not listed start at 1.
    detection_efficiencies : dict, optional
        ``{detector: g}``; detectors not listed start at 1.

    Attributes
    ----------
    dyes, lasers, detectors : list of str
        Labels found in the payload, in its order.
    """

    def __init__(self, matrices: dict | None = None, name: str = "Optical path",
                 quantum_yields: dict | None = None,
                 detection_efficiencies: dict | None = None):
        """Create the group from a light-path crosstalk payload."""
        super().__init__(name=name)
        self.lasers: list[str] = []
        self.dyes: list[str] = []
        self.detectors: list[str] = []
        #: ("ex"|"em"|"qy"|"g"|"factor", label…) -> FittingParameter
        self._by_key: dict[tuple, FittingParameter] = {}
        # Derived read-outs: recomputed by update_factors() from the probabilities.
        self._gamma = FittingParameter(value=1.0, name="gamma (optics)", fixed=True,
                                       lb=1e-6, ub=1e6, bounds_on=True)
        self._alpha = FittingParameter(value=0.0, name="alpha (optics)", fixed=True,
                                       lb=0.0, ub=1.0, bounds_on=True)
        self._delta = FittingParameter(value=0.0, name="delta (optics)", fixed=True,
                                       lb=0.0, ub=1.0, bounds_on=True)
        if matrices:
            self.adopt(matrices, quantum_yields=quantum_yields,
                       detection_efficiencies=detection_efficiencies)
        self.find_parameters()

    # ── construction ──
    def adopt(self, matrices: dict, *, quantum_yields: dict | None = None,
              detection_efficiencies: dict | None = None) -> None:
        """Create or update a parameter per matrix entry, quantum yield and efficiency.

        Parameters
        ----------
        matrices : dict
            ``{"excitation": payload, "emission": payload}`` from the simulator.
        quantum_yields : dict, optional
            ``{dye: QY}``.
        detection_efficiencies : dict, optional
            ``{detector: g}``.
        """
        lasers, dyes, excitation = _payload_entries((matrices or {}).get("excitation"))
        emission_dyes, detectors, emission = _payload_entries((matrices or {}).get("emission"))
        self.lasers = lasers or self.lasers
        self.dyes = dyes or emission_dyes or self.dyes
        self.detectors = detectors or self.detectors

        created = False
        for i, laser in enumerate(lasers):
            for j, dye in enumerate(dyes):
                created |= self._set(("ex", laser, dye), f"ex[{laser}→{dye}]",
                                     float(excitation[i, j]), (0.0, 1.0))
        for i, dye in enumerate(emission_dyes):
            for j, detector in enumerate(detectors):
                created |= self._set(("em", dye, detector), f"em[{dye}→{detector}]",
                                     float(emission[i, j]), (0.0, 1.0))
        for dye in self.dyes:
            created |= self._set(("qy", dye), f"QY[{dye}]",
                                 float((quantum_yields or {}).get(dye, 1.0)), (0.0, 1.0))
        for detector in self.detectors:
            created |= self._set(("g", detector), f"g[{detector}]",
                                 float((detection_efficiencies or {}).get(detector, 1.0)),
                                 (0.0, 10.0))
        if created:
            self.find_parameters()
        self.update_factors()

    def _set(self, key: tuple, label: str, value: float,
             bounds: tuple[float, float] | None) -> bool:
        """Create or update one parameter; return True when it was created."""
        if not np.isfinite(value):
            return False
        parameter = self._by_key.get(key)
        if parameter is not None:
            parameter.value = float(value)
            return False
        parameter = FittingParameter(
            value=float(value), name=label, fixed=False,
            lb=bounds[0] if bounds else float("-inf"),
            ub=bounds[1] if bounds else float("inf"),
            bounds_on=bounds is not None,
        )
        self._by_key[key] = parameter
        setattr(self, _attribute_name(key[0], *key[1:]), parameter)
        return True

    # ── access ──
    def parameter(self, kind: str, *labels: str) -> FittingParameter | None:
        """Return one parameter by its key.

        Keys are ``("ex", laser, dye)``, ``("em", dye, detector)``,
        ``("qy", dye)`` or ``("g", detector)``.
        """
        return self._by_key.get((kind, *labels))

    def value(self, kind: str, *labels: str, default: float = 0.0) -> float:
        """Return one parameter's value, or *default* when it does not exist."""
        parameter = self._by_key.get((kind, *labels))
        return float(parameter.value) if parameter is not None else float(default)

    @property
    def gamma(self) -> float:
        """Detection/quantum-yield ratio implied by the current optics."""
        return float(self._gamma.value)

    @property
    def alpha(self) -> float:
        """Donor leakage implied by the current optics."""
        return float(self._alpha.value)

    @property
    def delta(self) -> float:
        """Direct acceptor excitation implied by the current optics."""
        return float(self._delta.value)

    def as_matrices(self) -> dict:
        """Rebuild the crosstalk payload from the current parameter values.

        Editing a probability in the Global View therefore changes what the
        prior says, without going back to the simulator.

        Returns
        -------
        dict
            ``{"excitation": {...}, "emission": {...}}`` in the payload format.
        """
        excitation = [[self.value("ex", laser, dye) for dye in self.dyes]
                      for laser in self.lasers]
        emission = [[self.value("em", dye, detector) for detector in self.detectors]
                    for dye in self.dyes]
        return {
            "excitation": {"rows": list(self.lasers), "columns": list(self.dyes),
                           "values": excitation},
            "emission": {"rows": list(self.dyes), "columns": list(self.detectors),
                         "values": emission},
        }

    def update_factors(self, *, donor: str | None = None, acceptor: str | None = None,
                       green_detector: str | None = None, red_detector: str | None = None,
                       green_laser: str | None = None,
                       red_laser: str | None = None) -> dict:
        """Recompute ``gamma``/``alpha``/``delta`` from the current parameters.

        Parameters
        ----------
        donor, acceptor : str, optional
            Dye labels; default to the first two dyes.
        green_detector, red_detector : str, optional
            Detector labels; default to the first two detectors.
        green_laser : str, optional
            Donor-excitation laser; defaults to the first one.
        red_laser : str, optional
            Acceptor-excitation laser (``delta`` is referenced to it); defaults
            to the second one.

        Returns
        -------
        dict
            ``{"gamma", "alpha", "delta"}`` — also written into the parameters.
        """
        from chisurf.core.fluorescence.fret.calibration import lightpath_correction_factors

        donor = donor or (self.dyes[0] if self.dyes else None)
        acceptor = acceptor or (self.dyes[1] if len(self.dyes) > 1 else None)
        green_detector = green_detector or (self.detectors[0] if self.detectors else None)
        red_detector = red_detector or (self.detectors[1] if len(self.detectors) > 1 else None)
        if not (donor and acceptor and green_detector and red_detector):
            return {"gamma": self.gamma, "alpha": self.alpha, "delta": self.delta}
        factors = lightpath_correction_factors(
            self.as_matrices(), donor, acceptor, green_detector, red_detector,
            green_laser=green_laser or (self.lasers[0] if self.lasers else None),
            red_laser=red_laser or (self.lasers[1] if len(self.lasers) > 1 else None),
            gG=self.value("g", green_detector, default=1.0),
            gR=self.value("g", red_detector, default=1.0),
            qy_d=self.value("qy", donor, default=1.0),
            qy_a=self.value("qy", acceptor, default=1.0),
        )
        for key, parameter in (("gamma", self._gamma), ("alpha", self._alpha),
                               ("delta", self._delta)):
            value = float(factors.get(key, float("nan")))
            if np.isfinite(value):
                parameter.value = value
        return factors

    def as_prior_arguments(self, **overrides) -> dict:
        """Return the ``lightpath=`` argument of the automatic calibration.

        The optics group *is* the prior; this hands it over in the shape
        :func:`~chisurf.core.fluorescence.fret.calibration.set_priors_from_lightpath`
        expects, so what the Global View shows and what regularizes the
        calibration are the same numbers.

        Parameters
        ----------
        **overrides
            Any keyword of ``set_priors_from_lightpath`` (dye/detector labels,
            prior widths, …).

        Returns
        -------
        dict
            Keyword arguments ready for ``auto_calibrate(..., lightpath=...)``.
        """
        donor = overrides.pop("donor", None) or (self.dyes[0] if self.dyes else None)
        acceptor = overrides.pop("acceptor", None) or (
            self.dyes[1] if len(self.dyes) > 1 else None)
        green = overrides.pop("green_detector", None) or (
            self.detectors[0] if self.detectors else None)
        red = overrides.pop("red_detector", None) or (
            self.detectors[1] if len(self.detectors) > 1 else None)
        arguments = {
            "matrices": self.as_matrices(),
            "donor": donor, "acceptor": acceptor,
            "green_detector": green, "red_detector": red,
            "green_laser": self.lasers[0] if self.lasers else None,
            "red_laser": self.lasers[1] if len(self.lasers) > 1 else None,
            "gG": self.value("g", green, default=1.0),
            "gR": self.value("g", red, default=1.0),
            "qy_d": self.value("qy", donor, default=1.0),
            "qy_a": self.value("qy", acceptor, default=1.0),
        }
        arguments.update(overrides)
        return arguments


#: Strong references to registered optical models (the registry holds weakly).
_REGISTERED: dict[str, LightPathParameters] = {}


def register_lightpath_parameters(matrices: dict, *, owner_id: str = "lightpath",
                                  label: str = "Optical path",
                                  quantum_yields: dict | None = None,
                                  detection_efficiencies: dict | None = None
                                  ) -> LightPathParameters:
    """Publish a simulated optical path in the Global View.

    Re-registering the same ``owner_id`` updates the existing group in place, so
    re-running the simulation refreshes the numbers instead of creating a second
    optical model (and keeps any links pointing at it alive).

    Parameters
    ----------
    matrices : dict
        ``get_crosstalk_matrices()`` payload.
    owner_id : str, optional
        Registry slot.
    label : str, optional
        Label shown in the Global View.
    quantum_yields, detection_efficiencies : dict, optional
        Per-dye quantum yields and per-detector efficiencies.

    Returns
    -------
    LightPathParameters
        The registered group.
    """
    from chisurf.core.parameter_group_registry import register_parameter_group

    group = _REGISTERED.get(owner_id)
    if group is None:
        group = LightPathParameters(
            matrices, name=label, quantum_yields=quantum_yields,
            detection_efficiencies=detection_efficiencies,
        )
        _REGISTERED[owner_id] = group
        register_parameter_group(group, owner_id=owner_id, label=label)
    else:
        group.adopt(matrices, quantum_yields=quantum_yields,
                    detection_efficiencies=detection_efficiencies)
    return group


def unregister_lightpath_parameters(owner_id: str = "lightpath") -> None:
    """Remove a registered optical model from the Global View."""
    from chisurf.core.parameter_group_registry import unregister_parameter_group

    _REGISTERED.pop(owner_id, None)
    try:
        unregister_parameter_group(owner_id)
    except Exception:
        pass


def registered_lightpath_parameters(owner_id: str = "lightpath") -> LightPathParameters | None:
    """Return the registered optical model (``None`` when there is none)."""
    return _REGISTERED.get(owner_id)
