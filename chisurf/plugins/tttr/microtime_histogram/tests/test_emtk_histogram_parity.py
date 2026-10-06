"""The native histogram app against the Qt wizard on the same photons (BH_SPC132.spc, green detector).

The Qt wizard runs in a subprocess (this process stays Qt-free); its cumulative VV|VH export, channel lists and G-factor
are compared with the emtk model fed the same detector, binning and shifts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
from test.gui.emtk_port_parity import qt_free  # noqa: E402,F401  (before the plugin import)
from chisurf.plugins.tttr.microtime_histogram.gui.model import HistogramModel  # noqa: E402
# isort: on

PHOTONS = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))


@pytest.fixture(scope="module")
def qt(tmp_path_factory):
    root = tmp_path_factory.mktemp("qt_ref")
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        HOME=str(root / "home"),
        CHISURF_SETTINGS_DIR=str(root / "s"),
        MMFDB_SETTINGS_DIR=str(root / "m"),
        MMFDB_DATABASE_PATH=str(root / "m.sqlite"),
        PYTHONPATH=f"{REPO}:{os.environ.get('PYTHONPATH', '')}",
    )
    run = subprocess.run(
        [sys.executable, str(HERE / "qt_reference.py"), str(REPO), str(root / "ref.npz")],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    assert run.returncode == 0, run.stderr[
        -2000:
    ]  # a broken Qt host fails here, it is never skipped
    info = json.loads(next(line for line in run.stdout.splitlines() if line.startswith("JSON"))[4:])
    return info, dict(np.load(root / "ref.npz"))


def emtk_model(info):
    model = HistogramModel()
    model.auto_save = False
    model.set_setup(
        {"detectors": {info["detector"]: info["setup"]}, "windows": {}, "tttr_reading": {}}
    )
    model.filetype = "SPC-130"  # the wizard reads with its (disabled) format box: SPC-130
    model.binning, model.vv_shift, model.vh_shift, model.g_factor = (
        info["binning"],
        info["vv"],
        info["vh"],
        info["g"],
    )
    model.add_paths([PHOTONS])
    model.compute()
    return model


@pytest.mark.parametrize("name", ["default", "shifted"])
def test_the_export_equals_the_qt_wizards_for_the_same_photons(qt, name):
    info, arrays = qt
    model = emtk_model(info[name])
    assert (
        model.parallel == info[name]["parallel"]
        and model.perpendicular == info[name]["perpendicular"]
    )
    assert model.g_factor == info[name]["g"]
    np.testing.assert_array_equal(model.cumulative_ps, arrays[name])
    qt_channels = float(
        info[name]["fwhm_text"].split("(")[1].split()[0]
    )  # "5.65 ns (113.0 channels)"
    assert model.fwhm_bins == qt_channels  # same crossing rule, same width


def test_the_qt_reference_is_not_empty(qt):
    info, arrays = qt
    assert arrays["default"].sum() > 100_000 and info["default"]["detector"] == "green"
    assert info["default"]["output_name"] == "decay.dat"


def test_qt_free():
    assert qt_free("microtime_histogram")
