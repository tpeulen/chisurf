"""Tests for the Burst Selection API adapters."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from chisurf.core.datastore import column_names, numeric_column, row_count
from chisurf.core.fio.fluorescence.burst import generate_burst_dataframe
from chisurf.plugins.burst.burst_selection.api import selection as selection_module
from chisurf.plugins.burst.burst_selection.api.contract import (
    METHOD_ANALYZE_FILES,
    analysis_request_from_payload,
    analysis_request_to_payload,
    analysis_result_to_payload,
    contract_descriptor,
)
from chisurf.plugins.burst.burst_selection.api.features import extract_features, fit_gmm
from chisurf.plugins.burst.burst_selection.api.io import load_tttr
from chisurf.plugins.burst.burst_selection.api.models import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisSettings,
    BurstDetectionSettings,
    BurstFilterMode,
    CountRateFilterSettings,
    DeltaMacroTimeFilterSettings,
    GMMSettings,
    MMFDBContext,
    PhotonFilterSettings,
)
from chisurf.plugins.burst.burst_selection.api.selection import (
    analyze_file,
    analyze_request,
    apply_photon_filters,
    find_bursts,
    legacy_output_folder_name,
    summarize_bursts,
)
from chisurf.plugins.burst.burst_selection.api.serialization import settings_from_dict, to_jsonable
from chisurf.plugins.burst.burst_selection.gui.adapter import (
    burst_rows_for_display,
    make_ui_dataframe,
)

DATA_DIR = Path(__file__).resolve().parent / "data" / "bh_spc132_sm_dna"
BH_SPC_FILE = DATA_DIR / "m000.spc"
STREAM_CHANNELS = [0, 1, 8, 9]


def real_data_settings() -> AnalysisSettings:
    """Return deterministic settings for the bundled BH SPC example.

    Asks for ``"bur"`` explicitly. The default is ``["pto"]`` — the
    measurement's own container — and these tests read the *legacy* companion,
    so they have to say they need one written.
    """
    settings = AnalysisSettings()
    settings.output_formats = ["pto", "bur"]
    settings.photon_filter = PhotonFilterSettings(
        channels=STREAM_CHANNELS,
        filter_active=False,
        delta_macro_time_filter=DeltaMacroTimeFilterSettings(
            dT_min=0.0,
            dT_min_active=False,
            dT_max_active=False,
        ),
    )
    settings.burst_detection = BurstDetectionSettings(
        min_photons=20,
        photon_window=10,
        time_window=1e-3,
    )
    return settings


def assert_tables_equal(left, right):
    """Compare two column-addressable tables, column for column.

    The replacement for ``assert_frame_equal`` now that the burst layer produces
    stores. It checks the same things that mattered here -- the column names in
    order, the row count, and every value -- and nothing that did not (an index a
    store does not have).
    """
    assert column_names(left) == column_names(right)
    assert row_count(left) == row_count(right)
    for name in column_names(left):
        a, b = np.asarray(left[name]), np.asarray(right[name])
        if a.dtype.kind in "fiu" and b.dtype.kind in "fiu":
            np.testing.assert_allclose(
                a.astype(float), b.astype(float), equal_nan=True, err_msg=name
            )
        else:
            assert list(a) == list(b), name


def test_contract_descriptor_defines_workflow_io() -> None:
    """The public contract should define canonical analysis input and output."""
    contract = contract_descriptor()
    assert contract["plugin_id"] == "burst_selection"
    assert contract["contract_version"]
    assert contract["inputs"]["AnalyzeFiles"]["required"] == ["files"]
    assert contract["outputs"]["AnalysisResult"]["required"] == [
        "files",
        "dataframes",
        "output_paths",
        "metadata",
    ]
    assert "mmfdb" in contract["inputs"]["AnalyzeFiles"]["properties"]
    assert "output_paths_by_file" in contract["outputs"]["AnalysisResult"]["properties"]
    assert "mmfdb_artifacts" in contract["outputs"]["AnalysisResult"]["properties"]
    assert contract["rpc_methods"][METHOD_ANALYZE_FILES]["input"] == "AnalyzeFiles"


def test_analysis_request_payload_roundtrip_normalizes_json_inputs() -> None:
    """Workflow payloads should normalize to dataclasses and back to JSON."""
    request = analysis_request_from_payload(
        {
            "files": ["m000.spc"],
            "windows": {"prompt": [0, 2048]},
            "settings": {
                "photon_filter": {
                    "channels": [0, 1],
                    "microtime_ranges": None,
                    "used_filter": "burst",
                },
                "output_formats": ["bur", "hdf5"],
            },
            "legacy_output": True,
            "selected_setup": "Test",
        }
    )

    assert request.files == ["m000.spc"]
    assert request.windows == {"prompt": (0, 2048)}
    assert request.settings.photon_filter.microtime_ranges == []
    assert request.settings.photon_filter.used_filter == BurstFilterMode.BURST
    assert request.settings.output_formats == ["bur", "hdf5"]
    assert request.legacy_output is True
    assert request.selected_setup == "Test"

    payload = analysis_request_to_payload(request)
    assert payload["windows"] == {"prompt": [0, 2048]}
    assert payload["settings"]["photon_filter"]["used_filter"] == "burst"
    assert payload["mmfdb"]["enabled"] is False


def test_analysis_request_accepts_nested_mmfdb_context() -> None:
    """Workflow payloads should accept nested MMFDB archival context."""
    request = analysis_request_from_payload(
        {
            "files": ["m000.spc"],
            "mmfdb": {
                "enabled": False,
                "sample_id": "sample_1",
                "source_artifact_ids": {"m000.spc": "artifact_1"},
                "register_missing_inputs": False,
                "setup_id": "tttr_detector_setup:bh_spc_130",
                "setup_version": 1,
            },
        }
    )

    assert isinstance(request.mmfdb, MMFDBContext)
    assert request.mmfdb.enabled is False
    assert request.mmfdb.sample_id == "sample_1"
    assert request.mmfdb.source_artifact_ids == {"m000.spc": "artifact_1"}
    assert request.mmfdb.register_missing_inputs is False
    assert request.mmfdb.setup_id == "tttr_detector_setup:bh_spc_130"
    assert request.mmfdb.setup_version == 1


def test_analysis_result_payload_is_json_safe() -> None:
    """Analysis results should serialize through the workflow output helper."""
    payload = analysis_result_to_payload(
        AnalysisResult(
            files=[str(BH_SPC_FILE)],
            dataframes={str(BH_SPC_FILE): [{"First Photon": 0}]},
            output_paths={"bur": str(BH_SPC_FILE.with_suffix(".bur"))},
            metadata={"n_photons": 1},
            mmfdb_artifacts={"burst_table_artifacts": {str(BH_SPC_FILE): "artifact_1"}},
            warnings=["mmfdb unavailable"],
        )
    )

    assert payload["files"] == [str(BH_SPC_FILE)]
    assert payload["dataframes"][str(BH_SPC_FILE)][0]["First Photon"] == 0
    assert payload["output_paths"]["bur"].endswith(".bur")
    assert payload["mmfdb_artifacts"]["burst_table_artifacts"][str(BH_SPC_FILE)] == "artifact_1"
    assert payload["warnings"] == ["mmfdb unavailable"]


def test_find_bursts_bridges_configured_gap() -> None:
    """Burst finding should bridge small gaps in the selection mask."""
    mask = np.array([1, 1, 0, 0, 0, 1, 1, 0, 1], dtype=np.uint8)
    bursts = find_bursts(mask, max_gap=2)
    assert bursts.tolist() == [[0, 8]]


def test_apply_photon_filters_without_filter_uses_tttr_length() -> None:
    """Disabled filtering should return a selection mask with the TTTR length."""
    tttr = load_tttr(BH_SPC_FILE)
    settings = real_data_settings()
    selected = apply_photon_filters(tttr, settings.photon_filter)
    assert selected.shape == (len(tttr),)
    assert np.all(selected == 1)


def test_delta_macro_time_prefilters_the_burst_search() -> None:
    """The min/max dMT interval must change burst selection, not be a no-op.

    Regression: the interval used to be AND-ed onto the burst-search result
    *after* the search, so for real data the burst photons already satisfied it
    and it had no effect. It is now a photon-stream pre-filter applied (via
    tttrlib) to the stream the search sees, so widening/narrowing ``dT_max``
    genuinely moves the selection.
    """
    tttr = load_tttr(BH_SPC_FILE)

    def fraction(dt_max: float, active: bool) -> float:
        settings = PhotonFilterSettings(
            channels=[],
            filter_active=True,
            used_filter=BurstFilterMode.COUNT_RATE,
            count_rate_filter=CountRateFilterSettings(n_ph_max=5, time_window=0.005),
            delta_macro_time_filter=DeltaMacroTimeFilterSettings(
                dT_min=1e-4, dT_max=dt_max, dT_min_active=False, dT_max_active=active
            ),
            use_gap_fill=False,
        )
        selected = apply_photon_filters(tttr, settings, BurstDetectionSettings(min_photons=20))
        return float(selected.mean())

    off = fraction(0.15, active=False)
    tight = fraction(0.02, active=True)
    loose = fraction(0.15, active=True)

    # The interval is active -> the selection differs from the unfiltered search,
    # and a tighter interval selects a different (here smaller) fraction than a
    # looser one. The point is that the bound *matters*.
    assert tight != pytest.approx(off, abs=1e-4)
    assert loose != pytest.approx(off, abs=1e-4)
    assert tight != pytest.approx(loose, abs=1e-4)


def test_delta_macro_time_prefilter_keeps_bursts_in_original_index_space() -> None:
    """Bursts are found over the original photons, so spans still cover in-burst gaps.

    "Exclude from search only": a photon the interval removes cannot seed/extend a
    burst, but a detected burst's [start, stop] still spans it, so its selection
    mask indexes the original stream (length == n photons), not the reduced one.
    """
    tttr = load_tttr(BH_SPC_FILE)
    settings = PhotonFilterSettings(
        channels=[],
        filter_active=True,
        used_filter=BurstFilterMode.COUNT_RATE,
        count_rate_filter=CountRateFilterSettings(n_ph_max=5, time_window=0.005),
        delta_macro_time_filter=DeltaMacroTimeFilterSettings(
            dT_min=1e-4, dT_max=0.05, dT_min_active=False, dT_max_active=True
        ),
        use_gap_fill=False,
    )
    selected = apply_photon_filters(tttr, settings, BurstDetectionSettings(min_photons=20))
    assert selected.shape == (len(tttr),)
    assert selected.any()


def test_analyze_file_writes_bur(tmp_path: Path) -> None:
    """API analysis should produce a ChiSurf-compatible .bur file from real data."""
    settings = real_data_settings()
    result = analyze_file(BH_SPC_FILE, settings=settings, output_dir=tmp_path)
    bur_path = tmp_path / "m000.bur"
    assert bur_path.exists()
    assert set(result.output_paths) == {"bur"}
    df = pd.read_csv(bur_path, sep="\t")
    assert len(df) == len(result.dataframes[str(BH_SPC_FILE)])
    assert "First Photon" in df.columns
    assert (pd.to_numeric(df["Number of Photons"], errors="coerce").fillna(0) == 0).any()
    assert len(make_ui_dataframe(df)) < len(df)


def test_legacy_folder_name_reflects_the_filter_mode() -> None:
    """The legacy output folder is prefixed by the search that produced it.

    A registry-driven search names the folder after the algorithm itself, so a
    maxtree run and a sliding-window run of the same data do not collide, while
    the built-in modes keep their historical prefixes.
    """
    settings = AnalysisSettings()
    settings.photon_filter.channels = []

    settings.photon_filter.used_filter = BurstFilterMode.CUSUM
    assert legacy_output_folder_name(settings).startswith("cusum_")

    settings.photon_filter.used_filter = BurstFilterMode.TTTRLIB
    settings.photon_filter.tttrlib_search.algorithm = "sliding_window"
    assert legacy_output_folder_name(settings).startswith("sliding_window_")

    settings.photon_filter.used_filter = BurstFilterMode.BURST
    assert legacy_output_folder_name(settings).startswith("burstwise_")


def test_analyze_request_writes_legacy_burstwise_output(tmp_path: Path) -> None:
    """API legacy-output mode should own the old burstwise folder layout."""
    source = tmp_path / BH_SPC_FILE.name
    source.write_bytes(BH_SPC_FILE.read_bytes())
    settings = real_data_settings()
    settings.photon_filter.channels = []
    settings.output_formats = ["bur"]
    settings.photon_filter.delta_macro_time_filter.dT_max = 0.2
    settings.burst_detection.min_photons = 60

    result = analyze_request(
        AnalysisRequest(
            files=[str(source)],
            settings=settings,
            legacy_output=True,
            selected_setup="Test",
        )
    )

    output_folder = tmp_path / legacy_output_folder_name(settings)
    bur_path = output_folder / "bi4_bur" / f"{source.stem}.bur"
    info_dir = output_folder / "Info"
    mti_files = list(info_dir.glob("*.mti"))

    assert output_folder.is_dir()
    assert bur_path.exists()
    assert (info_dir / "photon_selection_parameters.json").exists()
    assert (info_dir / "datetime.txt").exists()
    assert len(mti_files) == 1
    assert str(source) in mti_files[0].read_text()
    assert result.output_paths["output_folder"] == str(output_folder)
    assert result.metadata["output_folder"] == str(output_folder)


def test_analyze_request_reuses_first_macro_time_resolution(monkeypatch) -> None:
    """Batch output summaries should reuse the first file's macro-time resolution."""
    calls: list[float | None] = []

    def fake_analyze_file(path: str, **kwargs: object):
        calls.append(kwargs.get("macro_time_resolution"))
        return selection_module.AnalysisResult(
            files=[path],
            dataframes={path: []},
            metadata={
                "n_photons": 1,
                "n_selected": 1,
                "n_bursts": 0,
                "macro_time_resolution": 0.001,
            },
        )

    monkeypatch.setattr(selection_module, "analyze_file", fake_analyze_file)

    selection_module.analyze_request(
        AnalysisRequest(
            files=["first.spc", "second.spc"],
            settings=AnalysisSettings(output_formats=[]),
        )
    )

    assert calls == [None, 0.001]


