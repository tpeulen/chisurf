"""The IRF estimator's example: a seeded VV/VH decay with a known IRF start."""

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.irf_estimator.demo import (
    BIN_NS,
    LIFETIMES_NS,
    N_BINS,
    TRUE_IRF,
    demo_folder,
    make_demo,
)
from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import make_app


def test_make_demo_writes_a_vvvh_decay():
    """The demo decay loads in the VV/VH format and carries counts."""
    from chisurf.core.fio.vv_vh import read_vv_vh

    path = make_demo()
    data = read_vv_vh(str(path), split=True)
    vv = data["VV"] if isinstance(data, dict) else data[0]
    assert np.asarray(vv, dtype=float).max() > 100
    assert demo_folder() / "irf_demo_vvvh.dat" == path


def test_load_example_estimates_the_irf():
    """The affordance loads the decay and estimates; the lifetime lands near 1.1 ns."""
    app = make_app()
    model = app.model
    model.load_example()
    result = model.result
    assert result is not None
    assert abs(result.lifetime_ns - LIFETIMES_NS[0]) < 0.35
    assert model.status


def test_the_estimated_irf_recovers_the_demos_known_irf():
    """The estimate lands on the Gaussian IRF the demo was simulated with: centre and width."""
    app = make_app()
    try:
        model = app.model
        model.load_example()
        x = np.asarray(model.channel_axis)
        irf = np.asarray(model.result.irf)
        assert abs(float(x[np.argmax(irf)]) - TRUE_IRF["center_ns"]) < 0.06
        half = x[irf >= irf.max() / 2.0]
        assert abs(float(half.max() - half.min()) - TRUE_IRF["fwhm_ns"]) < 0.06
        # the time axis line states the demo's own sampling
        text = model.time_axis_text()
        assert f"dt = {BIN_NS:.4f} ns" in text and f"{N_BINS} pts" in text
        # every result row is a number with its unit; the lifetime and the rate agree
        rows = dict(model.result_rows())
        assert set(rows) == {"Lifetime (τ)", "Decay Rate (k)", "Amplitude (A)", "Offset (C)"}
        tau = float(rows["Lifetime (τ)"].split()[0])
        rate = float(rows["Decay Rate (k)"].split()[0])
        assert rows["Lifetime (τ)"].endswith(" ns") and rows["Decay Rate (k)"].endswith(" ns⁻¹")
        assert tau * rate == pytest.approx(1.0, rel=1e-3)
    finally:
        app.close()
