import numpy as np

from chisurf.plugins.vv_vh_g_factor.core.calculations import (
    calculate_g_factor_core,
    compute_steady_state_anisotropy,
    perrin_steady_state_anisotropy,
    solve_linked_l_from_steady_state,
)


def test_calculate_g_factor_core():
    # Make a clean decay with known g-factor ratio = 1.5
    t = np.linspace(0, 10, 1000)
    decay = np.exp(-t / 2.0)
    par = decay
    perp = decay / 1.5

    # Tail bounds in channel units (0 to 1000)
    res = calculate_g_factor_core(
        parallel_data=par,
        perpendicular_data=perp,
        region_bounds=[700, 900],
        decay_shift=0.0,
        use_bg=False,
    )
    assert res["g_factor"] is not None
    assert np.allclose(res["g_factor"], 1.5, atol=1e-3)


def test_perrin_steady_state():
    val = perrin_steady_state_anisotropy(tau_ns=4.0, rho_ns=16.0, r0=0.38)
    assert np.allclose(val, 0.38 / (1.0 + 4.0 / 16.0))


def test_solve_linked_l():
    sp = 1000.0
    ss = 600.0
    g = 1.5
    # G=VV/VH corrects VH; solve r=(sp-G*ss)/(sp+2G*ss-3l(sp+G*ss)).
    expected = (sp + 2 * g * ss - (sp - g * ss) / 0.3) / (3 * (sp + g * ss))
    val = solve_linked_l_from_steady_state(sp=sp, ss=ss, g_factor=g, r_target=0.3)
    assert np.allclose(val, expected)


def test_compute_steady_state_anisotropy():
    sp = 1000.0
    ss = 600.0
    g = 1.2
    l1 = 0.05
    l2 = 0.08
    expected = (sp - g * ss) / ((1.0 - 3.0 * l2) * sp + (2.0 - 3.0 * l1) * g * ss)
    val = compute_steady_state_anisotropy(sp=sp, ss=ss, g_factor=g, l1=l1, l2=l2)
    assert np.allclose(val, expected)
