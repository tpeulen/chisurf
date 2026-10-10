"""The LUT compute view model: load, channels, region, parameter changes."""

import pathlib

import numpy as np
import pytest

_SPC = (
    pathlib.Path(__file__).resolve().parents[5]
    / "test"
    / "data"
    / "tttr"
    / "BH"
    / "132"
    / "BH_SPC132.spc"
)


def test_compute_viewmodel_load_and_region():
    import pathlib

    from chisurf.plugins.tttr.tttr_lut_tools.gui.view_model import LutComputeViewModel

    spc = (
        pathlib.Path(__file__).resolve().parents[5]
        / "test"
        / "data"
        / "tttr"
        / "BH"
        / "132"
        / "BH_SPC132.spc"
    )
    if not spc.is_file():
        import pytest

        pytest.skip("sample SPC not available")

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
    # compute_all_channels: one LUT per used channel, per-channel distinct
    all_luts = vm.compute_all_channels()
    assert sorted(all_luts) == list(vm.available_channels)
    chs = list(vm.available_channels)
    assert not np.array_equal(all_luts[chs[0]], all_luts[chs[1]])
