"""The acquisition simulator applies the canonical per-species decay."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import (
    build_engine,
    tttrlib_available,
)

pytestmark = pytest.mark.skipif(
    not tttrlib_available(), reason="tttrlib SimEngine not available"
)


def _run(lifetimes, irf_fwhm=None):
    params = {
        "N_species": 1, "N_channels": 1, "q": [80.0], "D": [3.0], "M": [30.0],
        "N_tac_channels": 512, "tac_dt": 0.032, "laser_period": 16.0,
        "N_ph_max": 120000, "decay_lifetimes": [lifetimes],
    }
    if irf_fwhm:
        params["irf_fwhm_ns"] = irf_fwhm
    engine = build_engine(params)
    engine.run()
    return np.asarray(engine.micro_time()).astype(float)


def test_longer_lifetime_shifts_decay_later():
    short = _run([1.0])
    long = _run([6.0])
    assert short.size > 1000 and long.size > 1000
    # A longer fluorescence lifetime → later mean micro-time (the decay is applied).
    assert long.mean() > short.mean() * 1.5


def test_irf_gives_a_prompt_offset():
    mt = _run([3.5], irf_fwhm=0.3)
    hist, _ = np.histogram(mt, bins=64, range=(0, 512))
    peak = int(np.argmax(hist))
    assert peak > 0  # convolution moves the prompt off bin 0
    assert hist[peak] > hist[min(peak + 15, 63)]  # and it decays after the prompt


def test_no_lifetimes_leaves_engine_runnable():
    # Without decay_lifetimes the engine still builds and runs (no decay set).
    engine = build_engine({
        "N_species": 1, "N_channels": 1, "q": [80.0], "D": [3.0], "M": [10.0],
        "N_tac_channels": 256, "tac_dt": 0.032, "N_ph_max": 5000,
    })
    engine.run()
    assert engine.n_photons() >= 0
