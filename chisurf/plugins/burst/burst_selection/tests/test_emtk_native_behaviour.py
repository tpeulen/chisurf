"""Behaviours of the Qt Burst Selection tool, stated against the Qt-free model.

The retired tool's tests drove widgets through ``BurstSelectionTool.__new__`` and fakes of Qt controls
(``test_new_gui.py``, ``test_filter_ui_elements.py``, ``test_photon_range_controls.py``, ...). What they pinned was
never the widget: it was a rule about the data (a window is clamped, a count rate is a rate, a preview searches
nothing, MMFDB output needs a sample, "All" selects everything, a search parameter changes the burst count). Each is
here against :class:`BurstSelectionModel`, on the in-repository BH SPC-132 photons where a real file is needed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from .test_emtk_native_model import DATA, SETUP, hermetic, model  # noqa: F401  (fixtures)

RAW = DATA / "m000.spc"


@pytest.fixture
def photons():
    import tttrlib

    return tttrlib.TTTR(str(RAW), "SPC-130")


class _Header:
    def __init__(self, resolution: float = 0.001) -> None:
        self.macro_time_resolution = resolution


# --- defaults ------------------------------------------------------------------------------------------


def test_the_defaults_are_the_photon_filter_pages(model):  # noqa: F811
    """The model starts from the shared photon-filter page's defaults (what the Qt tool showed on opening)."""
    from chisurf.plugins.burst.burst_selection.api.models import BurstFilterMode

    assert (model.dt_min, model.dt_max) == (0.001, 0.150)
    assert (model.dt_min_active, model.dt_max_active) == (False, True)
    assert (model.use_gap_fill, model.merge_gap) == (True, 3)
    assert (model.min_photons, model.photon_window) == (60, 5)
    assert model.filter_active is True and model.invert is False
    s = model.analysis_settings()
    assert s.photon_filter.used_filter == BurstFilterMode.TTTRLIB
    assert s.photon_filter.delta_macro_time_filter.dT_max == model.dt_max
    assert s.burst_detection.min_photons == 60 and s.burst_detection.photon_window == 5
    # every registry search is offered, none of the retired hand-written modes
    from chisurf.core.fluorescence.burst import tttrlib_search

    assert [name for name, _label in model.algorithm_options()] == list(tttrlib_search.algorithms())
    labels = [label for _name, label in model.algorithm_options()]
    for retired in ("Count rate", "Burst", "Kalman Burst", "CUSUM Burst", "BOCPD Burst"):
        assert retired not in labels, retired


# --- the filter settings reach the analysis ----------------------------------------------------------------


def test_macro_time_bounds_reach_the_analysis(model):  # noqa: F811
    model.dt_min, model.dt_max = 0.002, 0.080
    model.dt_min_active, model.dt_max_active = True, False
    f = model.analysis_settings().photon_filter.delta_macro_time_filter
    assert (f.dT_min, f.dT_max, f.dT_min_active, f.dT_max_active) == (0.002, 0.080, True, False)
    assert model.thresholds() == {"dt_min": 0.002, "dt_max": None}
    assert model.enabled("dt_min") is True and model.enabled("dt_max") is False


def test_macro_time_bounds_actually_filter_photons(model, photons):  # noqa: F811
    """The bound must change the selection, not merely be stored."""
    from chisurf.plugins.burst.burst_selection.api.selection import apply_photon_filters

    model.dt_min_active = model.dt_max_active = True
    model.dt_min = 0.001
    model.use_gap_fill = False  # gap filling widens the result
    fractions = []
    for dt_max in (0.05, 0.15, 1000.0):
        model.dt_max = dt_max
        settings = model.analysis_settings().photon_filter
        settings.filter_active = False  # isolate the macro-time filter
        fractions.append(apply_photon_filters(photons, settings).mean())
    assert fractions[0] < fractions[1] < fractions[2], fractions
    assert fractions[2] > 0.95, "an unbounded interval should keep nearly everything"


def test_the_merge_gap_is_zero_when_gap_filling_is_off(model):  # noqa: F811
    model.use_gap_fill, model.merge_gap = True, 7
    assert model.analysis_settings().photon_filter.max_gap == 7
    model.use_gap_fill = False
    assert model.analysis_settings().photon_filter.max_gap == 0


