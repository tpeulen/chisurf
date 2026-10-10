"""The settings model and the plot sources of the native burst-FCS app are Qt-free."""

import numpy as np


def test_selecting_a_curve_drives_the_plot_sources():
    from chisurf.plugins.burst.burst_fcs_correlator.gui.view_model import _BurstFcsModel

    m = _BurstFcsModel()
    tau = np.logspace(-3, 2, 40)
    g = 0.5 / (1.0 + tau) + 1.0
    m._selected = {
        "tau_raw": tau.tolist(),
        "g_raw": g.tolist(),
        "tau": tau.tolist(),
        "g": g.tolist(),
        "g_fit": (g * 0.99).tolist(),
        "td_grid": [],
        "p": [],
    }
    assert len(m.corr_plot_series()) == 2  # data + fit
    assert m.dist_plot_series() == []


def test_settings_model_to_core_settings():
    from chisurf.plugins.burst.burst_fcs_correlator.gui.view_model import _BurstFcsModel

    m = _BurstFcsModel()
    m.maxent_log10_reg = -1.0
    m.fit_mode = "maxent"
    s = m.to_settings()
    assert s.fit_mode == "maxent"
    assert abs(s.maxent_reg - 0.1) < 1e-9  # 10**-1
