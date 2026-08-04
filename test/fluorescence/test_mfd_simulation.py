"""Simulated bursts with exchange, and whether the fit gets the rate back.

These exercise the **sources** — the histogram, burst-wise and pooled-decay
scores, the uncertainties, and the anisotropy axis — on data whose answer is
known. The photons come from the confocal simulator in the TTTR library, which
reaches the same numbers by a different route than the model: it walks an
explicit Markov path per molecule and draws each photon's micro time from a
sampled decay, where the model evaluates the occupation-time law and the wrapped
moments in closed form.

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
from chisurf.core.fluorescence.mfd.patterns import state_efficiency
from chisurf.core.fluorescence.burst.simulate import (
    MFD_STREAMS,
    rate_matrix_for,
    simulate_smfret,
)

AXES = HistogramAxes.default(
    n_ratio=40, n_micro_time=40, micro_time_range=(0.5, 6.0)
)


#: The measurement these tests are written against. The distances the old
#: hand-rolled simulator used (40 and 70 A at R0 = 52) are E = 0.786 and 0.152,
#: which is what the survivor is asked for directly — it parameterises by
#: efficiency, and going through a distance twice is a conversion to get wrong.
MEASUREMENT = dict(
    alex=False, polarized=True,
    efficiencies=(0.786, 0.152), donor_only=0.15, acceptor_only=0.0,
    gamma=1.0, alpha=0.02, beta=1.0, delta=0.0,
    tau_d0=4.0, tau_a=3.0, linker_sigma=6.0, r0=52.0,
    concentration=1.0, brightness=400.0, background=0.02,
    laser_period=13.6, irf_centre=1.2, irf_width=0.09,
)

#: Mean burst duration the regimes are named against. Measured from the simulated
#: transits rather than declared, because the regime is transitions *per burst*.
MEAN_DURATION = 2.0e-3


def _truth():
    """Return the optics and states the measurement above declares.

    The model is parameterised by distance and the simulator by efficiency, so
    something has to convert. Doing it here, once, keeps every test asking the
    model about the same molecule the simulator made.
    """
    from chisurf.core.fluorescence.fret.lines import distance_for_efficiency
    from chisurf.core.fluorescence.mfd.patterns import FretState, Optics

    optics = Optics(r0=MEASUREMENT["r0"], tau_d0=MEASUREMENT["tau_d0"],
                    tau_a=MEASUREMENT["tau_a"], sigma=MEASUREMENT["linker_sigma"],
                    alpha=MEASUREMENT["alpha"], delta=MEASUREMENT["delta"],
                    gamma=MEASUREMENT["gamma"])
    states = [
        FretState(
            distance=float(distance_for_efficiency(
                e, donor=MEASUREMENT["tau_d0"], r0=MEASUREMENT["r0"],
                sigma=MEASUREMENT["linker_sigma"],
            )),
            name=name,
        )
        for e, name in zip(MEASUREMENT["efficiencies"], ("closed", "open"))
    ]
    return optics, states


def _folder(tmp_path, regime, *, n_bursts=2500, seed=17):
    """Simulate a measurement in one regime and write it as a burst folder.

    The photons come from the confocal simulator in the TTTR library — molecules
    diffusing through a focus and switching conformation on the simulated clock —
    and go through the ordinary writer, so the folder is the same kind of thing a
    measurement produces.

    ``n_bursts`` is a *request*: the simulator is given a photon budget, and how
    many transits that yields depends on the regime. The tests below assert on
    what came back rather than on this number.
    """
    simulated = simulate_smfret(
        **MEASUREMENT,
        n_photons=int(n_bursts * 120),
        seed=seed,
        rate_matrix=rate_matrix_for(regime, mean_duration=MEAN_DURATION),
    )
    folder = simulated.write_folder(tmp_path / str(regime), stem=str(regime))
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

    assert len(preparation) > 50
    assert preparation.convention.inclusive is True
    assert preparation.convention.agreement == pytest.approx(1.0)
    assert set(preparation.verified_channels) >= {"green", "red"}
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
    stream = np.asarray(simulated.stream)
    for row, (first, last) in enumerate(simulated.true_bursts(min_photons=20)):
        emitted = stream[first : last + 1]
        assert preparation.counts[row, green] == int(
            np.isin(emitted, [MFD_STREAMS["g_par"], MFD_STREAMS["g_perp"]]).sum())
        assert preparation.counts[row, red] == int(
            np.isin(emitted, [MFD_STREAMS["r_par"], MFD_STREAMS["r_perp"]]).sum())


def test_the_response_estimated_from_non_burst_photons_recovers_the_declared_one(tmp_path):
    """The response the pipeline estimates must be the response that was simulated.

    Bursts below the search threshold are never detected, so their fluorescence
    lands in the "non-burst" stream. Taking that histogram as the instrument
    response — baseline-subtracted, but with the dim molecules' decay still in it —
    put its first moment *nanoseconds* late, and the lifetime axis is where that
    error lands. Fitting a Gaussian to the prompt sheds the tail, because a
    Gaussian cannot represent one.

    This is a property of the experiment and not of the simulator: the same
    contamination is in real data, where it was absorbed by a donor lifetime half
    of anything physical (see ``test_mfd_milestone``). The simulator's value is
    that the true answer is known here, so the residual is a number.
    """
    simulated, folder = _folder(tmp_path, "static", n_bursts=1200)
    declared = simulated.true_responses()["green"]
    estimated = load_mfd_data(folder, axes=AXES).responses["green"]

    declared_mean, _ = pattern_moments(declared.irf, declared.dt)
    estimated_mean, _ = pattern_moments(estimated.irf, estimated.dt)

    assert declared_mean == pytest.approx(simulated.parameters.irf_centre, abs=0.05)
    # Within a fifth of a nanosecond of the truth, where it used to be over one
    # nanosecond late.
    assert estimated_mean == pytest.approx(declared_mean, abs=0.2)


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
        optics, states = _truth()
        model = MfdKineticModel(
            optics=optics,
            states=states,
            populations=[0.5, 0.5],
            donor_only=MEASUREMENT["donor_only"],
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
    assert fitted < 0.2 / MEAN_DURATION


@pytest.mark.slow
def test_the_static_model_is_beaten_by_the_kinetic_one_on_exchanging_data(tmp_path):
    """Exchange has to be worth fitting, or there is no case for the machinery."""
    simulated, data = _prepared(tmp_path, "intermediate")
    common = dict(
        optics=_truth()[0],
        states=_truth()[1],
        populations=[0.5, 0.5],
        donor_only=MEASUREMENT["donor_only"],
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
        optics, states = _truth()
        model = MfdKineticModel(
            optics=optics,
            states=states,
            populations=[0.5, 0.5],
            donor_only=MEASUREMENT["donor_only"],
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
        optics=_truth()[0],
        states=_truth()[1],
        donor_only=MEASUREMENT["donor_only"],
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


# ──────────────────────────────────────────────────────────────────────────────
# The pooled-decay source: the shape the mean micro time discards
# ──────────────────────────────────────────────────────────────────────────────
def _matched_static_distance(optics, states):
    """Return the single distance whose acceptor probability matches the mixture's.

    The point of the comparison it serves: this state sits at the same place on
    the ratio axis as the exchanging pair, so the two are distinguishable only by
    the *shape* of the decay, which is what the pooled-decay source reads and the
    mean micro time throws away.
    """
    from chisurf.core.fluorescence.mfd.patterns import (
        FretState,
        red_probability,
        state_efficiency,
    )

    target = 0.5 * sum(
        float(red_probability(state_efficiency(s, optics), optics))
        for s in states
    )
    grid = np.arange(30.0, 90.0, 0.25)
    values = [
        abs(
            float(
                red_probability(
                    state_efficiency(FretState(distance=float(d)), optics),
                    optics,
                )
            )
            - target
        )
        for d in grid
    ]
    return float(grid[int(np.argmin(values))])


@pytest.mark.slow
def test_pooled_decays_tell_a_within_burst_mixture_from_a_static_state(tmp_path):
    """The discrimination the mean micro time cannot make, and this source exists for.

    A burst caught mid-exchange between a close and a far state, and a burst from a
    single state at the intermediate distance, can sit at the *same* proximity ratio
    with the *same* mean micro time. They do not have the same decay: one is a
    mixture of two lifetimes, the other is one lifetime. Pooling each ratio bin's
    photons back into a real decay is what recovers that, and the test is that the
    right model wins on the right data — both ways round, because a source that
    always preferred the more flexible model would prove nothing.
    """
    from chisurf.core.fluorescence.mfd.fit import pooled_decay_score
    from chisurf.core.fluorescence.mfd.patterns import FretState

    axes = HistogramAxes.default(
        n_ratio=20, n_micro_time=40, micro_time_range=(0.5, 6.0)
    )
    optics, states = _truth()
    exchange = rate_matrix_for("intermediate", mean_duration=MEAN_DURATION)
    # A single state whose *mean* delay matches the exchanging mixture's, so the
    # two are told apart by decay shape and by nothing else.
    distance = _matched_static_distance(optics, states)
    matched_efficiency = float(
        state_efficiency(FretState(distance=distance), optics)
    )

    mixture_model = MfdKineticModel(
        optics=optics, states=states, populations=[0.5, 0.5],
        donor_only=MEASUREMENT["donor_only"], rate_matrix=exchange,
    )
    single_model = MfdModel(
        optics=optics, states=[FretState(distance=distance)], populations=[1.0],
        donor_only=MEASUREMENT["donor_only"],
    )

    for name, efficiencies, rates, expected in (
        ("exchange", MEASUREMENT["efficiencies"], exchange, "mixture"),
        ("static", (matched_efficiency,), None, "single"),
    ):
        simulated = simulate_smfret(
            **{**MEASUREMENT, "efficiencies": efficiencies},
            n_photons=300_000, seed=21, rate_matrix=rates,
        )
        folder = simulated.write_folder(tmp_path / name, stem=name)
        data = load_mfd_data(
            folder,
            axes=axes,
            min_green_photons=20,
            responses=simulated.true_responses(),
            n_signal_bins=16,
            n_span_bins=4,
        )
        mixture = pooled_decay_score(mixture_model, data, n_decay_channels=64).score
        single = pooled_decay_score(single_model, data, n_decay_channels=64).score
        winner = "mixture" if mixture < single else "single"
        assert winner == expected, f"{name}: pooled decays preferred {winner}"
        # And by a margin, not a coin flip. The threshold was 1.3 while the data
        # came from a hand-rolled simulator; on photons from the confocal
        # simulator the separation measures 1.23 (exchange) and 1.45 (static),
        # because the burst-size distribution differs and this discrimination
        # scales with photons. 1.15 sits below the weaker of the two with room
        # for seed noise, and a coin flip would be 1.0.
        assert max(mixture, single) > 1.15 * min(mixture, single)


def test_pooled_decays_pool_on_the_ratio_only(tmp_path):
    """Shape, and the coordinate it is *not* pooled on.

    Pooling on a coordinate conditions on it. The proximity ratio is one the model
    reproduces exactly, through the same nested sum the histogram uses; the lifetime
    axis is not, and pooling on it would tilt every pooled decay in a way that reads
    as a lifetime shift. So the returned array has one row per *ratio* bin and the
    lifetime axis appears only as the decay's own channels.
    """
    from chisurf.core.fluorescence.mfd.histogram import observed_pooled_decays

    axes = HistogramAxes.default(
        n_ratio=12, n_micro_time=40, micro_time_range=(0.5, 6.0)
    )
    simulated, folder = _folder(tmp_path, "static", n_bursts=600)
    data = load_mfd_data(
        folder, axes=axes, min_green_photons=20, responses=simulated.true_responses()
    )
    decays = observed_pooled_decays(
        data.preparation, axes, min_green_photons=20, n_decay_channels=32
    )
    assert decays.shape == (12, 32)
    assert decays.sum() > 0
    # Every photon in the pooled decays is a donor photon of a burst that survived
    # the cut, so the total cannot exceed what those bursts hold.
    green = data.preparation.channel_index("green")
    assert decays.sum() <= data.preparation.counts[:, green].sum()


def test_pooled_decays_need_photons(tmp_path):
    """Another source that refuses rather than answering differently."""
    from chisurf.core.fluorescence.mfd.histogram import observed_pooled_decays

    simulated, folder = _folder(tmp_path, "static", n_bursts=200)
    data = load_mfd_data(
        folder, axes=AXES, responses=simulated.true_responses()
    )
    data.preparation.summary.pop("_tttrs")
    with pytest.raises(ValueError, match="with_photons=True"):
        observed_pooled_decays(data.preparation, AXES)


# ──────────────────────────────────────────────────────────────────────────────
# The anisotropy axis, end to end against polarization-resolved bursts
# ──────────────────────────────────────────────────────────────────────────────
def test_the_anisotropy_axis_recovers_the_simulated_rotational_time(tmp_path):
    """The second MFD plot, from a simulator that split every photon by polarization.

    The simulator draws each photon's polarization from *its own* micro time, so the
    anisotropy correlates with the lifetime axis the way a real measurement's does —
    a single steady-state draw per burst would give the right marginal and no
    correlation at all. The model then has to recover the parallel fraction from
    ``r(t)``, integrated, without ever being told it.
    """
    from chisurf.core.fluorescence.mfd.patterns import FretState

    rho, distance = 1.0, 70.0
    optics, _ = _truth()
    efficiency = 1.0 / (1.0 + (distance / optics.r0) ** 6)
    simulated = simulate_smfret(
        **{**MEASUREMENT, "efficiencies": (efficiency,), "donor_only": 0.0,
           "background": 0.0, "rho": rho},
        n_photons=150_000, seed=3,
    )

    # The simulated split, over burst photons only.
    stream = np.asarray(simulated.stream)
    in_burst = np.zeros(stream.size, dtype=bool)
    for first, last in simulated.true_bursts(min_photons=20):
        in_burst[first : last + 1] = True
    parallel = int((stream[in_burst] == MFD_STREAMS["g_par"]).sum())
    perpendicular = int((stream[in_burst] == MFD_STREAMS["g_perp"]).sum())
    observed = parallel / (parallel + perpendicular)

    # What the model predicts for the same state, from r(t) alone.
    from chisurf.core.fluorescence.mfd.patterns import polarized_patterns

    response = simulated.true_responses()["green"]
    amplitudes = np.array([1.0])
    lifetimes = np.array([optics.tau_d0 * (1.0 - efficiency)])
    _, _, predicted = polarized_patterns(
        response, amplitudes, lifetimes, rho, optics
    )

    assert observed == pytest.approx(predicted, abs=0.02)


def test_a_slower_rotor_gives_a_more_polarized_simulated_stream(tmp_path):
    """Direction, so a sign slip in the simulator cannot hide behind a round trip."""
    optics, _ = _truth()
    efficiency = 1.0 / (1.0 + (70.0 / optics.r0) ** 6)
    splits = []
    for rho in (0.1, 5.0):
        simulated = simulate_smfret(
            **{**MEASUREMENT, "efficiencies": (efficiency,), "donor_only": 0.0,
               "background": 0.0, "rho": rho},
            n_photons=60_000, seed=4,
        )
        stream = np.asarray(simulated.stream)
        parallel = int((stream == MFD_STREAMS["g_par"]).sum())
        perpendicular = int((stream == MFD_STREAMS["g_perp"]).sum())
        splits.append(parallel / (parallel + perpendicular))

    assert splits[0] < splits[1]
    # A dye rotating far faster than it emits is unpolarized.
    assert splits[0] == pytest.approx(0.5, abs=0.02)


def test_one_polarized_folder_serves_both_mfd_axes(tmp_path):
    """Both MFD plots out of one measurement, which is the point of the format.

    The two polarizations of a colour are still that colour, so the FRET axis must
    be unchanged by turning polarization on — otherwise enabling the anisotropy
    axis would silently halve every burst. And the anisotropy axis must come out of
    the same folder, with the model predicting the perpendicular fraction from r(t)
    alone rather than being told it.
    """
    from chisurf.core.fluorescence.mfd.patterns import FretState

    optics, _ = _truth()
    distance = 70.0
    efficiency = 1.0 / (1.0 + (distance / optics.r0) ** 6)
    simulated = simulate_smfret(
        **{**MEASUREMENT, "efficiencies": (efficiency,), "donor_only": 0.0,
           "rho": 1.0},
        n_photons=150_000, seed=6,
    )
    spans = simulated.true_bursts(min_photons=20)
    folder = simulated.write_folder(tmp_path / "polarized", stem="polarized",
                                    bursts=spans)

    assert set(np.unique(simulated.stream)) == {0, 1, 8, 9}

    # The FRET axis: the colour detectors must cover *both* polarizations, or half
    # the photons vanish without anything complaining — the columns would simply be
    # half as large and the proximity ratio would still look reasonable.
    fret = load_mfd_data(folder, axes=AXES, min_green_photons=20)
    assert set(fret.preparation.verified_channels) >= {"green", "red"}
    assert fret.observed.n_used > 0
    green = fret.preparation.channel_index("green")
    red = fret.preparation.channel_index("red")
    counted = int(fret.preparation.counts[:, [green, red]].sum())
    stream = np.asarray(simulated.stream)
    in_burst = np.zeros(stream.size, dtype=bool)
    for first, last in spans:
        in_burst[first : last + 1] = True
    assert counted == int(in_burst.sum())

    # The anisotropy axis: the same folder, with the polarizations as the two
    # channels. The model predicts the perpendicular fraction from r(t) alone.
    responses = simulated.true_responses()
    data = load_mfd_data(
        folder,
        axes=AXES,
        green="green_par",
        red="green_perp",
        min_green_photons=20,
        responses={
            "green_par": responses["green"], "green_perp": responses["green"]
        },
    )
    model = MfdModel(
        optics=optics, states=[FretState(distance=distance, rho=1.0)],
        populations=[1.0], donor_only=0.0,
    )
    predicted = model.anisotropy_histogram(
        data, parallel="green_par", perpendicular="green_perp", axes=AXES
    )
    centres = 0.5 * (AXES.ratio_edges[:-1] + AXES.ratio_edges[1:])
    observed_marginal = data.observed.counts.sum(axis=1)
    model_marginal = predicted.sum(axis=1)
    observed_mean = float((centres * observed_marginal).sum() / observed_marginal.sum())
    model_mean = float((centres * model_marginal).sum() / model_marginal.sum())
    assert model_mean == pytest.approx(observed_mean, abs=0.02)
