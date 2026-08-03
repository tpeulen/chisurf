"""Fitting kinetic models to the 2D MFD burst histogram.

The physics is in :mod:`chisurf.core.fluorescence.mfd`; this module is the fitting
surface over it — parameter groups, the model/view split, and the residual the
optimizer sees. Nothing here recomputes anything the compute layer already does.

Two models:

* :class:`Mfd2DModel` — states that do not exchange. This is what milestone 1a is
  fitted with, and the right starting point for any measurement: the static answer
  is what a dynamic one has to beat.
* :class:`Mfd2DKineticModel` — the same states with a fittable rate matrix, using
  the shared rate-matrix group rather than a private copy.

**Uncertainties are refused rather than quietly reported.** The histogram source
scores the same bursts through more than one marginal, so its summed deviance is an
M-estimator: the optimum is meaningful, the curvature is not. Asking this model for
parameter errors from the fit's covariance therefore raises, and points at the
burst-wise source or a bootstrap. That is enforced in code because the footnote
version of the rule is exactly the kind that goes unread, and confidently narrow
error bars look like success.
"""

from __future__ import annotations

import numpy as np

import chisurf as cs
from chisurf.core.fitting.kinetics import RateMatrixParameters
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.fluorescence.mfd.fit import MfdKineticModel, MfdModel
from chisurf.core.fluorescence.mfd.patterns import FretState, Optics
from chisurf.core.fluorescence.mfd.sources import uncertainty_is_valid
from chisurf.core.models.model import ModelCurve

__all__ = [
    "Mfd2DKineticModel",
    "Mfd2DModel",
    "MfdCalibration",
    "MfdStates",
]


def burst_payload(data):
    """Return the MFD objects a dataset carries, or ``None``.

    Parameters
    ----------
    data : object
        A dataset, or ``None``.

    Returns
    -------
    chisurf.core.fluorescence.mfd.fit.MfdData or None
    """
    if data is None:
        return None
    payload = getattr(data, "mfd", None)
    if payload is not None:
        return payload
    meta = getattr(data, "meta_data", None) or {}
    return meta.get("mfd_data")


class MfdCalibration(FittingParameterGroup):
    """The instrument's correction factors and the dyes' constants.

    Deliberately a thin group over the *same* quantities the shared
    :class:`~chisurf.core.fluorescence.fret.calibration.CalibrationParameters`
    carries, so that a value fitted here can be linked to a calibration fit rather
    than being a second, independent copy of γ.

    ``sigma`` — the combined linker width — sits here rather than with the states
    because it is a property of the labelling, shared across every state. It is
    fixed by default: it is *not* a free broadening parameter, and freeing it under
    the histogram source alone lets it absorb width that belongs to the kinetics.
    Free it only with a prior, or under the pooled-decay source which can see the
    linker width in the decay *shape*.
    """

    def __init__(self, name: str = "calibration", **kwargs):
        """Create the calibration group.

        Parameters
        ----------
        name : str
            Group name.
        **kwargs
            Forwarded to :class:`FittingParameterGroup`.
        """
        super().__init__(name=name, **kwargs)
        self._r0 = FittingParameter(
            name="R0", value=52.0, lb=5.0, ub=200.0, bounds_on=True, fixed=True
        )
        self._tau_d0 = FittingParameter(
            name="tauD0", value=4.0, lb=0.05, ub=30.0, bounds_on=True
        )
        self._tau_a = FittingParameter(
            name="tauA", value=3.0, lb=0.05, ub=30.0, bounds_on=True, fixed=True
        )
        self._alpha = FittingParameter(
            name="alpha", value=0.0, lb=0.0, ub=1.0, bounds_on=True
        )
        self._delta = FittingParameter(
            name="delta", value=0.0, lb=0.0, ub=1.0, bounds_on=True, fixed=True
        )
        self._gamma = FittingParameter(
            name="gamma", value=1.0, lb=0.05, ub=20.0, bounds_on=True, fixed=True
        )
        self._sigma = FittingParameter(
            name="sigma", value=6.0, lb=0.0, ub=30.0, bounds_on=True, fixed=True
        )
        self.find_parameters()

    def _scalar(self, parameter) -> float:
        """Return a parameter's value as a plain float."""
        return float(parameter.value)

    @property
    def optics(self) -> Optics:
        """Return the plain-number view the compute layer takes."""
        return Optics(
            r0=self._scalar(self._r0),
            tau_d0=self._scalar(self._tau_d0),
            tau_a=self._scalar(self._tau_a),
            alpha=self._scalar(self._alpha),
            delta=self._scalar(self._delta),
            gamma=self._scalar(self._gamma),
            sigma=self._scalar(self._sigma),
        )


