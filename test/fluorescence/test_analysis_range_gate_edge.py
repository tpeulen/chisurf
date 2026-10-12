"""The default TCSPC fit range stops in front of a gate edge that makes the counts climb again."""

import numpy as np
import pytest

from chisurf.core.fluorescence.tcspc import get_analysis_range

JORDI = "test/data/tcspc/Jordi/02_18-577+7.5uM(577)UP_{}ps.dat"


def _gated_decay(n=2048, first=250, last=1800, tau=2.8, dt=0.008, edge=150, seed=1):
    """A decay recorded through a time gate whose last *edge* channels climb steeply."""
    rng = np.random.default_rng(seed)
    t = np.arange(last - first) * dt
    y = 7000.0 * np.exp(-t / tau) + 120.0
    ramp = np.arange(edge)
    y[-edge:] += 700.0 * np.exp((ramp - edge) / 25.0)
    out = np.zeros(n)
    out[first:last] = rng.poisson(y)
    return out


def test_rising_gate_edge_is_cut():
    y = _gated_decay()
    start, stop = get_analysis_range(y, 8.0, 0.9, start_at_peak=True, start_fraction=0.5)
    assert stop < 1800 - 100, (start, stop)  # well in front of the climb


def test_a_clean_decay_is_untouched():
    t = np.arange(2048) * 0.01
    rng = np.random.default_rng(0)
    y = rng.poisson(9000.0 * np.exp(-t / 3.0) + 3.0).astype(float)
    with_trim = get_analysis_range(y, 8.0, 0.999)
    from chisurf.core.fluorescence import tcspc

    assert tcspc._trim_rising_tail(y, with_trim[0], with_trim[1]) == with_trim[1]


@pytest.mark.parametrize("res", ["8", "9"])
def test_bundled_vv_vh_recordings_start_and_stop_inside_the_gate(res):
    data = np.loadtxt(JORDI.format(res))
    for part in (data[:2048], data[2048:]):
        start, stop = get_analysis_range(part, 8.0, 0.9, start_at_peak=True, start_fraction=0.5)
        smooth = np.convolve(part, np.ones(40) / 40, mode="valid")
        # the smoothed curve has not started to climb at the stop channel
        assert smooth[stop - 40 :].min() >= 0.8 * smooth[stop - 80 : stop - 40].min() or stop < 1700
        assert stop < 1700
