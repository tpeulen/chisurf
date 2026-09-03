"""A fittable TCSPC model for acceptors *distributed* rather than placed.

Every other FRET model here parameterizes a donor–acceptor **distance** and
turns it into a rate spectrum. That is the wrong shape for a donor surrounded by
many acceptors at many distances — dyes in solution, probes across a membrane,
intercalators along a helix — where the quantity the data determine is an
acceptor **density** and the decay is a stretched exponential rather than a sum
of exponentials.

The physics is in :mod:`chisurf.core.fluorescence.fret.dimensionality` and the
theory page is ``docs/concepts/distributed_acceptors.md``. What this module adds
is the fit: the density ``C/C0`` and the donor lifetimes are released, the
dimensionality is chosen, and the model is reconvolved against the instrument
response like any other.

Two things it deliberately does not do:

* **No anisotropy mixing.** The polarized channels are built from a lifetime
  spectrum, and this model has no spectrum to give — its decay is not a finite
  mixture of exponentials. Fit magic-angle or total decays with it.
* **No distance.** Reporting one would be a category error
  (:ref:`concept-distributed-acceptors` says why); the fitted quantity is a
  density, and the Förster radius is an input used to express it.
"""

from __future__ import annotations

import numpy as np

import chisurf.core.settings
from chisurf.core.curve import Curve
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.fluorescence.fret.dimensionality import (
    characteristic_density,
    quench_decay,
    transfer_efficiency,
)
from chisurf.core.models.tcspc.lifetime import LifetimeModel

#: How many preceding excitation pulses are folded in when the convolution runs
#: in a periodic mode. The stretched decay has a longer tail than a single
#: exponential of the same nominal lifetime, so a couple of periods is not
#: enough; eight is well past the point where the sum stops moving.
N_FOLDED_PERIODS = 8


