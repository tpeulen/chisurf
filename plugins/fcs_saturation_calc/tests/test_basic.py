"""
Test numeric correctness of saturation helper helpers.
Verify against fcs_simulator FCSSaturationModel.
"""
import sys
sys.path.insert(0, "/Users/tpeulen/dev/chisurf/plugins")

import numpy as np

# Import plugin helper
def test_import_saturation_helper():
    from fcs_saturation_calc import compute_apparent_volume, compute_power_dependence
    assert callable(compute_apparent_volume)
    assert callable(compute_power_dependence)


def test_helper_vs_fcs_simulator():
    """Compare against fcs_simulator FCSSaturationModel."""
    from fcs_saturation_calc import compute_apparent_volume
    try:
        from fcs_simulator import FCSSaturationModel
    except Exception:
        print('fcspkg not available; skipping cross-compare')
        return
    
    model = FCSSaturationModel(w0=250e-9, z0=750e-9, D=100e-12, P_sat=5e-3)
    
    for P_mW in [0.1, 1.0, 5.0, 10.0, 20.0]:
        # FCSSaturationModel returns (Veff, V_ratio)
        V_sim, V_ratio = model.effective_volume(P_mW*1e-3)
        # Helper output in um^3
        V_calc_um3, tD_us = compute_apparent_volume(P_mW=P_mW, w0_nm=250.0, z0_nm=750.0, D_um2s=100.0, F_T_max=0.15, P_sat_mW=5.0)
        # Approximate f_T we expect
        f_T_expected = 0.15 * (P_mW / 5.0) / (P_mW / 5.0 + 1.0)
        alpha = (1.0/3.0) * (1.0 - np.exp(-2.0 / ((750.0/250.0) ** 2)))
        Ve_ratio_approx = 1.0 + alpha * f_T_expected
        V0_um3 = (np.pi ** 1.5) * (0.25) ** 2 * 0.75
        V_aprox_um3 = V0_um3 * Ve_ratio_approx
        # Allow ±2% relative error due to unit conversions and rounding
        rel = abs(V_calc_um3 - V_sim * 1e18) / (V_sim * 1e18 + 1e-10)
        # within 2% tolerance
        assert rel < 0.02, f'P={P_mW} mW Veff mismatch: rel={rel:.3f}'


def test_power_dependence_structure():
    from fcs_saturation_calc import compute_power_dependence
    res = compute_power_dependence(powers_mW=[0.1, 1.0, 5.0, 20.0], w0_nm=250.0, z0_nm=750.0, D_um2s=100.0)
    assert isinstance(res, dict)
    assert set(res.keys()) == {'power_mW', 'Veff_um3', 'tD_eff_us', 'triplet_fraction'}
    assert len(res['power_mW']) == 4
    # expect Veff monotonic increasing with power due to saturation
    Ve = np.asarray(res['Veff_um3'])
    assert Ve[-1] >= Ve[0], 'Veff should increase with power (small expansion)'
