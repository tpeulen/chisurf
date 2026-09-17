"""FRET lines computed from BFF-described lifetime models.

A FRET line is the locus a population occupies in the plane of transfer
efficiency against donor lifetime while one quantity of its model -- a mean
distance, a chain length, a mixing fraction -- is varied. The models are the
same views a decay fit uses (:func:`chisurf.core.models.description.for_family`);
nothing is convolved: a line reads each model's published lifetime spectrum,
so a view needs no data and models its IRF.

:func:`sweep` is the one engine; the FRET-line tool
(``chisurf.plugins.fret_line``) and the :class:`StaticFRETLine` /
:class:`DynamicFRETLine` conveniences use it. The closed-form lines are in
:mod:`chisurf.core.fluorescence.fret.lines`.
"""

from __future__ import annotations

import numpy as np

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.fluorescence.general as general

__all__ = [
    "model_view",
    "lifetime_spectrum",
    "averaged_lifetimes",
    "donor_lifetime",
    "find_parameter",
    "sweep",
    "FRETLineGenerator",
    "StaticFRETLine",
    "DynamicFRETLine",
]

#: The structure axis that counts a family's components (distances, lifetimes).
_COMPONENT_AXES = ("g", "n")


def model_view(family: str, n_components: int = 1, sources=()):
    """A live view of ``family`` with ``n_components`` components, ready to read.

    Built over a placeholder decay with a modelled IRF: a FRET line reads the
    model's lifetime spectrum, never its curve. ``sources`` are the views a
    family that reads other models (a mixture) reads.
    """
    from chisurf.core.models.description import for_family

    fit = chisurf.core.fitting.fit.Fit()
    x = np.linspace(0.0, 50.0, 200)
    fit.data = chisurf.core.data.DataCurve(x=x, y=np.ones_like(x))
    fit.model = for_family(family)
    view = fit.model
    if "generated_response" in view.scalar_names():
        view.set_scalar("generated_response", 1.0)
    wanted = max(1, int(n_components))
    if (
        "max_components" in view.scalar_names()
        and (view.get_scalar("max_components") or 0) < wanted
    ):
        view.set_scalar("max_components", float(wanted))
    for i, source in enumerate(sources):
        view.append_model(source, name=f"C{i}")
    if view.problem is None:
        raise ValueError(f"{family!r} cannot be built: missing {', '.join(view.missing)}")
    for key, _ in view.structure_options():
        axes = view._structure_axes(key)
        count = next((axes[a] for a in _COMPONENT_AXES if a in axes), None)
        if count == wanted:
            view.structure = key
            break
    return view


def lifetime_spectrum(view) -> np.ndarray:
    """The interleaved (amplitude, lifetime) spectrum ``view`` publishes now."""
    return np.asarray(view.problem.get_output("lifetime_spectrum"), dtype=float)


def averaged_lifetimes(view) -> tuple[float, float]:
    """The species- and fluorescence-averaged lifetimes, ``(<tau>_x, <tau>_F)``."""
    spectrum = lifetime_spectrum(view)
    tau_x = general.species_averaged_lifetime(spectrum.copy())
    return tau_x, general.fluorescence_averaged_lifetime(spectrum.copy(), tau_x)


def find_parameter(view, name: str):
    """A view's parameter by canonical id (``distance.mean.0``) or displayed name."""
    parameters = list(view.parameters_all)
    for parameter in parameters:
        if getattr(parameter, "canonical_id", None) == name:
            return parameter
    for parameter in parameters:
        if parameter.name == name:
            return parameter
    raise KeyError(f"{view.name!r} has no parameter {name!r}")


def donor_lifetime(views, fallback: float | None = None) -> float | None:
    """The donor's species-averaged lifetime without FRET, from the first view that has a donor.

    The donor's own spectrum (``donor.amplitude.i`` / ``donor.tau.i``) where the
    view's structure uses one, else ``fret.tau0``.
    """
    for view in views:
        used = set(view.structure_parameter_ids())
        by_id = {p.canonical_id: p for p in view.parameters_all if hasattr(p, "canonical_id")}
        pairs = []
        i = 0
        while f"donor.tau.{i}" in by_id:
            if f"donor.tau.{i}" in used:
                pairs += [
                    abs(by_id[f"donor.amplitude.{i}"].value),
                    abs(by_id[f"donor.tau.{i}"].value),
                ]
            i += 1
        if pairs:
            return general.species_averaged_lifetime(np.asarray(pairs, dtype=float))
        if "fret.tau0" in by_id:
            return float(by_id["fret.tau0"].value)
    return fallback


