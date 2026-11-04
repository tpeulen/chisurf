"""A reference dye is described once -- lifetime, rotation, initial anisotropy -- for its IRF, its
shift calibration and its reference fit, and the description is the data's where they disagree.

On the owner's Alexa647_thick_1 (RVZMT150's red pair) the reference fit was chi2_r 31: the IRF was
deconvolved with the tail's lifetime (1.15 ns) and the shifts fitted with the database's (1.0 ns);
the dye's initial anisotropy is far below the ideal 0.38 (r0 0.15, rho ~1 ns: chi2_r 1.3, 16 with
0.38); and its VV and VH channels are swapped in that setup (its anisotropy starts at -0.10).
Simulated here: an Alexa-like dye of 1.15 ns, r0 0.15, rho 1.0 ns, G 1.5, its database lifetime
1.0 ns.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import (
    calibrate_shifts,
    irf_from_reference,
    reference_anisotropy,
    reference_lifetime,
)

from .test_irf_from_references import DT, N, OS, _fine_irf


def _alexa_like(tau=1.15, rho=1.0, r0=0.15, g=1.5, seed=5):
    t = (np.arange(N * OS) + 0.5) * DT / OS
    fine = _fine_irf()
    r = r0 * np.exp(-t / rho)
    out = [
        np.real(np.fft.ifft(np.fft.fft(fine) * np.fft.fft(pol * np.exp(-t / tau)))).reshape(N, OS).sum(1)
        for pol in (1 + 2 * r, (1 - r) / g)
    ]
    total = sum(o.sum() for o in out)
    rng = np.random.default_rng(seed)
    return [rng.poisson(o / total * 1.5e6 + 100.0).astype(float) for o in out]


def test_the_database_lifetime_is_used_unless_the_tail_clearly_disagrees():
    vv, vh = _alexa_like()
    tau, info = reference_lifetime(vv, vh, DT, 1.0)
    assert not info["consistent"] and info["how"] == "from its tail"
    assert tau == pytest.approx(1.15, abs=0.04) and info["listed"] == 1.0
    tau, info = reference_lifetime(vv, vh, DT, 1.14)  # within 5 %: the database's
    assert info["consistent"] and tau == 1.14


def test_swapped_vv_and_vh_show_as_a_negative_anisotropy():
    vv, vh = _alexa_like(r0=0.38, rho=0.6)
    assert reference_anisotropy(vv, vh, 1.5) > 0.1
    assert reference_anisotropy(vh, vv, 1 / 1.5) < -0.05


def test_the_initial_anisotropy_is_the_datas_when_the_ideal_one_fails():
    vv, vh = _alexa_like()
    tau, _info = reference_lifetime(vv, vh, DT, 1.0)
    ideal = irf_from_reference(vv, vh, DT, tau_ns=tau)  # r0 0.38, no G to judge it by
    assert ideal.info["r0"] == 0.38
    found = irf_from_reference(vv, vh, DT, tau_ns=tau, g_factor=1.5)
    assert found.info["r0"] == pytest.approx(0.15, abs=0.051)
    assert "r0" in found.text
    cal = calibrate_shifts(
        [vv, vh], found.halves, DT, tau_ns=tau, rho_ns=found.info["rho_ns"], r0=found.info["r0"],
        g_factor=1.5,
    )
    assert cal.fit.chi2r < 1.5, cal.fit.text
    assert cal.fit.g_fitted == pytest.approx(1.5, rel=0.05)
    worse = calibrate_shifts(
        [vv, vh], ideal.halves, DT, tau_ns=tau, rho_ns=ideal.info["rho_ns"], g_factor=1.5
    )
    assert worse.fit.chi2r > 2 * cal.fit.chi2r
    # deconvolved with one lifetime and fitted with another: no calibration at all
    mixed = calibrate_shifts(
        [vv, vh], found.halves, DT, tau_ns=1.0, rho_ns=found.info["rho_ns"], r0=found.info["r0"],
        g_factor=1.5,
    )
    assert mixed.fit.chi2r > 3 * cal.fit.chi2r