def test_min_photons_and_window_reach_the_analysis(model):  # noqa: F811
    model.min_photons, model.photon_window = 123, 9
    s = model.analysis_settings()
    assert s.burst_detection.min_photons == 123 and s.burst_detection.photon_window == 9
    assert model.burst_selection_parameters()["photon_threshold"] == 123


def test_cusum_and_kalman_parameters_reach_the_search(model):  # noqa: F811
    """Each search's own parameters (the registry schema) are what the analysis marshals."""
    model.set_algorithm("cusum_sprt")
    model.search.background_cps = "3210"
    model.search.signal_to_background_ratio = "12.5"
    model.search.alpha, model.search.beta = "0.02", "0.03"
    p = model.analysis_settings().photon_filter.tttrlib_search
    assert p.algorithm == "cusum_sprt"
    assert (p.parameters["background_cps"], p.parameters["signal_to_background_ratio"]) == (3210.0, 12.5)
    assert (p.parameters["alpha"], p.parameters["beta"]) == (0.02, 0.03)
    model.set_algorithm("kalman")
    model.search.r_scale, model.search.z_thresh, model.search.min_len = "0.25", "4.5", "6"
    p = model.analysis_settings().photon_filter.tttrlib_search
    assert (p.parameters["r_scale"], p.parameters["z_thresh"], p.parameters["min_len"]) == (0.25, 4.5, 6)


def test_every_search_is_selectable_and_reported(model):  # noqa: F811
    from chisurf.core.fluorescence.burst import tttrlib_search

    for name in tttrlib_search.algorithms():
        model.set_algorithm(name)
        assert model.algorithm == name
        s = model.analysis_settings().photon_filter
        assert s.used_filter.value == "tttrlib" and s.tttrlib_search.algorithm == name
        assert s.tttrlib_search.parameters == model.parameters
        assert model.search_summary() is not None
    assert "bocpd" in dict(model.algorithm_options())
    with_unknown = model.algorithm
    model.set_algorithm("not_an_algorithm")
    assert model.algorithm == with_unknown, "an unknown search is refused, not half selected"


def test_the_selection_state_survives_the_refresh_that_follows_it(model):  # noqa: F811
    """An edit must still be there after the refresh it triggers (the page once rebuilt its settings from stale widgets)."""
    model.invert = False
    model.dt_max = 0.05
    model.use_gap_fill, model.merge_gap = True, 6
    model.settings_changed()
    s = model.analysis_settings().photon_filter
    assert s.invert_filter is False
    assert s.delta_macro_time_filter.dT_max == pytest.approx(0.05)
    assert s.max_gap == 6


def test_all_means_no_selection(model):  # noqa: F811
    """'All' must apply no mask at all, for detector and time window alike."""
    model.detector, model.window = "All", "All"
    s = model.analysis_settings().photon_filter
    assert list(s.channels) == [] and list(s.microtime_ranges) == []
    model.detector = "green"
    assert list(model.analysis_settings().photon_filter.channels) == [0, 1]
    assert model.detector_options()[0] == "All" and model.window_options()[0] == "All"
    # the options follow the detector setup
    model.set_setup(
        {"detectors": {"x": {"chs": [3]}}, "windows": {"w": [0, 10]}, "tttr_reading": {"file_type": "SPC-130"}}
    )
    assert model.detector_options() == ["All", "x"] and model.window_options() == ["All", "w"]
    assert model.detector == "All", "a selection that left the setup falls back to All"


def test_a_search_parameter_changes_the_number_of_bursts(model, photons):  # noqa: F811
    """The end-to-end property that matters: a parameter changes the result."""
    from chisurf.core.fluorescence.burst import tttrlib_search

    model.set_algorithm("maxtree")
    counts = []
    for min_photons in (20, 60, 200):
        model.search.L = str(min_photons)
        counts.append(len(tttrlib_search.search(photons, "maxtree", dict(model.parameters))))
    assert counts[0] > counts[1] > counts[2], counts