class MfdStates(FittingParameterGroup):
    """Mean donor–acceptor distances, their populations, and the donor-only fraction.

    The donor-only fraction is a first-class parameter rather than something to be
    cropped out of the data. Real single-molecule measurements always have some
    molecules whose acceptor is missing or bleached, and leaving them out of the
    model does not remove them from the histogram — it makes the fit drag a FRET
    state down to explain them.

    Distances live in a **list**, because
    :func:`chisurf.core.base.find_objects` recurses into lists only; a dict of them
    would be invisible to the optimizer.
    """

    def __init__(self, name: str = "states", n_states: int = 1, **kwargs):
        """Create the state group.

        Parameters
        ----------
        name : str
            Group name.
        n_states : int
            Number of FRET states.
        **kwargs
            Forwarded to :class:`FittingParameterGroup`.
        """
        super().__init__(name=name, **kwargs)
        self._distances: list[FittingParameter] = []
        self._fractions: list[FittingParameter] = []
        self._donor_only = FittingParameter(
            name="donorOnly", value=0.2, lb=0.0, ub=1.0, bounds_on=True
        )
        self.n_states = n_states

    @property
    def n_states(self) -> int:
        """Return the number of FRET states."""
        return len(self._distances)

    @n_states.setter
    def n_states(self, value: int) -> None:
        """Resize the state list, keeping the distances already set."""
        target = max(1, int(value))
        while len(self._distances) > target:
            self._distances.pop()
            self._fractions.pop()
        while len(self._distances) < target:
            index = len(self._distances) + 1
            self._distances.append(
                FittingParameter(
                    name=f"R{index}", value=50.0, lb=5.0, ub=250.0, bounds_on=True
                )
            )
            self._fractions.append(
                FittingParameter(
                    name=f"x{index}", value=1.0, lb=0.0, ub=1.0, bounds_on=True,
                    fixed=(index == 1),
                )
            )
        self.find_parameters()

    @property
    def states(self) -> list[FretState]:
        """Return the compute layer's view of the states."""
        return [
            FretState(distance=float(p.value), name=p.name) for p in self._distances
        ]

    @property
    def populations(self) -> np.ndarray:
        """Return the state populations, normalised."""
        values = np.array([float(p.value) for p in self._fractions], dtype=float)
        values = np.clip(values, 0.0, None)
        total = values.sum()
        return values / total if total > 0 else np.full(values.size, 1.0 / values.size)

    @property
    def donor_only(self) -> float:
        """Return the fraction of molecules with no active acceptor."""
        return float(np.clip(self._donor_only.value, 0.0, 1.0))

    def distance_rows(self):
        """Return the per-state parameter rows an editor renders.

        Returns
        -------
        list of list
            One row per state, ``[distance, fraction]``.
        """
        return [[d, x] for d, x in zip(self._distances, self._fractions)]

    def append(self) -> None:
        """Add a state."""
        self.n_states = self.n_states + 1

    def pop(self) -> None:
        """Remove the last state."""
        if self.n_states > 1:
            self.n_states = self.n_states - 1


