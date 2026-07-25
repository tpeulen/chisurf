"""Dynamic three-state PDA model via Monte-Carlo (Gillespie) simulation.

Port of PAM's arbitrary-state dynamic PDA
(``functions/PDAFit/dynamic_sim/dyn_sim_arbitrary_states_gillespie.m``),
restricted here to **three** exchanging conformational states with two-colour
detection. Unlike the two-state model — whose occupation-time distribution has
a closed form (see :mod:`chisurf.core.models.pda.dynamic`) — three or more
states have no simple analytic form, so PAM (and this port) sample the
continuous-time Markov trajectory.

Method
------
Each state ``i`` has a Gaussian inter-dye distance (``R_i`` ± ``s_i``) and hence
a mean per-photon green probability ``pG_i`` (see
:func:`chisurf.core.models.pda.common.green_probability_from_efficiency`). A
rate matrix ``K`` (Hz) with ``K[target, source]`` = rate ``source -> target``
governs the kinetics. For ``n_windows`` observation windows of length
``sim_time`` we sample the trajectory and record the fraction of time spent in
each state — via
:func:`chisurf.core.fluorescence.kinetics.occupation_time_fractions`, which runs
the photon simulator's kinetics rather than keeping a second Gillespie loop
here. The time-averaged green probability of a window is
``pG(f) = f1 pG1 + f2 pG2 + f3 pG3`` (equal-brightness assumption); the
histogram of ``pG`` over all windows becomes the amplitude/probability spectrum
handed to :class:`tttrlib.Pda`.

The (rate-only) Monte-Carlo result is cached and reused across fit iterations
that change only distances/corrections, so the simulation reruns only when the
rate matrix, ``sim_time`` or ``n_windows`` change.
"""

from __future__ import annotations

import numpy as np
import tttrlib

import chisurf as cs
import chisurf.core.models.tcspc.fret
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.fluorescence.general import distance_to_fret_efficiency
from chisurf.core.fluorescence.kinetics import occupation_time_fractions
from chisurf.core.math.functions.distributions import normal_distribution
from chisurf.core.models.model import ModelCurve
from chisurf.core.models.pda.common import (
    PdaDiagnosticsMixin,
    green_probability_from_efficiency,
    mask_zero_photon_bins,
    pda_1d_residuals_from_s1s2,
    pda_observation_time,
    resolve_fit_settings,
)
from chisurf.core.models.pda.nusiance import PdaFretNuisance


class PdaDynamicThreeStates(FittingParameterGroup):
    """Three exchanging states (R, sigma) with a 3x3 rate scheme (Hz)."""

    def __init__(self, name: str = "pda_dynamic3_states", **kwargs):
        """Initialize the three-state parameter group."""
        super().__init__(name=name, **kwargs)
        self._R = []
        self._s = []
        defaults_R = (35.0, 50.0, 70.0)
        for i, r0 in enumerate(defaults_R, start=1):
            self._R.append(FittingParameter(
                value=r0, name=f"R{i}", lb=1.0, ub=200.0, bounds_on=True,
                label_text=f"R<sub>{i}</sub>"))
            self._s.append(FittingParameter(
                value=6.0, name=f"s{i}", lb=0.5, ub=50.0, bounds_on=True,
                label_text=f"s<sub>{i}</sub>"))
        # Six inter-state rates kIJ (I->J), Hz, fixed by default.
        self._rates = {}
        for i in (1, 2, 3):
            for j in (1, 2, 3):
                if i == j:
                    continue
                self._rates[(i, j)] = FittingParameter(
                    value=100.0, name=f"k{i}{j}", lb=0.0, ub=1e9, bounds_on=True,
                    fixed=True, label_text=f"k<sub>{i}{j}</sub>")
        # Monte-Carlo controls (fixed, output-only spinners). The observation
        # time is deliberately NOT one of them: it is a property of the data,
        # and a spinner that disagrees with how the data was segmented silently
        # rescales every rate. The model reads it from the dataset instead.
        self._n_windows = FittingParameter(
            value=2000, name="n_windows", lb=100, ub=200000, bounds_on=True, fixed=True,
            label_text="N<sub>win</sub>")

    @property
    def distances(self) -> np.ndarray:
        """Mean distances of the three states."""
        return np.array([p.value for p in self._R])

    @property
    def sigmas(self) -> np.ndarray:
        """Widths of the three states."""
        return np.array([p.value for p in self._s])

    def rate_matrix(self) -> np.ndarray:
        """Return the 3x3 rate matrix ``K[target, source]`` (Hz)."""
        K = np.zeros((3, 3), dtype=float)
        for (i, j), p in self._rates.items():
            # kIJ is rate I->J, so target=j, source=i (0-based indices).
            K[j - 1, i - 1] = max(0.0, float(p.value))
        return K

    @property
    def n_windows(self) -> int:
        """Number of Monte-Carlo observation windows."""
        return int(round(float(self._n_windows.value)))