def test_analyze_request_reports_progress_per_file(monkeypatch) -> None:
    """One file is the chunk: progress must advance between files, not just at the end.

    Regression: a multi-file batch went through the GUI as a single opaque
    backend call with an indeterminate spinner. One file finishing is exactly
    the granularity a caller (the GUI's TaskHandle) can turn into a real,
    advancing progress bar.
    """

    def fake_analyze_file(path: str, **kwargs: object):
        return selection_module.AnalysisResult(
            files=[path],
            dataframes={path: []},
            metadata={"n_photons": 1, "n_selected": 1, "n_bursts": 0},
        )

    monkeypatch.setattr(selection_module, "analyze_file", fake_analyze_file)

    progress_calls: list[tuple[int, int, str]] = []
    selection_module.analyze_request(
        AnalysisRequest(
            files=["first.spc", "second.spc", "third.spc"],
            settings=AnalysisSettings(output_formats=[]),
        ),
        progress_callback=lambda done, total, path: progress_calls.append((done, total, path)),
    )

    assert progress_calls == [
        (1, 3, "first.spc"),
        (2, 3, "second.spc"),
        (3, 3, "third.spc"),
    ]


def test_analyze_request_with_no_progress_callback_is_unchanged(monkeypatch) -> None:
    """The default (no callback) must behave exactly as before."""

    def fake_analyze_file(path: str, **kwargs: object):
        return selection_module.AnalysisResult(
            files=[path],
            dataframes={path: []},
            metadata={},
        )

    monkeypatch.setattr(selection_module, "analyze_file", fake_analyze_file)

    result = selection_module.analyze_request(
        AnalysisRequest(files=["only.spc"], settings=AnalysisSettings(output_formats=[]))
    )

    assert result.files == ["only.spc"]


