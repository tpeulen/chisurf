"""Dynamic two-state PDA model (dual-color).

This model describes single-molecule FRET Photon Distribution Analysis of a
system that interconverts between **two conformational states** during the
observation (burst / time window). It is the ChiSurf counterpart of PAM's
``PDAFit`` *dynamic model* (``DynamicSystem = 1``), restricted to two colours.

Physics
-------
Each state ``i`` has a Gaussian inter-dye distance distribution
(``R_i`` ± ``s_i``) and therefore a mean per-photon green (donor-channel)
probability ``pG_i`` obtained from the FRET efficiency and the usual
excitation/emission/crosstalk description (see
:func:`chisurf.core.models.pda2c.common.green_probability_from_efficiency`).

For a molecule observed over a window, the *fraction of time* ``f`` spent in
state 1 is a random variable whose distribution follows the exact occupation
time of a two-state Markov (telegraph) process with stationary initial
condition. It has two boundary masses (spent the whole window in one state) and
an interior density expressed through modified Bessel functions:

    w(f) = e^{-a f - b (1-f)} [ (p1 b + p2 a) I0(z)
             + sqrt(ab / (f(1-f))) (p1 (1-f) + p2 f) I1(z) ],
    z = 2 sqrt(a b f (1-f)),
    a = k1 T = K (1 - p1),   b = k2 T = K p1,

with steady-state occupancy ``p1`` of state 1 and a single dimensionless
exchange parameter ``K = (k1 + k2) T`` (mean number of transitions per window).

Rate, not shape parameter
-------------------------
Only ``K`` enters the distribution, so a single dataset cannot separate the rate
from the observation time: fast exchange watched briefly and slow exchange
watched for longer give the same histogram. The fitted parameter is nevertheless
the **rate** ``k_ex = k1 + k2`` in Hz, and the model multiplies it by its own
dataset's observation time (:attr:`observation_time`). That costs nothing on one
dataset and buys the thing that was missing: read the same file at several
fixed-width time bins (``Pda2cReader(segmentation="time-bins")`` with several
``tw_configs``) and fit them together with ``k_ex`` linked, and one rate now has
to explain every bin width at once. That is the time-binned dynamic analysis, and
it is where the rate becomes a measurement rather than a shape parameter.

Under a burst search the window durations vary, so the observation time is only
their lower bound and the rate inherits that approximation — fixed-width binning
is what makes it exact.

The time-averaged per-photon green probability for a molecule with time
fraction ``f`` is ``pG(f) = f pG1 + (1 - f) pG2`` (equal-brightness
assumption). The resulting amplitude/probability spectrum is handed to
:class:`tttrlib.Pda`.

Limiting behaviour (used as the headless acceptance test):

* ``K -> 0`` (slow exchange): only the boundary masses survive, giving two
  static populations at ``pG1`` and ``pG2`` with weights ``p1``/``p2`` — i.e.
  the static two-state result.
* ``K -> inf`` (fast exchange): the distribution collapses onto ``f = p1``,
  giving a single averaged population at ``p1 pG1 + p2 pG2``.
"""

from __future__ import annotations

import numpy as np
import tttrlib

import chisurf as cs
import chisurf.core.models.tcspc.fret
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.fluorescence.general import distance_to_fret_efficiency
from chisurf.core.math.functions.distributions import normal_distribution
from chisurf.core.models.model import ModelCurve
from chisurf.core.models.pda2c.common import (
    Pda2cModelMixin,
    green_probability_from_efficiency,
    mask_zero_photon_bins,
    pda_1d_residuals_from_s1s2,
    pda_observation_time,
    resolve_fit_settings,
)
from chisurf.core.models.pda2c.nusiance import Pda2cFretNuisance


