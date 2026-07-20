"""Tests for coupled per-detector smFRET labeling-state decays."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.fret.species_decay import (
    Anisotropy,
    CrosstalkFactors,
    FretSpecies,
    fret_species_from_dict,
    fret_species_patterns,
)

N = 512
DT = 0.032


def _species(**kw):
    return FretSpecies(**kw)


def test_donor_only_has_no_yellow_and_green_dominates():
    sp = _species(state="d_only", crosstalk=CrosstalkFactors(alpha=0.05))
    p = fret_species_patterns(N, sp, dt=DT)
    assert set(p) == {"green", "red", "yellow"}
    assert p["yellow"].sum() == 0.0                 # no acceptor
    assert p["green"].sum() > p["red"].sum()        # red is only leakage
    # Red is exactly the leakage fraction of green (both convolved identically).
    ratio = p["red"].sum() / p["green"].sum()
    assert ratio == pytest.approx(0.05, rel=1e-6)


def test_acceptor_only_has_no_green():
    sp = _species(state="a_only", crosstalk=CrosstalkFactors(gamma=1.0, delta=0.1))
    p = fret_species_patterns(N, sp, dt=DT)
    assert p["green"].sum() == 0.0                   # no donor
    assert p["yellow"].sum() > 0.0
    assert p["red"].sum() > 0.0                      # direct-excited acceptor


def test_da_green_is_quenched_relative_to_donor_only():
    donor = [1.0, 4.0]
    d_only = fret_species_patterns(N, _species(state="d_only", donor_spectrum=donor),
                                   dt=DT, normalize=False)
    da = fret_species_patterns(N, _species(state="da", donor_spectrum=donor,
                                           transfer_efficiency=0.6), dt=DT, normalize=False)
    # A higher transfer efficiency shortens the donor decay: its mean arrival
    # time (first moment) drops relative to the unquenched donor-only channel.
    t = np.arange(N) * DT
    mean_d = (t * d_only["green"]).sum() / d_only["green"].sum()
    mean_da = (t * da["green"]).sum() / da["green"].sum()
    assert mean_da < mean_d


def test_da_red_has_sensitized_rise():
    # The FRET-sensitized acceptor rises (donor-shaped) rather than peaking at t=0.
    sp = _species(state="da", donor_spectrum=[1.0, 4.0], acceptor_spectrum=[1.0, 2.0],
                  transfer_efficiency=0.7, crosstalk=CrosstalkFactors(gamma=1.0))
    p = fret_species_patterns(N, sp, dt=DT, normalize=False)
    red = p["red"]
    assert np.argmax(red) > 2                         # peak is delayed (rise)


def test_efficiency_vs_distance_modes_agree_at_matched_e():
    donor = [1.0, 4.0]
    # A single distance == R0 gives E = 0.5 for a single-exponential donor.
    dist = fret_species_patterns(N, _species(state="da", donor_spectrum=donor,
        fret_mode="distance", forster_radius=52.0,
        distance_rows=[{"mean": 52.0, "sigma": 0.0, "amplitude": 1.0}]), dt=DT, normalize=False)
    eff = fret_species_patterns(N, _species(state="da", donor_spectrum=donor,
        fret_mode="efficiency", transfer_efficiency=0.5), dt=DT, normalize=False)
    t = np.arange(N) * DT
    m_dist = (t * dist["green"]).sum() / dist["green"].sum()
    m_eff = (t * eff["green"]).sum() / eff["green"].sum()
    assert m_dist == pytest.approx(m_eff, rel=0.05)


def test_distributed_distance_broadens_donor_decay():
    donor = [1.0, 4.0]
    narrow = _species(state="da", donor_spectrum=donor, fret_mode="distance",
                      distance_rows=[{"mean": 50.0, "sigma": 0.0, "amplitude": 1.0}])
    broad = _species(state="da", donor_spectrum=donor, fret_mode="distance",
                     distance_rows=[{"mean": 50.0, "sigma": 12.0, "amplitude": 1.0}])
    # A distributed distance mixes many FRET rates → the green (donor) decay is a
    # broader multi-exponential (its spectrum has more components).
    from chisurf.core.fluorescence.fret.species_decay import _resolve_fret
    from chisurf.core.fluorescence.fret.species_decay import _spectrum_pairs
    s_narrow, _ = _resolve_fret(narrow, _spectrum_pairs(donor))
    s_broad, _ = _resolve_fret(broad, _spectrum_pairs(donor))
    assert s_broad.size > s_narrow.size


def test_gamma_scales_red_relative_to_green():
    from chisurf.core.fluorescence.fret.species_decay import CrosstalkFactors

    lo = fret_species_patterns(N, _species(state="da",
        crosstalk=CrosstalkFactors(gamma=0.5)), dt=DT, normalize=False)
    hi = fret_species_patterns(N, _species(state="da",
        crosstalk=CrosstalkFactors(gamma=2.0)), dt=DT, normalize=False)
    # Higher γ (acceptor detection) raises red relative to green — matrix amplitude.
    assert (hi["red"].sum() / hi["green"].sum()) > (lo["red"].sum() / lo["green"].sum())


def test_polarized_channels_sum_to_intensity():
    sp = _species(state="da", anisotropy=Anisotropy(donor_r0=0.38, acceptor_r0=0.3, g_factor=1.0))
    inten = fret_species_patterns(N, sp, dt=DT, polarized=False, normalize=False)
    pol = fret_species_patterns(N, sp, dt=DT, polarized=True, normalize=False)
    # Magic-angle identity: I_par + 2·I_perp == I_total when G = 1 (per channel).
    for ch in ("green", "red", "yellow"):
        recon = pol[f"{ch}_parallel"] + 2.0 * pol[f"{ch}_perpendicular"]
        assert np.allclose(recon, inten[ch], atol=1e-9)


def test_polarized_keys_and_anisotropy_ordering():
    sp = _species(state="a_only", anisotropy=Anisotropy(acceptor_r0=0.4, acceptor_rho=2.0, r_inf=0.0))
    pol = fret_species_patterns(N, sp, dt=DT, polarized=True, normalize=False)
    assert "yellow_parallel" in pol and "yellow_perpendicular" in pol
    # Early time is polarized (par > perp); at long time r→0 so they converge.
    par, perp = pol["yellow_parallel"], pol["yellow_perpendicular"]
    assert par[1] > perp[1]


def test_normalize_preserves_channel_ratios():
    sp = _species(state="da")
    raw = fret_species_patterns(N, sp, dt=DT, normalize=False)
    norm = fret_species_patterns(N, sp, dt=DT, normalize=True)
    assert sum(p.sum() for p in norm.values()) == pytest.approx(1.0)
    # Ratio green:red preserved by the common scale factor.
    assert (norm["green"].sum() / norm["red"].sum()) == pytest.approx(
        raw["green"].sum() / raw["red"].sum(), rel=1e-6)


def test_irf_convolution_delays_peak():
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    t = np.arange(N) * DT
    irf = synthetic_irf(t, center_ns=0.5, fwhm_ns=0.3)
    sp = _species(state="d_only")
    ideal = fret_species_patterns(N, sp, dt=DT, normalize=False)
    conv = fret_species_patterns(N, sp, dt=DT, irf=irf, normalize=False)
    assert np.argmax(conv["green"]) > np.argmax(ideal["green"])


def test_from_dict_roundtrip():
    sp = fret_species_from_dict({
        "state": "da", "fret_mode": "distance", "distance": 45.0, "forster_radius": 52.0,
        "donor_spectrum": [1.0, 3.8], "acceptor_spectrum": [1.0, 1.9],
        "crosstalk": {"alpha": 0.02, "gamma": 0.9, "delta": 0.03},
        "anisotropy": {"donor_r0": 0.35, "g_factor": 1.1},
    })
    assert sp.state == "da" and sp.fret_mode == "distance"
    assert sp.crosstalk.alpha == 0.02 and sp.anisotropy.g_factor == 1.1
    p = fret_species_patterns(N, sp, dt=DT)
    assert set(p) == {"green", "red", "yellow"}


def test_anisotropy_spectrum_multi_component():
    import numpy as np
    from chisurf.core.fluorescence.fret.species_decay import Anisotropy

    t = np.linspace(0, 10, 256)
    # Single fast component vs. fast+slow spectrum → different r(t) shape.
    single = Anisotropy(donor_spectrum=[{"amplitude": 0.4, "rho": 0.5}])
    multi = Anisotropy(donor_spectrum=[{"amplitude": 0.2, "rho": 0.5},
                                       {"amplitude": 0.2, "rho": 8.0}], r_inf=0.02)
    r1 = single.r_of_t("donor", t)
    r2 = multi.r_of_t("donor", t)
    assert r1[0] == pytest.approx(0.4, abs=1e-6)          # Σ b_i at t=0
    assert r2[0] == pytest.approx(0.2 + 0.2 + 0.02, abs=1e-6)
    # The slow component keeps the multi spectrum more anisotropic at long time.
    assert r2[-1] > r1[-1]


def test_anisotropy_spectrum_in_polarized_patterns():
    import numpy as np
    from chisurf.core.fluorescence.fret.species_decay import Anisotropy, FretSpecies

    sp = FretSpecies(state="a_only", anisotropy=Anisotropy(
        acceptor_spectrum=[{"amplitude": 0.2, "rho": 0.4}, {"amplitude": 0.15, "rho": 12.0}]))
    pol = fret_species_patterns(N, sp, dt=DT, polarized=True, normalize=False)
    # Magic-angle identity still holds with a multi-component anisotropy.
    recon = pol["yellow_parallel"] + 2.0 * pol["yellow_perpendicular"]
    inten = fret_species_patterns(N, sp, dt=DT, polarized=False, normalize=False)
    assert np.allclose(recon, inten["yellow"], atol=1e-9)