def test_bocpd_runs_without_error(photons):
    """BOCPD is backed by the tttrlib C++ engine and runs."""
    from chisurf.plugins.burst.burst_selection.api.models import BurstFilterMode, PhotonFilterSettings
    from chisurf.plugins.burst.burst_selection.api.selection import apply_photon_filters

    mask = apply_photon_filters(photons, PhotonFilterSettings(used_filter=BurstFilterMode.BOCPD))
    assert mask.shape == (len(photons),)


# --- output ---------------------------------------------------------------------------------------------


def test_a_container_source_keeps_the_folder_controls_disabled(model):  # noqa: F811
    """Zipping and removing act on the companion *folder*; a `.pto` keeps its bursts inside itself."""
    model.files = [Path("m000.pto")]
    model.zip_output = model.remove_folder = True
    assert model.output_formats() == ["pto"]
    assert model.enabled("zip_output") is False and model.enabled("remove_folder") is False
    s = model.analysis_settings()
    assert s.zip_output is False and s.remove_folder is False, "no folder, nothing to zip"
    assert "own .pto" in model.output_text()


def test_a_vendor_source_leaves_the_folder_controls_available(model):  # noqa: F811
    """There is a folder to zip when the source cannot hold the results."""
    model.files = [Path("m000.spc")]
    model.zip_output = True
    assert model.output_formats() == ["bur"]
    assert model.enabled("zip_output") is True and model.enabled("remove_folder") is True
    assert model.analysis_settings().zip_output is True
    model.zip_output = False
    assert model.enabled("remove_folder") is False


# --- MMFDB ------------------------------------------------------------------------------------------------


def _database(tmp_path, user):
    from mmfdb.repository import MFDatabase
    from mmfdb.security.auth import create_session

    from chisurf.core.transform.mmfdb import session_from_auth

    db = MFDatabase(tmp_path / "mmfdb.sqlite")
    db.ensure_user(user)
    token = create_session(db.conn, user)["token"]
    db.conn.commit()
    return db, session_from_auth(db, {"token": token})


def test_mmfdb_output_needs_a_sample_and_registers_the_raw_files_to_it(model, tmp_path, monkeypatch):  # noqa: F811
    """MMFDB output binds the raw content to the sample, with the detector setup, and says when there is no sample."""
    from mmfdb.models import SampleDefinition
    from mmfdb.samples.sample_manager import create_sample

    from chisurf.core.fio.setup_store import setup_id_for_name
    from chisurf.plugins.burst.burst_selection.api.mmfdb import sample_id_for_raw_path

    db, session = _database(tmp_path, "gui-context-user")
    sample_id = create_sample(db, SampleDefinition(name="Registered sample"))
    monkeypatch.setattr(model, "_mmfdb_db", lambda: db)
    monkeypatch.setattr(model, "_mmfdb_session", lambda: session)
    raw_paths = sorted(DATA.glob("*.spc"))[:2]
    model.files = list(raw_paths)
    model.mmfdb_output = True

    with pytest.raises(RuntimeError, match="needs a sample"):
        model.mmfdb_context()  # the Qt tool asked in a dialog; here the Sample field says which

    model.sample_id = sample_id
    context = model.mmfdb_context()
    assert context["enabled"] is True and context["sample_id"] == sample_id
    assert set(context["source_artifact_ids"]) == {str(p.resolve()) for p in raw_paths}
    assert context["register_missing_inputs"] is True
    assert context["setup_id"] == setup_id_for_name(
        model.setup_name, session.user_id, "tttr_detector_setup"
    )
    assert db.get_setup(context["setup_id"]) is not None
    assert all(sample_id_for_raw_path(db, p) == sample_id for p in raw_paths)

    # once registered the content knows its sample: no Sample field is needed any more
    model.sample_id = ""
    again = model.mmfdb_context()
    assert again["sample_id"] == sample_id and again["source_artifact_ids"] == context["source_artifact_ids"]


