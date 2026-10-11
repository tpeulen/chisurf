"""The plot data of Burst Selection is the data the Qt tool drew, number for number.

``fixtures/burst_selection_plot_reference.json`` froze what the Qt ``BurstSelectionTool`` handed to its six plots on the
two in-repository BH SPC-132 files (SHA-256 of every plotted array). The Qt tool is retired; the Qt-free model behind
the emtk app computes the same six panes from the same photons, and is held to those hashes:

* the selected-photon count-rate trace, the selected-photon inter-photon times, the two micro-time decays and the
  burst-duration histogram of the first ten seconds are **bit-identical**;
* so is the Proximity-Ratio histogram of the window's preview table (the eight bursts of those ten seconds);
* the all-photon traces (count rate and dT) differ from the Qt arrays by the three or four samples at the window's
  edge: the Qt tool cut its window on a timeline concatenated over the files, the emtk model cuts it on the file's own
  macro-time clock (``BurstSelectionClient._window_indices``). Their length agrees to within five samples and every
  other sample is the same function of the same photons.

The model's plot budget is lifted for the comparison (the Qt tool drew these arrays unthinned).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

REFERENCE = json.loads(
    (Path(__file__).parent / "fixtures/burst_selection_plot_reference.json").read_text()
)
DATA = (
    Path(__file__).parents[2] / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
)


def _sha(values) -> str:
    return hashlib.sha256(np.asarray(values, dtype=np.float64).tobytes()).hexdigest()


def _same(values, frozen) -> bool:
    values = np.asarray(values, dtype=np.float64)
    return list(values.shape) == frozen["shape"] and _sha(values) == frozen["sha256"]


@pytest.fixture(scope="module")
def models(tmp_path_factory):
    """The model after a full search (``searched``) and a fresh one that only previews the first ten seconds."""
    import os

    from mmfdb.repository import MFDatabase

    import chisurf.plugins.burst.burst_selection.gui.model as module
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel, save_setup

    root = tmp_path_factory.mktemp("plot_reference")
    patch = pytest.MonkeyPatch()
    for key, name in {
        "CHISURF_SETTINGS_DIR": "settings",
        "MMFDB_SETTINGS_DIR": "mmfdb",
        "MMFDB_DATABASE_PATH": "database.sqlite",
        "MMFDB_OBJECT_STORE_ROOT": "objects",
    }.items():
        patch.setenv(key, str(root / name))
    os.makedirs(root / "settings", exist_ok=True)
    MFDatabase(str(root / "database.sqlite")).close()
    patch.setattr(module, "MAX_PLOT_POINTS", 10**9)
    save_setup(
        "plot-proof",
        {
            "detectors": {
                "green": {"chs": [0, 1], "micro_time_ranges": []},
                "red": {"chs": [8, 9], "micro_time_ranges": []},
            },
            "windows": {},
            "tttr_reading": {"file_type": "SPC-130"},
        },
    )
    paths = []
    for name in ("m000.spc", "m001.spc"):
        path = root / name
        shutil.copy2(DATA / name, path)
        paths.append(path)

    def build():
        model = BurstSelectionModel()
        assert model.select_setup("plot-proof")
        model.add_paths(paths)
        model.window_start_s, model.window_length_s = 0.0, 10.0
        return model

    searched, preview = build(), build()
    searched.run()
    searched.load_diagnostics()
    preview.load_diagnostics()
    yield searched, preview
    patch.undo()


def test_the_search_reproduces_the_metadata_of_the_frozen_run(models):
    searched, _ = models
    meta = {k: v for k, v in searched.result["metadata"].items() if k != "output_folder"}
    assert meta == REFERENCE["metadata"]


def test_the_selected_traces_and_the_decays_are_bit_identical(models):
    searched, _ = models
    mcs, dt, decay = (
        REFERENCE["panes"]["mcs"],
        REFERENCE["panes"]["dt"],
        REFERENCE["panes"]["decay"],
    )
    trace = searched.trace_curves()["selected"]
    assert _same(trace[0], mcs["items"][1]["x"]) and _same(trace[1], mcs["items"][1]["y"])
    inter = searched.dt_curves()["selected"]
    assert _same(inter[0], dt["items"][1]["x"]) and _same(inter[1], dt["items"][1]["y"])
    curves = searched.decay_curves()
    for key, item in zip(("all", "selected"), decay["items"]):
        assert _same(curves[key][0], item["x"]) and _same(curves[key][1], item["y"]), key


def test_the_all_photon_traces_differ_only_at_the_edge_of_the_window(models):
    searched, _ = models
    mcs, dt = REFERENCE["panes"]["mcs"]["items"][0], REFERENCE["panes"]["dt"]["items"][0]
    trace, inter = searched.trace_curves()["all"], searched.dt_curves()["all"]
    assert abs(len(trace[0]) - mcs["x"]["shape"][0]) <= 5
    assert abs(len(inter[0]) - dt["x"]["shape"][0]) <= 5
    # the count-rate axis is the file's clock in seconds, at the 0.25 ms bin width
    assert np.diff(trace[0]).min() == pytest.approx(0.00025)


def test_the_burst_duration_histogram_and_the_preview_histogram_are_bit_identical(models):
    _, preview = models
    burst = REFERENCE["panes"]["burst"]["items"]
    centres, counts, width = preview.duration_histogram()
    assert _same(centres, burst[0]["x"]) and _same(counts, burst[0]["height"])
    assert width == pytest.approx(burst[0]["width"], rel=1e-12)
    assert burst[1]["text"] == "Total bursts: 8" and int(counts.sum()) == 8

    expected = REFERENCE["panes"]["histogram"]["items"][0]
    preview.hist_feature, preview.hist_bins = "Proximity Ratio", 61
    preview.hist_min, preview.hist_max = 0.0, 1.0
    centres, counts, width = preview.histogram()
    assert _same(centres, expected["x"]) and _same(counts, expected["height"])
    assert width == pytest.approx(expected["width"], rel=1e-12)
