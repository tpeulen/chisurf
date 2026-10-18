"""Synthetic-decay generator behaviours the retired editor view-model relied on.

The Qt-free ``SyntheticDecayEditorModel`` (spectrum rows, preview, "Read from Fit") lived in
``chisurf/gui/widgets`` and went with the Qt shell; the emtk window is covered by
``test/native_emtk/test_synthetic_decay_window_contract.py``. What is left here is the generator
itself: ``periodic_shift`` and ``synthetic_decay`` with an IRF, a time shift and a laser period.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.decay import synthetic_decay
from chisurf.core.fluorescence.tcspc.convolve import periodic_shift
from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

BIN_WIDTH = 0.05
N_BINS = 256


def _irf(fwhm_ns: float, center_ns: float = 1.0) -> np.ndarray:
    time = np.arange(N_BINS) * BIN_WIDTH
    return synthetic_irf(time, center_ns=center_ns, fwhm_ns=fwhm_ns, norm=True)


def test_periodic_shift_wraps():
    a = np.zeros(8)
    a[1] = 1.0
    # Integer shift moves the impulse; the tail wraps around.
    shifted = periodic_shift(a, 2.0)
    assert np.argmax(shifted) == 3
    wrapped = periodic_shift(a, -2.0)
    assert np.argmax(wrapped) == 7  # wrapped to the end


def test_irf_pushes_the_peak_away_from_the_first_bin():
    kw = dict(amplitudes=[1.0], bin_width=BIN_WIDTH, normalize=False)
    ideal = synthetic_decay(N_BINS, [3.0], **kw)
    convolved = synthetic_decay(N_BINS, [3.0], irf=_irf(0.5), **kw)
    assert np.argmax(convolved) > np.argmax(ideal)


def test_a_delayed_irf_delays_the_peak():
    kw = dict(amplitudes=[1.0], bin_width=BIN_WIDTH, normalize=False)
    base = np.argmax(synthetic_decay(N_BINS, [3.0], irf=_irf(0.3, 1.0), **kw))
    later = np.argmax(synthetic_decay(N_BINS, [3.0], irf=_irf(0.3, 2.0), **kw))
    assert later > base


def test_skewed_irf_is_asymmetric():
    time = np.arange(N_BINS) * BIN_WIDTH
    sym = synthetic_irf(time, center_ns=1.0, fwhm_ns=0.5, shape=0.0)
    skew = synthetic_irf(time, center_ns=1.0, fwhm_ns=0.5, shape=3.0)
    assert not np.array_equal(sym, skew)


def test_periodic_convolution_adds_interpulse_tail():
    kw = dict(amplitudes=[1.0], bin_width=BIN_WIDTH, irf=_irf(0.3), normalize=False)
    aperiodic = synthetic_decay(N_BINS, [4.0], **kw)
    periodic = synthetic_decay(N_BINS, [4.0], period=12.5, **kw)
    # The finite laser period lifts the late-time baseline (earlier-pulse tail).
    assert periodic[-1] > aperiodic[-1]
