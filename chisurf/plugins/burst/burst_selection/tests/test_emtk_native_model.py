"""The Qt-free Burst Selection model (card BS0): same search, same bursts as the Qt tool, no toolkit.

The parity test runs the Qt ``BurstSelectionTool`` and :class:`BurstSelectionModel` on copies of the same two raw
files with the same detector setup and asserts identical burst tables (the measured baseline is 198 bursts).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[5]
DATA = Path(__file__).parent / "data" / "bh_spc132_sm_dna"
SETUP = {
    "detectors": {
        "green": {"chs": [0, 1], "micro_time_ranges": []},
        "red": {"chs": [8, 9], "micro_time_ranges": []},
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


def test_same_bursts_as_the_qt_tool(hermetic, qapp, tmp_path):
    """Run the Qt tool and the model on separate copies; the burst tables must be identical."""
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel
    from chisurf.plugins.burst.burst_selection.gui.tool import BurstSelectionTool

    qt_dir = tmp_path / "qt"
    qt_dir.mkdir()
    qt_paths = [Path(shutil.copy(p, qt_dir / p.name)) for p in hermetic]
    tool = BurstSelectionTool(embedded=True)
    try:
        tool._apply_detector_setup("probe")
        tool._add_paths(qt_paths)
        qs = tool._settings_from_controls()
        qt = tool._client.analyze_files(
            qt_paths,
            settings=asdict(qs),
            windows=tool.wizard.windows,
            detectors=tool.wizard.detectors,
            filetype=tool._selected_filetype,
            legacy_output=True,
            selected_setup=tool.wizard.comboBox.currentText(),
            legacy_parameters=tool._legacy_parameters(),
            mmfdb=None,
        )
    finally:
        tool.close()

    m = BurstSelectionModel()
    assert m.select_setup("probe")
    m.add_paths(hermetic)
    ms = m.analysis_settings()
    # every setting the registry search reads equals the Qt tool's
    pq, pm = asdict(qs)["photon_filter"], asdict(ms)["photon_filter"]
    for key in (
        "channels",
        "microtime_ranges",
        "filter_active",
        "invert_filter",
        "tttrlib_search",
        "delta_macro_time_filter",
        "use_gap_fill",
        "max_gap",
        "used_filter",
    ):
        assert pm[key] == pq[key], key
    assert ms.burst_detection.min_photons == qs.burst_detection.min_photons == 60
    assert ms.output_formats == qs.output_formats == ["bur"]
    assert m.prepare_run() is None
    mine = m.run()

    assert qt["metadata"]["n_bursts"] == mine["metadata"]["n_bursts"] == 198
    assert (
        Path(mine["metadata"]["output_folder"]).name == Path(qt["metadata"]["output_folder"]).name
    )
    by_name_qt = {Path(k).name: v for k, v in qt["dataframes"].items()}
    by_name = {Path(k).name: v for k, v in mine["dataframes"].items()}
    assert by_name.keys() == by_name_qt.keys()
    for name, rows in by_name_qt.items():
        assert len(by_name[name]) == len(rows)
        for a, b in zip(rows, by_name[name]):
            assert a.keys() == b.keys()
            for key, value in a.items():
                if "path" in key.lower():
                    continue
                other = b[key]
                if isinstance(value, float) and np.isnan(value):
                    assert isinstance(other, float) and np.isnan(other), key
                else:
                    assert other == value, key
    assert [r["bursts"] for r in m.file_rows()] == ["71", "127"]
    # the deliberate corrections: the macro-time cut in seconds, not min_photons / 1000
    assert qs.burst_detection.time_window == pytest.approx(0.06)
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
    assert model.detector_options() == ["All", "green", "red"]
    assert model.channels == []
    model.detector = "red"
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
    assert model.duration_histogram() is not None
    model.show_all_photons = False
    assert set(model.trace_curves()) == {"selected"}
    model.hist_feature = "Number of Photons"
    model.auto_range()
    centres, counts, _w = model.histogram()
    assert counts.sum() == len(model.burst_rows()) == 71
    model.gmm_components = 2
    result = model.fit_gmm()
    assert result["n"] == 2 and len(model.gmm_rows()) == 2
    xy = model.scatter()
    assert xy is not None and len(xy[0]) == 71
    model.set_metadata("pH", "7.4")
    cif = model.export_flr_cif(tmp_path / "out.cif")
    text = cif.read_text()
    assert "_pH 7.4" in text and "loop_" in text
    bur = model.save_bur(tmp_path / "all.bur")
    assert bur.read_text().count("\n") > 100
    assert model.output_path() and Path(model.output_path()).exists()
    assert model.output_folder() is not None


def test_empty_model_has_no_invented_data(hermetic):
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    m = BurstSelectionModel()
    assert m.trace_curves() == {} and m.dt_curves() == {} and m.decay_curves() == {}
    assert m.histogram() is None and m.scatter() is None and m.burst_rows() == []
    assert m.prepare_run() == "No TTTR files selected."
    with pytest.raises(ValueError):
        m.save_bur("x.bur")
    assert isinstance(np.asarray(m.feature_data("Duration (ms)")), np.ndarray)
    assert json.loads(m.result_json())["settings"]["photon_filter"]["used_filter"] == "tttrlib"