def test_analyze_file_duration_uses_macro_time_resolution_override() -> None:
    """Output burst durations should use the supplied macro-time resolution."""
    settings = real_data_settings()
    tttr = load_tttr(BH_SPC_FILE)
    native_resolution = float(tttr.header.macro_time_resolution)

    native = analyze_file(BH_SPC_FILE, settings=settings)
    overridden = analyze_file(
        BH_SPC_FILE,
        settings=settings,
        macro_time_resolution=native_resolution * 2.0,
    )

    native_df = make_ui_dataframe(pd.DataFrame(native.dataframes[str(BH_SPC_FILE)]))
    overridden_df = make_ui_dataframe(pd.DataFrame(overridden.dataframes[str(BH_SPC_FILE)]))
    assert (
        numeric_column(overridden_df, "Duration (ms)")[0]
        == numeric_column(native_df, "Duration (ms)")[0] * 2.0
    )


def test_summarize_bursts_matches_core_helper() -> None:
    """API burst summary output should match the existing core helper on real data."""
    tttr = load_tttr(BH_SPC_FILE)
    settings = real_data_settings()
    selected = apply_photon_filters(tttr, settings.photon_filter)
    start_stop = find_bursts(selected)
    api_df = summarize_bursts(start_stop, BH_SPC_FILE, tttr)
    core_df = generate_burst_dataframe(
        start_stop=start_stop,
        filename=BH_SPC_FILE,
        tttr=tttr,
        windows={},
        detectors={},
        include_interleaved_zeros=True,
    )
    assert_tables_equal(api_df, core_df)


