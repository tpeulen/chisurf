"""Pin the degenerate-input handling of :func:`add_pile_up_to_model` (RF-193).

``n_excitation_pulses`` used to be clamped up to the number of detected photons
(``max(live_time * rep_rate, n_pulse_detected)``), so a measurement time that is
too short for the recorded decay made the last denominator of Coates' eq. 2
exactly zero: ``p[-1]`` became ``inf``, ``-log(1 - inf)`` ``NaN``, and the
normalisation of the scaling factors broadcast that single ``NaN`` over the whole
model. The function is jit-compiled, so the fit silently reported ``NaN`` chi².
"""

import numpy as np

from chisurf.core.fluorescence.tcspc.corrections import add_pile_up_to_model

REP_RATE = 20.0  # MHz
DEAD_TIME = 85.0  # ns


def _decay(n_photons: float = 1e8, n_channels: int = 64) -> np.ndarray:
    """Build a normalized single-exponential decay holding `n_photons` counts.

    Parameters
    ----------
    n_photons : float
        Total number of photons in the decay.
    n_channels : int
        Number of TCSPC channels.

    Returns
    -------
    numpy-array
        The decay, summing to `n_photons`.
    """
    x = np.linspace(0, 40, n_channels)
    y = np.exp(-x / 4.0)
    return y / y.sum() * n_photons


def test_a_too_short_measurement_time_leaves_the_model_unscaled():
    """A measurement time that cannot account for the photons must not yield NaN."""
    data = _decay()
    model = data.copy()
    # 1 s at 20 MHz are 2e7 pulses for 1e8 detected photons - undefined.
    corrected = add_pile_up_to_model(data, model, REP_RATE, DEAD_TIME, 1.0, False)
    assert np.all(np.isfinite(corrected))
    np.testing.assert_array_equal(corrected, model)


def test_a_barely_sufficient_measurement_time_stays_finite():
    """Pile-up is finite even when the pulse count only just exceeds the counts."""
    data = np.array([1.0, 2.0, 1e5])
    n_photons = data.sum()
    for factor in (1.0000001, 1.5, 2.0):
        n_pulses = n_photons * factor
        measurement_time = n_pulses / (REP_RATE * 1e6) + n_photons * DEAD_TIME * 1e-9
        corrected = add_pile_up_to_model(
            data, data.copy(), REP_RATE, DEAD_TIME, measurement_time, False
        )
        assert np.all(np.isfinite(corrected)), factor
        assert np.all(corrected > 0.0), factor


def test_pile_up_is_applied_for_a_sufficient_measurement_time():
    """The regular path is untouched: it scales the model by Coates' factors."""
    data = _decay()
    corrected = add_pile_up_to_model(data, data.copy(), REP_RATE, DEAD_TIME, 300.0, False)
    assert np.all(np.isfinite(corrected))

    rep_rate = REP_RATE * 1e6
    n_excitation_pulses = (300.0 - data.sum() * DEAD_TIME * 1e-9) * rep_rate
    p = data / (n_excitation_pulses - np.cumsum(data))
    rescaled = -np.log(1.0 - p)
    sf = data / rescaled
    sf = sf / sf.sum() * len(data)
    np.testing.assert_allclose(corrected, data * sf)
    # Pile-up suppresses the late channels relative to the early ones.
    assert sf[0] > sf[-1]


def test_the_input_model_is_only_modified_in_place_when_requested():
    """`modify_inplace=False` must not touch the caller's model array."""
    data = _decay()
    model = data.copy()
    add_pile_up_to_model(data, model, REP_RATE, DEAD_TIME, 300.0, False)
    np.testing.assert_array_equal(model, data)
    returned = add_pile_up_to_model(data, model, REP_RATE, DEAD_TIME, 300.0, True)
    assert returned is model
    assert not np.array_equal(model, data)
