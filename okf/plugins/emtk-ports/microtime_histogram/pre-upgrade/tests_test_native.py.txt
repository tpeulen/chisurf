"""Native histogram physics, safe burst boundaries, exports and Qt isolation."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from chisurf.plugins.tttr.microtime_histogram.gui.model import (
    HistogramModel,
    burst_mask,
    read_burst_ranges,
    shift_histogram,
)


class Stream:
    def __init__(self):
        self.micro_times = np.array([0, 1, 2, 3, 1, 2, 4, 5])
        self.routing_channels = np.array([0, 0, 0, 0, 1, 1, 1, 1])
        self.header = SimpleNamespace(
            micro_time_resolution=1e-10, get_effective_number_of_micro_time_channels=lambda: 8
        )


def test_histogram_polarization_shift_fwhm_and_saved_flat_decay(tmp_path):
    path = tmp_path / "one.ptu"
    path.write_bytes(b"x")
    model = HistogramModel()
    model.auto_save = False
    model.add_paths([path])
    model.compute(reader=lambda _: Stream())
    np.testing.assert_array_equal(model.cumulative_parallel[:6], [1, 1, 1, 1, 0, 0])
    np.testing.assert_array_equal(model.cumulative_perpendicular[:6], [0, 1, 1, 0, 1, 1])
    assert model.dt_ns == 0.1
    model.vv_shift = 1
    model.vh_shift = -1
    model.update_timeshifts()
    assert model.cumulative_parallel[0] == 0 and model.cumulative_perpendicular[-1] == 0
    np.testing.assert_array_equal(
        model.combined,
        model.cumulative_parallel + 2 * model.g_factor * model.cumulative_perpendicular,
    )
    output = tmp_path / "decay.dat"
    model.save(output)
    np.testing.assert_array_equal(np.loadtxt(output), model.cumulative_ps)


def test_burst_header_columns_and_safe_inclusive_mask(tmp_path):
    path = tmp_path / "one.bur"
    path.write_text("First File\tLast File\tFirst Photon\tLast Photon\nunits\n0\t0\t2\t4\n")
    assert read_burst_ranges(path) == [(2, 4)]
    np.testing.assert_array_equal(
        burst_mask(6, [(2, 4), (4, 100)]), [False, False, True, True, True, True]
    )
    assert len(burst_mask(6, [(100, 200)])) == 6
    np.testing.assert_array_equal(shift_histogram([1, 2, 3], 1), [0, 1, 2])
    np.testing.assert_array_equal(shift_histogram([1, 2, 3], -1), [2, 3, 0])


def test_burst_selection_and_detector_excitation_gates(tmp_path):
    source = tmp_path / "one.ptu"
    source.write_bytes(b"x")
    bid = tmp_path / "one.ptu.bst"
    bid.write_text("1\t5\n")
    model = HistogramModel()
    model.auto_save = False
    model.set_setup(
        {
            "detectors": {"green": {"chs": [0, 1], "micro_time_ranges": [[1, 2]]}},
            "windows": {"excitation": [1, 1]},
        }
    )
    model.window = "excitation"
    model.add_paths([source])
    model.add_paths([bid], bids=True)
    model.compute(reader=lambda _: Stream())
    assert model.cumulative_parallel.sum() == 1 and model.cumulative_perpendicular.sum() == 1


def test_native_factories_draw_without_qt_imports():
    script = """
import sys
class Block:
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
from emtk.pil_painter import PilPainter
from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app
from chisurf.plugins.vv_vh_g_factor.gui.app import create_app as factor
for app in (create_app(),factor()):
 app.draw(PilPainter(1200,800),0,0,1200,800)
 app.close()
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_native_histogram_transfer_saves_and_calls_tcspc_context(tmp_path):
    from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app

    source = tmp_path / "one.ptu"
    source.write_bytes(b"x")
    transferred = []
    app = create_app(
        reader=lambda _: Stream(),
        add_dataset=lambda path, params: transferred.append((path, params)),
    )
    app.add_files([source])
    app.model.auto_save = False
    app.model.output = str(tmp_path / "decay.dat")
    app.compute(transfer=True)
    app.job.future.result(timeout=5)
    app.job.poll()
    assert transferred and transferred[0][1]["dt"] == 0.1
    assert transferred[0][0].exists()
    app.close()


def test_native_histogram_background_snapshot_cancel_and_clear(tmp_path):
    from threading import Event

    from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app

    entered, release = Event(), Event()

    def reader(_):
        entered.set()
        assert release.wait(5)
        return Stream()

    source = tmp_path / "one.ptu"
    source.write_bytes(b"x")
    app = create_app(reader=reader)
    app.add_files([source])
    app.model.auto_save = False
    try:
        assert app.compute()
        assert entered.wait(5)
        assert not app.compute()
        app.model.parallel = [1]
        release.set()
        app.job.future.result(timeout=5)
        app.job.poll()
        assert app.model.parallel == [0]
        assert app.model.cumulative_parallel.sum() == 4
        app.clear()
        assert app.model.cumulative_parallel is None
        assert app.model.cumulative_perpendicular is None
        entered.clear()
        release.clear()
        app.add_files([source])
        assert app.compute()
        assert entered.wait(5)
        app.job.stop()
        release.set()
        app.job.future.result(timeout=5)
        app.job.poll()
        assert app.model.cumulative_parallel is None
    finally:
        release.set()
        app.close()


def test_native_real_ptu_polarized_histogram_matches_installed_reader(tmp_path):
    import pytest

    from chisurf.core.fio.staging import open_tttr

    source = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
    if not source.is_file():
        pytest.skip("Real PTU fixture unavailable.")
    model = HistogramModel()
    model.auto_save = False
    model.parallel = [0]
    model.perpendicular = [1]
    model.add_paths([source])
    model.compute()
    stream = open_tttr(source, apply_lut=False, channel_shifts={})
    n = int(stream.header.get_effective_number_of_micro_time_channels())
    expected = [
        np.bincount(
            np.asarray(stream.micro_times)[np.asarray(stream.routing_channels) == channel],
            minlength=n,
        )
        for channel in [0, 1]
    ]
    size = max(map(len, expected))
    expected = [np.pad(vector, (0, size - len(vector))) for vector in expected]
    np.testing.assert_array_equal(model.cumulative_parallel, expected[0])
    np.testing.assert_array_equal(model.cumulative_perpendicular, expected[1])
    output = tmp_path / "real_decay.dat"
    model.save(output)
    assert len(np.loadtxt(output)) == len(expected[0]) + len(expected[1])


def test_unpolarized_does_not_duplicate_photons_in_vh(tmp_path):
    path = tmp_path / "one.ptu"
    path.write_bytes(b"x")
    model = HistogramModel()
    model.auto_save = False
    model.polarized = False
    model.parallel = [0, 1]
    model.add_paths([path])
    model.compute(reader=lambda _: Stream())
    assert model.cumulative_parallel.sum() == 8
    assert model.cumulative_perpendicular.sum() == 0


def test_header_timing_override_is_picoseconds_to_binned_nanoseconds(tmp_path):
    path = tmp_path / "one.ptu"
    path.write_bytes(b"x")
    model = HistogramModel()
    model.auto_save = False
    model.binning = 2
    model.setup["tttr_reading"] = {"override_timing": True, "micro_time_resolution": 25}
    model.add_paths([path])
    model.compute(reader=lambda _: Stream())
    assert model.dt_ns == 0.05