def test_mmfdb_only_output_runs_the_batch_analysis(model, monkeypatch):  # noqa: F811
    """The batch accepts MMFDB as the selected output mode and hands its context to the backend."""
    context = {"enabled": True, "sample_id": "sample_1", "source_artifact_ids": {}}
    calls = []

    class FakeClient:
        def analyze_files(self, file_paths, **kwargs):
            calls.append({"file_paths": file_paths, **kwargs})
            return {
                "dataframes": {str(p): [{"Number of Photons": 12}] for p in file_paths},
                "metadata": {"n_files": len(file_paths), "n_bursts": len(file_paths)},
            }

    monkeypatch.setattr(type(model), "client", property(lambda self: FakeClient()))
    model.mmfdb_output = True
    monkeypatch.setattr(model, "mmfdb_context", lambda: context)
    assert model.prepare_run() is None
    model.run()
    assert calls[0]["file_paths"] == list(model.files)
    assert calls[0]["detectors"] == model.detectors
    assert calls[0]["mmfdb"] == context
    assert calls[0]["legacy_output"] is True


def test_the_batch_reports_per_file_progress(model, monkeypatch):  # noqa: F811
    """The batch must give real per-file progress, not silence (a busy spinner for the whole duration)."""
    seen = []

    class FakeClient:
        def analyze_files(self, file_paths, progress_callback=None, **kwargs):
            for i, path in enumerate(file_paths):
                progress_callback(i + 1, len(file_paths), str(path))
                seen.append(model.status_text)
            return {"dataframes": {}, "metadata": {}}

    monkeypatch.setattr(type(model), "client", property(lambda self: FakeClient()))
    model.run()
    assert seen == ["Searched m000.spc (1/2)", "Searched m001.spc (2/2)"]


# --- previews --------------------------------------------------------------------------------------------


def test_a_preview_searches_nothing(model, monkeypatch):  # noqa: F811
    """Arriving at the step must not run a full burst search (20 M photons take seconds and froze the window).

    The window's own bursts still reach the table, but they come from the diagnostics, not from analysing every
    photon of every file; and a preview never emits an MMFDB context as an output side effect.
    """

    def fail(*_args, **_kwargs):
        raise AssertionError("a preview ran the full search")

    monkeypatch.setattr(model.client, "analyze_files", fail)
    diag = model.load_diagnostics()
    assert diag is not None and model.preview and model.display_frame is not None
    assert model.has_processed is False and model.frames_by_file == {}
    assert "Preview of" in model.status_text and "press Run" in model.status_text


def test_a_preview_still_shows_the_table_it_already_has(model):  # noqa: F811
    model.run()
    table = model.display_frame
    model.load_diagnostics()
    assert model.has_processed and not model.preview
    assert model.display_frame is table, "the searched table is not replaced by the window's preview"


def test_frames_stay_paired_with_their_files(model):  # noqa: F811
    """Selecting another file shows that file's burst table, never the previous one's."""
    model.run()
    first = [r["bursts"] for r in model.file_rows()]
    assert first == ["71", "127"]
    model.select_file(1)
    assert model.active_file.name == "m001.spc"
    assert len(model.burst_rows()) == 127
    model.select_file({"path": str(model.files[0])})
    assert model.active_file.name == "m000.spc" and len(model.burst_rows()) == 71
    model.select_file(99)
    assert model.active_file.name == "m000.spc", "an index outside the list changes nothing"


def test_the_plots_still_draw_when_the_preview_fails(model, monkeypatch):  # noqa: F811
    """A failure in the preview table must not blank the whole window.

    Regression (the Qt tool): one printf-style logging call raised inside the loader's broad ``except``, which
    *cleared the diagnostics*, so a cosmetic step cost every plot. Here the diagnostics are kept before the preview
    is built, so a failing preview leaves the plots their data.
    """

    def boom(_diag):
        raise TypeError("warning() takes 2 positional arguments but 3 were given")

    monkeypatch.setattr(model, "_preview", boom)
    with pytest.raises(TypeError):
        model.load_diagnostics()
    assert model.diagnostic is not None and "tttr" in model.diagnostic
    assert set(model.trace_curves()) == {"all", "selected"}


