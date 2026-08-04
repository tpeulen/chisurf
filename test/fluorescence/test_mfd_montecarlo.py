"""The transcribed Sim2D forward model, against the closed-form one.

Where the two agree, the closed form's approximations are harmless and its speed
is free. Where they part is the interesting part, and the ground-truth benchmark
(``test/benchmarks/benchmark_mfd_engines.py``) says which one is right — these
tests only pin that they are comparing the same thing.
"""
import numpy as np
import pytest

from chisurf.core.fluorescence.mfd.montecarlo import monte_carlo_histogram

pytest.importorskip("tttrlib")


@pytest.fixture(scope="module")
def measurement(tmp_path_factory):
    """A small simulated MFD folder, loaded through the ordinary reader."""
    from chisurf.core.fluorescence.burst.simulate import simulate_smfret
    from chisurf.core.fluorescence.mfd.fit import load_mfd_data

    sim = simulate_smfret(
        n_photons=150_000, seed=23, alex=False, polarized=True,
        efficiencies=(0.2, 0.8), donor_only=0.05, acceptor_only=0.0,
        gamma=1.0, alpha=0.0, beta=1.0, delta=0.0,
        concentration=1.0, brightness=400.0, background=0.02, rho=1.0,
        irf_centre=1.0, irf_width=0.1,
    )
    folder = sim.write_folder(tmp_path_factory.mktemp("mc"), bursts="truth")
    return load_mfd_data(folder, min_green_photons=20)


def _model(rate, weighting="green"):
    from chisurf.core.fluorescence.mfd.fit import MfdKineticModel
    from chisurf.core.fluorescence.mfd.patterns import FretState, Optics

    matrix = None if rate == 0 else np.array([[0.0, rate / 2.0], [rate / 2.0, 0.0]])
    return MfdKineticModel(
        optics=Optics(r0=52.0, tau_d0=4.0, sigma=6.0, gamma=1.0, alpha=0.0, delta=0.0),
        states=[FretState(distance=66.2, name="low"),
                FretState(distance=39.3, name="high")],
        populations=[0.5, 0.5], donor_only=0.05, rate_matrix=matrix,
        donor_weighting=weighting,
    )


def _moments(histogram, axes):
    """Return the two marginal means and the micro-time spread."""
    normalised = histogram / histogram.sum()
    ratio = 0.5 * (axes.ratio_edges[:-1] + axes.ratio_edges[1:])
    micro = 0.5 * (axes.micro_time_edges[:-1] + axes.micro_time_edges[1:])
    mean_micro = float(micro @ normalised.sum(axis=0))
    spread = float(np.sqrt(micro**2 @ normalised.sum(axis=0) - mean_micro**2))
    return float(ratio @ normalised.sum(axis=1)), mean_micro, spread


@pytest.mark.slow
@pytest.mark.parametrize("rate", [0.0, 500.0])
def test_the_monte_carlo_reproduces_the_closed_form(measurement, rate):
    """Static and exchanging, the two forward models agree to sampling scatter.

    Static comes first on purpose: if the two disagree with no kinetics at all,
    the fault is in the patterns or the nested sum and nothing about the kinetic
    comparison can be interpreted.
    """
    model = _model(rate)
    analytic = model.histogram(measurement)
    sampled = monte_carlo_histogram(model, measurement, n_bursts=120_000, seed=0)

    a_ratio, a_micro, a_spread = _moments(analytic, measurement.axes)
    m_ratio, m_micro, m_spread = _moments(sampled, measurement.axes)

    assert m_ratio == pytest.approx(a_ratio, abs=0.02)
    assert m_micro == pytest.approx(a_micro, abs=0.05)
    assert m_spread == pytest.approx(a_spread, abs=0.08)

    total_variation = 0.5 * float(
        np.abs(analytic / analytic.sum() - sampled / sampled.sum()).sum()
    )
    assert total_variation < 0.10


def test_common_random_numbers_make_the_objective_deterministic(measurement):
    """The same seed must give the same histogram, or an optimiser is differentiating noise."""
    model = _model(500.0)
    first = monte_carlo_histogram(model, measurement, n_bursts=20_000, seed=3)
    again = monte_carlo_histogram(model, measurement, n_bursts=20_000, seed=3)
    assert np.array_equal(first, again)

    other = monte_carlo_histogram(model, measurement, n_bursts=20_000, seed=4)
    assert not np.array_equal(first, other)


def test_exchange_moves_the_monte_carlo_histogram(measurement):
    """A rate the model is given must change what it predicts."""
    static = monte_carlo_histogram(_model(0.0), measurement, n_bursts=40_000, seed=1)
    exchanging = monte_carlo_histogram(_model(5_000.0), measurement,
                                       n_bursts=40_000, seed=1)
    centres = 0.5 * (measurement.axes.ratio_edges[:-1] + measurement.axes.ratio_edges[1:])
    between = (centres > 0.35) & (centres < 0.65)

    def share(histogram):
        marginal = histogram.sum(axis=1)
        return float(marginal[between].sum() / marginal.sum())

    assert share(exchanging) > share(static)
