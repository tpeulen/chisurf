"""The native histogram app against preserved legacy measured-SPC outputs.

The successful legacy wizard run was frozen before retirement. Counts, routing
and FWHM bins remain identical; its unsaved 50 ps initializer is not treated as
an instrument calibration. Explicit/native/header timing branches have separate guards.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
from test.gui.emtk_port_parity import qt_free  # noqa: E402,F401
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
def legacy():
    """Read the successful pre-retirement run and its immutable count vectors."""
    folder = HERE / "data"
    info = json.loads((folder / "legacy_reference.json").read_text())
    return info, {name: np.load(folder / f"legacy_{name}.npy") for name in ("default", "shifted")}


def emtk_model(info):
    model = HistogramModel()
    model.auto_save = False
    model.set_setup(info["full_setup"])
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
def test_the_export_equals_preserved_legacy_counts_for_the_same_photons(legacy, name):
    info, arrays = legacy
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


def test_the_preserved_reference_is_not_empty(legacy):
    info, arrays = legacy
    assert arrays["default"].sum() > 100_000 and info["default"]["detector"] == "green"
    assert "no physical calibration provenance" in info["default"]["timing_provenance"]


def test_qt_free():
    assert qt_free("microtime_histogram")