def test_the_search_refuses_unconverted_alex_data(model, monkeypatch):  # noqa: F811
    """A warning was not enough: by the time it is read, files exist.

    A search whose detectors gate on a micro-time the data does not have writes a burst run -- and a container to hold
    it -- in which every per-detector count is zero. The setup persists between sessions, so arriving here with last
    week's ``ALEX Suite (auto)`` and this week's raw files is ordinary.
    """
    import chisurf.core.fio.staging as staging

    class _Unconverted:
        micro_times = np.zeros(1000, dtype=int)

    model.files = [Path("/data/a.sm")]
    model.detectors = {"green": {"chs": [1], "micro_time_ranges": [[616, 3784]]}}
    monkeypatch.setattr(staging, "open_tttr", lambda *_a, **_k: _Unconverted())
    reason = model.blocked_reason()
    assert reason is not None
    assert "Nothing was written" in reason and "Alternation" in reason
    assert model.prepare_run() == reason, "the run is refused with the same sentence"

    # An ungated setup is not blocked.
    model.detectors = {"green": {"chs": [1]}}
    assert model.blocked_reason() is None


# --- the visible window --------------------------------------------------------------------------------------


def test_the_window_start_runs_over_the_active_file_and_survives_a_reload(model):  # noqa: F811
    """The range the plots draw is the one the controls show, and is not thrown away by an unrelated setting.

    Regression (the Qt form): the re-clamp reset the range to the whole file on every diagnostics reload, which
    happened on every filter change, so a range narrowed by hand was lost the moment any other setting was touched.
    """
    model.load_diagnostics()
    span = model.timeline_span()
    assert span > 10.0
    low, high = model.bounds("window_start_s")
    assert (low, high) == (0.0, pytest.approx(span - model.window_length_s))
    model.window_start_s = 5.0
    model.window_length_s = 3.0
    model.min_photons = 61  # an unrelated setting: the diagnostics reload
    model.load_diagnostics()
    assert (model.window_start_s, model.window_length_s) == (5.0, 3.0)
    diag = model.diagnostic
    macro = np.asarray(diag["tttr"].macro_times) * diag["tttr"].header.macro_time_resolution
    first, last = model._window_indices()
    assert macro[first] == pytest.approx(5.0, abs=0.05)
    assert macro[last - 1] - macro[first] <= 3.05


def test_a_window_longer_than_the_file_is_the_whole_file(model):  # noqa: F811
    model.window_length_s = 10_000.0
    model.load_diagnostics()
    first, last = model._window_indices()
    assert (first, last) == (0, len(model.diagnostic["selected"]))
    assert model.bounds("window_start_s") == (0.0, 0.0)


# --- plot data: count rates, layers, budgets ---------------------------------------------------------------------


class _Trace:
    """A TTTR stand-in that distinguishes the full stream, the window and the selected photons."""

    calls: list[list[int]] = []

    def __init__(self, label: str = "full", n: int = 5) -> None:
        self.label = label
        self.header = _Header(0.001)
        self.macro_times = np.arange(n, dtype=np.int64)

    def __len__(self) -> int:
        return len(self.macro_times)

    def __getitem__(self, indices):
        values = np.asarray(indices, dtype=int).tolist()
        _Trace.calls.append(values)
        return _Trace("range" if values == [1, 2, 3] else "selected", n=len(values))

    def get_intensity_trace(self, time_window_length: float) -> np.ndarray:
        assert time_window_length == 0.00025
        return {"range": np.array([1.0, 2.0, 3.0]), "selected": np.array([10.0])}.get(
            self.label, np.array([99.0])
        )


def _diagnostic(model, tttr, selected):
    model.diagnostic = {
        "tttr": tttr,
        "selected": np.asarray(selected, dtype=bool),
        "start_stop": np.array([[0, 1]]),
        "path": Path("x.spc"),
    }


def test_the_count_rate_trace_draws_all_before_selected_and_respects_the_toggles(model, monkeypatch):  # noqa: F811
    """The selected trace is last (drawn on top) and a disabled trace is not even computed."""
    _Trace.calls.clear()
    _diagnostic(model, _Trace(), [False, False, True, False, True])
    model.window_length_s = 0.0
    model.trace_bin_ms = 0.25
    # the window is fixed to photons 1..3 by a stand-in client
    window = type("Client", (), {"_window_indices": staticmethod(lambda *a, **k: (1, 4))})()
    monkeypatch.setattr(type(model), "client", property(lambda self: window))
    curves = model.trace_curves()
    assert list(curves) == ["all", "selected"]
    assert curves["all"][1].tolist() == [4000.0, 8000.0, 12000.0]
    assert curves["selected"][1].tolist() == [40000.0]
    assert _Trace.calls == [[1, 2, 3], [2]]
    model.show_all_photons = False
    _Trace.calls.clear()
    curves = model.trace_curves()
    assert list(curves) == ["selected"] and curves["selected"][1].tolist() == [40000.0]
    assert _Trace.calls == [[2]]


