"""Tests for the smFRET calibration core (light-path prior → data-optimized)."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fitting.priors import NormalPrior, TruncatedNormalPrior
from chisurf.core.fluorescence.burst.es import apparent_es, corrected_es
from chisurf.core.fluorescence.fret.calibration import (
    CalibrationParameters,
    direct_excitation_from_acceptor_only,
    global_es_correction,
    leakage_from_donor_only,
    lightpath_correction_factors,
    refine_calibration,
    set_priors_from_lightpath,
)


def _lightpath(gamma_via_cgd=0.85, alpha=0.066, delta=0.03):
    """Build a synthetic ALEX light-path payload with a chosen gamma/alpha/delta."""
    c_gd = gamma_via_cgd
    c_rd = alpha * c_gd  # so alpha = I_DA/I_DD = gR*cRD/(gG*cGD)  (Hellenkamp)
    return {
        # two excitation rows: delta = I_DA/I_AA = ex[532, A]/ex[640, A] is
        # referenced to the acceptor-excitation laser, not to ex[532, donor]
        "excitation": {
            "rows": ["532", "640"],
            "columns": ["donor", "acceptor"],
            "values": [[1.0, delta], [0.0, 1.0]],
        },
        "emission": {
            "rows": ["donor", "acceptor"],
            "columns": ["gdet", "rdet"],
            "values": [[c_gd, c_rd], [0.02, 1.0]],
        },
    }


def _simulate(gamma, alpha, delta, e_true, n_bursts, seed=1):
    """Synthesize per-burst green/red/yellow counts for FRET populations."""
    rng = np.random.default_rng(seed)
    g, r, y, lab = [], [], [], []
    for i, e in enumerate(e_true):
        tot = rng.poisson(200, n_bursts).astype(float)
        f_dd = (1 - e) * tot
        f_aa = rng.poisson(200, n_bursts).astype(float)
        ida = gamma * e * tot + alpha * f_dd + delta * f_aa
        g.append(rng.poisson(np.clip(f_dd, 0, None)))
        r.append(rng.poisson(np.clip(ida, 0, None)))
        y.append(rng.poisson(np.clip(f_aa, 0, None)))
        lab.append(np.full(n_bursts, i))
    to = lambda xs: np.concatenate(xs).astype(float)  # noqa: E731
    return to(g), to(r), to(y), np.concatenate(lab)


def test_calibration_parameters_defaults():
    """The group builds with the expected free factors and defaults."""
    c = CalibrationParameters()
    d = c.as_dict()
    assert set(d) == {
        "gamma",
        "alpha",
        "beta",
        "delta",
        "Bg_DD",
        "Bg_DA",
        "Bg_AA",
        "R0",
        "PhiA",
        "PhiD",
    }
    assert d["gamma"] == 1.0 and d["alpha"] == 0.0 and d["beta"] == 1.0 and d["R0"] == 52.0


def test_lightpath_correction_factors():
    """gamma/alpha/delta are computed from the light-path matrices."""
    f = lightpath_correction_factors(
        _lightpath(0.8, 0.05, 0.04), "donor", "acceptor", "gdet", "rdet"
    )
    assert f["gamma"] == pytest.approx(1.0 / 0.8, rel=1e-6)  # cRA=1, cGD=0.8
    assert f["alpha"] == pytest.approx(0.05, rel=1e-6)
    assert f["delta"] == pytest.approx(0.04, rel=1e-6)


def test_lightpath_alpha_matches_the_donor_only_data_estimator():
    """The light-path prior mean for ``alpha`` is the quantity consumers apply.

    ``alpha`` is Hellenkamp's ``I_DA/I_DD``, so the light path must return exactly
    what :func:`leakage_from_donor_only` measures on donor-only counts synthesised
    from the *same* excitation/emission matrices — not the legacy MFD fraction
    ``R_D0/(G_D0 + R_D0)``, which is ``alpha/(1 + alpha)`` and biases every
    corrected E (RF-239). Non-unit ``gG``/``gR``/``qy_d`` pin the QY cancellation.
    """
    c_gd, c_rd, gG, gR, qy_d = 0.85, 0.06, 1.3, 0.7, 0.4
    matrices = {
        "excitation": {"rows": ["532"], "columns": ["donor", "acceptor"], "values": [[0.9, 0.03]]},
        "emission": {
            "rows": ["donor", "acceptor"],
            "columns": ["gdet", "rdet"],
            "values": [[c_gd, c_rd], [0.02, 1.0]],
        },
    }
    f = lightpath_correction_factors(
        matrices, "donor", "acceptor", "gdet", "rdet", gG=gG, gR=gR, qy_d=qy_d, qy_a=0.6
    )

    # donor-only counts produced by those same matrices
    excited = 2.0e5 * 0.9 * qy_d
    data_alpha = leakage_from_donor_only([excited * c_gd * gG], [excited * c_rd * gR])
    assert f["alpha"] == pytest.approx(data_alpha, rel=1e-9)
    assert f["alpha"] == pytest.approx(gR * c_rd / (gG * c_gd), rel=1e-9)
    # and is *not* the legacy fraction-of-all-donor-photons convention
    legacy = gR * c_rd / (gG * c_gd + gR * c_rd)
    assert f["alpha"] > legacy


def test_lightpath_delta_matches_the_acceptor_only_data_estimator():
    """The light-path prior mean for ``delta`` is the quantity consumers apply.

    ``delta`` is Hellenkamp's ``I_DA/I_AA``, so the light path must return exactly
    what :func:`direct_excitation_from_acceptor_only` measures on acceptor-only
    counts synthesised from the *same* matrices — the ratio of the two excitation
    rows for the acceptor, **not** the acceptor/donor ratio within the green row,
    which differs from it by ``beta`` (RF-240).
    """
    ex_ag, ex_ar, ex_dg = 0.03, 0.8, 0.9
    c_ra, gR, qy_a = 0.9, 0.7, 0.6
    matrices = {
        "excitation": {
            "rows": ["532", "640"],
            "columns": ["donor", "acceptor"],
            "values": [[ex_dg, ex_ag], [0.0, ex_ar]],
        },
        "emission": {
            "rows": ["donor", "acceptor"],
            "columns": ["gdet", "rdet"],
            "values": [[0.85, 0.06], [0.02, c_ra]],
        },
    }
    f = lightpath_correction_factors(
        matrices, "donor", "acceptor", "gdet", "rdet", gG=1.3, gR=gR, qy_d=0.4, qy_a=qy_a
    )

    # acceptor-only counts produced by those same matrices: the acceptor emission,
    # its quantum yield and gR cancel, leaving the excitation ratio
    detected = 2.0e5 * c_ra * qy_a * gR
    data_delta = direct_excitation_from_acceptor_only([detected * ex_ag], [detected * ex_ar])
    assert f["delta"] == pytest.approx(data_delta, rel=1e-9)
    assert f["delta"] == pytest.approx(ex_ag / ex_ar, rel=1e-9)
    # and is *not* referenced to the donor's own excitation by the green laser
    assert f["delta"] != pytest.approx(ex_ag / ex_dg, rel=1e-3)

    # naming the acceptor-excitation laser explicitly gives the same answer, and
    # the donor's excitation cannot influence delta
    named = lightpath_correction_factors(
        matrices, "donor", "acceptor", "gdet", "rdet", green_laser="532", red_laser="640"
    )
    assert named["delta"] == pytest.approx(f["delta"], rel=1e-12)
    matrices["excitation"]["values"][0][0] = 0.1
    moved = lightpath_correction_factors(matrices, "donor", "acceptor", "gdet", "rdet")
    assert moved["delta"] == pytest.approx(f["delta"], rel=1e-12)


def test_lightpath_delta_is_zero_without_an_acceptor_excitation_laser():
    """Single-laser optics have no ``I_AA``, so there is nothing for delta to scale."""
    matrices = {
        "excitation": {"rows": ["532"], "columns": ["donor", "acceptor"], "values": [[0.9, 0.03]]},
        "emission": {
            "rows": ["donor", "acceptor"],
            "columns": ["gdet", "rdet"],
            "values": [[0.85, 0.06], [0.02, 1.0]],
        },
    }
    f = lightpath_correction_factors(matrices, "donor", "acceptor", "gdet", "rdet")
    assert f["delta"] == 0.0


def test_set_priors_from_lightpath_attaches_priors():
    """The light-path value becomes each factor's Gaussian prior mean."""
    c = CalibrationParameters()
    f = set_priors_from_lightpath(
        c, _lightpath(0.8, 0.05, 0.04), "donor", "acceptor", "gdet", "rdet", r0=55.0
    )
    assert isinstance(c._gamma.prior, NormalPrior)
    assert c._gamma.prior.mu == pytest.approx(f["gamma"])
    assert isinstance(c._alpha.prior, TruncatedNormalPrior)
    assert c._alpha.prior.mu == pytest.approx(0.05)
    assert c._delta.prior.mu == pytest.approx(0.04)
    assert c._r0.prior.mu == pytest.approx(55.0)
    # seeded starting values equal the prior means
    assert c.gamma == pytest.approx(f["gamma"])


