"""Simulated bursts with exchange, and whether the fit gets the rate back.

**These are code tests, never physics tests.** The simulator and the model share
the physics being asserted, so an error in that physics passes here silently. What
they do prove is that the implementation computes what it claims to — and that is
worth having, because the simulator reaches the same numbers by a *different route*:
it samples an explicit Markov path per burst and draws each photon's micro time as
a response sample plus an exponential delay, where the model evaluates the
occupation-time law and the wrapped moments in closed form.

The interesting axis is the **timescale**. Exchange is only visible when it is
comparable to a burst, and the recovery is correspondingly good in the middle and
poor at both ends — which is physics, not a defect, and is asserted as such.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.mfd.fit import (
    MfdKineticModel,
    MfdModel,
    load_mfd_data,
)
from chisurf.core.fluorescence.mfd.histogram import HistogramAxes
from chisurf.core.fluorescence.mfd.moments import pattern_moments
from chisurf.core.fluorescence.mfd.simulate import (
    SimulationParameters,
    rate_matrix_for,
    simulate_mfd,
)

AXES = HistogramAxes.default(
    n_ratio=40, n_micro_time=40, micro_time_range=(0.5, 6.0)
)


def _folder(tmp_path, regime, *, n_bursts=2500, seed=17):
    """Simulate a measurement in one regime and write it as a burst folder."""
    parameters = SimulationParameters(
        n_bursts=n_bursts,
        rate_matrix=rate_matrix_for(regime, mean_duration=2.0e-3),
        seed=seed,
    )
    simulated = simulate_mfd(parameters)
    folder = simulated.write_folder(tmp_path / str(regime))
    return simulated, folder


# ──────────────────────────────────────────────────────────────────────────────
# The simulator describes itself honestly
# ──────────────────────────────────────────────────────────────────────────────
def test_the_written_folder_reads_back_through_the_ordinary_path(tmp_path):
    """A simulated folder must go through the same reader as a measured one.

    Including the channel verification and the photon-index detection — a simulator
    with its own private loader would test the model and none of the machinery
    around it.
    """
    simulated, folder = _folder(tmp_path, "intermediate", n_bursts=400)
    data = load_mfd_data(folder, axes=AXES, min_green_photons=20)
    preparation = data.preparation

    assert len(preparation) == 400
    assert preparation.convention.inclusive is True
    assert preparation.convention.agreement == pytest.approx(1.0)
    assert preparation.verified_channels == ("green", "red")
    # Sources come from the manifest the simulator wrote, not from a guess.
    assert set(preparation.sources.origin.values()) == {"manifest"}
    # And the mean micro time is the writer's column, not the photon fallback.
    assert preparation.summary["mean_micro_time_source"] == "bur column"


def test_the_burst_tables_reproduce_the_generated_photons(tmp_path):
    """Per-detector counts in the `.bur` must be the photons that were emitted."""
    simulated, folder = _folder(tmp_path, "static", n_bursts=200)
    data = load_mfd_data(folder, axes=AXES, min_green_photons=20)
    preparation = data.preparation

    green = preparation.channel_index("green")
    red = preparation.channel_index("red")
    for row, (first, last) in enumerate(simulated.start_stop):
        emitted = simulated.channels[first : last + 1]
        assert preparation.counts[row, green] == int((emitted == 0).sum())
        assert preparation.counts[row, red] == int((emitted == 1).sum())


def test_the_declared_response_is_recoverable_and_the_estimated_one_is_biased(tmp_path):
    """Estimating the response from non-burst photons is contaminated — measurably.

    Bursts below the search threshold are never detected, so their fluorescence
    lands in the "non-burst" stream and drags the estimated response late. This is a
    property of the experiment, visible on real data too; the simulator's value is
    that here the true answer is known, so the bias is a number rather than a
    suspicion.
    """
    simulated, folder = _folder(tmp_path, "static", n_bursts=1200)
    declared = simulated.true_responses()["green"]
    estimated = load_mfd_data(folder, axes=AXES).responses["green"]

    declared_mean, _ = pattern_moments(declared.irf, declared.dt)
    estimated_mean, _ = pattern_moments(estimated.irf, estimated.dt)

    assert declared_mean == pytest.approx(simulated.parameters.irf_centre, abs=0.05)
    # The estimate is late, by nanoseconds rather than picoseconds.
    assert estimated_mean > declared_mean + 1.0


# ──────────────────────────────────────────────────────────────────────────────
# The three regimes are actually different
# ──────────────────────────────────────────────────────────────────────────────
def test_the_regimes_are_named_in_transitions_per_burst():
    """A rate only means something next to a burst duration."""
    slow = rate_matrix_for("slow", mean_duration=2.0e-3)
    fast = rate_matrix_for("fast", mean_duration=2.0e-3)
    assert rate_matrix_for("static", mean_duration=2.0e-3) is None
    assert float(fast.sum()) > float(slow.sum()) * 100.0
    # The same regime at a ten-times shorter burst needs ten-times faster rates.
    shorter = rate_matrix_for("slow", mean_duration=2.0e-4)
    assert float(shorter.sum()) == pytest.approx(float(slow.sum()) * 10.0, rel=1e-9)
    # Varying the timescale must not move the equilibrium populations.
    from chisurf.core.fluorescence.kinetics import equilibrium_populations

    assert np.allclose(
        equilibrium_populations(slow), equilibrium_populations(fast), atol=1e-9
    )


def test_exchange_fills_the_gap_between_the_states(tmp_path):
    """The signal: bursts caught mid-exchange land between the two populations."""
    centres = 0.5 * (AXES.ratio_edges[:-1] + AXES.ratio_edges[1:])
    between = {}
    for regime in ("slow", "intermediate", "fast"):
        _, folder = _folder(tmp_path, regime, n_bursts=1500)
        counts = load_mfd_data(folder, axes=AXES, min_green_photons=20).observed.counts
        marginal = counts.sum(axis=1)
        marginal = marginal / marginal.sum()
        between[regime] = float(marginal[(centres > 0.30) & (centres < 0.60)].sum())

    # Slow exchange leaves the gap empty; intermediate fills it; fast puts
    # everything there, because the two states have merged into their average.
    assert between["slow"] < 0.12
    assert between["intermediate"] > between["slow"] * 1.5
    assert between["fast"] > between["intermediate"]


# ──────────────────────────────────────────────────────────────────────────────
# Rate recovery — milestone 1b as a *code* test
# ──────────────────────────────────────────────────────────────────────────────
def _fit_rate(data, parameters, start=400.0):
    """Fit the single exchange rate of a symmetric two-state scheme."""
    from scipy.optimize import least_squares

    def residuals(values):
        rate = float(np.exp(values[0]))
        model = MfdKineticModel(
            optics=parameters.optics,
            states=parameters.states,
            populations=[0.5, 0.5],
            donor_only=parameters.donor_only,
            rate_matrix=np.array([[0.0, rate / 2.0], [rate / 2.0, 0.0]]),
        )
        # Every bin scored, so the residual vector has a fixed length: masking
        # empty-model bins makes it change with the parameter, and the optimizer
        # cannot difference a vector whose length moves.
        return model.score(data, mask_empty_model=False).residuals

    result = least_squares(residuals, [np.log(start)], diff_step=0.05, xtol=1e-8)
    return float(np.exp(result.x[0]))


def _prepared(tmp_path, regime, n_bursts=3000):
    """Simulate a regime and load it with the declared instrument response."""
    simulated, folder = _folder(tmp_path, regime, n_bursts=n_bursts)
    data = load_mfd_data(
        folder,
        axes=AXES,
        min_green_photons=20,
        responses=simulated.true_responses(),
        n_signal_bins=16,
        n_span_bins=4,
    )
    return simulated, data


@pytest.mark.slow
def test_a_known_exchange_rate_is_recovered_where_it_is_identifiable(tmp_path):
    """The rate that generated the bursts comes back, near one transition per burst.

    This is what milestone 1b would test on real data. On simulated data it tests
    the *implementation* — the occupation-time propagator, the nested background sum
    and the deviance, wired together — and explicitly not the physics they share
    with the generator.
    """
    simulated, data = _prepared(tmp_path, "intermediate")
    truth = float(np.asarray(simulated.parameters.rate_matrix).sum())
    assert _fit_rate(data, simulated.parameters) == pytest.approx(truth, rel=0.20)


@pytest.mark.slow
@pytest.mark.parametrize("regime", ["slow", "fast"])
def test_the_rate_is_only_an_order_of_magnitude_away_from_that_window(tmp_path, regime):
    """Outside the informative window the rate is not accurately determined.

    That is the physics, and it is symmetric. Far below one transition per burst
    almost no burst ever switches, so the histogram barely constrains how *rarely*
    it happens; far above, every burst reports the same average, so it barely
    constrains how *often*. The fit still lands on the right order of magnitude and
    should not be asked for more — a test demanding accuracy here would be
    asserting something the data cannot support, and would eventually be "fixed"
    by making the model agree with it.
    """
    simulated, data = _prepared(tmp_path, regime)
    truth = float(np.asarray(simulated.parameters.rate_matrix).sum())
    start = 400.0 if regime == "slow" else 5000.0
    fitted = _fit_rate(data, simulated.parameters, start=start)
    assert 0.3 * truth < fitted < 3.0 * truth


@pytest.mark.slow
def test_static_data_does_not_invent_exchange(tmp_path):
    """The most important negative: no dynamics in, no rate out.

    A model that produced a finite rate here would be reporting exchange from
    static heterogeneity, which is the failure every part of this design is
    arranged to avoid.
    """
    simulated, data = _prepared(tmp_path, "static")
    fitted = _fit_rate(data, simulated.parameters)
    # Far below one transition per burst, i.e. indistinguishable from no exchange.
    assert fitted < 0.2 / simulated.parameters.mean_duration


@pytest.mark.slow
def test_the_static_model_is_beaten_by_the_kinetic_one_on_exchanging_data(tmp_path):
    """Exchange has to be worth fitting, or there is no case for the machinery."""
    simulated, data = _prepared(tmp_path, "intermediate")
    common = dict(
        optics=simulated.parameters.optics,
        states=simulated.parameters.states,
        populations=[0.5, 0.5],
        donor_only=simulated.parameters.donor_only,
    )
    truth = float(np.asarray(simulated.parameters.rate_matrix).sum())
    static = MfdModel(**common).score(data, mask_empty_model=False)
    kinetic = MfdKineticModel(
        **common, rate_matrix=np.array([[0.0, truth / 2.0], [truth / 2.0, 0.0]])
    ).score(data, mask_empty_model=False)
    assert kinetic.score < static.score * 0.9


# ──────────────────────────────────────────────────────────────────────────────
# The burst-wise source, and the uncertainties only it can support
# ──────────────────────────────────────────────────────────────────────────────
def _burstwise_curve(data, parameters, rates, max_bursts=500):
    """Return the burst-wise log-likelihood at each of several exchange rates."""
    from chisurf.core.fluorescence.mfd.fit import burstwise_log_probabilities

    out = []
    for rate in rates:
        model = MfdKineticModel(
            optics=parameters.optics,
            states=parameters.states,
            populations=[0.5, 0.5],
            donor_only=parameters.donor_only,
            rate_matrix=np.array([[0.0, rate / 2.0], [rate / 2.0, 0.0]]),
        )
        values = burstwise_log_probabilities(
            model, data, max_bursts=max_bursts, seed=1
        )
        out.append(float(np.sum(values[np.isfinite(values)])))
    return np.asarray(out)


@pytest.mark.slow
def test_the_photon_by_photon_likelihood_peaks_at_the_true_rate(tmp_path):
    """A second, independent scoring route agrees with the first.

    The histogram source compresses each burst to two numbers; this one keeps every
    photon's micro time. They share the model but not the statistic, so a rate they
    agree on is worth far more than one either produces alone — and a rate they
    disagreed on would be one nobody should report.
    """
    simulated, data = _prepared(tmp_path, "intermediate", n_bursts=1500)
    truth = float(np.asarray(simulated.parameters.rate_matrix).sum())
    rates = truth * np.array([1 / 6, 1 / 2, 1.0, 2.0, 6.0])
    curve = _burstwise_curve(data, simulated.parameters, rates)

    assert int(np.argmax(curve)) == 2, "the likelihood does not peak at the truth"
    # And it is a peak, not a plateau: the neighbours are meaningfully worse.
    assert curve[2] - curve[1] > 5.0
    assert curve[2] - curve[3] > 5.0


@pytest.mark.slow
def test_static_data_gives_no_burstwise_preference_for_exchange(tmp_path):
    """The negative again, through the reference source rather than the fast one."""
    simulated, data = _prepared(tmp_path, "static", n_bursts=1500)
    rates = np.array([1.0, 50.0, 1500.0, 20000.0])
    curve = _burstwise_curve(data, simulated.parameters, rates)
    # The slowest rate — i.e. effectively no exchange — is preferred.
    assert int(np.argmax(curve)) == 0


def test_the_burstwise_source_needs_photons(tmp_path):
    """Asking for it without photons is an error, not a silently different answer."""
    from chisurf.core.fluorescence.mfd.fit import burstwise_log_probabilities

    simulated, folder = _folder(tmp_path, "static", n_bursts=200)
    data = load_mfd_data(
        folder, axes=AXES, responses=simulated.true_responses()
    )
    data.preparation.summary.pop("_tttrs")
    model = MfdModel(
        optics=simulated.parameters.optics,
        states=simulated.parameters.states,
        donor_only=simulated.parameters.donor_only,
    )
    with pytest.raises(ValueError, match="with_photons=True"):
        burstwise_log_probabilities(model, data)


def test_only_the_burstwise_source_may_supply_uncertainties():
    """Enforced in code, because the footnote version of this rule goes unread."""
    from chisurf.core.fluorescence.mfd.sources import uncertainty_is_valid

    assert uncertainty_is_valid(["burstwise"])
    assert not uncertainty_is_valid(["histogram"])
    assert not uncertainty_is_valid(["pooled_decay"])
    assert not uncertainty_is_valid(["burstwise", "histogram"])
    with pytest.raises(ValueError):
        uncertainty_is_valid(["nonsense"])


@pytest.mark.slow
def test_a_burst_bootstrap_gives_a_finite_spread(tmp_path):
    """Resampling bursts perturbs what actually varies between repeats."""
    from chisurf.core.fluorescence.mfd.fit import bootstrap_uncertainties

    simulated, data = _prepared(tmp_path, "intermediate", n_bursts=1500)
    truth = float(np.asarray(simulated.parameters.rate_matrix).sum())

    def refit(replica):
        return {"rate": _fit_rate(replica, simulated.parameters, start=truth)}

    result = bootstrap_uncertainties(refit, data, n_resamples=6, seed=3)
    assert set(result) == {"rate"}
    assert result["rate"]["std"] > 0.0
    # The spread must be a fraction of the value, not the same size as it — a
    # bootstrap that wide would mean the rate is not determined at all.
    assert result["rate"]["std"] < 0.5 * result["rate"]["mean"]
    assert len(result["rate"]["values"]) == 6
