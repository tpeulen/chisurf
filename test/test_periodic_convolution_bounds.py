"""``convolve_lifetime_spectrum_periodic`` must not run past the end of its buffers.

Callers pass ``n_points`` -- a *length* -- while ``tttrlib.fconv_per_cs`` treats
its ``stop``/``conv_stop`` arguments as inclusive *indices*. Passing them through
unclamped therefore touched one element past the end of ``decay`` and ``irf``.

That is a heap overrun, and it behaved like one: the process aborted at some
later allocation with no message and a traceback pointing at whatever innocent
code happened to be allocating at the time. It only appeared on tttrlib builds
that do not clamp internally, so a locally patched build ran clean while the
released one crashed the GUI as soon as a fit started (SIGABRT, exit 134).

``convolve_lifetime_spectrum_periodic_nb`` has always clamped with
``stop = min(stop, n_points - 1)``; these tests pin the tttrlib path to the same
contract so the two cannot drift apart again.
"""
import numpy as np
import pytest

from chisurf.core.fluorescence.tcspc.convolve import (
    convolve_lifetime_spectrum_periodic,
)

N = 512
DT = 0.032
PERIOD = 1000.0 / 40.0
SPECTRUM = np.array([0.7, 4.0, 0.3, 1.2])


def _irf(n=N):
    t = np.arange(n) * DT
    y = np.exp(-0.5 * ((t - 1.0) / 0.25) ** 2) * 1e4
    y[y < 1e-3] = 0.0
    return y


def _run(conv_stop, stop=None, n_points=N):
    decay = np.zeros(N)
    convolve_lifetime_spectrum_periodic(
        decay, SPECTRUM, _irf(), 0,
        N if stop is None else stop,
        n_points, PERIOD, DT, conv_stop)
    return decay


def test_length_valued_stop_is_clamped_to_the_last_index():
    """The regression: conv_stop == n_points must behave as n_points - 1."""
    np.testing.assert_allclose(_run(N), _run(N - 1), rtol=0, atol=0)


@pytest.mark.parametrize("over", [1, 2, 10, 1000])
def test_stops_beyond_the_end_are_clamped(over):
    np.testing.assert_allclose(_run(N + over, stop=N + over), _run(N - 1, stop=N - 1),
                               rtol=0, atol=0)


def test_in_range_stops_are_untouched():
    """Clamping must not quietly truncate a legitimate request."""
    a = _run(N // 2, stop=N // 2)
    b = _run(N - 1, stop=N - 1)
    assert not np.array_equal(a, b), "a shorter convolution should differ"
    assert np.all(np.isfinite(a))


def test_produces_a_sane_decay():
    decay = _run(N - 1)
    assert np.all(np.isfinite(decay))
    assert decay.sum() > 0
    assert int(np.argmax(decay)) > 10, "peak at channel 0 -- IRF was not applied"


def test_repeated_calls_are_stable():
    """A heap overrun shows up as drift or a crash under repetition."""
    first = _run(N)
    for _ in range(200):
        np.testing.assert_allclose(_run(N), first, rtol=0, atol=0)


def test_degenerate_lengths_do_not_touch_memory():
    empty = np.zeros(0)
    convolve_lifetime_spectrum_periodic(
        empty, SPECTRUM, empty, 0, 0, 0, PERIOD, DT, 0)
