"""GUI smoke tests for the LUT Tools workspace (offscreen)."""

import numpy as np
import pytest

pytest.importorskip("qtpy")


@pytest.fixture(scope="module")
def qapp():
    from qtpy.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_tool_builds_and_exposes_panels(qapp):
    from chisurf.plugins.tttr.tttr_lut_tools.gui.tool import TTRLutToolsWidget

    w = TTRLutToolsWidget()
    # channel-definition editor relies on these attributes for the LUT transfer.
    assert hasattr(w, "settings_panel")
    assert hasattr(w, "tac_panel")
    assert hasattr(w, "bridge_btn")


def test_compute_to_assign_bridge(qapp):
    from chisurf.plugins.tttr.tttr_lut_tools.gui.tool import TTRLutToolsWidget

    w = TTRLutToolsWidget()
    w.tac_panel.current_table = {
        "NTAC_fract": np.linspace(0, 4096, 4096),
        "linear_start": 100, "linear_stop": 4000,
    }
    w._bridge_compute_to_assign()
    assert "computed_100_4000" in w.settings_panel.loaded_luts
    assert w.settings_panel.lut_list.count() == 1


def test_help_dialog_builds_from_readme(qapp):
    from chisurf.plugins.tttr.tttr_lut_tools.gui.tool import _HelpDialog

    d = _HelpDialog()
    assert d.windowTitle().startswith("TTTR LUT Tools")