def test_burst_dataframe_has_confidence_column() -> None:
    """Each burst carries a per-burst detection confidence, in sigma.

    tttrlib computes the significance of the burst's photon excess over the
    local background from the boundaries alone, so the number is comparable
    across searches. The column is always present (left at 0 on a tttrlib too
    old to provide it) so the .bur layout does not depend on the tttrlib build.
    """
    from chisurf.core.fluorescence.burst import tttrlib_search

    tttr = load_tttr(BH_SPC_FILE)
    # A real burst search over the trace yields many bursts to score, unlike the
    # unfiltered whole-trace selection.
    start_stop = find_bursts(tttrlib_search.tttrlib_burst_filter(tttr, "maxtree"))
    assert len(start_stop) > 1, "fixture must produce bursts to score"

    df = generate_burst_dataframe(
        start_stop=start_stop,
        filename=BH_SPC_FILE,
        tttr=tttr,
        windows={},
        detectors={},
        include_interleaved_zeros=False,
    )

    assert "Confidence (sigma)" in column_names(df)
    # Position is fixed relative to the other static columns.
    cols = column_names(df)
    assert cols.index("Confidence (sigma)") == cols.index("Count Rate (KHz)") + 1

    confidence = numeric_column(df, "Confidence (sigma)")
    assert np.isfinite(confidence).all()
    if hasattr(tttr, "burst_confidence"):
        # A real detection over background scores above zero for at least one burst.
        assert (confidence > 0).any()


