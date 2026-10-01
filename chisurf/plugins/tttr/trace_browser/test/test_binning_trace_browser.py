"""The Qt-free trace binner (``core.binning``) and uncached ``core.trace.load_trace``.

Equality with the legacy ``IntensityTrace`` engine is proven by the numbers recorded from it
(see ``REFERENCE``): the legacy engine needs Qt and a saved setup and is not run here.
Everything uses temporary COPIES of repository sample data.
"""

import os
import pathlib
import shutil
import subprocess
import sys
import time
import types

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.tttr.trace_browser.core import trace as core_trace  # noqa: E402
from chisurf.plugins.tttr.trace_browser.core.binning import bin_trace  # noqa: E402
from chisurf.plugins.tttr.trace_browser.test.conftest import ALEX  # noqa: E402

HERE = pathlib.Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
BH132 = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"

# Recorded from the legacy engine (``IntensityTrace.process_ptu`` via the pre-change widget's
# ``_compute_trace_cached``) on a copy of BH_SPC132.spc with the "ALEX Suite (auto)" setup.
REFERENCE = {
    10.0: {"bins": 6233, "last": 62.32},
    1.0: {"bins": 62329, "last": 62.328},
}
SUMS = [22443, 56257, 0]
LABELS = ["green", "red", "yellow"]


@pytest.fixture
def spc(tmp_path):
    if not BH132.exists():
        pytest.skip("sample TTTR data missing")
    dst = tmp_path / "m000.spc"
    shutil.copy(BH132, dst)
    return dst


class FakeTTTR:
    """Duck-typed TTTR: 1 clock = 1 microsecond."""

    def __init__(self, macro, rc, micro, res=1e-6):
        self.macro_times = np.asarray(macro, dtype=np.uint64)
        self.routing_channels = np.asarray(rc, dtype=np.int16)
        self.micro_times = np.asarray(micro, dtype=np.uint16)
        self.header = types.SimpleNamespace(macro_time_resolution=res)

    def get_used_routing_channels(self):
        return np.unique(self.routing_channels)


@pytest.mark.parametrize("window_ms", [10.0, 1.0])
def test_reference_numbers_of_the_legacy_engine(spc, window_ms):
    ta, counts, labels = bin_trace(spc, window_ms / 1000.0, detectors=ALEX["detectors"])
    ref = REFERENCE[window_ms]
    assert labels == LABELS
    assert counts.shape == (ref["bins"], 3) and counts.dtype == np.float64
    assert ta.shape == (ref["bins"],) and ta.dtype == np.float64
    assert ta[-1] == pytest.approx(ref["last"])
    assert [int(x) for x in counts.sum(axis=0)] == SUMS
    if window_ms == 10.0:
        assert int(counts.max()) == 467


def test_channel_list_gives_one_series_per_routing_channel(spc):
    ta, counts, labels = bin_trace(spc, 0.01, channels=[1, 0])
    assert labels == ["Ch1", "Ch0"]
    assert counts.shape[1] == 2
    # no micro-time gating: more photons than the gated detectors of the reference
    assert counts[:, 0].sum() >= 22443 and counts[:, 1].sum() >= 56257
    # a channel absent from the file is an all-zero column, not an error
    _, c, lab = bin_trace(spc, 0.01, channels=[0, 5])
    assert lab == ["Ch0", "Ch5"] and c[:, 1].sum() == 0 and c[:, 0].sum() > 0


@pytest.mark.parametrize("mapping", [None, {}])
def test_empty_or_absent_mapping_uses_the_channel_list_then_all_channels(spc, mapping):
    _, c1, l1 = bin_trace(spc, 0.01, detectors=mapping, channels=[1])
    assert l1 == ["Ch1"] and c1.shape[1] == 1
    _, ca, la = bin_trace(spc, 0.01, detectors=mapping)
    assert la == ["Ch0", "Ch1", "Ch8", "Ch9"]  # every used routing channel, ascending
    assert int(ca.sum()) == int(sum(bin_trace(spc, 0.01, channels=[0, 1, 8, 9])[1].sum(axis=0)))


def test_selected_names_filter_and_order_detectors(spc):
    _, c, labels = bin_trace(spc, 0.01, detectors=ALEX["detectors"], selected=["red", "nope", "green"])
    assert labels == ["red", "green"]
    assert [int(x) for x in c.sum(axis=0)] == [56257, 22443]
    assert bin_trace(spc, 0.01, detectors=ALEX["detectors"], selected=["nope"])[2] == []


