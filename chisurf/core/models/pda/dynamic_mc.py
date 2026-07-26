"""Dynamic **N-state** PDA model with a free transition-rate matrix (two colours).

Counterpart of PAM's arbitrary-state dynamic PDA
(``functions/PDAFit/dynamic_sim/dyn_sim_arbitrary_states_gillespie.m``). The
two-state model (:mod:`chisurf.core.models.pda.dynamic`) has a closed-form
occupation-time law; beyond two states there is none, so the time average is
either moment-matched or sampled — see ``method`` below.

Any number of states, any scheme
--------------------------------
The number of states is a settable ``n_states``, and **every** off-diagonal rate
``k_ij`` is an ordinary fitting parameter. Nothing about the scheme is baked in:
fix the rates you do not want (a linear chain is the cycle with ``k_13`` and
``k_31`` at zero), free the ones you do, and link them to impose detailed balance
or a symmetry. The rate matrix is ``K[target, source]`` in Hz, and since the
model knows its dataset's observation time the rates are absolute rather than
per-window.

Method
------
Each state ``i`` has a Gaussian inter-dye distance (``R_i`` ± ``s_i``) and hence
a mean per-photon green probability ``pG_i`` (see
:func:`chisurf.core.models.pda.common.green_probability_from_efficiency`). The
time-averaged green probability of a window is ``pG(f) = sum_i f_i pG_i``
(equal-brightness assumption) over the fraction ``f_i`` of the window spent in
each state; the distribution of ``pG`` becomes the amplitude/probability spectrum
handed to :class:`tttrlib.Pda`.

The distribution of ``f`` comes from one of two routes, both valid for any ``N``:

* ``"szabo-gopich"`` (default) matches a bounded shape to the exact first two
  moments — deterministic, so the fit objective is smooth;
* ``"monte-carlo"`` samples occupation times with
  :func:`chisurf.core.fluorescence.kinetics.occupation_time_fractions`, which
  runs the photon simulator's kinetics rather than a second Gillespie loop here.
  Exact, at the cost of a stochastic objective; needed in the slow-exchange limit
  where the distribution is multimodal and no two-moment match has three peaks.

The sampled result is cached on the rate matrix, observation time and sample
count, so it reruns only when the kinetics actually change.
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

#: Starting distances when a state is added, cycled so a fresh scheme is spread
#: over the FRET-sensitive range rather than stacked on one value.
_DEFAULT_DISTANCES = (35.0, 50.0, 70.0, 45.0, 60.0, 80.0)


class PdaDynamicNStates(FittingParameterGroup):
    """``n`` exchanging states (R, sigma) with a free ``n x n`` rate scheme (Hz).

    Every off-diagonal rate is an ordinary fitting parameter, so the scheme is
    whatever the rates say: fix ``k_13``/``k_31`` at zero for a linear chain,
    free everything for a fully connected one, link a pair to impose detailed
    balance. Rates are held in **lists**, which is what makes them visible to
    ``find_parameters`` — parameters stored in a dict or a tuple are silently
    invisible to the optimiser, and this group used to keep them in a dict.
    """

    def __init__(self, name: str = "pda_dynamic_n_states", n_states: int = 3, **kwargs):
        """Initialize the N-state parameter group.

        Parameters
        ----------
        name : str
            Group name.
        n_states : int
            Number of exchanging states; at least two.
        **kwargs
            Forwarded to the parent constructor.
        """
        super().__init__(name=name, **kwargs)
        self._R: list = []
        self._s: list = []
        #: Off-diagonal rates, row-major over ``(i, j), i != j`` with 1-based
        #: labels. A list, not a dict -- see the class docstring.
        self._rates: list = []
        self._n_states = 0
        # Sample size of the Monte-Carlo route; the observation time is
        # deliberately NOT a setting here -- it is a property of the data, and a
        # spinner that disagrees with how the data was segmented silently
        # rescales every rate. The model reads it from the dataset instead.
        self._n_windows = FittingParameter(
            value=2000, name="n_windows", lb=100, ub=200000, bounds_on=True, fixed=True,
            label_text="N<sub>win</sub>")
        self.n_states = int(n_states)

    # -- size ---------------------------------------------------------------

    @property
    def n_states(self) -> int:
        """Number of exchanging states."""
        return self._n_states

    @n_states.setter
    def n_states(self, value: int) -> None:
        """Resize the scheme, keeping the values of states and rates that survive."""
        target = max(2, int(value))
        if target == self._n_states:
            return
        old_rates = {(i, j): p.value for (i, j), p in self.rate_items()}

        while len(self._R) > target:
            self._R.pop()
            self._s.pop()
        while len(self._R) < target:
            index = len(self._R) + 1
            self._R.append(FittingParameter(
                value=_DEFAULT_DISTANCES[(index - 1) % len(_DEFAULT_DISTANCES)],
                name=f"R{index}", lb=1.0, ub=200.0, bounds_on=True,
                label_text=f"R<sub>{index}</sub>"))
            self._s.append(FittingParameter(
                value=6.0, name=f"s{index}", lb=0.5, ub=50.0, bounds_on=True,
                label_text=f"s<sub>{index}</sub>"))

        self._rates = []
        for i in range(1, target + 1):
            for j in range(1, target + 1):
                if i == j:
                    continue
                self._rates.append(FittingParameter(
                    value=float(old_rates.get((i, j), 100.0)),
                    name=f"k{i}_{j}", lb=0.0, ub=1e9, bounds_on=True,
                    fixed=True, label_text=f"k<sub>{i}{j}</sub>"))
        self._n_states = target

    def rate_items(self):
        """Yield ``((i, j), parameter)`` for every off-diagonal rate, 1-based."""
        pairs = [(i, j)
                 for i in range(1, self._n_states + 1)
                 for j in range(1, self._n_states + 1) if i != j]
        return list(zip(pairs, self._rates))

    def rates_by_name(self) -> dict:
        """Return ``{"k<i>_<j>": parameter}`` for every off-diagonal rate.

        The handle for scripting a scheme: free the rates it has, fix the ones
        it does not, and link a pair to impose detailed balance::

            rates = model.states.rates_by_name()
            rates["k1_3"].value = 0.0        # no direct 1 <-> 3
            rates["k3_1"].value = 0.0
            rates["k1_2"].fixed = False      # fit the rest
        """
        return {p.name: p for p in self._rates}

    # -- values -------------------------------------------------------------

    @property
    def distances(self) -> np.ndarray:
        """Mean distances of the states."""
        return np.array([p.value for p in self._R])

    @property
    def sigmas(self) -> np.ndarray:
        """Widths of the states."""
        return np.array([p.value for p in self._s])

    def rate_matrix(self) -> np.ndarray:
        """Return the ``n x n`` rate matrix ``K[target, source]`` (Hz)."""
        n = self._n_states
        K = np.zeros((n, n), dtype=float)
        for (i, j), p in self.rate_items():
            # k_ij is the rate i -> j, so target = j, source = i (0-based).
            K[j - 1, i - 1] = max(0.0, float(p.value))
        return K

    @property
    def rate_values(self) -> list:
        """Return the flat row-major ``n*n`` rates, diagonal zeroed.

        The view the editable rate-matrix grid binds to; the entries are the
        fitting parameters themselves, so editing the grid moves the parameters
        and their fixed/free state is still controlled from the table.
        """
        n = self._n_states
        flat = [0.0] * (n * n)
        for (i, j), p in self.rate_items():
            flat[(i - 1) * n + (j - 1)] = float(p.value)
        return flat

    @rate_values.setter
    def rate_values(self, values) -> None:
        """Write a flat row-major ``n*n`` grid back onto the rate parameters."""
        n = self._n_states
        flat = list(values)
        if len(flat) != n * n:
            return
        for (i, j), p in self.rate_items():
            p.value = max(0.0, float(flat[(i - 1) * n + (j - 1)]))

    @property
    def state_names(self) -> list:
        """Row/column labels for the rate-matrix grid."""
        return [str(i) for i in range(1, self._n_states + 1)]

    @property
    def n_windows(self) -> int:
        """Number of Monte-Carlo observation windows."""
        return int(round(float(self._n_windows.value)))


class PdaDynamicNStateModel(PdaDiagnosticsMixin, ModelCurve):
    """Dynamic N-state (dual-colour) PDA model with a free rate matrix."""

    name = "PDA-dynamic-N-state"

    #: Declarative AutoForm layout (PRD-38 model/view-spec split).
    view_spec_file = "dynamic_mc.view.json"

    def __init__(
        self,
        fit: cs.core.fitting.fit.Fit,
        nuisance: PdaFretNuisance | None = None,
        states: PdaDynamicNStates | None = None,
        n_hist: int = 81,
        seed: int = 1,
        **kwargs,
    ):
        """Initialize the dynamic N-state PDA model.

        Parameters
        ----------
        fit : cs.core.fitting.fit.Fit
            Fit holding the experimental PDA data.
        nuisance : PdaFretNuisance, optional
            Correction/nuisance parameter group.
        states : PdaDynamicNStates, optional
            Distance / rate group; defaults to three states.
        n_hist : int
            Number of bins for the pG histogram (probability spectrum size).
        seed : int
            Monte-Carlo seed (kept fixed for reproducible fits).
        **kwargs
            Forwarded to the parent constructor.
        """
        super().__init__(fit, **kwargs)
        self.nuisance = nuisance or PdaFretNuisance(name="pda_fret_nuisance", fit=fit, **kwargs)
        self.states = states or PdaDynamicNStates(
            name="pda_dynamic_n_states", fit=fit, **kwargs
        )
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

    # -- scheme size, delegated so the editor can bind to the model ---------

    @property
    def n_states(self) -> int:
        """Number of exchanging states."""
        return self.states.n_states

    @n_states.setter
    def n_states(self, value: int) -> None:
        """Resize the scheme and re-discover the parameters it now has."""
        self.states.n_states = value
        self.states.find_parameters()
        self.find_parameters()
        self._mc_cache_key = None          # the rate matrix changed shape

    @property
    def state_names(self) -> list:
        """Row/column labels for the rate-matrix grid."""
        return self.states.state_names

    @property
    def rate_values(self) -> list:
        """Flat row-major ``n*n`` rates, for the editable rate-matrix grid."""
        return self.states.rate_values

    @rate_values.setter
    def rate_values(self, values) -> None:
        """Write the grid back onto the rate parameters."""
        self.states.rate_values = values

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
        """Build the N-state probability spectrum and update the curve."""
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