def test_corrected_es_recovers_known_efficiency():
    """The three-cube correction recovers the true E and a flat S."""
    gamma, alpha, delta = 1.4, 0.08, 0.05
    e = np.array([0.2, 0.5, 0.8])
    n = 1000.0
    f_dd = (1 - e) * n
    f_aa = np.full_like(e, n)
    ida = gamma * e * n + alpha * f_dd + delta * f_aa
    out = corrected_es(f_dd, ida, f_aa, gamma=gamma, alpha=alpha, delta=delta)
    assert np.allclose(out["E"], e, atol=1e-9)
    assert np.allclose(out["S"], gamma / (gamma + 1.0), atol=1e-9)  # flat across E
    # apparent (uncorrected) proximity ratio differs from true E
    assert not np.allclose(apparent_es(f_dd, ida, f_aa)["E"], e, atol=0.02)


def test_global_es_correction_recovers_gamma():
    """The E-S population fit recovers the injected gamma."""
    gamma, alpha, delta = 1.4, 0.08, 0.05
    g, r, y, lab = _simulate(gamma, alpha, delta, [0.25, 0.55, 0.8], 500, seed=3)
    est = global_es_correction(g, r, y, lab, alpha=alpha, delta=delta)
    assert est["gamma"] == pytest.approx(gamma, abs=0.05)