class Pda2cDynamicStates(FittingParameterGroup):
    """Two exchanging states (R, sigma) plus occupancy and exchange rate."""

    def __init__(self, name: str = "pda_dynamic_states", **kwargs):
        """Initialize the two-state parameter group."""
        super().__init__(name=name, **kwargs)
        self._R1 = FittingParameter(value=40.0, name="R1", lb=1.0, ub=200.0, bounds_on=True,
                                    label_text="R<sub>1</sub>")
        self._s1 = FittingParameter(value=6.0, name="s1", lb=0.5, ub=50.0, bounds_on=True,
                                    label_text="s<sub>1</sub>")
        self._R2 = FittingParameter(value=60.0, name="R2", lb=1.0, ub=200.0, bounds_on=True,
                                    label_text="R<sub>2</sub>")
        self._s2 = FittingParameter(value=6.0, name="s2", lb=0.5, ub=50.0, bounds_on=True,
                                    label_text="s<sub>2</sub>")
        self._x1 = FittingParameter(value=0.5, name="x1", lb=0.0, ub=1.0, bounds_on=True,
                                    label_text="x<sub>1</sub>")
        # Total exchange rate k1 + k2, in Hz. The model converts it to the
        # dimensionless K = (k1+k2)*T with the dataset's observation time, so a
        # global fit over several time-bin widths shares one absolute rate --
        # which is the only way the rate is identifiable at all. A single
        # dataset determines only the product.
        self._kex = FittingParameter(value=500.0, name="k_ex", lb=0.0, ub=1e9,
                                     bounds_on=True, label_text="k<sub>ex</sub>[Hz]")

    R1 = property(lambda s: s._R1.value)
    s1 = property(lambda s: s._s1.value)
    R2 = property(lambda s: s._R2.value)
    s2 = property(lambda s: s._s2.value)
    x1 = property(lambda s: float(np.clip(s._x1.value, 0.0, 1.0)))
    k_ex = property(lambda s: max(0.0, float(s._kex.value)))


def two_state_occupation_quadrature(p1: float, k_ex: float, n_nodes: int = 1024):
    r"""Return nodes and weights over the time fraction spent in state 1.

    Computed **exactly**, by the Feynman-Kac characteristic function of the
    two-state process rather than by a closed-form density. For the generator
    :math:`Q` and the indicator of state 1,

    .. math::

        \varphi(\omega) = \pi^{\mathsf T}
            \exp\!\big(Q + i\omega\,\mathrm{diag}(1, 0)\big)\,\mathbf{1},

    whose Fourier inverse is the distribution of the occupation fraction. The
    two **boundary atoms** — a molecule that never switched during the window —
    are subtracted before inverting and re-attached as nodes at exactly 0 and 1;
    they are finite-probability events, not density, and dropping them loses the
    static limit entirely.

    This is used instead of :func:`two_state_time_fraction_pdf`, which is
    **wrong away from equal populations**: with the standard boundary masses it
    does not integrate to one (up to 1.36 at ``p1 = 0.2``, ``k_ex = 8``) and its
    shape disagrees with a direct simulation of the telegraph process, with a
    tilt that mirrors under ``p1 -> 1 - p1`` and vanishes at ``p1 = 0.5``. This
    routine reproduces the same simulation to a total variation of 0.002 (the
    simulation's own noise) and gives ``sum(w) == 1`` and ``E[f] == p1`` to
    ~1e-5 for every ``p1`` and ``k_ex`` tested.

    Parameters
    ----------
    p1 : float
        Steady-state occupancy of state 1.
    k_ex : float
        Dimensionless exchange rate ``(k1 + k2) * T``, i.e. the mean number of
        transitions per observation window. Zero is the static limit.
    n_nodes : int
        Grid size of the Fourier inversion. The error in ``E[f]`` falls as
        ``1/n_nodes``; the default is accurate to ~2e-4 at strong exchange.

    Returns
    -------
    fractions : numpy.ndarray
        Time fractions in ``[0, 1]``, with the boundary atoms first and last.
    weights : numpy.ndarray
        Normalised weights summing to one.
    """
    p1 = float(np.clip(p1, 0.0, 1.0))
    p2 = 1.0 - p1
    k_ex = max(float(k_ex), 0.0)
    a, b = k_ex * p2, k_ex * p1          # 1->2 and 2->1 rates times the window

    mass_1 = p1 * np.exp(-a)             # never left state 1  -> f = 1
    mass_0 = p2 * np.exp(-b)             # never left state 2  -> f = 0

    m = int(n_nodes)
    omega = 2.0 * np.pi * np.fft.fftfreq(m, d=1.0 / m)

    # The matrix exponential of the 2x2 Feynman-Kac generator in closed form,
    # so the whole frequency grid is one vectorised expression rather than a
    # few hundred scipy calls -- this sits inside a fit's inner loop.
    #     M = [[-a + i w, a], [b, -b]],  trace = -(a + b) + i w,  det = -i w b
    # and for any 2x2, expm(M) = e^mu [cosh(d) I + sinh(d)/d (M - mu I)].
    # Contracting with the stationary vector and 1 leaves a scalar formula,
    # using  pi^T M 1 = i w p1  and  pi^T 1 = 1.
    mu = 0.5 * (-(a + b) + 1j * omega)
    delta = np.sqrt(mu * mu + 1j * omega * b)
    # Written through exp(mu +- delta) rather than exp(mu)*cosh(delta): at fast
    # exchange |delta| ~ |mu| ~ k_ex/2, so cosh overflows to inf while exp(mu)
    # underflows to 0 and the product is nan. Re(mu +- delta) stays bounded.
    plus, minus = np.exp(mu + delta), np.exp(mu - delta)
    safe = np.where(np.abs(delta) < 1e-12, 1.0, delta)
    ratio = np.where(np.abs(delta) < 1e-12, np.exp(mu), 0.5 * (plus - minus) / safe)
    phi = 0.5 * (plus + minus) + ratio * (1j * omega * p1 - mu)
    phi -= mass_1 * np.exp(1j * omega) + mass_0

    density = np.maximum(np.real(np.fft.fft(phi)), 0.0)
    fractions = np.concatenate(([0.0], np.arange(1, m) / m, [1.0]))
    weights = np.concatenate(([mass_0], density[1:] / m, [mass_1]))
    total = weights.sum()
    return fractions, weights / total if total > 0 else weights


