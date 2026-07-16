"""Data-driven alpha/delta from donor-only/acceptor-only reference samples."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.burst.es import corrected_es
from chisurf.core.fluorescence.fret.calibration import (
    CalibrationParameters,
    calibrate_from_samples,
    direct_excitation_from_acceptor_only,
    leakage_from_donor_only,
)

GAMMA, ALPHA, DELTA = 1.4, 0.08, 0.05


def _fret(seed=1):
    rng = np.random.default_rng(seed)
    dd, da, aa, lab = [], [], [], []
    for i, e in enumerate((0.25, 0.55, 0.8)):
        tot = rng.poisson(200, 500).astype(float)
        f_dd = (1 - e) * tot
        f_aa = rng.poisson(200, 500).astype(float)
        ida = GAMMA * e * tot + ALPHA * f_dd + DELTA * f_aa
        dd.append(rng.poisson(np.clip(f_dd, 0, None)))
        da.append(rng.poisson(np.clip(ida, 0, None)))
        aa.append(rng.poisson(np.clip(f_aa, 0, None)))
        lab.append(np.full(tot.size, i))
    cat = lambda xs: np.concatenate(xs).astype(float)  # noqa: E731
    return cat(dd), cat(da), cat(aa), np.concatenate(lab)


def _donor_only(seed=2, n=2000):
    rng = np.random.default_rng(seed)
    i_dd = rng.poisson(200, n).astype(float)
    i_da = rng.poisson(np.clip(ALPHA * i_dd, 0, None)).astype(float)  # pure leakage
    return i_dd, i_da


def _acceptor_only(seed=3, n=2000):
    rng = np.random.default_rng(seed)
    i_aa = rng.poisson(200, n).astype(float)
    i_da = rng.poisson(np.clip(DELTA * i_aa, 0, None)).astype(float)  # pure direct exc.
    i_dd = rng.poisson(2.0, n).astype(float)  # near-background donor
    return i_da, i_aa, i_dd


def test_leakage_from_donor_only_recovers_alpha():
    a = leakage_from_donor_only(*_donor_only())
    assert a == pytest.approx(ALPHA, abs=0.01)


def test_direct_excitation_from_acceptor_only_recovers_delta():
    i_da, i_aa, i_dd = _acceptor_only()
    d = direct_excitation_from_acceptor_only(i_da, i_aa, i_dd, alpha=ALPHA)
    assert d == pytest.approx(DELTA, abs=0.01)


def test_calibrate_from_samples_full_recovery():
    """The full procedure recovers alpha, delta and gamma, and corrects E."""
    calib = CalibrationParameters()
    out = calibrate_from_samples(
        calib,
        _fret(),
        donor_only=_donor_only(),
        acceptor_only=_acceptor_only(),
        refine=False,  # pure data-driven (no light-path prior seeded here)
    )
    assert out["alpha"] == pytest.approx(ALPHA, abs=0.012)
    assert out["delta"] == pytest.approx(DELTA, abs=0.012)
    assert out["gamma"] == pytest.approx(GAMMA, abs=0.06)

    dd, da, aa, lab = _fret()
    e_rec = [corrected_es(dd[lab == i], da[lab == i], aa[lab == i],
                          gamma=calib.gamma, alpha=calib.alpha, delta=calib.delta)["E"].mean()
             for i in range(3)]
    assert np.allclose(e_rec, [0.25, 0.55, 0.8], atol=0.03)


def test_calibrate_without_reference_samples_keeps_current():
    """Omitting reference samples leaves alpha/delta at their current values."""
    calib = CalibrationParameters()
    calib.alpha, calib.delta = 0.07, 0.04  # e.g. from a light-path prior
    calibrate_from_samples(calib, _fret(), refine=False)
    assert calib.alpha == pytest.approx(0.07)
    assert calib.delta == pytest.approx(0.04)
