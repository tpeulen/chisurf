"""Pin the binning range of :func:`bin_lifetime_spectrum` (RF-975).

The call into :func:`chisurf.core.math.datatools.histogram1D` used to omit
``tth_min``/``tth_max`` and therefore ran on the kernel's *inverted* sentinel
defaults (``tth_max=-1e12`` below ``tth_min=1e12``). Every lifetime was skipped,
so the binned spectrum came back with all-zero amplitudes on an axis counting
down from ``1e12`` — the FRET/PDDEM models silently lost their decay whenever
``fret.bin_lifetime`` was on. Nothing raised, so the range must stay pinned.
"""

import numpy as np
import pytest

from chisurf.core.fluorescence.tcspc.tcspc import bin_lifetime_spectrum

# Interleaved (amplitude, lifetime) spectrum: 0.25@1 ns, 0.5@2 ns, 0.25@4 ns.
SPECTRUM = np.array([0.25, 1.0, 0.5, 2.0, 0.25, 4.0])


def _two_columns(interleaved: np.ndarray):
    """Split an interleaved spectrum into amplitudes and lifetimes.

    Parameters
    ----------
    interleaved : numpy.ndarray
        Interleaved ``(amplitude, lifetime)`` spectrum.

    Returns
    -------
    tuple of numpy.ndarray
        The amplitudes and the lifetimes.
    """
    return interleaved[::2], interleaved[1::2]


def test_binned_spectrum_keeps_its_amplitudes():
    """Binning conserves the total amplitude instead of returning zeros."""
    amplitudes, lifetimes = _two_columns(
        bin_lifetime_spectrum(SPECTRUM, n_lifetimes=101, discriminate=False)
    )
    assert amplitudes.sum() == pytest.approx(SPECTRUM[::2].sum())
    assert amplitudes.max() > 0.0
    assert np.count_nonzero(amplitudes) == 3


def test_binned_axis_spans_the_input_lifetimes():
    """The axis covers the input range, not the ``1e12`` sentinel."""
    _, lifetimes = _two_columns(
        bin_lifetime_spectrum(SPECTRUM, n_lifetimes=101, discriminate=False)
    )
    assert lifetimes.min() == pytest.approx(1.0)
    assert lifetimes.max() == pytest.approx(4.0)
    assert np.all(np.diff(lifetimes) > 0.0)


def test_each_lifetime_lands_in_its_own_bin():
    """Every input lifetime reappears within one bin width of its amplitude."""
    amplitudes, lifetimes = _two_columns(
        bin_lifetime_spectrum(SPECTRUM, n_lifetimes=101, discriminate=False)
    )
    bin_width = lifetimes[1] - lifetimes[0]
    for amplitude, lifetime in zip(SPECTRUM[::2], SPECTRUM[1::2]):
        occupied = lifetimes[amplitudes > 0.0]
        nearest = occupied[np.argmin(abs(occupied - lifetime))]
        assert abs(nearest - lifetime) <= bin_width
        assert amplitudes[lifetimes == nearest][0] == pytest.approx(amplitude)


def test_discriminate_keeps_the_dominant_lifetime():
    """The discriminator sees real weights rather than an all-zero histogram."""
    amplitudes, lifetimes = _two_columns(
        bin_lifetime_spectrum(
            SPECTRUM, n_lifetimes=101, discriminate=True, discriminator=0.3
        )
    )
    assert amplitudes.size == 1
    assert amplitudes[0] == pytest.approx(0.5)
    assert lifetimes[0] == pytest.approx(2.0, abs=0.05)


def test_single_lifetime_spectrum_is_returned_unchanged():
    """A degenerate range has nothing to bin and must not divide by zero."""
    spectrum = np.array([1.0, 2.0])
    np.testing.assert_allclose(
        bin_lifetime_spectrum(spectrum, n_lifetimes=101, discriminate=False),
        spectrum
    )


def test_empty_spectrum_stays_empty():
    """An empty spectrum bins to an empty spectrum."""
    binned = bin_lifetime_spectrum(np.array([]), n_lifetimes=101, discriminate=False)
    assert binned.size == 0