def test_the_dt_curves_are_thinned_for_a_large_measurement(model, monkeypatch):  # noqa: F811
    """A merged multi-file .pto can hand the plots millions of photons at once.

    Regression: every visible photon was handed straight to the plot; laying out and repainting millions of points was
    the reported lag. The decimation keeps each bin's minimum and maximum, so a burst survives the thinning.
    """
    import chisurf.plugins.burst.burst_selection.gui.model as module

    n = 2_000_000
    tttr = _Trace(n=n)
    tttr.macro_times = np.arange(n, dtype=np.int64)
    tttr.macro_times[1_000_000:1_000_050] += np.arange(50) * 0  # a stretch of equal times: a dense burst
    _diagnostic(model, tttr, np.ones(n, dtype=bool))
    model.window_length_s = 0.0
    budget = 10_000
    monkeypatch.setattr(module, "MAX_PLOT_POINTS", budget)
    curves = model.dt_curves()
    assert set(curves) == {"all", "selected"}
    for _label, (x, y) in curves.items():
        assert len(x) == len(y) <= 2 * budget and len(x) < n
    # the extremes survive: the largest inter-photon time of the full stream is on the thinned curve
    full = np.diff(tttr.macro_times, prepend=tttr.macro_times[0]) * 0.001 * 1000.0
    assert curves["all"][1].max() == pytest.approx(full.max())


def test_the_decay_curves_compute_only_the_enabled_layers(model):  # noqa: F811
    """Decay plotting computes only the enabled photon layers (a histogram per layer is not free)."""
    calls = []

    class _Decay:
        def __init__(self, label="all"):
            self.label = label
            self.header = _Header()
            self.macro_times = np.arange(3)

        def __getitem__(self, _indices):
            return _Decay("selected")

        def get_microtime_histogram(self, coarse):
            assert coarse == 2
            calls.append(self.label)
            return np.array([1.0, 0.0]), np.array([1.0, 2.0])

    _diagnostic(model, _Decay(), [True, False, True])
    model.decay_bins = 2
    model.show_all_photons, model.show_selected_photons = False, True
    assert set(model.decay_curves()) == {"selected"} and calls == ["selected"]
    calls.clear()
    model.show_all_photons, model.show_selected_photons = True, False
    assert set(model.decay_curves()) == {"all"} and calls == ["all"]
    # the trailing empty bins are cut, and the axis is in ns
    x, y = model.decay_curves()["all"]
    assert y.tolist() == [1.0] and x.tolist() == [1.0e9]


def test_the_burst_durations_histogram_is_in_milliseconds(model):  # noqa: F811
    tttr = _Trace(n=4)
    tttr.header = _Header(0.002)
    tttr.macro_times = np.array([0, 5, 8, 20])
    model.diagnostic = {"tttr": tttr, "start_stop": np.array([[0, 1], [1, 3]]), "selected": np.ones(4, bool)}
    model.burst_bins = 3
    centres, counts, width = model.duration_histogram()
    assert counts.sum() == 2 and 10.0 <= centres.min() and centres.max() <= 30.0
    assert width == pytest.approx(20.0 / 3)


def test_the_feature_list_survives_a_refresh_with_the_same_columns(model):  # noqa: F811
    """Re-reading a table with the same column count must not compare Column objects.

    Regression: `list(frame.columns)` returns `Column` objects; comparing it with the previous list raised "truth
    value of an array is ambiguous" the moment both had the same length -- on the *second* selection of a file with
    the same feature set.
    """
    from chisurf.core.datastore import store_from_arrays

    def frame(n):
        return store_from_arrays(
            {
                "Number of Photons": np.arange(n, dtype=np.int32),
                "Proximity Ratio": np.linspace(0.2, 0.3, n),
            }
        )

    model.display_frame = frame(2)
    first = model.feature_options()
    model.display_frame = frame(1)
    assert model.feature_options() == first == ["Number of Photons", "Proximity Ratio"]