def test_global_es_correction_requires_two_populations():
    g, r, y, lab = _simulate(1.4, 0.08, 0.05, [0.5], 100)
    with pytest.raises(ValueError):
        global_es_correction(g, r, y, lab)


def test_refine_strong_data_matches_truth():
    """With ample data the posterior gamma ≈ the data estimate ≈ truth."""
    gamma, alpha, delta = 1.4, 0.08, 0.05
    g, r, y, lab = _simulate(gamma, alpha, delta, [0.25, 0.55, 0.8], 500, seed=4)
    c = CalibrationParameters()
    set_priors_from_lightpath(
        c, _lightpath(0.74, alpha, delta), "donor", "acceptor", "gdet", "rdet"
    )
    c.alpha, c.delta = alpha, delta
    out = refine_calibration(c, g, r, y, lab)
    assert out["gamma"] == pytest.approx(gamma, abs=0.05)
    e_rec = [
        corrected_es(
            g[lab == i], r[lab == i], y[lab == i], gamma=out["gamma"], alpha=alpha, delta=delta
        )["E"].mean()
        for i in range(3)
    ]
    assert np.allclose(e_rec, [0.25, 0.55, 0.8], atol=0.03)


def test_refine_weak_data_leans_on_prior():
    """With scarce data the posterior gamma is pulled toward the light-path prior."""
    gamma, alpha, delta = 1.4, 0.08, 0.05
    g, r, y, lab = _simulate(gamma, alpha, delta, [0.25, 0.8], 8, seed=5)
    c = CalibrationParameters()
    set_priors_from_lightpath(
        c, _lightpath(0.74, alpha, delta), "donor", "acceptor", "gdet", "rdet"
    )
    c.alpha, c.delta = alpha, delta
    out = refine_calibration(c, g, r, y, lab)
    # posterior sits between the (noisy) data estimate and the prior mean, and the
    # large bootstrap sigma keeps it close to the prior.
    assert (
        abs(out["gamma"] - out["gamma_prior"]) <= abs(out["gamma_data"] - out["gamma_prior"]) + 1e-9
    )
    assert out["data_sigma"] > 0.05
    assert out["gamma_updated"] is True


def test_refine_keeps_gamma_when_the_data_estimate_is_not_finite():
    """A degenerate population must not clip a NaN gamma to the lower bound."""
    gamma, alpha, delta = 1.4, 0.08, 0.05
    g, r, y, lab = _simulate(gamma, alpha, delta, [0.25, 0.55], 200, seed=6)
    # a third population without any signal makes 1/S — and with it the E-S
    # population fit — non-finite
    n_zero = 50
    g = np.concatenate([g, np.zeros(n_zero)])
    r = np.concatenate([r, np.zeros(n_zero)])
    y = np.concatenate([y, np.zeros(n_zero)])
    lab = np.concatenate([lab, np.full(n_zero, 2)])
    with np.errstate(divide="ignore", invalid="ignore"):
        assert not np.isfinite(
            global_es_correction(g, r, y, lab, alpha=alpha, delta=delta)["gamma"]
        )

        c = CalibrationParameters()
        set_priors_from_lightpath(
            c, _lightpath(0.74, alpha, delta), "donor", "acceptor", "gdet", "rdet"
        )
        c.alpha, c.delta = alpha, delta
        gamma_before = c.gamma
        out = refine_calibration(c, g, r, y, lab)
    assert out["gamma_updated"] is False
    assert not np.isfinite(out["gamma_data"])
    # the prior-seeded value survives — in particular it is not the 0.05 bound
    assert c.gamma == pytest.approx(gamma_before)
    assert out["gamma"] == pytest.approx(gamma_before)
