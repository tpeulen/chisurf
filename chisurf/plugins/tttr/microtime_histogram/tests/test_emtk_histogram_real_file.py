"""The histogram app on a measured SPC-130 file, checked against the file itself.

The oracle is the photon stream as tttrlib reads it: the VV and VH histograms
are the per-channel ``bincount`` of the routed photons' micro times, binning
sums neighbouring channels and a time shift moves the histogram by whole bins.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
from test.gui.emtk_port_parity import qt_free  # noqa: E402,F401
from chisurf.plugins.tttr.microtime_histogram.gui.model import (  # noqa: E402
    HistogramModel,
    shift_histogram,
)
# isort: on

PHOTONS = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
PARALLEL, PERPENDICULAR = [8, 3], [0]
SETUP = {
    "detectors": {
        "green": {
            "chs": [8, 0, 3],
            "micro_time_ranges": [[0, 4095]],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
        }
    },
    "polarization_resolved": True,
}


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))


@pytest.fixture(scope="module")
def stream():
    tttrlib = pytest.importorskip("tttrlib")
    data = tttrlib.TTTR(str(PHOTONS), "SPC-130")
    n = int(data.header.get_effective_number_of_micro_time_channels())
    return np.asarray(data.routing_channels), np.asarray(data.micro_times, np.int64), n


def expected(stream, channels, binning):
    routing, micro, n = stream
    bins = (n + binning - 1) // binning
    return np.bincount(micro[np.isin(routing, channels)] // binning, minlength=bins)


def model_for(binning=1, vv=0, vh=0, g=1.0):
    model = HistogramModel()
    model.auto_save = False
    model.set_setup(SETUP)
    model.filetype = "SPC-130"
    model.parallel, model.perpendicular = list(PARALLEL), list(PERPENDICULAR)
    model.polarized = True
    model.binning, model.vv_shift, model.vh_shift, model.g_factor = binning, vv, vh, g
    model.add_paths([PHOTONS])
    model.compute()
    return model


def test_vv_and_vh_are_the_routed_photons_micro_time_counts(stream):
    model = model_for()
    vv, vh = expected(stream, PARALLEL, 1), expected(stream, PERPENDICULAR, 1)
    np.testing.assert_array_equal(model.cumulative_ps, np.concatenate([vv, vh]))
    # every photon of the green detector's three channels is counted once
    assert model.cumulative_ps.sum() == np.isin(stream[0], [8, 0, 3]).sum() > 100_000
    assert model.fwhm_bins > 0 and model.fwhm_ns == pytest.approx(model.fwhm_bins * model.dt_ns)


def test_binning_and_time_shifts_move_whole_bins(stream):
    model = model_for(binning=4, vv=3, vh=-2, g=1.25)
    vv = shift_histogram(expected(stream, PARALLEL, 4), 3)
    vh = shift_histogram(expected(stream, PERPENDICULAR, 4), -2)
    np.testing.assert_array_equal(model.cumulative_parallel, vv)
    np.testing.assert_array_equal(model.cumulative_perpendicular, vh)
    np.testing.assert_allclose(model.combined, vv + 2 * 1.25 * vh)


def test_qt_free():
    assert qt_free("microtime_histogram")