def _mixture(views, fractions=None):
    """One view mixing ``views``' lifetime spectra (``tcspc_mixture``)."""
    mix = model_view("tcspc_mixture", sources=views)
    if fractions is not None:
        for parameter, weight in zip(mix._fractions, fractions):
            parameter.value = max(float(weight), 0.0)
    return mix


def sweep(views, target: dict, values, fractions=None, tau_d0: float | None = None) -> dict:
    """Walk ``target`` through ``values`` and record the line.

    ``views`` are the components; more than one are mixed by ``fractions``
    (equal by default). ``target`` is ``{"kind": "param", "component": i,
    "name": <canonical id or name>}`` or ``{"kind": "fraction", "component": i}``.
    The efficiency is ``1 - <tau>_x / tau_D0``, with ``tau_D0`` from the donor
    unless given. Returns ``parameter_values``, ``tau_x``, ``tau_f``, ``e_fret``.
    """
    views = list(views)
    if not views:
        raise ValueError("At least one component is required.")
    mix = _mixture(views, fractions) if len(views) > 1 else None
    reader = mix if mix is not None else views[0]
    if tau_d0 is None:
        tau_d0 = donor_lifetime(views, fallback=float("nan"))
    component = int(target.get("component", 0))
    if not 0 <= component < len(views):
        raise ValueError(f"Component index {component} out of range.")
    kind = target.get("kind", "param")
    if kind == "param":
        parameter = find_parameter(views[component], target["name"])

        def apply(value):
            parameter.value = float(value)
    elif kind == "fraction":
        if mix is None:
            raise ValueError("Fraction sweep requires at least two components.")
        weights = mix._fractions

        def apply(value):
            others = [p for j, p in enumerate(weights) if j != component]
            current = np.array([max(p.value, 0.0) for p in others], dtype=float)
            if current.sum() <= 0.0:
                current = np.ones(len(others))
            current = current / current.sum() * (1.0 - float(value))
            weights[component].value = float(value)
            for p, w in zip(others, current):
                p.value = float(w)
    else:
        raise ValueError(f"Unknown sweep kind {kind!r}.")
    values = np.asarray(values, dtype=float)
    tau_x = np.empty(values.size)
    tau_f = np.empty(values.size)
    for i, value in enumerate(values):
        apply(value)
        tau_x[i], tau_f[i] = averaged_lifetimes(reader)
    e_fret = 1.0 - tau_x / tau_d0 if tau_d0 and tau_d0 > 0 else np.full(values.size, np.nan)
    return {
        "parameter_values": values.tolist(),
        "tau_x": tau_x.tolist(),
        "tau_f": tau_f.tolist(),
        "e_fret": e_fret.tolist(),
    }


