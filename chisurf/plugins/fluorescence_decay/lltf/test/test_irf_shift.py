"""Tests for the IRF shift of the LLTF decay model (RF-880)."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.lltf.core.convolve import (
    convolve_lifetime_spectrum,
)
from chisurf.plugins.fluorescence_decay.lltf.core.fitter import (
    Decay,
    _shift_irf_numba,
)


def _gaussian_irf(n: int, centre: float, sigma: float) -> np.ndarray:
    """
    Build a normalised Gaussian IRF.

    Parameters
    ----------
    n : int
        Number of channels.
    centre : float
        Channel of the IRF maximum.
    sigma : float
        Width of the IRF in channels.

    Returns
    -------
    numpy.ndarray
        The IRF, scaled to a maximum of one.
    """
    ch = np.arange(n, dtype=np.float64)
    return np.exp(-0.5 * ((ch - centre) / sigma) ** 2)


def _decay_from_irf(irf: np.ndarray, time_axis: np.ndarray, lifetime: float) -> np.ndarray:
    """
    Convolve a mono-exponential decay with an IRF.

    Parameters
    ----------
    irf : numpy.ndarray
        The instrument response function.
    time_axis : numpy.ndarray
        Time axis in nanoseconds.
    lifetime : float
        Fluorescence lifetime in nanoseconds.

    Returns
    -------
    numpy.ndarray
        The convolved decay, scaled to a peak of 10000 counts.
    """
    model = np.zeros_like(irf)
    convolve_lifetime_spectrum(
        model,
        np.array([1.0, lifetime]),
        irf,
        convolution_stop=len(irf),
        time_axis=time_axis,
    )
    return model / model.max() * 1.0e4


@pytest.mark.parametrize("dt", [0.008, 0.032, 0.128])
def test_irf_shift_is_in_nanoseconds(dt: float) -> None:
    """A shift given in nanoseconds moves the IRF by shift / channel width."""
    n = 1024
    time_axis = np.arange(n) * dt
    irf = np.zeros(n)
    irf[300] = 1.0

    decay = Decay(decay=np.ones(n), irf=irf, time_axis=time_axis)
    assert decay.channel_width == pytest.approx(dt)

    for shift_ch in (-64, -1, 0, 1, 64):
        decay.irf_shift = shift_ch * dt
        assert int(np.argmax(decay.irf)) == 300 + shift_ch


def test_channel_width_falls_back_to_one_without_time_axis() -> None:
    """Without a usable time axis the shift is counted in channels."""
    irf = np.zeros(32)
    irf[10] = 1.0

    decay = Decay(decay=np.ones(32), irf=irf, time_axis=None)
    assert decay.channel_width == 1.0

    decay.irf_shift = 3.0
    assert int(np.argmax(decay.irf)) == 13


@pytest.mark.parametrize("shift_ch", [-3.5, -2.5, -1.5, -1.0, 0.0, 1.0, 1.5, 2.5, 3.5])
def test_shift_kernel_moves_the_centroid_by_the_requested_shift(shift_ch: float) -> None:
    """The shifted IRF samples the original at ``dst - shift_ch``, either sign."""
    irf = np.zeros(64)
    irf[32] = 1.0

    shifted = _shift_irf_numba(irf, shift_ch)

    assert shifted.sum() == pytest.approx(1.0)
    centroid = float(np.sum(np.arange(len(shifted)) * shifted))
    assert centroid == pytest.approx(32.0 + shift_ch)


def test_estimate_irf_shift_recovers_a_known_shift_in_nanoseconds() -> None:
    """The scan finds the nanosecond shift the data were built with."""
    n = 512
    dt = 0.032
    true_shift = 0.32  # ns, i.e. 10 channels

    time_axis = np.arange(n) * dt
    irf = _gaussian_irf(n, centre=60.0, sigma=3.0)
    shifted_irf = _shift_irf_numba(irf, true_shift / dt)
    data = _decay_from_irf(shifted_irf, time_axis, lifetime=2.0)

    decay = Decay(decay=data, irf=irf, time_axis=time_axis)
    decay.lifetime_spectrum = np.array([1.0, 2.0])
    decay.set_analysis_range(1, n - 1)

    scan_range = (-0.64, 0.64)
    estimated = decay.estimate_irf_shift(
        irf_time_shift_scan_range=scan_range,
        irf_time_shift_scan_n_steps=33,
        verbose=False,
    )

    assert estimated == pytest.approx(true_shift, abs=0.5 * dt)
    # the estimate must not simply rail at an edge of its own scan range
    assert min(abs(estimated - edge) for edge in scan_range) > dt
