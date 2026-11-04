"""The fit background of a burst decay: flat + scatter, or the buffer -- never a decay.

The photons outside the bursts are mostly fluorescence of molecules below the burst threshold; as
the background they gave a single-lifetime fit a second lifetime through gamma (a decay-shaped
"Background" under the bursts). The background is now a flat part plus a scatter part with the
IRF's shape, estimated from them (or the buffer measurement, when there is one), and its rate is
scaled by the time inside the bursts.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.burst.burst_mle_analysis import engine
from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import polarised_kernels

N, DT, GATE = 500, 0.08, (0, 250)


def _gauss(centre: float, width: float) -> np.ndarray:
    g = np.exp(-0.5 * ((np.arange(N) - centre) / width) ** 2)
    return g / g.sum()


IRF = np.hstack([_gauss(40, 3.0), _gauss(41, 3.2)])


def _outside(flat=(20.0, 30.0), scatter=5000.0, fluorescence=2e5,
             components=((0.6, 1.0), (0.4, 4.0)), seed=4) -> np.ndarray:
    """Photons outside the bursts: a flat floor in the gate, a scatter of the IRF's shape and the
    fluorescence of dim molecules (two lifetimes), Poisson."""
    rng = np.random.default_rng(seed)
    out = []
    for k, level in enumerate(flat):
        irf = IRF[k * N : (k + 1) * N]
        decay = sum(
            a * np.fft.irfft(np.fft.rfft(irf) * np.fft.rfft(polarised_kernels(N, DT, tau, None)[0]), N)
            for a, tau in components
        )
        mean = np.zeros(N)
        mean[GATE[0] : GATE[1]] = level
        mean += scatter * irf + decay / decay.sum() * fluorescence
        mean[GATE[1] :] = 0.0
        out.append(rng.poisson(mean).astype(float))
    return np.hstack(out)


@pytest.mark.parametrize("scatter", [0.0, 5000.0, 30000.0])
@pytest.mark.parametrize("components", [((0.6, 1.0), (0.4, 4.0)), ((0.3, 0.3), (0.7, 3.0))])
def test_the_flat_and_scatter_mix_is_recovered(scatter, components):
    pattern, parts = engine.flat_scatter_background(_outside(scatter=scatter, components=components),
                                                    IRF, DT, GATE)
    assert parts["flat"] == pytest.approx((20.0, 30.0), rel=0.1)
    for found in parts["scatter"]:
        assert found == pytest.approx(scatter, rel=0.2, abs=300.0)
    # the shape: flat in the gate, the scatter on it -- no fluorescence decay in it
    for k in range(2):
        half = pattern[k * N : (k + 1) * N]
        assert np.all(half[GATE[1] :] == 0.0)
        late = slice(120, GATE[1])  # 6 ns after the prompt: a decay would still fall here
        assert np.ptp(half[late]) < 1e-6 * max(1.0, half.max())


class _Session(engine.MleSession):
    """An MleSession with its times, timing and gate given, not read from photons."""

    def time_in_bursts(self):
        return (10.0, 1010.0)  # 10 s inside the bursts of 1010 s

    def current_tttr(self):
        return None

    def _gate_window(self, det, n_bins=None):
        return GATE


def _session(**kw) -> _Session:
    s = _Session()
    s.set_detectors({"G|G": {"chs": [0, 1], "micro_time_ranges": [list(GATE)]}})
    s.irf_np["G|G"] = IRF.copy()
    s.bg_np["G|G"] = _outside(**kw)
    return s


def test_without_a_strict_selection_the_background_is_a_flat_plus_scatter_model():
    s = _session(scatter=5000.0)
    counts = s.background_of("G|G")
    pattern, parts = engine.flat_scatter_background(s.bg_np["G|G"], IRF, 1.0, GATE)
    # their rate (counts over the 1000 s outside the bursts) times the 10 s inside them
    np.testing.assert_allclose(counts, pattern / 1000.0 * 10.0)
    info = s.background_info["G|G"]
    assert info["source"] == "model" and info["model_of"] == "outside"
    assert info["rate_khz"] == pytest.approx(pattern.sum() / 1000.0 / 1e3)
    # far less than every photon outside the bursts (mostly fluorescence)
    assert info["rate_khz"] < 0.5 * info["outside_khz"]


def test_a_buffer_measurement_is_the_shape_and_the_rate():
    s = _session()
    buffer = np.zeros(2 * N)
    buffer[GATE[0] : GATE[1]] = 0.5  # counts per second and bin
    buffer[N + GATE[0] : N + GATE[1]] = 0.7
    buffer[N + 40] += 30.0  # a Raman line
    s.bg_files["G|G"] = [Path("buffer.ptu")]
    s.buffer_np["G|G"] = buffer
    np.testing.assert_allclose(s.background_of("G|G"), buffer * 10.0)
    assert s.background_info["G|G"]["source"] == "buffer"
    assert s.background_info["G|G"]["rate_khz"] == pytest.approx(buffer.sum() / 1e3)


def test_a_strict_selection_of_background_photons_is_the_background_as_it_is():
    """A strict selection that kept enough time and holds no fluorescence: its own histogram is the
    shape, its photons over its time the rate."""
    s = _session()
    strict = _outside(scatter=4000.0, fluorescence=0.0)  # flat + scatter only
    s.bg_strict_np["G|G"] = strict
    s.strict_background = {"seconds": 400.0, "total_seconds": 1010.0, "fraction": 0.4, "warning": ""}
    np.testing.assert_allclose(s.background_of("G|G"), strict / 400.0 * 10.0)
    assert s.background_info["G|G"]["source"] == "strict"


def test_a_strict_selection_that_still_holds_molecules_falls_back_to_the_model():
    s = _session()
    s.bg_strict_np["G|G"] = _outside(fluorescence=2e5)
    s.strict_background = {"seconds": 400.0, "total_seconds": 1010.0, "fraction": 0.4, "warning": ""}
    s.background_of("G|G")
    info = s.background_info["G|G"]
    assert info["source"] == "model" and info["model_of"] == "strict"
    assert info["fluorescence_share"] > engine.MAX_FLUORESCENCE_SHARE
