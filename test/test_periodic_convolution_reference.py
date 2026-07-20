"""The numba periodic convolution must match tttrlib's C reference.

ChiSurf reimplements the periodic (high-repetition-rate) convolution in numba.
That reimplementation carried two off-by-one errors, both from translating C
``for (i = ...; i <= stop; i++)`` loops into Python ``range()``:

1. The convolution loop started at ``i = 0`` and read ``irf[i - 1]``, which in
   Python wraps to the **last** IRF sample instead of being out of range, and
   also added a second contribution to ``decay[0]`` on top of the explicit
   ``decay[0] +=`` line above it.
2. The periodic tail loop used ``range(stop)`` where the reference uses
   ``i <= stop``, so the final channel never received its tail contribution.

The first showed up as ~1e-5 relative error concentrated at channel 0; the
second only became visible with many exponentials, where the tail terms
accumulate -- i.e. exactly the FRET case (~128 lifetimes).
"""
import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.tcspc.convolve import (  # noqa: E402
    convolve_lifetime_spectrum_periodic_nb as _nb,
)

N = 1024
DT = 0.032
PERIOD = 25.0


def _irf(n=N, dt=DT):
    y = np.exp(-0.5 * ((np.arange(n) * dt - 1.0) / 0.25) ** 2) * 1e4
    return np.ascontiguousarray(y / y.sum())


def _spectrum(n_exp):
    return np.ascontiguousarray(
        np.array([[1.0 / n_exp, 0.5 + 0.05 * k] for k in range(n_exp)]).ravel())


@pytest.mark.parametrize("n_exp", [1, 2, 4, 16, 64, 128])
def test_matches_the_c_reference(n_exp):
    """Agreement must be at rounding level, not merely 'close'."""
    irf = _irf()
    spec = _spectrum(n_exp)

    got = np.zeros(N)
    _nb(got, spec, irf, 0, N, N, PERIOD, DT, N)

    ref = np.zeros(N)
    tttrlib.fconv_per_cs(ref, irf, spec, PERIOD, N, N - 1, DT)

    rel = np.abs(got - ref).max() / max(np.abs(ref).max(), 1e-30)
    assert rel < 1e-13, f"numba periodic convolution differs from C by {rel:.2e}"


def test_channel_zero_is_not_double_counted():
    """The i=0 wrap-around bug showed up here first."""
    irf = _irf()
    spec = _spectrum(2)
    got = np.zeros(N)
    _nb(got, spec, irf, 0, N, N, PERIOD, DT, N)
    ref = np.zeros(N)
    tttrlib.fconv_per_cs(ref, irf, spec, PERIOD, N, N - 1, DT)
    assert got[0] == pytest.approx(ref[0], rel=1e-12)


def test_final_channel_receives_its_tail():
    """The tail loop must cover the last channel (range(stop + 1))."""
    irf = _irf()
    spec = _spectrum(128)
    got = np.zeros(N)
    _nb(got, spec, irf, 0, N, N, PERIOD, DT, N)
    ref = np.zeros(N)
    tttrlib.fconv_per_cs(ref, irf, spec, PERIOD, N, N - 1, DT)
    assert got[-1] == pytest.approx(ref[-1], rel=1e-10)
    assert got[-1] > 0.0, "final channel got no tail contribution at all"


def test_irf_is_not_read_out_of_bounds():
    """A zero-prefix IRF must not pick up energy from its tail.

    With the wrap bug, irf[-1] (the last sample) leaked into channel 0.
    """
    irf = _irf()
    irf[:50] = 0.0
    irf[-1] = 1.0                      # a large, obvious value at the far end
    irf = np.ascontiguousarray(irf / irf.sum())
    spec = _spectrum(2)
    got = np.zeros(N)
    _nb(got, spec, irf, 0, N, N, PERIOD, DT, N)
    ref = np.zeros(N)
    tttrlib.fconv_per_cs(ref, irf, spec, PERIOD, N, N - 1, DT)
    np.testing.assert_allclose(got, ref, rtol=1e-10, atol=0)