class PdaDynamicThreeStateModel(PdaDiagnosticsMixin, ModelCurve):
    """Dynamic three-state (dual-color) PDA model via Monte-Carlo mixing."""

    name = "PDA-dynamic-3-state (MC)"

    #: Declarative AutoForm layout (PRD-38 model/view-spec split).
    view_spec_file = "dynamic_mc.view.json"

    def __init__(
        self,
        fit: cs.core.fitting.fit.Fit,
        nuisance: PdaFretNuisance | None = None,
        states: PdaDynamicThreeStates | None = None,
        n_hist: int = 81,
        seed: int = 1,
        **kwargs,
    ):
        """Initialize the dynamic three-state PDA model.

        Parameters
        ----------
        fit : cs.core.fitting.fit.Fit
            Fit holding the experimental PDA data.
        nuisance : PdaFretNuisance, optional
            Correction/nuisance parameter group.
        states : PdaDynamicThreeStates, optional
            Three-state distance / rate group.
        n_hist : int
            Number of bins for the pG histogram (probability spectrum size).
        seed : int
            Monte-Carlo seed (kept fixed for reproducible fits).
        **kwargs
            Forwarded to the parent constructor.
        """
        super().__init__(fit, **kwargs)
        self.nuisance = nuisance or PdaFretNuisance(name="pda_fret_nuisance", fit=fit, **kwargs)
        self.states = states or PdaDynamicThreeStates(name="pda_dynamic3_states", fit=fit, **kwargs)
        self.fret_parameters = chisurf.core.models.tcspc.fret.FRETParameters(
            enable_fret_efficiency=False
        )
        self.n_hist = int(n_hist)
        #: How the time-averaged probability distribution is obtained.
        #: ``"szabo-gopich"`` matches a shape to its exact first two moments
        #: (deterministic, closed form, any number of states);
        #: ``"monte-carlo"`` samples trajectories with Gillespie. The analytic
        #: route is the default because a stochastic objective makes the fit
        #: itself noisy -- the optimiser sees simulation scatter as structure.
        #: It agrees with sampling to ~1% once there is more than a transition
        #: or two per window; in the slow-exchange limit the true distribution
        #: is trimodal and a two-moment match cannot follow it, so use
        #: ``"monte-carlo"`` there -- or a static multi-species model, which is
        #: what slow exchange actually means.
        self.method = "szabo-gopich"
        self.seed = int(seed)
        self._mc_cache_key = None
        self._mc_fractions = None
        kw_pda = {
            "hist2d_nmax": fit.data.pda["maximum_number_of_photons"],
            "hist2d_nmin": fit.data.pda["minimum_number_of_photons"],
            "pF": fit.data.pda["ps"],
        }
        self.pda = tttrlib.Pda(**kw_pda)
        # Which 1D projection of the S1S2 matrix the fit runs on, how it is
        # binned, and under which counting statistic (see PdaFitSettings).
        self.fit_settings = resolve_fit_settings(None, None)
        self.residual_mode = "1D"

    @property
    def observation_time(self) -> float:
        """Return the dataset's observation time in seconds.

        See :func:`chisurf.core.models.pda.common.pda_observation_time`. The
        rates in the scheme are absolute (Hz), so this is what turns them into
        the transitions-per-window the occupation-time distribution depends on.
        """
        return pda_observation_time(self.fit)

    def _time_fractions(self) -> np.ndarray:
        """Return cached Monte-Carlo time-fractions, re-simulating only on change."""
        K = self.states.rate_matrix()
        sim_time = self.observation_time
        n_windows = self.states.n_windows
        key = (K.tobytes(), float(sim_time), int(n_windows), int(self.seed))
        if key != self._mc_cache_key or self._mc_fractions is None:
            self._mc_fractions = occupation_time_fractions(K, sim_time, n_windows, self.seed)
            self._mc_cache_key = key
        return self._mc_fractions

    def _mean_green_probability(self, R: float, sigma: float, r, pG) -> float:
        """Return a state's Gaussian-averaged per-photon green probability."""
        if sigma <= 0.0:
            e = distance_to_fret_efficiency(np.array([R]), self.fret_parameters.forster_radius)
            return float(green_probability_from_efficiency(e, self.nuisance)[0])
        g = normal_distribution(x=r, loc=float(R), scale=float(sigma), norm=False)
        s = float(np.sum(g))
        return 0.5 if s <= 0.0 else float(np.sum((g / s) * pG))

    def update_model(self, verbose: bool | None = None, **kwargs):
        """Build the three-state Monte-Carlo probability spectrum and update the curve."""
        st = self.states
        r = chisurf.core.models.tcspc.fret.rda_axis
        R0 = self.fret_parameters.forster_radius
        E = distance_to_fret_efficiency(r, R0)
        pG = green_probability_from_efficiency(E, self.nuisance)

        pG_states = np.array([
            self._mean_green_probability(R, s, r, pG)
            for R, s in zip(st.distances, st.sigmas)
        ])

        if self.method == "szabo-gopich":
            # Analytic: keep the exact first two moments of the time-averaged
            # green probability and match a shape to them. Deterministic, where
            # the Monte-Carlo route makes the fit objective itself noisy.
            from chisurf.core.fluorescence.kinetics import szabo_gopich_quadrature

            centers, weights = szabo_gopich_quadrature(
                self.states.rate_matrix(), pG_states, self.observation_time,
                n_nodes=self.n_hist,
            )
        else:
            fractions = self._time_fractions()  # (n_windows, 3)
            pch1_samples = fractions @ pG_states  # (n_windows,)

            # Histogram the per-window green probabilities into a compact spectrum.
            counts, edges = np.histogram(pch1_samples, bins=self.n_hist, range=(0.0, 1.0))
            centers = 0.5 * (edges[:-1] + edges[1:])
            weights = counts.astype(float)
            total = weights.sum()
            if total > 0.0:
                weights /= total

        keep = weights > 0.0
        weights = weights[keep]
        centers = centers[keep]

        # Optional donor-only fraction (shared semantics with the other models).
        xD0 = float(np.clip(self.fret_parameters.xDOnly, 0.0, 1.0))
        if xD0 > 0.0 and weights.size:
            weights = weights * (1.0 - xD0)
            pG_d0 = float(green_probability_from_efficiency(np.array([1e-9]), self.nuisance)[0])
            weights = np.concatenate(([xD0], weights))
            centers = np.concatenate(([pG_d0], centers))

        prob_spectrum = np.empty(weights.size * 2, dtype=np.float64)
        prob_spectrum[0::2] = weights
        prob_spectrum[1::2] = centers

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