def test_burst_dataframe_confidence_matches_tttrlib_per_burst() -> None:
    """The column carries tttrlib's own per-burst score, aligned to each burst.

    The scores are indexed by burst position, so each written row must hold the
    confidence of *its* burst. find_bursts yields only valid bursts (none are
    skipped), so the whole column equals ``burst_confidence`` computed directly.
    """
    from chisurf.core.fluorescence.burst import tttrlib_search

    tttr = load_tttr(BH_SPC_FILE)
    if not hasattr(tttr, "burst_confidence"):
        pytest.skip("installed tttrlib does not compute burst confidence")

    start_stop = find_bursts(tttrlib_search.tttrlib_burst_filter(tttr, "maxtree"))
    assert len(start_stop) >= 2

    df = generate_burst_dataframe(
        start_stop=start_stop,
        filename=BH_SPC_FILE,
        tttr=tttr,
        windows={},
        detectors={},
        include_interleaved_zeros=False,
    )

    flat = [int(v) for pair in start_stop for v in pair[:2]]
    expected = np.asarray(tttr.burst_confidence(flat), dtype=float)
    np.testing.assert_allclose(numeric_column(df, "Confidence (sigma)"), expected)


def test_make_ui_dataframe_adds_proximity_ratio() -> None:
    """GUI adapter should create the columns used by the histogram UI."""
    df = pd.DataFrame(
        {
            "First Photon": [0],
            "Last Photon": [2],
            "Duration (ms)": [1.0],
            "Number of Photons (red)": [2],
            "Number of Photons (green)": [2],
        }
    )
    ui_df = make_ui_dataframe(df)
    assert numeric_column(ui_df, "Proximity Ratio")[0] == 0.5


