"""The toolkit-free Burst Selection model (card BS0).

The model runs on copies of two raw files with a fixed detector setup; every burst row is checked against the
photons of the file it came from.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[5]
DATA = Path(__file__).parent / "data" / "bh_spc132_sm_dna"
SETUP = {
    "detectors": {
        "G|G": {"chs": [0, 1], "micro_time_ranges": []},
        "R|G": {"chs": [8, 9], "micro_time_ranges": []},
    },
    "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
    "tttr_reading": {"file_type": "SPC-130"},
}


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "mmfdb").mkdir()
    data = tmp_path / "data"
    data.mkdir()
    paths = []
    for name in ("m000.spc", "m001.spc"):
        shutil.copy(DATA / name, data / name)
        paths.append(data / name)
    from chisurf.plugins.burst.burst_selection.gui.model import save_setup

    save_setup("probe", SETUP)
    return paths


@pytest.fixture
def model(hermetic):
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    m = BurstSelectionModel()
    assert m.select_setup("probe")
    m.add_paths(hermetic)
    return m


def test_model_is_qt_free():
    script = (
        "import importlib.abc, sys\n"
        "class B(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, n, p=None, t=None):\n"
        "        if n.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}: raise RuntimeError(n)\n"
        "sys.meta_path.insert(0, B())\n"
        "from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel\n"
        "BurstSelectionModel()\n"
        "bad = [m for m in sys.modules if m == 'chisurf.gui' or m.startswith('chisurf.gui.')]\n"
        "assert not bad, bad\n"
    )
    env = dict(
        os.environ, PYTHONPATH=os.pathsep.join([str(REPO), os.environ.get("PYTHONPATH", "")])
    )
    done = subprocess.run(
        [sys.executable, "-c", script], cwd=REPO, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr[-2000:]


def _spc(path):
    import tttrlib

    t = tttrlib.TTTR(str(path), "SPC-130")
    seconds = np.asarray(t.macro_times, dtype=np.float64) * t.header.macro_time_resolution
    return np.asarray(t.routing_channels), seconds


def test_every_burst_row_counts_the_photons_of_its_span(hermetic):
    """Run the model on copies of the two raw files; every burst row is checked against the photons.

    The oracle is the input itself: each row's photon counts (all, ``G|G`` on 0/1, ``R|G`` on 8/9) and its duration
    are recounted from the raw file between the row's first and last photon, and each burst holds at least the
    minimum photon number the search was given.
    """
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    m = BurstSelectionModel()
    assert m.select_setup("probe")
    m.add_paths(hermetic)
    ms = m.analysis_settings()
    pf = ms.photon_filter
    assert pf.tttrlib_search.algorithm == "sliding_window"
    assert dict(pf.tttrlib_search.parameters) == {"L": 20, "m": 10, "T": 0.0005}
    assert ms.burst_detection.min_photons == 60
    # the run goes into the photon dataset's analysis container (the folder is an explicit export)
    assert ms.output_formats == ["pto"]
    assert m.prepare_run() is None
    mine = m.run()

    # the run is named after its search, detector, dT max (ms) and minimum photons
    assert Path(mine["output_paths"]["output_folder"]).name == "sliding_window_All 0.1500#60"
    # in process the search hands its tables over (no rows); the GUI reads them as they are
    from chisurf.core.datastore import rows_from_table

    by_name = {Path(k).name: rows_from_table(v) for k, v in m.frames_by_file.items()}
    assert by_name.keys() == {"m000.spc", "m001.spc"}
    counts = []
    for name, rows in by_name.items():
        channels, seconds = _spc(Path(hermetic[0]).parent / name)
        bursts = [r for r in rows if r["Number of Photons"]]  # the table interleaves empty spacer rows
        assert bursts and all(r["First File"] == name for r in bursts)
        for r in bursts:
            a, b = int(r["First Photon"]), int(r["Last Photon"])
            span = channels[a : b + 1]
            assert r["Number of Photons"] == b - a + 1 >= 60
            assert r["Number of Photons (G|G)"] == np.isin(span, [0, 1]).sum()
            assert r["Number of Photons (R|G)"] == np.isin(span, [8, 9]).sum()
            assert r["Duration (ms)"] == pytest.approx((seconds[b] - seconds[a]) * 1e3, rel=1e-9)
        counts.append(len(bursts))
    assert mine["metadata"]["n_bursts"] == sum(counts)
    assert [r["bursts"] for r in m.file_rows()] == [str(n) for n in counts]
    # the macro-time cut is in seconds (dT max 0.15 ms), not min_photons / 1000
    assert ms.burst_detection.time_window == pytest.approx(0.15 / 1000.0)
    assert m.burst_selection_parameters()["dT_min"] == m.dt_min == 0.001


def test_unchanged_request_is_kept_and_restart_forces(model):
    assert model.prepare_run() is None
    model.run()
    assert "Unchanged" in model.prepare_run()
    assert model.prepare_run(force=True) is None
    model.min_photons = 61
    assert model.prepare_run() is None


def test_detector_and_window_choices_drive_the_filter(model):
    assert model.detector_options() == ["All", "G|G", "R|G"]
    assert model.channels == []
    model.detector = "R|G"
    assert model.channels == [8, 9]
    model.window = "delayed"
    assert model.microtime_ranges == [(2048, 4095)]
    s = model.analysis_settings().photon_filter
    assert s.channels == [8, 9] and s.microtime_ranges == [(2048, 4095)]
    model.use_gap_fill = False
    assert model.analysis_settings().photon_filter.max_gap == 0
    assert model.enabled("merge_gap") is False


def test_search_parameters_follow_the_registry(model):
    from chisurf.plugins.burst.burst_selection.gui.model import search_defaults

    assert model.algorithm == "sliding_window"
    assert model.parameters == {"L": 20, "m": 10, "T": 0.0005}
    names = [s["attr"] for s in model.search_sections()]
    assert names == ["L", "m", "T"]
    assert all(s.get("description") for s in model.search_sections())
    model.search.m = "12"
    assert model.parameters["m"] == 12
    model.set_algorithm("maxtree")
    assert model.parameters == search_defaults("maxtree")
    model.set_algorithm("coincident")
    assert model.search.channel_groups == "0,1; 8,9"
    model.search.channel_groups = "0; 8, 9"
    assert model.parameters["channel_groups"] == [[0], [8, 9]]
    model.search.algorithm = "sliding_window"
    assert model.parameters["parameters"] == search_defaults("sliding_window")
    assert [s["attr"] for s in model.nested_sections()] == ["L", "m", "T"]
    model.inner_search.T = 0.001
    assert model.parameters["parameters"]["T"] == 0.001


def test_setup_defaults_round_trip(model):
    model.min_photons = 42
    model.dt_max = 0.2
    model.set_algorithm("maxtree")
    model.search.L = 33
    model.save_defaults_to_setup()
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    other = BurstSelectionModel()
    assert other.select_setup("probe")
    assert other.min_photons == 42 and other.dt_max == 0.2
    assert other.algorithm == "maxtree" and other.parameters["L"] == 33


def test_settings_round_trip(model, tmp_path):
    model.hist_bins = 17
    model.trace_bin_ms = 1.5
    model.metadata = {"pH": "7.5"}
    model.set_algorithm("bocpd")
    path = tmp_path / "s.json"
    model.save_settings(path)
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    other = BurstSelectionModel()
    other.load_settings(path)
    assert other.export_settings() == model.export_settings()
    with pytest.raises(ValueError):
        other.import_settings({"kind": "something_else"})


def test_preview_then_plots_histogram_gmm_and_exports(model, tmp_path):
    diag = model.load_diagnostics()
    assert diag is not None and model.preview and model.display_frame is not None
    assert "Preview" in model.status_text
    model.run()
    assert not model.preview
    model.load_diagnostics()
    curves = model.trace_curves()
    assert set(curves) == {"all", "selected"}
    assert curves["selected"][1].max() > 0
    assert set(model.dt_curves()) == {"all", "selected"}
    assert set(model.decay_curves()) == {"all", "selected"}
    model.show_all_photons = False
    assert set(model.trace_curves()) == {"selected"}
    model.hist_feature = "Number of Photons"
    model.auto_range()
    centres, counts, _w = model.histogram()
    assert counts.sum() == len(model.burst_rows()) == 198  # both files: one measurement
    model.gmm_components = 2
    result = model.fit_gmm()
    assert result["n"] == 2 and len(model.gmm_rows()) == 2
    xy = model.scatter()
    assert xy is not None and len(xy[0]) == 198
    model.set_metadata("pH", "7.4")
    cif = model.export_flr_cif(tmp_path / "out.cif")
    text = cif.read_text()
    assert "_pH 7.4" in text and "loop_" in text
    from chisurf.core.fio.address import container_of

    assert model.output_path() and container_of(model.output_path()).is_file()
    assert model.output_folder() is not None


def test_empty_model_has_no_invented_data(hermetic):
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    m = BurstSelectionModel()
    assert m.trace_curves() == {} and m.dt_curves() == {} and m.decay_curves() == {}
    assert m.histogram() is None and m.scatter() is None and m.burst_rows() == []
    assert m.prepare_run() == "No TTTR files selected."
    with pytest.raises(ValueError):
        m.export_flr_cif("x.cif")
    assert isinstance(np.asarray(m.feature_data("Duration (ms)")), np.ndarray)
    assert json.loads(m.result_json())["settings"]["photon_filter"]["used_filter"] == "tttrlib"


def test_reading_the_inner_search_form_leaves_the_request_alone():
    """Drawing the coincident search's inner form for another search must not add an empty
    ``parameters`` to the request: tttrlib rejects it ("sliding_window does not take
    ['parameters']"), and every search run after the form was drawn failed."""
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    model = BurstSelectionModel()
    model.set_algorithm("sliding_window")
    before = dict(model.parameters)
    for name in ("L", "m", "T", "algorithm", "parameters"):
        getattr(model.inner_search, name)
    assert model.parameters == before
    settings = model.analysis_settings()
    assert "parameters" not in settings.photon_filter.tttrlib_search.parameters
