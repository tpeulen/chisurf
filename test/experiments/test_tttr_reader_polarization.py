"""The TTTR TCSPC reader applies its polarization, g-factor and VH-shift controls.

BH_SPC132.spc carries routing channels 0/8 and 1/9; here 0,8 play VV and 1,9 VH.
Expected values are histograms of the same file taken directly with tttrlib.
"""

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.experiments.core.experiment import Experiment  # noqa: E402
from chisurf.core.experiments.tcspc.tttr_reader import TCSPCTTTRReader  # noqa: E402

FILE = "test/data/tttr/BH/132/BH_SPC132.spc"
VV, VH = [0, 8], [1, 9]


def _hist(chs):
    tttr = tttrlib.TTTR(FILE, "SPC-130")
    y, _ = tttr.get_tttr_by_channel(chs).get_microtime_histogram(1)
    return np.asarray(y, dtype=float)


def _reader(**kwargs):
    return TCSPCTTTRReader(
        experiment=Experiment(name="tcspc"),
        record_provenance=False,
        reading_routine="SPC-130",
        channel_numbers=VV,
        **kwargs,
    )


def test_without_vh_channels_polarization_is_one_decay_of_the_routing_channels():
    group = _reader(polarization="vv/vh").read(FILE)
    assert len(group) == 1
    assert group[0].y.sum() == _hist(VV).sum() == 79468 + 56499


def test_vv_vh_pair_is_two_stacked_curves_with_shifted_vh_and_calibration():
    reader = _reader(vh_channel_numbers=VH, polarization="vv/vh", g_factor=1.25, vh_shift=3)
    group = reader.read(FILE)
    assert [c.name.split()[-1] for c in group] == ["VV", "VH"]
    vv, vh = _hist(VV), _hist(VH)
    n = group[0].y.size
    np.testing.assert_array_equal(group[0].y, vv[:n])
    np.testing.assert_array_equal(group[1].y[3:], vh[: n - 3])
    assert np.all(group[1].y[:3] == 0)
    assert group.meta_data["g_factor"] == pytest.approx(1.25)
    assert group[1].meta_data["g_factor"] == pytest.approx(1.25)


def test_vm_is_vv_plus_two_g_vh_and_single_polarizations_select_one_channel():
    vv, vh = _hist(VV), _hist(VH)
    vm = _reader(vh_channel_numbers=VH, polarization="vm", g_factor=1.5).read(FILE)
    assert len(vm) == 1
    n = vm[0].y.size
    np.testing.assert_allclose(vm[0].y, (vv + 3.0 * vh)[:n])
    np.testing.assert_allclose(vm[0].ey, np.sqrt(np.maximum(vv + 9.0 * vh, 1.0))[:n])
    only_vh = _reader(vh_channel_numbers=VH, polarization="vh").read(FILE)
    assert len(only_vh) == 1 and only_vh[0].y.sum() == vh.sum()
    only_vv = _reader(vh_channel_numbers=VH, polarization="vv").read(FILE)
    assert len(only_vv) == 1 and only_vv[0].y.sum() == vv.sum()


def test_vh_channels_editor_adapter_round_trips():
    reader = _reader()
    reader.vh_channel_numbers_str = "9; 1, x"
    assert reader.vh_channel_numbers == [9, 1]
    assert reader.vh_channel_numbers_str == "9, 1"
    import json

    from chisurf.core.experiments.tcspc import tttr_reader

    spec = json.loads(tttr_reader._VIEW_JSON.read_text())
    assert any(
        s.get("attr") == "vh_channel_numbers_str"
        for panel in spec["sections"]
        for s in panel.get("sections", [])
    )
    assert reader.view_spec() is not None