class Mfd2DModel(ModelCurve):
    """Static states fitted to the 2D MFD histogram."""

    name = "MFD 2D (static)"
    view_spec_file = "two_dimensional.view.json"

    def __init__(self, fit, n_states: int = 1, **kwargs):
        """Create the model.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            The fit this model belongs to.
        n_states : int
            Number of FRET states.
        **kwargs
            Forwarded to :class:`ModelCurve`.
        """
        super().__init__(fit, **kwargs)
        self.calibration = MfdCalibration()
        self.state_group = MfdStates(n_states=n_states)
        self._last_summary: dict = {}
        self.find_parameters()

    @classmethod
    def supports_data(cls, data) -> bool:
        """Return whether this model applies to a dataset.

        Parameters
        ----------
        data : object
            A dataset, or ``None`` for "list everything".

        Returns
        -------
        bool
        """
        if data is None:
            return True
        return burst_payload(data) is not None

    def _compute_model(self):
        """Return the compute-layer model this fitting model describes."""
        return MfdModel(
            optics=self.calibration.optics,
            states=self.state_group.states,
            populations=self.state_group.populations,
            donor_only=self.state_group.donor_only,
        )

    def update_model(self, **kwargs):
        """Recompute the predicted histogram and store it flattened.

        Parameters
        ----------
        **kwargs
            Ignored; present for the base-class signature.
        """
        data = burst_payload(self.fit.data)
        if data is None:
            return
        try:
            predicted = self._compute_model().histogram(data)
        except Exception as exc:  # pragma: no cover - surfaced, never swallowed
            cs.logging.error("MFD model evaluation failed: %s", exc)
            raise
        observed = np.asarray(self.fit.data.y, dtype=float)
        flat = predicted.ravel(order="C")
        total = flat.sum()
        if total > 0:
            flat = flat * (observed.sum() / total)
        self.y = flat
        self.d = np.vstack((self.x, self.y))

    @property
    def summary_html(self) -> str:
        """Return what the fit is being asked to explain, and what it excluded."""
        data = burst_payload(self.fit.data)
        if data is None:
            return "<i>No MFD dataset.</i>"
        summary = data.observed.summary
        rows = [
            ("Bursts in the folder", f"{summary['n_input']}"),
            ("In the histogram", f"{summary['n_used']}"),
            ("Excluded", f"{summary['excluded_fraction']:.1%}"),
            ("Donor-photon cut", f"{summary['min_green_photons']}"),
        ]
        for name, response in data.responses.items():
            rows.append(
                (f"{name} background", f"{response.background_rate * 1e-3:.3f} kHz")
            )
        body = "".join(f"<tr><td>{k}</td><td><b>{v}</b></td></tr>" for k, v in rows)
        return (
            "<table cellspacing='4'>" + body + "</table>"
            "<p><i>Uncertainties from this fit's covariance are not valid: the "
            "histogram source scores the same bursts through more than one "
            "marginal, so its curvature is not a likelihood's. Use the burst-wise "
            "source or a bootstrap over bursts.</i></p>"
        )

    def parameter_uncertainties(self):
        """Refuse to report uncertainties the histogram source cannot support.

        Raises
        ------
        RuntimeError
            Always, for the histogram source. The optimum from a summed deviance
            over marginals is meaningful; its curvature is not, because the same
            bursts enter every marginal and the score double-counts them.
        """
        if not uncertainty_is_valid(["histogram"]):
            raise RuntimeError(
                "the marginal-histogram score is an M-estimator, not a likelihood: "
                "the same bursts appear in every marginal, so its curvature reports "
                "uncertainties that are too small. Take them from the burst-wise "
                "source or from a bootstrap over bursts instead."
            )
        return None  # pragma: no cover - unreachable while only this source exists


class Mfd2DKineticModel(Mfd2DModel):
    """States that exchange during the burst, fitted to the 2D MFD histogram."""

    name = "MFD 2D (kinetic)"
    view_spec_file = "two_dimensional_kinetic.view.json"

    def __init__(self, fit, n_states: int = 2, **kwargs):
        """Create the model.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            The fit this model belongs to.
        n_states : int
            Number of exchanging states.
        **kwargs
            Forwarded to :class:`Mfd2DModel`.
        """
        super().__init__(fit, n_states=max(2, int(n_states)), **kwargs)
        self.kinetics = RateMatrixParameters(
            name="kinetics", n_states=max(2, int(n_states))
        )
        self.find_parameters()

    @property
    def n_states(self) -> int:
        """Return the number of exchanging states."""
        return self.state_group.n_states

    @n_states.setter
    def n_states(self, value: int) -> None:
        """Resize the states and the rate matrix together.

        They must move as one: a rate matrix that disagrees with the state count is
        the kind of mismatch that reads as a broadcasting error three layers down.
        """
        target = max(2, int(value))
        self.state_group.n_states = target
        self.kinetics.n_states = target
        self.find_parameters()

    @property
    def state_names(self) -> list[str]:
        """Return state labels for the rate-matrix editor."""
        return [f"R{i + 1}" for i in range(self.n_states)]

    @property
    def rate_values(self):
        """Return the flat rate matrix the AutoForm grid binds to."""
        return self.kinetics.rate_values

    @rate_values.setter
    def rate_values(self, values) -> None:
        """Set the flat rate matrix from the editor."""
        self.kinetics.rate_values = values

    def _compute_model(self):
        """Return the compute-layer model, with the rate matrix attached."""
        return MfdKineticModel(
            optics=self.calibration.optics,
            states=self.state_group.states,
            populations=self.state_group.populations,
            donor_only=self.state_group.donor_only,
            # ``rate_matrix`` is a method on the shared mixin, not a property; passing
            # the bound method here yields a zero-dimensional array and a broadcast
            # error three layers down.
            rate_matrix=np.asarray(self.kinetics.rate_matrix(), dtype=float),
        )