class FRETLineGenerator:
    """A FRET line of one described model: vary ``parameter_name`` over ``parameter_range``.

    >>> fl = FRETLineGenerator("tcspc_fret_gaussian", parameter_name="distance.mean.0",
    ...                        parameter_range=(20.0, 100.0))  # doctest: +SKIP
    >>> fl.update()  # doctest: +SKIP
    >>> fl.species_averaged_lifetimes, fl.fret_efficiencies  # doctest: +SKIP
    """

    def __init__(
        self,
        family: str = "tcspc_fret_gaussian",
        n_components: int = 1,
        polynomial_degree: int = 4,
        quantum_yield_donor: float = 0.8,
        quantum_yield_acceptor: float = 0.32,
        parameter_name: str | None = None,
        n_points: int = 100,
        parameter_range: tuple[float, float] = (0.1, 100.0),
    ):
        self.model = model_view(family, n_components)
        self.polynomial_degree = polynomial_degree
        self.quantum_yield_donor = quantum_yield_donor
        self.quantum_yield_acceptor = quantum_yield_acceptor
        self.parameter_name = parameter_name
        self.n_points = n_points
        self.parameter_range = parameter_range
        self.fret_efficiencies = np.zeros(n_points)
        self.fluorescence_averaged_lifetimes = np.zeros(n_points)
        self.species_averaged_lifetimes = np.zeros(n_points)

    def parameter(self, name: str):
        return find_parameter(self.model, name)

    @property
    def parameter_values(self) -> np.ndarray:
        return np.linspace(self.parameter_range[0], self.parameter_range[1], self.n_points)

    @property
    def fret_species_averaged_lifetime(self) -> float:
        return averaged_lifetimes(self.model)[0]

    @property
    def fret_fluorescence_averaged_lifetime(self) -> float:
        return averaged_lifetimes(self.model)[1]

    @property
    def donor_species_averaged_lifetime(self) -> float:
        return donor_lifetime([self.model])

    @property
    def transfer_efficiency(self) -> float:
        return 1.0 - self.fret_species_averaged_lifetime / self.donor_species_averaged_lifetime

    @property
    def conversion_function(self) -> tuple[np.ndarray, np.ndarray]:
        return self.fluorescence_averaged_lifetimes, self.species_averaged_lifetimes

    @property
    def polynom_coefficients(self) -> np.ndarray:
        return np.polyfit(
            self.fluorescence_averaged_lifetimes,
            self.species_averaged_lifetimes,
            self.polynomial_degree,
        )

    @property
    def conversion_function_string(self) -> str:
        return "+".join("%.6f*x^%i" % (c, i) for i, c in enumerate(self.polynom_coefficients[::-1]))

    @property
    def transfer_efficency_string(self) -> str:
        return (
            f"1.0-({self.conversion_function_string})/({self.donor_species_averaged_lifetime:.6f})"
        )

    @property
    def fdfa_string(self) -> str:
        return f"{self.quantum_yield_donor}/{self.quantum_yield_acceptor} / (({self.donor_species_averaged_lifetime})/({self.conversion_function_string}) - 1)"

    def update(
        self,
        parameter_name: str | None = None,
        parameter_range: tuple[float, float] | None = None,
        n_points: int | None = None,
    ) -> None:
        """Recompute the line."""
        if parameter_name is not None:
            self.parameter_name = parameter_name
        if parameter_range is not None:
            self.parameter_range = tuple(parameter_range)
        if n_points is not None:
            self.n_points = int(n_points)
        result = sweep(
            [self.model],
            {"kind": "param", "component": 0, "name": self.parameter_name},
            self.parameter_values,
            tau_d0=self.donor_species_averaged_lifetime,
        )
        self.species_averaged_lifetimes = np.asarray(result["tau_x"])
        self.fluorescence_averaged_lifetimes = np.asarray(result["tau_f"])
        self.fret_efficiencies = np.asarray(result["e_fret"])


class StaticFRETLine(FRETLineGenerator):
    """The static FRET line of one Gaussian distance distribution, swept over its mean."""

    def __init__(self, sigma: float = 6.0, **kwargs):
        kwargs.setdefault("parameter_name", "distance.mean.0")
        super().__init__("tcspc_fret_gaussian", 1, **kwargs)
        self.parameter("fret.x_donly").value = 0.0
        self.sigma = sigma

    @property
    def sigma(self) -> float:
        """Width of the distance distribution."""
        return self.parameter("distance.sigma.0").value

    @sigma.setter
    def sigma(self, v: float):
        self.parameter("distance.sigma.0").value = float(v)


class DynamicFRETLine(FRETLineGenerator):
    """The dynamic FRET line between two Gaussian states, swept over the second state's weight."""

    def __init__(
        self,
        distance_1: float = 40.0,
        distance_2: float = 80.0,
        sigma_1: float = 6.0,
        sigma_2: float = 6.0,
        **kwargs,
    ):
        kwargs.setdefault("parameter_name", "distance.amplitude.1")
        kwargs.setdefault("parameter_range", (0.0, 10.0))
        super().__init__("tcspc_fret_gaussian", 2, **kwargs)
        self.parameter("fret.x_donly").value = 0.0
        for name, value in (
            ("distance.mean.0", distance_1),
            ("distance.mean.1", distance_2),
            ("distance.sigma.0", sigma_1),
            ("distance.sigma.1", sigma_2),
            ("distance.amplitude.0", 1.0),
            ("distance.amplitude.1", 0.0),
        ):
            self.parameter(name).value = float(value)

    @property
    def sigma(self) -> tuple[float, float]:
        return self.parameter("distance.sigma.0").value, self.parameter("distance.sigma.1").value

    @sigma.setter
    def sigma(self, v):
        first, second = (v, v) if np.isscalar(v) else v
        self.parameter("distance.sigma.0").value = float(first)
        self.parameter("distance.sigma.1").value = float(second)
