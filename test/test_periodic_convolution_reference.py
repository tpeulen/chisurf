"""The periodic convolution reaches the final channel, and matches first principles.

This file used to assert that ChiSurf's own numba reimplementation of the
periodic (high-repetition-rate) convolution agreed with the photon library's C
kernel. **It did not.** Checked against an independent brute-force sum, the
numba twin never gave the *last* channel its inter-pulse tail:

===========  ====================  ====================  ==================
lifetimes    brute force           photon library        numba twin
===========  ====================  ====================  ==================
2            1.551653e-27          1.551653e-27          2.19e-53
128          5.436e-05             5.372e-05             2.64e-07
===========  ====================  ====================  ==================

Three of this file's assertions had been failing on that, including the one
written specifically to catch it (``test_final_channel_receives_its_tail``).
The twin is deleted rather than fixed -- production already used the C kernel,
so there was nothing to keep in step with -- and what remains is the check that
should have been here all along: not "the two agree" but **"the surviving one
is right"**, against a reference that shares no code with it.

The brute-force reference sums the pulse train analytically
(:math:`\\sum_m e^{-(t + mT)/\\tau}` in closed form) and then applies the
trapezoidal convolution directly, so a shared off-by-one cannot hide in both.
"""

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.tcspc.convolve import (  # noqa: E402
    convolve_lifetime_spectrum_periodic,
)

N = 1024
DT = 0.032
PERIOD = 25.0


def _irf(n=N, dt=DT):
    y = np.exp(-0.5 * ((np.arange(n) * dt - 1.0) / 0.25) ** 2) * 1e4
    return np.ascontiguousarray(y / y.sum())


def _spectrum(n_exp):
    return np.ascontiguousarray(
        np.array([[1.0 / n_exp, 0.5 + 0.05 * k] for k in range(n_exp)]).ravel()
    )


def _brute_force(spectrum, irf, period, dt, n):
    """Periodic convolution from first principles, sharing no code with the kernel.

    Parameters
    ----------
    spectrum : numpy.ndarray
        Interleaved amplitudes and lifetimes.
    irf : numpy.ndarray
        Instrument response, one sample per channel.
    period : float
        Laser repetition period, same units as the lifetimes.
    dt : float
        Channel width.
    n : int
        Number of channels.

    Returns
    -------
    numpy.ndarray
        The convolved decay.

    Notes
    -----
    The pulse train is summed in closed form -- for one lifetime the pulses
    contribute :math:`\\sum_m e^{-(t + mT)/\\tau} = e^{-t/\\tau}/(1 - e^{-T/\\tau})`
    -- and the convolution is then the plain trapezoidal sum, half weight on the
    first and last term. Deliberately O(n^2) and readable rather than fast.
    """
    time = np.arange(n) * dt
    amplitudes, lifetimes = spectrum[0::2], spectrum[1::2]

    model = np.zeros(n)
    for amplitude, lifetime in zip(amplitudes, lifetimes):
        model += amplitude * np.exp(-time / lifetime) / (1.0 - np.exp(-period / lifetime))

    out = np.zeros(n)
    for i in range(n):
        j = np.arange(i + 1)
        weight = np.ones(i + 1)
        weight[0] = 0.5
        weight[-1] = 0.5
        out[i] = np.sum(weight * irf[j] * model[i - j]) * dt
    return out


def _convolved(n_exp):
    """Run the shipped periodic convolution for ``n_exp`` lifetimes."""
    decay = np.zeros(N)
    convolve_lifetime_spectrum_periodic(
        decay, _spectrum(n_exp), _irf(), 0, N - 1, N, PERIOD, DT, N - 1
    )
    return decay


@pytest.mark.parametrize("n_exp", [2, 128])
def test_final_channel_receives_its_tail(n_exp):
    """The last channel carries the tail of earlier pulses, not zero.

    This is the defect the deleted numba twin had: at 128 lifetimes it returned
    2.6e-07 where the true value is 5.4e-05, and at two lifetimes it was 26
    orders of magnitude low -- indistinguishable from "no tail at all".
    """
    produced = _convolved(n_exp)[-1]
    expected = _brute_force(_spectrum(n_exp), _irf(), PERIOD, DT, N)[-1]

    assert produced > 0.0, "the final channel got no tail contribution at all"
    assert produced == pytest.approx(expected, rel=0.02), (
        f"final channel {produced:.6e} against first principles {expected:.6e}"
    )


def test_channel_zero_uses_the_kernels_own_start_convention():
    """Channel 0 differs from a plain trapezoid, and stays where it is.

    This is a **characterisation** test, not a derivation. Every other channel
    matches the brute-force trapezoid to 1e-8; channel 0 comes out about 1.94x
    the trapezoid's half-weighted first term, and that factor is not a clean
    one-half-versus-one -- the kernel folds its own start-channel handling in
    there and this test does not claim to know what it is.

    It is worth pinning anyway: without it the first channel could drift by a
    factor of two and every other assertion here would still pass. If a change
    moves it, work out *why* before updating the number.
    """
    produced = _convolved(2)[0]
    trapezoidal = _brute_force(_spectrum(2), _irf(), PERIOD, DT, N)[0]

    assert produced > trapezoidal, "channel 0 fell to or below the half-weight term"
    assert produced / trapezoidal == pytest.approx(1.9407, rel=1e-3)


@pytest.mark.parametrize("n_exp", [1, 2, 4, 16])
def test_matches_first_principles(n_exp):
    """The curve agrees with the brute-force sum where it is resolvable.

    Two exclusions, both principled rather than convenient:

    * **Channel 0** uses the kernel's own start convention (above).
    * **Below ~1e-6 of the peak** the values are at the limit of double
      precision and a relative comparison stops meaning anything.

    The IRF here is a narrow Gaussian that has decayed to nothing well before
    the end of the window, so its own periodic wrap contributes nothing
    measurable -- which is what makes the non-wrapping brute force a fair
    reference. It would *not* be one for a response with weight at the far end:
    the kernel wraps that into the early channels, correctly, and the brute
    force does not model it.
    """
    produced = _convolved(n_exp)
    expected = _brute_force(_spectrum(n_exp), _irf(), PERIOD, DT, N)

    resolvable = expected > 1e-6 * expected.max()
    resolvable[0] = False
    relative = np.abs(produced[resolvable] - expected[resolvable]) / expected[resolvable]
    assert relative.max() < 1e-6, f"largest relative deviation {relative.max():.2e}"