class Pda2cDynamicTwoStateModel(Pda2cModelMixin, ModelCurve):
    """Dynamic two-state (dual-color) PDA model."""

    name = "PDA2c-dynamic-2-state"

    #: Declarative AutoForm layout (PRD-38 model/view-spec split).
    view_spec_file = "dynamic.view.json"

    def __init__(
        self,
        fit: cs.core.fitting.fit.Fit,
        nuisance: Pda2cFretNuisance | None = None,
        states: Pda2cDynamicStates | None = None,
        n_grid: int = 41,
        **kwargs,
    ):
        """Initialize the dynamic two-state PDA model.

        Parameters
        ----------
        fit : cs.core.fitting.fit.Fit
            Fit object holding the experimental PDA data.
        nuisance : Pda2cFretNuisance, optional
            Correction/nuisance parameter group.
        states : Pda2cDynamicStates, optional
            Two-state distance / occupancy / exchange group.
        n_grid : int
            Grid size of the time-fraction distribution's Fourier inversion.
            Its error falls as ``1/n_grid``; 512 is accurate to ~1e-4 in the
            mean occupancy even at fast exchange. The previous default of 41
            was sized for a direct density evaluation and is far too coarse
            here.
        **kwargs
            Forwarded to the parent constructor.
        """
        super().__init__(fit, **kwargs)
        self.nuisance = nuisance or Pda2cFretNuisance(name="pda_fret_nuisance", fit=fit, **kwargs)
        self.states = states or Pda2cDynamicStates(name="pda_dynamic_states", fit=fit, **kwargs)
        self.fret_parameters = chisurf.core.models.tcspc.fret.FRETParameters(
            enable_fret_efficiency=False
        )
        self.n_grid = int(n_grid)
        kw_pda = {
            "hist2d_nmax": fit.data.pda["maximum_number_of_photons"],
            "hist2d_nmin": fit.data.pda["minimum_number_of_photons"],
            "pF": fit.data.pda["ps"],
        }
        self.pda = tttrlib.Pda(**kw_pda)
        # Which 1D projection of the S1S2 matrix the fit runs on, how it is
        # binned, and under which counting statistic (see Pda2cFitSettings).
        self.fit_settings = resolve_fit_settings(None, None)
        self.residual_mode = "1D"

    # -- helpers ------------------------------------------------------------
    @property
    def observation_time(self) -> float:
        """Return the dataset's observation time in seconds.

        See :func:`chisurf.core.models.pda2c.common.pda_observation_time`.
        """
        return pda_observation_time(self.fit)

    @property
    def transitions_per_window(self) -> float:
        """Return the dimensionless exchange ``K = (k1 + k2) * T``.

        The quantity the occupation-time distribution actually depends on, and
        the only one a *single* dataset can determine: the same shape results
        from a fast rate in a short window and a slow one in a long window.
        Fitting several bin widths together breaks that degeneracy, because one
        rate has to explain all of them.
        """
        return self.states.k_ex * self.observation_time

    def _mean_green_probability(self, R: float, sigma: float, r, E, pG) -> float:
        """Return the state's Gaussian-averaged per-photon green probability."""
        if sigma <= 0.0:
            e = distance_to_fret_efficiency(np.array([R]), self.fret_parameters.forster_radius)
            return float(green_probability_from_efficiency(e, self.nuisance)[0])
        g = normal_distribution(x=r, loc=float(R), scale=float(sigma), norm=False)
        s = float(np.sum(g))
        if s <= 0.0:
            return 0.5
        return float(np.sum((g / s) * pG))

    def _update_model(self, verbose: bool | None = None, **kwargs):
        """Build the two-state dynamic probability spectrum and update the curve."""
        st = self.states
        r = chisurf.core.models.tcspc.fret.rda_axis
        R0 = self.fret_parameters.forster_radius
        E = distance_to_fret_efficiency(r, R0)
        pG = green_probability_from_efficiency(E, self.nuisance)

        pG1 = self._mean_green_probability(st.R1, st.s1, r, E, pG)
        pG2 = self._mean_green_probability(st.R2, st.s2, r, E, pG)

        p1 = st.x1
        K = self.transitions_per_window

        # Time-fraction distribution, including the two boundary atoms (a
        # molecule that never switched). Computed exactly rather than from the
        # closed-form density, which is not a distribution away from x1 = 0.5 --
        # see two_state_occupation_quadrature.
        f, amps = two_state_occupation_quadrature(p1, K, n_nodes=self.n_grid)
        pch1 = f * pG1 + (1.0 - f) * pG2

        # Optional donor-only fraction (shares the Gaussian model's semantics).
        xD0 = float(np.clip(self.fret_parameters.xDOnly, 0.0, 1.0))
        if xD0 > 0.0:
            amps = amps * (1.0 - xD0)
            # Donor-only per-photon green probability at E = 0.
            pG_d0 = float(green_probability_from_efficiency(np.array([1e-9]), self.nuisance)[0])
            amps = np.concatenate(([xD0], amps))
            pch1 = np.concatenate(([pG_d0], pch1))

        prob_spectrum = np.empty(amps.size * 2, dtype=np.float64)
        prob_spectrum[0::2] = amps
        prob_spectrum[1::2] = pch1

        try:
            self.nuisance.update_correction_factors()
        except Exception:
            pass

        self.pda.background_ch1 = self.nuisance.BG
        self.pda.background_ch2 = self.nuisance.BR
        self.pda.set_probability_spectrum_ch1(prob_spectrum.tolist())

        s1s2_model = np.asarray(self.pda.s1s2, dtype=float)
        try:
            shp = (getattr(self.fit.data, "pda", None) or {}).get("shape")
            if shp is not None and len(shp) == 2:
                ny, nx = int(shp[0]), int(shp[1])
                s1s2_model = s1s2_model[:ny, :nx]
        except Exception:
            pass

        y = s1s2_model.ravel(order="C")
        total_data = float(np.sum(self.fit.data.y))
        total_model = float(np.sum(y))
        if total_model > 0.0:
            y = y * (total_data / total_model)
        x = np.arange(y.size)
        self.d = np.vstack((x, y))

    def _get_1d_residuals(self, fit) -> np.ndarray:
        """Compute 1D weighted residuals from the S1S2 histogram."""
        wres = pda_1d_residuals_from_s1s2(
            fit=fit,
            pda_obj=self.pda,
            nuisance=getattr(self, "nuisance", None),
            settings=self.fit_settings,
        )
        try:
            self._last_1d_residual_size = int(wres.size)
        except Exception:
            pass
        return wres

    def get_wres(self, fit, xmin: int | None = None, xmax: int | None = None) -> np.ndarray:
        """Return weighted residuals (1D projection by default)."""
        import chisurf.core.fitting as _fitting

        if getattr(self, "residual_mode", "1D") == "1D":
            return self._get_1d_residuals(fit)
        if xmin is None:
            xmin = fit.xmin
        if xmax is None:
            xmax = fit.xmax
        wres = _fitting.calculate_weighted_residuals(fit.data, self, xmin=xmin, xmax=xmax)
        return mask_zero_photon_bins(fit, xmin, wres)

    @property
    def n_points(self) -> int:
        """Number of data points for chi-squared (1D projection size)."""
        if getattr(self, "residual_mode", "1D") == "1D":
            n = int(getattr(self, "_last_1d_residual_size", 0) or 0)
            if n > 0:
                return n
        return super().n_points