def test_photons_outside_every_window_are_not_counted_and_bounds_are_inclusive():
    # 1 clock = 1 us, window 10 us -> 10 clocks per bin
    macro = [0, 1, 2, 3, 12, 13, 25, 26, 27]
    micro = [5, 99, 100, 200, 201, 300, 150, 151, 5000]
    rc = [0] * 9
    t = FakeTTTR(macro, rc, micro)
    det = {"d": {"chs": [0], "micro_time_ranges": [[100, 200], (300, 300)]}}
    ta, c, labels = bin_trace(t, 10e-6, detectors=det)
    # photons kept (micro in [100,200] or ==300): macro 2, 3, 13, 25, 26 (micro 100, 200, 300, 150, 151)
    assert labels == ["d"]
    assert c.shape == (3, 1)
    assert c[:, 0].tolist() == [2.0, 1.0, 2.0]
    # the macro-5000 photon (micro outside) and micro 5, 99, 201 photons are not counted
    assert c.sum() == 5
    assert ta.tolist() == pytest.approx([0.0, 10e-6, 20e-6])


def test_each_series_is_as_long_as_its_last_photon_then_padded():
    t = FakeTTTR([0, 5, 95, 100], [0, 0, 1, 1], [0, 0, 0, 0])
    det = {"a": {"chs": [0], "micro_time_ranges": []}, "b": {"chs": [1]}, "none": {"chs": []},
           "empty": {"chs": [7]}}
    ta, c, labels = bin_trace(t, 10e-6, detectors=det)
    assert labels == ["a", "b", "empty"]  # a detector without chs is skipped
    assert c.shape == (11, 3)  # b's last photon (clock 100) -> 100 // 10 + 1 bins
    assert c[:, 0].tolist() == [2] + [0] * 10 and c[9, 1] == 1 and c[10, 1] == 1
    assert c[:, 2].sum() == 0
    assert ta[-1] == pytest.approx(100e-6)


def test_degenerate_inputs_give_the_empty_trace(spc):
    for window in (0.0, -1.0):
        ta, c, labels = bin_trace(spc, window, detectors=ALEX["detectors"])
        assert ta.size == 0 and c.shape == (0, 0) and labels == []
    ta, c, labels = bin_trace(FakeTTTR([], [], []), 0.01, channels=[0])
    assert ta.size == 0 and c.shape == (0, 0) and labels == []


def test_window_shorter_than_a_clock_uses_one_clock_per_bin():
    t = FakeTTTR([0, 1, 1, 3], [0] * 4, [0] * 4)
    _, c, _ = bin_trace(t, 1e-9, channels=[0])
    assert c[:, 0].tolist() == [1, 2, 0, 1]


def test_speed_of_the_one_millisecond_window(spc):
    t0 = time.perf_counter()
    bin_trace(spc, 0.001, detectors=ALEX["detectors"])
    assert time.perf_counter() - t0 < 5.0


# ---- core.trace.load_trace: uncached, hermetic, no Qt ---------------------------------------
def test_load_trace_computes_an_uncached_trace_with_the_binner(spc):
    out = core_trace.load_trace(str(spc), 10.0, setup_settings=ALEX)
    assert out["labels"] == LABELS and np.asarray(out["counts"]).shape == (6233, 3)
    assert [int(x) for x in np.asarray(out["counts"]).sum(axis=0)] == SUMS
    assert core_trace.load_cached(spc, spc.parent, 10.0, ALEX, None) is not None
    again = core_trace.load_trace(str(spc), 10.0, setup_settings=ALEX)
    assert again == out


def test_load_trace_without_a_setup_uses_channels_or_all_channels(spc):
    assert core_trace.load_trace(str(spc), 10.0, selected_channels=[0, 1])["labels"] == ["Ch0", "Ch1"]
    assert core_trace.load_trace(str(spc), 10.0)["labels"] == ["Ch0", "Ch1", "Ch8", "Ch9"]
    # a setup with an empty detector mapping behaves like no setup
    assert core_trace.load_trace(str(spc), 10.0, setup_settings={"detectors": {}},
                                 selected_channels=[1])["labels"] == ["Ch1"]


def test_binner_and_trace_are_qt_free_and_compute_uncached(spc):
    script = f"""
import importlib.abc, sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'qtpy','PyQt5','PyQt6','PySide2','PySide6'}}:
            raise RuntimeError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from chisurf.plugins.tttr.trace_browser.core import binning, trace
det = {{"green": {{"chs": [1], "micro_time_ranges": [[616, 3784]]}}}}
out = trace.load_trace({str(spc)!r}, 10.0, setup_settings={{"detectors": det}})
assert out["labels"] == ["green"] and int(sum(r[0] for r in out["counts"])) == 22443, out["labels"]
bad = sorted(x for x in sys.modules if x == 'chisurf.gui' or x.startswith('chisurf.gui.'))
assert not bad, bad[:5]
print('QT-FREE OK')
"""
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(REPO), os.environ.get("PYTHONPATH", "")]))
    done = subprocess.run([sys.executable, "-c", script], cwd=REPO, env=env,
                          capture_output=True, text=True)
    assert done.returncode == 0 and "QT-FREE OK" in done.stdout, done.stdout + done.stderr[-1500:]
