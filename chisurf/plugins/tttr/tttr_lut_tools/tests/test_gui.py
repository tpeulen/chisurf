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


def test_compute_panel_is_autoform(qapp):
    from chisurf.plugins.tttr.tttr_lut_tools.gui.tac_lut_panel import TACLinearizationPanel

    panel = TACLinearizationPanel()
    assert hasattr(panel, "auto_form")
    assert hasattr(panel, "model")


def test_compute_viewmodel_load_and_region():
    import pathlib

    from chisurf.plugins.tttr.tttr_lut_tools.gui.view_model import LutComputeViewModel

    spc = (pathlib.Path(__file__).resolve().parents[5]
           / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc")
    if not spc.is_file():
        import pytest

        pytest.skip("sample SPC not available")
    import numpy as np

    vm = LutComputeViewModel()
    vm.load_files([str(spc)])
    assert vm.n_bins and vm.n_bins > 0
    assert vm.linear_start < vm.linear_stop
    assert vm.current_table is not None
    # per-channel: the file exposes multiple routing channels
    assert len(vm.available_channels) > 1
    assert vm.channel == str(vm.available_channels[0])
    lut0 = np.asarray(vm.current_table["NTAC_fract"]).copy()
    # switching channel re-histograms and yields a different LUT
    vm.channel = str(vm.available_channels[1])
    vm.update()
    lut1 = np.asarray(vm.current_table["NTAC_fract"])
    n = min(lut0.size, lut1.size)
    assert not np.array_equal(lut0[:n], lut1[:n])
    # a parameter change recomputes without error
    vm.ntac_required = 2048
    vm.update()
    assert vm.current_table["ntac_required"] == 2048