# --- the GMM settings -----------------------------------------------------------------------------------------


def test_the_gmm_settings_reach_the_estimator(model):  # noqa: F811
    """The advanced settings update and ``_gmm`` honours them (the Qt dialog's only job)."""
    from chisurf.plugins.burst.burst_selection.gui.model import DEFAULT_GMM_SETTINGS

    assert model.gmm_settings == dict(DEFAULT_GMM_SETTINGS)
    assert set(DEFAULT_GMM_SETTINGS) == {
        "covariance_type", "random_state", "max_iter", "n_init", "tol", "max_components", "reg_covar",
    }
    model.gmm.covariance_type = "diag"
    model.gmm.max_iter = "123"
    model.gmm.random_state = 7
    assert model.gmm_settings["covariance_type"] == "diag" and model.gmm_settings["max_iter"] == 123
    estimator = model._gmm(2)
    assert estimator.covariance_type == "diag" and estimator.max_iter == 123 and estimator.random_state == 7
    with pytest.raises(AttributeError):
        model.gmm.not_a_setting = 1
    # a round trip through the settings file is loss-less
    other = type(model)()
    other.import_settings(model.export_settings())
    assert other.gmm_settings == model.gmm_settings


# --- construction -----------------------------------------------------------------------------------------


def test_constructing_the_model_and_the_app_opens_no_mmfdb_connection(hermetic, monkeypatch):  # noqa: F811
    """No MMFDB connection was opened on construction (a read-only init), and the app keeps its model."""
    import chisurf.plugins.burst.burst_selection.api.mmfdb as mmfdb_api
    from chisurf.plugins.burst.burst_selection.gui.native import create_app

    def refuse(*_args, **_kwargs):
        raise AssertionError("an MMFDB connection was opened on construction")

    monkeypatch.setattr(mmfdb_api, "acquire_mmfdb_connection", refuse)
    app = create_app()
    try:
        assert app.model.files == [] and app.model.mmfdb_output is False
    finally:
        app.close()


# --- pooling the files ---------------------------------------------------------------------------------------


def test_pooling_the_files_stacks_every_files_bursts_for_the_histogram_and_the_table(model):  # noqa: F811
    """Fitting the histogram of a whole measurement needs the bursts of all its files together.

    The Qt tool stacked the tables of all selected files (guides 29 and 35 pool ten repeats); the emtk app shows the
    active file unless "Pool all files" is on. The diagnostic plots stay on the active file either way.
    """
    from chisurf.core.datastore import numeric_column

    model.run()
    assert model.pool_files is False
    assert len(model.burst_rows()) == 71 and model.histogram() is not None
    model.hist_feature, model.hist_bins, model.hist_min, model.hist_max = "Proximity Ratio", 61, 0.0, 1.0
    single = model.histogram()[1].sum()
    model.pool_files = True
    assert len(model.burst_rows()) == 198
    assert numeric_column(model.display_frame, "File Idx").tolist().count(1) == 127
    assert model.histogram()[1].sum() == 198 > single
    model.gmm_components = 2
    assert model.fit_gmm()["n"] == 2
    # the pool follows the active file's selection only for the diagnostics
    model.select_file(1)
    assert len(model.burst_rows()) == 198 and model.active_file.name == "m001.spc"
    # and it survives a round trip of the settings
    other = type(model)()
    other.import_settings(model.export_settings())
    assert other.pool_files is True
    model.pool_files = False
    assert len(model.burst_rows()) == 127


def test_the_summary_reports_the_mean_photons_per_burst_in_each_detector(model):  # noqa: F811
    """The Qt info box listed ``Mean ph (green)`` and ``Mean ph (red)`` beside the overall means."""
    model.run()
    rows = {r["key"]: r["value"] for r in model.summary_rows()}
    assert {"Mean photons", "Mean duration (ms)", "Mean photons (green)", "Mean photons (red)"} <= set(rows)
    frame = model.display_frame
    from chisurf.core.datastore import numeric_column

    green = numeric_column(frame, "Number of Photons (green)")
    nonzero = green[np.isfinite(green) & (numeric_column(frame, "Number of Photons") > 0)]
    assert float(rows["Mean photons (green)"]) == pytest.approx(float(nonzero.mean()), rel=1e-3)