class DistributedAcceptorModel(LifetimeModel):
    """Donor decay quenched by acceptors distributed in 1, 2 or 3 dimensions."""

    name = "FRET: distributed acceptors"
    view_spec_file = "distributed_acceptor.view.json"

    #: Reported, not fitted -- see :attr:`LifetimeModel.derived_quantities`.
    derived_quantities = (
        "species_averaged_lifetime",
        "fluorescence_averaged_lifetime",
        "fret_efficiency",
        "acceptor_density",
    )

    def __init__(self, fit, **kwargs):
        """Initialize the model and its two model-specific parameters."""
        super().__init__(fit, **kwargs)
        self._c_over_c0 = FittingParameter(
            value=kwargs.get("c_over_c0", 1.0),
            name="c_over_c0",
            label_text="C/C<sub>0</sub>",
            lb=0.0,
            ub=100.0,
            bounds_on=True,
            fixed=False,
            description='Ratio of acceptor concentration to the quenching concentration C0 (dimensionless).',
        )
        self._forster_radius = FittingParameter(
            value=kwargs.get("forster_radius", 52.0),
            name="R0",
            label_text="R<sub>0</sub> [&#8491;]",
            fixed=True,
            description='Forster radius R0 of the donor-acceptor pair (Angstrom).',
        )
        self._tau_d0 = FittingParameter(
            value=kwargs.get("tau_d0", 4.0),
            name="tauD0",
            label_text="&tau;<sub>D(0)</sub> [ns]",
            fixed=True,
            description='Donor lifetime in the absence of the acceptor (ns).',
        )
        self._dimension = int(kwargs.get("dimension", 2))

    # ── model-specific parameters ────────────────────────────────────

    @property
    def c_over_c0(self) -> float:
        """Acceptor density, in units of the characteristic density C0.

        This is the number of acceptors within R0 of a donor, which is what
        makes it interpretable without knowing the geometry first.
        """
        return self._c_over_c0.value

    @c_over_c0.setter
    def c_over_c0(self, v: float) -> None:
        self._c_over_c0.value = v

    @property
    def forster_radius(self) -> float:
        """Förster radius R0 (Å), an input rather than a fitted quantity."""
        return self._forster_radius.value

    @forster_radius.setter
    def forster_radius(self, v: float) -> None:
        self._forster_radius.value = v

    @property
    def tau_d0(self) -> float:
        """Reference donor lifetime R0 -- and hence C0 -- was computed with."""
        return self._tau_d0.value

    @tau_d0.setter
    def tau_d0(self, v: float) -> None:
        self._tau_d0.value = v

    @property
    def dimension(self) -> int:
        """Dimensionality of the acceptor distribution: 1, 2 or 3."""
        return self._dimension

    @dimension.setter
    def dimension(self, v: int) -> None:
        self._dimension = int(v)

    # ── reported quantities ──────────────────────────────────────────

    @property
    def fret_efficiency(self) -> float:
        """Transfer efficiency implied by the fitted density."""
        try:
            return transfer_efficiency(self.c_over_c0, self.dimension)
        except Exception:
            return float("nan")

    @property
    def acceptor_density(self) -> float:
        """Absolute acceptor density, in Å^-d.

        ``C/C0`` is the interpretable number; this is what it corresponds to for
        the Förster radius entered, and it is the quantity to compare against an
        independently measured surface or volume concentration.
        """
        try:
            c0 = characteristic_density(self.forster_radius, self.dimension)
        except Exception:
            return float("nan")
        return self.c_over_c0 * c0

    def derived_html(self) -> str:
        """Formatted readout for the editor's info section.

        A method rather than a property, and formatted here rather than in the
        spec: an ``info`` section renders whatever string its source returns, so
        handing it a bare float prints the full repr with no label.
        """
        try:
            e = self.fret_efficiency
            rho = self.acceptor_density
            d = self.dimension
        except Exception:
            return "<i>not computed</i>"
        return (
            f"<b>E</b> = {e:.3f} &nbsp;&nbsp; "
            f"<b>density</b> = {rho:.3e} &#8491;<sup>-{d}</sup>"
        )

    def _density_parameter_rows(self) -> list:
        """Return the model-specific parameters for the editor's table."""
        return [self._c_over_c0, self._tau_d0, self._forster_radius]

    # ── the decay ────────────────────────────────────────────────────

    def _donor_only_decay(self, time: np.ndarray) -> np.ndarray:
        """Unconvolved donor-only decay on *time*, from the lifetime spectrum."""
        spectrum = np.asarray(self.lifetime_spectrum, dtype=float).ravel()
        decay = np.zeros_like(time)
        for amplitude, tau in spectrum.reshape(-1, 2):
            if tau > 0:
                decay += amplitude * np.exp(-time / tau)
        return decay

    def unconvolved_decay(self, time: np.ndarray) -> np.ndarray:
        """The quenched donor decay before the instrument sees it.

        Periodic excitation is folded in here rather than by the convolution:
        the decays of the preceding pulses are summed, which is what a high
        repetition rate does to the histogram. Doing it on the *decay* keeps the
        stretched term exact, which folding a lifetime spectrum could not.
        """
        t = np.asarray(time, dtype=float)
        decay = quench_decay(
            self._donor_only_decay(t), t, self.tau_d0, self.c_over_c0, self.dimension
        )
        if str(getattr(self.convolve, "mode", "")) == "per":
            rep_rate = float(getattr(self.convolve, "rep_rate", 0.0) or 0.0)
            if rep_rate > 0:
                period = 1000.0 / rep_rate          # MHz -> ns
                for k in range(1, N_FOLDED_PERIODS + 1):
                    shifted = t + k * period
                    decay = decay + quench_decay(
                        self._donor_only_decay(shifted), shifted,
                        self.tau_d0, self.c_over_c0, self.dimension,
                    )
        return decay

    def _update_model(
        self,
        verbose: bool = None,
        scatter: float = None,
        background: float = None,
        background_curve: Curve = None,
        shift_bg_with_irf: bool = None,
        **kwargs,
    ) -> None:
        """Recompute the model decay.

        This mirrors :meth:`LifetimeModel.update_model` from the convolution
        onwards and must be kept in step with it -- a nuisance term added there
        and not here is a silent parity gap between two editors a user reads as
        the same. What differs is only the first step: the decay is built and
        quenched on the time axis, then convolved as a *curve*, because it is
        not a finite mixture of exponentials and cannot be handed to the
        spectrum convolution.
        """
        if verbose is None:
            verbose = chisurf.core.settings.cs_settings["verbose"]
        if scatter is None:
            scatter = self.generic.scatter
        if background is None:
            background = self.generic.background
        if shift_bg_with_irf is None:
            shift_bg_with_irf = chisurf.core.settings.cs_settings["tcspc"]["shift_bg_with_irf"]
        if background_curve is None:
            background_curve = self.generic.background_curve

        time = np.asarray(self.convolve.data.x, dtype=float)
        decay = self.unconvolved_decay(time)

        # `full` is a plain linear convolution of a decay with the IRF, which is
        # what this model needs; the `per`/`exp` branches expect a lifetime
        # spectrum. Periodicity is already folded into `decay` above.
        decay = self.convolve.convolve(
            decay, verbose=verbose, scatter=scatter, mode="full", **kwargs
        )

        if isinstance(background_curve, Curve):
            if shift_bg_with_irf:
                background_curve = background_curve << self.convolve.timeshift
            bg_y = np.copy(background_curve.y)
            bg_y *= self.generic.n_ph_bg / bg_y.sum()
            decay *= self.generic.n_ph_fl / decay.sum()
            decay += bg_y

        self.corrections.pileup(decay)
        self.convolve.scale(decay, bg=self.generic.background)
        decay += background
        decay = self.corrections.linearize(decay)
        self.y = np.maximum(decay, 0)

    # ── persistence ──────────────────────────────────────────────────

    def get_state(self) -> dict:
        """Return a JSON-serializable state snapshot.

        The dimensionality is a plain attribute rather than a
        :class:`FittingParameter` -- it selects a decay *law*, it is not
        optimized -- so nothing in the parameter machinery persists it. Without
        this, saving a 1-D fit and reopening it gave a 2-D fit carrying the 1-D
        density: the number survived and the geometry it belongs to did not.
        """
        state = super().get_state()
        if not isinstance(state, dict):
            state = {}
        extra = state.get("extra")
        if not isinstance(extra, dict):
            extra = {}
            state["extra"] = extra
        extra["dimension"] = int(self.dimension)
        extra["c_over_c0"] = float(self.c_over_c0)
        extra["forster_radius"] = float(self.forster_radius)
        extra["tau_d0"] = float(self.tau_d0)
        return state

    def set_state(self, state: dict) -> None:
        """Restore state from a JSON-serializable snapshot."""
        super().set_state(state)
        if not isinstance(state, dict):
            return
        extra = state.get("extra")
        if not isinstance(extra, dict):
            return
        if "dimension" in extra:
            try:
                self.dimension = int(extra["dimension"])
            except (TypeError, ValueError):
                pass
        for key, setter in (
            ("c_over_c0", "c_over_c0"),
            ("forster_radius", "forster_radius"),
            ("tau_d0", "tau_d0"),
        ):
            if key in extra:
                try:
                    setattr(self, setter, float(extra[key]))
                except (TypeError, ValueError):
                    pass

    def __str__(self) -> str:
        """Return a string representation."""
        s = super().__str__()
        s += "\nDistributed acceptors"
        s += "\n------------------\n"
        s += (
            f"dimensionality: {self.dimension}\n"
            f"C/C0: {self.c_over_c0:.3f}\n"
            f"E: {self.fret_efficiency:.3f}\n"
            f"density: {self.acceptor_density:.3e} 1/A^{self.dimension}\n"
        )
        return s
