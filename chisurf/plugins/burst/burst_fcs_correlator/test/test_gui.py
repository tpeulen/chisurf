"""The Qt tool is the emtk app hosted in a dock tool; the settings model and the plot sources stay Qt-free."""

import numpy as np


def test_tool_hosts_the_one_native_app(qapp, qtbot):
    from chisurf.plugins.burst.burst_fcs_correlator.gui.app import BurstFcsApp
    from chisurf.plugins.burst.burst_fcs_correlator.gui.tool import BurstFcsTool

    w = BurstFcsTool(embedded=True)
    qtbot.addWidget(w)
    assert isinstance(w.app, BurstFcsApp) and w.controller is w.app.controller
    assert w._model is w.controller._model and w._curves is w.controller._curves
    assert w.centralWidget() is w.host


def test_selecting_a_curve_drives_the_plot_sources():
    from chisurf.plugins.burst.burst_fcs_correlator.gui.view_model import _BurstFcsModel

    m = _BurstFcsModel()
    tau = np.logspace(-3, 2, 40)
    g = 0.5 / (1.0 + tau) + 1.0
    m._selected = {"tau_raw": tau.tolist(), "g_raw": g.tolist(), "tau": tau.tolist(), "g": g.tolist(), "g_fit": (g * 0.99).tolist(), "td_grid": [], "p": []}
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


def test_the_workflow_shell_hands_a_burst_folder_over_through_file_list(qapp, qtbot, tmp_path):
    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstAnalysisTool
    from chisurf.plugins.burst.burst_fcs_correlator.gui.tool import BurstFcsTool

    w = BurstFcsTool(embedded=True)
    qtbot.addWidget(w)
    tool = type("Shell", (), {"workflow_context": type("Ctx", (), {"burst_folder": tmp_path})()})()
    BurstAnalysisTool._apply_context_to_burst_fcs(tool, w)
    assert w.controller.checked_files() == [str(tmp_path)]
    BurstAnalysisTool._apply_context_to_burst_fcs(tool, w)  # a selection already there is kept
    assert w.controller.files == [str(tmp_path)]
