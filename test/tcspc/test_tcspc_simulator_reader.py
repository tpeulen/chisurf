"""Tests for the reader-level ``read()`` path of the TCSPC simulator setup.

Pins RF-637: a curve produced by :meth:`TCSPCSimulatorSetup.read` — the path
behind the *Read data* header's **+ Data** button — must carry the
``data_reader`` back-reference, otherwise a fit created from it opens at range
(0, 0) and fitting is a silent no-op.

Pins RF-636: the same ``read()`` must return the *same* data the simulator
panel's **Simulate**/**Add** buttons produce — peak-scaled to ``p0``, convolved
with the panel's IRF and Poisson-sampled — instead of an amplitude-normalised
noise-free curve with an error bar as large as its peak.
"""

import types

import numpy as np

from chisurf.core.agent.tools.fitting import apply_auto_fit_range
from chisurf.core.experiments.tcspc.simulator import (
    TCSPCSimulatorSetup,
    gaussian_irf,
    resolve_irf,
    simulate_decay,
)

SPECTRUM = [0.75, 4.0, 0.25, 1.0]


def make_setup(**kwargs) -> TCSPCSimulatorSetup:
    """Build a simulator setup without a GUI controller.

    Parameters
    ----------
    **kwargs
        Forwarded to :class:`TCSPCSimulatorSetup`.

    Returns
    -------
    TCSPCSimulatorSetup
        Setup configured with a two-component lifetime spectrum.
    """
    kwargs.setdefault("n_tac", 512)
    kwargs.setdefault("dt", 0.0141)
    kwargs.setdefault("lifetime_spectrum", SPECTRUM)
    return TCSPCSimulatorSetup(**kwargs)


def test_simulator_constructs_without_controller():
    """A lifetime spectrum may be passed headlessly, i.e. with no controller."""
    setup = make_setup()
    assert setup.controller is None
    np.testing.assert_allclose(setup.lifetime_spectrum, SPECTRUM)


def test_read_sets_data_reader_on_curve():
    """``read()`` annotates the curve with the reader that produced it."""
    setup = make_setup()
    group = setup.read()
    curve = group[0]
    assert curve.data_reader is setup
    assert group.data_reader is setup


def test_read_curve_auto_ranges():
    """The simulated curve auto-ranges through its own ``data_reader``."""
    setup = make_setup()
    curve = setup.read()[0]

    start, stop = curve.data_reader.autofitrange(curve)
    assert 0 <= start < stop <= curve.y.size - 1

    fit = types.SimpleNamespace(data=curve, fit_range=(0, 0))
    assert apply_auto_fit_range(fit) == [int(start), int(stop)]
    assert fit.fit_range != (0, 0)


def test_read_returns_peak_scaled_photon_counts():
    """``read()`` honours *Peak count*: integer counts peaking near ``p0``."""
    setup = make_setup(p0=20000, seed=7)
    curve = setup.read()[0]

    np.testing.assert_allclose(curve.y, np.round(curve.y))
    peak = float(curve.y.max())
    # Poisson noise around a peak of p0 is ~sqrt(p0); 5 sigma is ample.
    assert abs(peak - 20000.0) < 5.0 * np.sqrt(20000.0)
    assert curve.y.sum() > 1e5


def test_read_error_bars_follow_counting_statistics():
    """The error bar at the peak is sqrt(counts), not the peak itself."""
    setup = make_setup(p0=20000, seed=7)
    curve = setup.read()[0]

    peak_bin = int(np.argmax(curve.y))
    np.testing.assert_allclose(curve.ey[peak_bin], np.sqrt(curve.y[peak_bin]), rtol=1e-12)
    assert curve.ey[peak_bin] > 1.0


def test_read_uses_the_panel_generator():
    """``read()`` and the panel's generator agree for identical settings."""
    setup = make_setup(p0=20000, irf_mean=2.0, irf_sigma=0.15, seed=3)
    curve = setup.read()[0]

    x, y = simulate_decay(
        SPECTRUM,
        n_tac=512,
        dt=0.0141,
        p0=20000,
        irf_mean=2.0,
        irf_sigma=0.15,
        seed=3,
    )
    np.testing.assert_allclose(curve.x, x)
    np.testing.assert_allclose(curve.y, y)


def test_read_convolves_with_the_irf():
    """The simulated decay rises at the IRF, so early channels stay empty."""
    setup = make_setup(n_tac=1024, p0=20000, irf_mean=2.0, irf_sigma=0.1, seed=5)
    curve = setup.read()[0]

    # The IRF sits at 2 ns; nothing may arrive a nanosecond before it.
    assert curve.y[curve.x < 1.0].sum() == 0.0
    assert abs(curve.x[int(np.argmax(curve.y))] - 2.0) < 0.5


def test_noise_free_simulation_is_deterministic():
    """``add_noise=False`` returns the deterministic expectation."""
    setup = make_setup(p0=20000, add_noise=False)
    first = setup.read()[0]
    second = setup.read()[0]

    np.testing.assert_allclose(first.y, second.y)
    np.testing.assert_allclose(first.y.max(), 20000.0)


def test_empty_spectrum_yields_a_zero_decay():
    """A setup without a lifetime spectrum simulates a zero decay."""
    x, y = simulate_decay([], n_tac=64, dt=0.0141, p0=1000.0)
    assert x.size == y.size == 64
    assert not np.any(y)


def test_resolve_irf_prefers_a_measured_curve():
    """A curve-like IRF is interpolated onto the time axis, peak-normalised."""
    time_axis = np.arange(64) * 0.1
    measured = types.SimpleNamespace(
        x=np.arange(64) * 0.1, y=np.exp(-0.5 * ((np.arange(64) * 0.1 - 3.0) / 0.3) ** 2)
    )
    response = resolve_irf(time_axis, measured, mean=0.5, sigma=0.2)

    assert abs(time_axis[int(np.argmax(response))] - 3.0) < 0.15
    np.testing.assert_allclose(response.max(), 1.0)


def test_resolve_irf_falls_back_to_a_gaussian():
    """Without a curve the Gaussian defined by mean/sigma is used."""
    time_axis = np.arange(64) * 0.1
    np.testing.assert_allclose(
        resolve_irf(time_axis, None, mean=2.0, sigma=0.3),
        gaussian_irf(time_axis, mean=2.0, sigma=0.3),
    )