def test_make_ui_dataframe_ignores_margarita_zero_rows() -> None:
    """GUI table data should hide interleaved zero separator rows."""
    df = pd.DataFrame(
        {
            "First Photon": [0, 10, 0, 30],
            "Last Photon": [0, 19, 0, 39],
            "Duration (ms)": [0.0, 1.0, 0.0, 1.5],
            "Mean Macro Time (ms)": [0.0, 12.0, 0.0, 35.0],
            "Number of Photons": [0, 10, 0, 20],
            "Count Rate (KHz)": [0.0, 10.0, 0.0, 13.3],
            "Number of Photons (red)": [0, 4, 0, 8],
            "Number of Photons (green)": [0, 6, 0, 12],
        }
    )

    visible = burst_rows_for_display(df)
    ui_df = make_ui_dataframe(df)

    assert len(df) == 4
    assert numeric_column(visible, "Number of Photons").tolist() == [10, 20]
    assert numeric_column(ui_df, "Number of Photons").tolist() == [10, 20]
    assert numeric_column(ui_df, "Proximity Ratio").tolist() == [0.4, 0.4]


def test_extract_features_supports_chisurf_bur_columns() -> None:
    """Feature extraction should support core .bur display column names."""
    df = pd.DataFrame(
        {
            "Number of Photons": [10, 20],
            "Duration (ms)": [1.0, 2.0],
            "Proximity Ratio": [0.25, 0.75],
        }
    )
    features = extract_features([df])
    assert numeric_column(features, "nphotons")[0] == 10
    assert numeric_column(features, "fret")[1] == 0.75


def test_extract_features_derives_proximity_ratio_from_green_red() -> None:
    """When there is no explicit Proximity Ratio column, the proximity ratio is
    derived from green/red photon counts (PR = red / (red + green)), not 0.
    """
    df = pd.DataFrame(
        {
            "Number of Photons": [10, 20, 0],
            "Duration (ms)": [1.0, 2.0, 0.0],
            "Number of Photons (red)": [2, 10, 0],
            "Number of Photons (green)": [8, 10, 0],
        }
    )
    features = extract_features([df])
    fret = numeric_column(features, "fret")
    assert fret[0] == 0.2
    assert fret[1] == 0.5
    # a burst with no green+red signal is NaN (excluded), not collapsed to 0
    assert np.isnan(fret[2])


def test_extract_features_and_fit_gmm() -> None:
    """Feature extraction and GMM fitting should work on burst tables."""
    df = pd.DataFrame(
        {
            "nphotons": [10, 20, 30, 40],
            "duration": [1.0, 2.0, 3.0, 4.0],
            "fret": [0.1, 0.2, 0.8, 0.9],
        }
    )
    features = extract_features([df])
    assert column_names(features) == ["nphotons", "duration", "brightness", "interphoton", "fret"]
    fit = fit_gmm(features, GMMSettings(covariance_type="spherical"))
    assert fit["n_components"] == 1
    assert fit["labels"] == [0, 0, 0, 0]


def test_settings_roundtrip() -> None:
    """Analysis settings should serialize to JSON-compatible data and deserialize."""
    settings = AnalysisSettings()
    settings.burst_detection.min_photons = 42
    payload = to_jsonable(settings)
    restored = settings_from_dict(payload)
    assert restored.burst_detection.min_photons == 42


def test_settings_from_dict_accepts_unset_microtime_ranges() -> None:
    """Unset microtime ranges from GUI controls should deserialize as no range filter."""
    payload = {
        "photon_filter": {
            "channels": [],
            "microtime_ranges": None,
            "filter_active": True,
            "used_filter": BurstFilterMode.BURST,
            "count_rate_filter": {
                "n_ph_max": 60,
                "time_window": 0.06,
                "invert": False,
            },
            "delta_macro_time_filter": {
                "dT_min": 0.003617366409160019,
                "dT_max": 0.7234732818320043,
                "dT_min_active": False,
                "dT_max_active": True,
            },
            "invert_filter": False,
            "max_gap": 0,
            "use_gap_fill": False,
        },
        "burst_detection": {
            "min_photons": 60,
            "photon_window": 5,
            "time_window": 0.06,
        },
    }

    restored = settings_from_dict(payload)

    assert restored.photon_filter.microtime_ranges == []
    assert restored.photon_filter.used_filter == BurstFilterMode.BURST
    assert restored.burst_detection.photon_window == 5


def test_photon_filter_settings_normalizes_unset_microtime_ranges() -> None:
    """Direct GUI settings construction should treat unset microtime ranges as all photons."""
    settings = PhotonFilterSettings(
        channels=None,
        microtime_ranges=None,
    )

    assert settings.channels == []
    assert settings.microtime_ranges == []
