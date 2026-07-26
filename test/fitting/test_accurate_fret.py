"""Accurate FRET: automatic calibration, lifetime-assisted gamma and error bars.

Every test works on simulated bursts whose correction factors are known, so the
assertions are recovery statements ("the procedure finds what was put in") rather
than regression snapshots.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.burst.es import corrected_es
from chisurf.core.fluorescence.fret.accurate import (
    accurate_fret,
    auto_calibrate,
    beta_from_stoichiometry,
    classify_es_populations,
    distance_from_efficiency,
    efficiency_uncertainty,
    gamma_from_lifetime,
    gaussian_mixture_1d,
)
from chisurf.core.fluorescence.fret.calibration import CalibrationParameters
from chisurf.core.fluorescence.fret.lines import static_fret_line

GAMMA, ALPHA, BETA, DELTA = 0.65, 0.08, 1.4, 0.06
TAU_D0, R0, LINKER = 4.0, 52.0, 6.0
LINE = static_fret_line(TAU_D0, r0=R0, sigma=LINKER)


def simulate(*, seed: int = 1, efficiencies=(0.3, 0.75), n_fret=(1200, 1200),
             n_donor_only: int = 400, n_acceptor_only: int = 400,
             photons: int = 400):
    """Simulate ALEX bursts with known correction factors.

    Photon budgets are Poisson; the donor channel carries ``(1-E)·N`` photons,
    the FRET channel ``gamma·E·N`` plus leakage and direct excitation, and the
    acceptor-excitation channel ``beta·gamma·N`` (a 1:1 labelled species, i.e.
    ``S = 0.5`` after correction). Donor lifetimes are drawn around the value the
    static FRET line assigns to each efficiency.

    Returns
    -------
    dict
        Channel arrays, per-burst lifetimes and the ground-truth class of every
        burst (``"fret0"``, ``"fret1"``, ``"donor_only"``, ``"acceptor_only"``).
    """
    rng = np.random.default_rng(seed)
    dd, da, aa, tau, kind = [], [], [], [], []
    for i, (e, n) in enumerate(zip(efficiencies, n_fret)):
        n_ph = rng.poisson(photons, n).astype(float)
        dd.append(rng.poisson((1.0 - e) * n_ph))
        aa.append(rng.poisson(BETA * GAMMA * n_ph))
        da.append(rng.poisson(
            GAMMA * e * n_ph + ALPHA * (1.0 - e) * n_ph + DELTA * BETA * GAMMA * n_ph
        ))
        tau.append(rng.normal(float(LINE.lifetime_at(e)), 0.12, n))
        kind.append(np.full(n, f"fret{i}"))
    if n_donor_only:
        n_ph = rng.poisson(photons, n_donor_only).astype(float)
        dd.append(rng.poisson(n_ph))
        da.append(rng.poisson(ALPHA * n_ph))
        aa.append(rng.poisson(2.0, n_donor_only))
        tau.append(rng.normal(TAU_D0, 0.12, n_donor_only))
        kind.append(np.full(n_donor_only, "donor_only"))
    if n_acceptor_only:
        n_ph = rng.poisson(photons, n_acceptor_only).astype(float)
        dd.append(rng.poisson(2.0, n_acceptor_only))
        aa.append(rng.poisson(BETA * GAMMA * n_ph))
        da.append(rng.poisson(DELTA * BETA * GAMMA * n_ph))
        tau.append(np.full(n_acceptor_only, np.nan))
        kind.append(np.full(n_acceptor_only, "acceptor_only"))
    return {
        "i_dd": np.concatenate(dd).astype(float),
        "i_da": np.concatenate(da).astype(float),
        "i_aa": np.concatenate(aa).astype(float),
        "tau_f": np.concatenate(tau),
        "kind": np.concatenate(kind),
    }


# ---------------------------------------------------------------------------
# automatic calibration
# ---------------------------------------------------------------------------


def test_auto_calibrate_recovers_all_factors():
    """Every Hellenkamp factor is recovered from an unlabelled ALEX dataset."""
    d = simulate()
    res = auto_calibrate(d["i_dd"], d["i_da"], d["i_aa"], n_bootstrap=25)
    assert res.factors["alpha"] == pytest.approx(ALPHA, abs=0.005)
    assert res.factors["delta"] == pytest.approx(DELTA, abs=0.005)
    assert res.factors["gamma"] == pytest.approx(GAMMA, rel=0.03)
    assert res.factors["beta"] == pytest.approx(BETA, rel=0.03)
    assert res.converged
    assert all(np.isfinite(res.uncertainties[k]) for k in ("alpha", "delta", "gamma", "beta"))


def test_population_classification_matches_the_truth():
    """The stoichiometry mixture finds the reference populations without gates."""
    d = simulate()
    es = corrected_es(d["i_dd"], d["i_da"], d["i_aa"])
    split = classify_es_populations(es["S"], es["E"])
    assert split.method == "mixture"
    truth = d["kind"]
    for mask, name in ((split.donor_only, "donor_only"),
                       (split.acceptor_only, "acceptor_only")):
        assert np.count_nonzero(mask) > 300
        purity = np.mean(truth[mask] == name)
        assert purity > 0.95, f"{name} gate is only {purity:.2%} pure"
    assert np.mean(np.char.startswith(truth[split.fret], "fret")) > 0.95
    assert split.counts["fret_populations"] == 2


def test_iteration_is_self_consistent():
    """Starting far from the answer converges to the same factors."""
    seeded = CalibrationParameters()
    seeded.gamma, seeded.alpha, seeded.delta = 3.0, 0.4, 0.3
    d = simulate()
    res = auto_calibrate(d["i_dd"], d["i_da"], d["i_aa"], calibration=seeded)
    assert res.factors["gamma"] == pytest.approx(GAMMA, rel=0.03)
    assert res.factors["alpha"] == pytest.approx(ALPHA, abs=0.005)


# ---------------------------------------------------------------------------
# the lifetime / static-FRET-line route
# ---------------------------------------------------------------------------


def test_gamma_from_lifetime_on_a_single_population():
    """One static population plus its donor lifetime identifies gamma."""
    d = simulate(efficiencies=(0.55,), n_fret=(2000,), n_donor_only=0,
                 n_acceptor_only=0, seed=3)
    res = gamma_from_lifetime(
        d["i_dd"], d["i_da"], d["tau_f"], line=LINE, i_aa=d["i_aa"],
        alpha=ALPHA, delta=DELTA,
    )
    assert res["gamma"] == pytest.approx(GAMMA, rel=0.03)


def test_auto_calibrate_falls_back_to_the_lifetime():
    """With a single FRET population the E-S fit cannot give gamma — the line can."""
    d = simulate(efficiencies=(0.55,), n_fret=(2000,), seed=4)
    res = auto_calibrate(
        d["i_dd"], d["i_da"], d["i_aa"], tau_f=d["tau_f"], donor_lifetime=TAU_D0,
    )
    assert not np.isfinite(res.gamma_estimates["es"])
    assert res.gamma_estimates["lifetime"] == pytest.approx(GAMMA, rel=0.03)
    assert res.factors["gamma"] == pytest.approx(GAMMA, rel=0.03)
    # beta is then defined by centring the 1:1 population at S = 0.5
    assert res.factors["beta"] == pytest.approx(BETA, rel=0.03)
    assert any("static FRET line" in m for m in res.messages)


def test_lifetime_and_es_routes_agree():
    """The two independent gamma estimates agree — the consistency check a user runs."""
    d = simulate()
    res = auto_calibrate(
        d["i_dd"], d["i_da"], d["i_aa"], tau_f=d["tau_f"], donor_lifetime=TAU_D0,
    )
    assert res.gamma_estimates["es"] == pytest.approx(
        res.gamma_estimates["lifetime"], rel=0.03
    )


def test_static_populations_sit_on_the_static_line():
    """After calibration the simulated (static) populations fall onto the line."""
    d = simulate()
    res = auto_calibrate(
        d["i_dd"], d["i_da"], d["i_aa"], tau_f=d["tau_f"], donor_lifetime=TAU_D0,
    )
    assert res.populations
    for p in res.populations:
        assert abs(p["deviation"]) < 0.02


# ---------------------------------------------------------------------------
# the optics prior
# ---------------------------------------------------------------------------


LIGHTPATH = {
    "matrices": {
        "excitation": {"rows": ["green"], "columns": ["D", "A"], "values": [[1.0, 0.055]]},
        "emission": {"rows": ["D", "A"], "columns": ["green_det", "red_det"],
                     "values": [[0.92, 0.075], [0.02, 0.90]]},
    },
    "donor": "D", "acceptor": "A",
    "green_detector": "green_det", "red_detector": "red_det",
    "gG": 1.0, "gR": 0.72, "qy_d": 0.92, "qy_a": 0.75,
}


def test_optics_prior_supplies_factors_the_data_cannot():
    """Without reference populations the factors fall back to the light path.

    The excitation/emission probabilities *are* the prior: when no donor-only or
    acceptor-only bursts exist, alpha and delta keep the optical value and carry
    the optical uncertainty rather than a fitted illusion.
    """
    d = simulate(n_donor_only=0, n_acceptor_only=0)
    res = auto_calibrate(
        d["i_dd"], d["i_da"], d["i_aa"], lightpath=LIGHTPATH, n_bootstrap=10
    )
    # Hellenkamp alpha = I_DA/I_DD = gR*cRD / (gG*cGD)
    optics_alpha = 0.72 * 0.075 / (1.0 * 0.92)
    optics_delta = 0.055
    assert res.factors["alpha"] == pytest.approx(optics_alpha, rel=1e-6)
    assert res.factors["delta"] == pytest.approx(optics_delta, rel=1e-6)
    assert res.uncertainties["alpha"] == pytest.approx(0.02)  # the prior width
    assert any("light-path value" in m for m in res.messages)


def test_data_overrides_a_broad_optics_prior():
    """A sharp data estimate wins over an uncertain optical model."""
    d = simulate()
    res = auto_calibrate(
        d["i_dd"], d["i_da"], d["i_aa"], lightpath={**LIGHTPATH, "alpha_sigma": 0.5},
        n_bootstrap=25,
    )
    assert res.factors["alpha"] == pytest.approx(ALPHA, abs=0.005)


# ---------------------------------------------------------------------------
# accurate efficiency, uncertainty, distance
# ---------------------------------------------------------------------------


def test_efficiency_uncertainty_matches_finite_differences():
    """The analytic derivatives equal a numerical differentiation of E."""
    i_dd, i_da, i_aa = np.array([400.0]), np.array([300.0]), np.array([500.0])
    base = dict(gamma=GAMMA, alpha=ALPHA, delta=DELTA)
    e0 = corrected_es(i_dd, i_da, i_aa, **base)["E"][0]
    step = 1e-6
    numeric = {}
    for key in ("gamma", "alpha", "delta"):
        shifted = dict(base)
        shifted[key] = base[key] + step
        numeric[key] = abs(corrected_es(i_dd, i_da, i_aa, **shifted)["E"][0] - e0) / step
    unc = efficiency_uncertainty(
        np.array([e0]), i_dd, i_aa, gamma=GAMMA,
        sigma_gamma=1.0, sigma_alpha=1.0, sigma_delta=1.0,
    )
    for key in ("gamma", "alpha", "delta"):
        assert float(unc["terms"][key][0]) == pytest.approx(numeric[key], rel=1e-4)


def test_uncertainties_add_in_quadrature():
    """Systematic and statistical contributions combine as independent errors."""
    unc = efficiency_uncertainty(
        0.5, 100.0, 100.0, gamma=1.0, sigma_gamma=0.05, sigma_statistical=0.01
    )
    assert unc["total"] == pytest.approx(np.hypot(unc["systematic"], 0.01))


def test_distance_round_trip_and_error():
    """R(E) inverts the Foerster relation and blows up at the ends of the range."""
    r = np.array([30.0, 52.0, 80.0])
    e = 1.0 / (1.0 + (r / R0) ** 6)
    out = distance_from_efficiency(e, R0, sigma_efficiency=0.02)
    np.testing.assert_allclose(out["distance"], r, rtol=1e-9)
    # relative distance error is smallest at E = 0.5 (R = R0)
    relative = out["sigma"] / out["distance"]
    assert relative[1] < relative[0] and relative[1] < relative[2]


def test_r0_uncertainty_propagates():
    """An uncertain Foerster radius scales straight through to the distance."""
    out = distance_from_efficiency(0.5, R0, sigma_efficiency=0.0, sigma_r0=2.0)
    assert out["sigma"] == pytest.approx(out["distance"] * 2.0 / R0)


def test_accurate_fret_reports_populations():
    """The end-to-end call returns per-population accurate E, R and off-line offset."""
    d = simulate()
    cal = auto_calibrate(d["i_dd"], d["i_da"], d["i_aa"], n_bootstrap=25)
    out = accurate_fret(
        d["i_dd"], d["i_da"], d["i_aa"], calibration=cal.calibration, tau_f=d["tau_f"],
        line=LINE, uncertainties=cal.uncertainties,
        labels=np.where(cal.split.fret, cal.split.fret_labels, -1),
    )
    populations = {p["label"]: p for p in out["populations"] if p["label"] >= 0}
    assert len(populations) == 2
    for expected, p in zip((0.3, 0.75), populations.values()):
        assert p["E"] == pytest.approx(expected, abs=0.02)
        assert p["sigma_E"] > 0
        assert p["distance"] == pytest.approx(R0 * (1.0 / expected - 1.0) ** (1 / 6), rel=0.03)
    assert np.all(np.isfinite(out["sigma_distance"][np.isfinite(out["distance"])]))


def test_beta_from_stoichiometry_centres_the_population():
    """The 1:1 fallback puts the doubly-labelled population at S = 0.5."""
    d = simulate(efficiencies=(0.5,), n_fret=(1500,), n_donor_only=0, n_acceptor_only=0)
    beta = beta_from_stoichiometry(
        d["i_dd"], d["i_da"], d["i_aa"], gamma=GAMMA, alpha=ALPHA, delta=DELTA
    )
    s = corrected_es(
        d["i_dd"], d["i_da"], d["i_aa"], gamma=GAMMA, alpha=ALPHA, delta=DELTA, beta=beta
    )["S"]
    assert float(np.mean(s)) == pytest.approx(0.5, abs=0.01)
    assert beta == pytest.approx(BETA, rel=0.05)


# ---------------------------------------------------------------------------
# building blocks
# ---------------------------------------------------------------------------


def test_gaussian_mixture_recovers_two_components():
    """The dependency-free EM finds two known Gaussians (and is deterministic)."""
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.normal(0.2, 0.05, 800), rng.normal(0.8, 0.08, 1200)])
    fit = gaussian_mixture_1d(x, 2)
    np.testing.assert_allclose(fit["means"], [0.2, 0.8], atol=0.02)
    np.testing.assert_allclose(fit["weights"], [0.4, 0.6], atol=0.03)
    assert np.array_equal(fit["labels"], gaussian_mixture_1d(x, 2)["labels"])


def test_report_is_printable():
    """The result renders a summary naming the route each factor came from."""
    d = simulate()
    res = auto_calibrate(
        d["i_dd"], d["i_da"], d["i_aa"], tau_f=d["tau_f"], donor_lifetime=TAU_D0
    )
    text = res.report()
    assert "gamma [E-S population fit]" in text
    assert "gamma [static FRET line]" in text
    assert "population 0" in text
