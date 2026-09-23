"""Tests for the migrated PyQt Burst Selection GUI defaults."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from mmfdb.models import SampleDefinition
from mmfdb.repository import MFDatabase
from mmfdb.samples.sample_manager import create_sample

from chisurf.core.datastore import column_names, numeric_column
from chisurf.core.runtime import analysis_cache
from chisurf.gui.widgets.dock_area.dock_area import DockArea
from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups import (
    setup_id_for_name,
)
from chisurf.plugins.burst.burst_selection import USE_LEGACY_GUI
from chisurf.plugins.burst.burst_selection.api.models import BurstFilterMode
from chisurf.plugins.burst.burst_selection.gui import tool as tool_module
from chisurf.plugins.burst.burst_selection.gui.client import BurstSelectionClient
from chisurf.plugins.burst.burst_selection.gui.tool import (
    DEFAULT_CHANNELS,
    DEFAULT_D_T_MAX,
    DEFAULT_D_T_MIN,
    DEFAULT_MAX_GAP,
    DEFAULT_MIN_PHOTONS,
    DEFAULT_PHOTON_WINDOW,
    DEFAULT_TIME_WINDOW_MS,
    BurstSelectionTool,
    _raw_artifact_id_for_path,
    _register_raw_input_for_sample,
    _sample_id_for_raw_path,
    default_analysis_settings,
    histogram_data_from_frame,
    make_ui_dataframe,
)


def _bh_spc130_files() -> list[Path]:
    """Return the real BH SPC-130 fixture set used for MMFDB preflight tests."""
    fixture_dir = Path(__file__).resolve().parent / "data" / "bh_spc132_sm_dna"
    return sorted(fixture_dir.glob("*.spc"))


def _bh_spc130_detectors() -> dict[str, dict[str, list[int]]]:
    """Return the BH SPC-130 donor/acceptor detector channel grouping."""
    return {"green": {"chs": [0, 8]}, "red": {"chs": [1, 9]}}


def test_migrated_gui_defaults_use_legacy_thresholding() -> None:
    """The migrated GUI defaults should match the legacy Burst Selection controls."""
    settings = default_analysis_settings()
    assert DEFAULT_CHANNELS == [0, 1, 8, 9]
    assert settings.photon_filter.channels == DEFAULT_CHANNELS
    assert settings.photon_filter.filter_active is True
    assert settings.photon_filter.used_filter == BurstFilterMode.BURST
    assert settings.photon_filter.invert_filter is True
    assert settings.photon_filter.delta_macro_time_filter.dT_min == DEFAULT_D_T_MIN
    assert settings.photon_filter.delta_macro_time_filter.dT_max == DEFAULT_D_T_MAX
    assert settings.photon_filter.delta_macro_time_filter.dT_min_active is False
    assert settings.photon_filter.delta_macro_time_filter.dT_max_active is True
    assert settings.photon_filter.max_gap == DEFAULT_MAX_GAP
    assert settings.photon_filter.use_gap_fill is False
    assert settings.burst_detection.min_photons == DEFAULT_MIN_PHOTONS
    assert settings.burst_detection.photon_window == DEFAULT_PHOTON_WINDOW
    assert settings.burst_detection.time_window == DEFAULT_TIME_WINDOW_MS / 1000.0
    assert BurstSelectionTool.__init__.__kwdefaults__["show_filter_plot"] is False
    assert BurstSelectionTool.__init__.__kwdefaults__["show_burst_plot"] is False


def test_diagnostic_pens_distinguish_all_and_selected_photons() -> None:
    """All-photon and selected-photon diagnostic layers must use different colors."""
    tool = BurstSelectionTool.__new__(BurstSelectionTool)

    assert BurstSelectionTool._diagnostic_pen(tool, 0) != BurstSelectionTool._diagnostic_pen(
        tool, 0, selected=True
    )
    assert BurstSelectionTool._diagnostic_pen(tool, 1) != BurstSelectionTool._diagnostic_pen(
        tool, 1, selected=True
    )


def test_macro_time_offsets_continue_across_file_boundaries() -> None:
    """Diagnostic macro times should continue at file boundaries instead of restarting."""

    class FakeHeader:
        """TTTR header stand-in."""

        macro_time_resolution = 0.001

    class FakeTTTR:
        """TTTR stand-in."""

        header = FakeHeader()
        macro_times = np.array([10, 15, 30])

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tttr_a = FakeTTTR()
    tttr_b = FakeTTTR()
    tool._last_diagnostics = [
        {"tttr": tttr_a, "selected": np.ones(3, dtype=bool)},
        {"tttr": tttr_b, "selected": np.ones(3, dtype=bool)},
    ]

    offsets = BurstSelectionTool._macro_time_offsets_ms(tool, tool._last_diagnostics)
    delta_b = BurstSelectionTool._delta_macro_time_ms(tool, tttr_b, offsets[1])

    assert offsets == [0.0, 20.0]
    assert delta_b.tolist() == [20.0, 5.0, 15.0]


def test_macro_time_offsets_accumulate_over_three_files() -> None:
    """File 3 continues from file 2's *continued* end, not its raw end.

    With the raw end, ten 642 s files showed as 126 s and files 2-10 overlapped;
    two identical files cannot tell the difference.
    """

    class FakeHeader:
        macro_time_resolution = 0.001

    class FakeTTTR:
        header = FakeHeader()
        macro_times = np.array([10, 15, 30])

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    diagnostics = [{"tttr": FakeTTTR(), "selected": np.ones(3, dtype=bool)} for _ in range(3)]
    offsets = BurstSelectionTool._macro_time_offsets_ms(tool, diagnostics)
    assert offsets == [0.0, 20.0, 40.0]


def test_histogram_data_ignores_interleaved_zero_rows() -> None:
    """Histogram updates should ignore Margarita zero separator rows."""
    frame = pd.DataFrame(
        {
            "Number of Photons": [0, 10, 0, 20],
            "Proximity Ratio": [0.0, 0.1, 0.0, 0.3],
        }
    )
    assert histogram_data_from_frame(frame, "Proximity Ratio").tolist() == [0.1, 0.3]


def test_histogram_data_for_a_plain_column_is_a_plain_array() -> None:
    """A non-Proximity-Ratio feature takes the generic numeric_column path.

    Regression: this used to end in `.to_numpy(dtype=float)` on a value
    `numeric_column` already returns as a plain `numpy.ndarray` (not a
    pandas Series) -- broken since `numeric_column` was written, but never
    caught because every other histogram test here asks for "Proximity
    Ratio", which takes the early-return branch above instead.
    """
    frame = pd.DataFrame(
        {
            "Number of Photons": [0, 10, 0, 20],
            "Proximity Ratio": [0.0, 0.1, 0.0, 0.3],
        }
    )
    result = histogram_data_from_frame(frame, "Number of Photons")
    assert isinstance(result, np.ndarray)
    assert result.tolist() == [10.0, 20.0]


def test_fill_table_reads_the_datastore_make_ui_dataframe_returns(qapp) -> None:
    """_fill_table must work on a real DataStore, not a pandas DataFrame.

    Regression: `make_ui_dataframe` returns a `DataStore`
    (`chisurf.core.datastore.store_from_arrays`), and `_fill_table` called
    `frame.to_numpy()` on it -- a pandas-only method -- which raised
    `'DataStore' object has no attribute 'to_numpy'` the moment a user
    selected any file in Burst Selection. Every other test in this file
    replaces `_fill_table` with a mock, so nothing exercised the real
    implementation. Found live.
    """
    from qtpy import QtCore, QtWidgets

    from chisurf.core.datastore import store_from_arrays

    frame = store_from_arrays(
        {
            "Number of Photons": np.array([10, 20], dtype=np.int32),
            "Proximity Ratio": np.array([0.2, 0.3], dtype=np.float64),
        }
    )

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool.table = QtWidgets.QTableWidget()
    tool.table.setColumnCount(2)

    tool_module.BurstSelectionTool._fill_table(tool, frame)

    assert tool.table.rowCount() == 2
    assert tool.table.item(0, 0).data(QtCore.Qt.ItemDataRole.DisplayRole) == 10.0
    assert tool.table.item(1, 1).data(QtCore.Qt.ItemDataRole.DisplayRole) == 0.3


def test_populate_feature_combo_survives_a_same_length_refresh(qapp) -> None:
    """Re-populating with the same column count must not compare Column objects.

    Regression: `list(frame.columns)` returns `Column` objects, not name
    strings; comparing that list against the combo's current items with
    `!=` is fine when the lengths differ (a plain `True`) but raises "truth
    value of an array is ambiguous" the moment the two lists are the same
    length and Python falls back to per-element `==`. That only bites on
    the *second* selection of a file with the same feature set -- found
    live, selecting a second file in Burst Selection right after the
    `_fill_table` bug above was fixed.
    """
    from qtpy import QtWidgets

    from chisurf.core.datastore import store_from_arrays

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool.feature_combo = QtWidgets.QComboBox()

    frame = store_from_arrays(
        {
            "Number of Photons": np.array([10, 20], dtype=np.int32),
            "Proximity Ratio": np.array([0.2, 0.3], dtype=np.float64),
        }
    )
    BurstSelectionTool._populate_feature_combo(tool, frame)
    first_items = [tool.feature_combo.itemText(i) for i in range(tool.feature_combo.count())]

    # Same column names, same count -> exercises the length-equal comparison.
    second = store_from_arrays(
        {
            "Number of Photons": np.array([30], dtype=np.int32),
            "Proximity Ratio": np.array([0.4], dtype=np.float64),
        }
    )
    BurstSelectionTool._populate_feature_combo(tool, second)

    assert first_items == ["Number of Photons", "Proximity Ratio"]
    assert [
        tool.feature_combo.itemText(i) for i in range(tool.feature_combo.count())
    ] == first_items


def test_make_ui_dataframe_computes_proximity_ratio() -> None:
    """The histogram feature list should include computed proximity ratios."""
    frame = pd.DataFrame(
        {
            "Number of Photons (red)": [0, 10, 30],
            "Number of Photons (green)": [0, 40, 70],
        }
    )

    ui_frame = make_ui_dataframe(frame)

    assert "Proximity Ratio" in column_names(ui_frame)
    assert np.round(numeric_column(ui_frame, "Proximity Ratio"), 6).tolist() == [0.2, 3 / 10]
    assert "Proximity Ratio" in column_names(ui_frame)


def test_histogram_data_uses_computed_proximity_ratio() -> None:
    """Histogram data should use the computed proximity-ratio column."""
    frame = pd.DataFrame(
        {
            "Number of Photons (red)": [10, 30],
            "Number of Photons (green)": [40, 70],
        }
    )

    values = histogram_data_from_frame(frame, "Proximity Ratio")

    assert values.tolist() == [0.2, 3 / 10]


def test_show_selected_file_result_updates_selected_table_and_histogram() -> None:
    """Selecting a cached file should display that file's burst table and histogram."""
    path = Path("selected.spc")
    frame = pd.DataFrame({"Number of Photons": [10, 20]})
    settings = default_analysis_settings()
    calls: list[str] = []

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._last_frames_by_file = {path.resolve(): frame}
    tool._fill_table = lambda df: (
        calls.append(f"table:{len(df)}") if df is not None else calls.append("table:0")
    )
    tool._populate_feature_combo = lambda df: calls.append(f"features:{len(column_names(df))}")
    tool.update_histogram = lambda: calls.append("histogram")

    BurstSelectionTool._show_selected_file_result(tool, path, settings)

    assert numeric_column(tool._last_frame, "Number of Photons").tolist() == [10, 20]
    assert tool._last_bur_frames == [frame]
    assert tool._last_settings is settings
    assert calls == ["table:2", "features:10", "histogram"]


def test_analyze_selected_file_updates_selected_table_and_histogram() -> None:
    """Selecting an uncached file should analyze only that file for the table and histogram."""
    path = Path("selected.spc")
    settings = default_analysis_settings()

    class FakeClient:
        """Client stub that returns one selected-file frame."""

        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def analyze_files(self, file_paths: list[Path], **kwargs: object) -> dict[str, object]:
            self.calls.append({"file_paths": file_paths, **kwargs})
            return {
                "dataframes": {str(path): [{"Number of Photons": 12}]},
                "metadata": {"n_files": 1, "n_bursts": 1, "n_photons": 30},
            }

    class FakeWizard:
        """Minimal wizard stand-in for RPC context."""

        windows = {"prompt": [0, 2048]}
        detectors = {"green": {"chs": [0]}}
        decay_coarse = 8

        class ComboBox:
            """Minimal combo-box stand-in."""

            def currentText(self) -> str:
                return "Test setup"

        comboBox = ComboBox()

    client = FakeClient()
    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._last_frames_by_file = {}
    tool._client = client
    tool.wizard = FakeWizard()
    tool._selected_filetype = "SPC-130"
    tool._status_bar = type("FakeStatusBar", (), {"showMessage": lambda self, message: None})()
    tool.summary = type("FakeSummary", (), {"setPlainText": lambda self, text: None})()
    tool._fill_table = lambda df: (
        calls.append(f"table:{len(df)}") if df is not None else calls.append("table:0")
    )
    tool._populate_feature_combo = lambda df: calls.append(f"features:{len(column_names(df))}")
    tool.update_histogram = lambda: calls.append("histogram")
    calls: list[str] = []

    BurstSelectionTool._analyze_selected_file(tool, path, settings)

    assert client.calls[0]["file_paths"] == [path]
    assert client.calls[0]["legacy_output"] is False
    assert client.calls[0]["selected_setup"] == "Test setup"
    assert client.calls[0]["legacy_parameters"] == {"decay_coarse": 8}
    assert numeric_column(
        tool._last_frames_by_file[path.resolve()], "Number of Photons"
    ).tolist() == [12]
    assert numeric_column(tool._last_bur_frames[0], "Number of Photons").tolist() == [12]
    assert calls == ["table:1", "features:10", "histogram"]


def test_analyze_selected_file_does_not_archive_preview() -> None:
    """Selected-file preview should not emit MMFDB context as an output side effect."""
    path = Path("selected.spc")
    settings = default_analysis_settings()

    class FakeClient:
        """Client stub that records MMFDB context for preview analysis."""

        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def analyze_files(self, file_paths: list[Path], **kwargs: object) -> dict[str, object]:
            self.calls.append({"file_paths": file_paths, **kwargs})
            return {
                "dataframes": {str(path): [{"Number of Photons": 12}]},
                "metadata": {"n_files": 1},
            }

    class FakeWizard:
        """Minimal wizard stand-in for RPC context."""

        windows = {}
        detectors = {}

        class ComboBox:
            """Minimal combo-box stand-in."""

            def currentText(self) -> str:
                return "Test setup"

        comboBox = ComboBox()

    client = FakeClient()
    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._last_frames_by_file = {}
    tool._client = client
    tool.wizard = FakeWizard()
    tool._selected_filetype = "SPC-130"
    tool._status_bar = type("FakeStatusBar", (), {"showMessage": lambda self, message: None})()

    BurstSelectionTool._analyze_file_frame(tool, path, settings)

    assert client.calls[0]["mmfdb"] is None


def test_mmfdb_raw_registration_binds_content_to_sample(tmp_path: Path) -> None:
    """Registering raw input should make future content-MD5 lookups find the sample."""
    db = MFDatabase(tmp_path / "mmfdb.sqlite")
    from mmfdb.security.auth import create_session

    from chisurf.core.transform.mmfdb import session_from_auth

    db.ensure_user("gui-test-user")
    token = create_session(db.conn, "gui-test-user")["token"]
    db.conn.commit()
    session = session_from_auth(db, {"token": token})
    sample_id = create_sample(db, SampleDefinition(name="DNA burst sample"))
    raw_paths = _bh_spc130_files()

    assert raw_paths
    for raw_path in raw_paths:
        artifact_id = _register_raw_input_for_sample(
            db=db,
            path=raw_path,
            sample_id=sample_id,
            filetype="SPC-130",
            selected_setup="Test setup",
            session=session,
        )

        assert artifact_id
        assert _raw_artifact_id_for_path(db, raw_path) == artifact_id
        assert _sample_id_for_raw_path(db, raw_path) == sample_id


def test_prepare_mmfdb_context_prompts_when_raw_sample_is_missing(
    tmp_path: Path, monkeypatch: object
) -> None:
    """MMFDB output should open sample registration when raw content has no sample."""
    db = MFDatabase(tmp_path / "mmfdb.sqlite")
    from mmfdb.security.auth import create_session

    from chisurf.core.transform.mmfdb import session_from_auth

    db.ensure_user("gui-context-user")
    token = create_session(db.conn, "gui-context-user")["token"]
    db.conn.commit()
    session = session_from_auth(db, {"token": token})
    sample_id = create_sample(db, SampleDefinition(name="Registered sample"))
    raw_paths = _bh_spc130_files()
    prompts: list[str] = []

    class FakeCheck:
        """Minimal checkbox stand-in."""

        def isChecked(self) -> bool:
            return True

    class FakeWizard:
        """Minimal wizard stand-in exposing the selected setup."""

        detectors = _bh_spc130_detectors()
        windows = {}

        class ComboBox:
            """Minimal combo-box stand-in."""

            def currentText(self) -> str:
                return "BH SPC-130 setup"

        comboBox = ComboBox()

    def fake_sample_picker(*, db: MFDatabase, parent: object | None = None) -> str:
        """Return the sample selected in the registration dialog."""
        prompts.append("shown")
        return sample_id

    monkeypatch.setattr(tool_module, "show_sample_picker_dialog", fake_sample_picker)
    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._mmfdb_db = db
    tool._mmfdb_session = session
    tool._mmfdb_client = None
    tool.mmfdb_output_check = FakeCheck()
    tool._selected_filetype = "SPC-130"
    tool.wizard = FakeWizard()
    tool._selected_sample_id = lambda: ""

    context = BurstSelectionTool._prepare_mmfdb_context_for_paths(tool, raw_paths)

    assert prompts == ["shown"]
    assert context is not None
    assert context["enabled"] is True
    assert context["sample_id"] == sample_id
    assert set(context["source_artifact_ids"]) == {str(path.resolve()) for path in raw_paths}
    assert context["register_missing_inputs"] is True
    assert context["setup_id"] == setup_id_for_name("BH SPC-130 setup", user_id=session.user_id)
    assert db.get_setup(context["setup_id"]) is not None
    assert all(_sample_id_for_raw_path(db, raw_path) == sample_id for raw_path in raw_paths)


def test_mmfdb_only_output_runs_batch_analysis(tmp_path: Path, monkeypatch: object) -> None:
    """Batch analysis should accept MMFDB as the only selected output mode."""
    paths = _bh_spc130_files()
    settings = default_analysis_settings()
    settings.output_formats = []
    mmfdb_context = {"enabled": True, "sample_id": "sample_1", "source_artifact_ids": {}}

    class FakeClient:
        """Client stub that records batch-analysis calls."""

        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def analyze_files(self, file_paths: list[Path], **kwargs: object) -> dict[str, object]:
            self.calls.append({"file_paths": file_paths, **kwargs})
            return {
                "dataframes": {str(path): [{"Number of Photons": 12}] for path in paths},
                "metadata": {
                    "n_files": len(paths),
                    "n_bursts": len(paths),
                    "n_photons": 12 * len(paths),
                    "n_selected": 12 * len(paths),
                },
            }

    class FakeDialog:
        """Progress stand-in for headless batch tests.

        ``ChiSurfProgress`` would already be harmless here (head-lessly it writes
        to the log), but the test asserts on the closing message, so it stands in
        to capture it.
        """

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.finished: list[str] = []

        def show(self) -> None:
            return

        def update_progress(self, *_args: object) -> None:
            return

        def finish(self, final_text: str, **_kwargs: object) -> None:
            self.finished.append(final_text)

        @staticmethod
        def run(_parent, _text, func, *, args=(), kwargs=None, on_result=None, **_kw):
            """Run the worker inline and deliver its result.

            The batch now goes through the shared task layer; this test is about
            what reaches the backend, so the worker runs here rather than in a
            thread.
            """

            class _Handle:
                """Minimal `TaskHandle` stand-in."""

                def set_progress(self, *_a, **_k):
                    return None

                def set_range(self, *_a, **_k):
                    return None

                def set_text(self, *_a, **_k):
                    return None

                def set_partial(self, *_a, **_k):
                    return None

                def raise_if_cancelled(self):
                    return None

                is_cancelled = False

            result = func(*args, _Handle(), **(kwargs or {}))
            if on_result is not None:
                on_result(result)

    class FakeWizard:
        """Minimal wizard stand-in for batch RPC context."""

        windows = {}
        detectors = _bh_spc130_detectors()
        decay_coarse = 8

        class ComboBox:
            """Minimal combo-box stand-in."""

            def currentText(self) -> str:
                return "Test setup"

        comboBox = ComboBox()

    client = FakeClient()
    summary_text: list[str] = []
    monkeypatch.setattr(tool_module, "ChiSurfProgress", FakeDialog)
    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    # The tool declares message conditions; `__new__` skips the binding that
    # `MessagesMixin.__init__` normally does.
    tool._message_bar = None
    tool.Error = BurstSelectionTool.Error(tool)
    tool.Warning = BurstSelectionTool.Warning(tool)
    tool.Information = BurstSelectionTool.Information(tool)
    tool._file_paths = paths
    tool._client = client
    tool.wizard = FakeWizard()
    tool._selected_filetype = "SPC-130"
    tool._settings_from_controls = lambda: settings
    tool._mmfdb_output_selected = lambda: True
    # The batch reuses a previous search when nothing changed; a tool built with
    # ``__new__`` has neither piece of that state, and on a QObject a missing
    # attribute raises rather than returning a default.
    tool._has_processed = False
    tool._result_cache = analysis_cache.ResultCache()
    tool._running_fingerprint = None
    tool._prepare_mmfdb_context_for_paths = lambda paths: mmfdb_context
    tool._legacy_parameters = lambda: {}
    tool._selected_file_paths_from_list = lambda: paths
    tool._display_frame_set = lambda frames, current_settings, indices: True
    tool._load_tttr_for_plots = lambda paths, current_settings: None
    tool.update_burst_plots = lambda: None
    tool.summary = type(
        "FakeSummary", (), {"setPlainText": lambda self, text: summary_text.append(text)}
    )()

    BurstSelectionTool.analyze_files(tool)

    assert client.calls[0]["file_paths"] == paths
    assert client.calls[0]["detectors"] == _bh_spc130_detectors()
    assert client.calls[0]["mmfdb"] == mmfdb_context
    assert client.calls[0]["legacy_output"] is True
    assert "No output format selected." not in summary_text


def test_a_container_source_keeps_the_folder_controls_disabled() -> None:
    """Zipping and removing act on the companion *folder*.

    A `.pto` measurement keeps its bursts inside itself, so there is no folder
    for either control to act on. They used to be gated on an output-format
    checkbox; the format is decided by the input now, so the gate is too.
    """

    class FakeCheck:
        """Minimal checkbox stand-in with mutable state."""

        def __init__(self, checked: bool) -> None:
            self.checked = checked
            self.enabled = True

        def isChecked(self) -> bool:
            return self.checked

        def setChecked(self, checked: bool) -> None:
            self.checked = checked

        def setEnabled(self, enabled: bool) -> None:
            self.enabled = enabled

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool.__dict__["_file_paths"] = [Path("m000.pto")]
    tool.mmfdb_output_check = FakeCheck(True)
    tool.zip_output_check = FakeCheck(True)
    tool.remove_folder_check = FakeCheck(True)

    BurstSelectionTool._sync_output_format_controls(tool)

    assert tool.zip_output_check.enabled is False
    assert tool.zip_output_check.checked is False
    assert tool.remove_folder_check.enabled is False


def test_a_vendor_source_leaves_the_folder_controls_available() -> None:
    """There is a folder to zip when the source cannot hold the results."""

    class FakeCheck:
        """Minimal checkbox stand-in with mutable state."""

        def __init__(self, checked: bool) -> None:
            self.checked = checked
            self.enabled = True

        def isChecked(self) -> bool:
            return self.checked

        def setChecked(self, checked: bool) -> None:
            self.checked = checked

        def setEnabled(self, enabled: bool) -> None:
            self.enabled = enabled

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool.__dict__["_file_paths"] = [Path("m000.spc")]
    tool.mmfdb_output_check = FakeCheck(False)
    tool.zip_output_check = FakeCheck(True)
    tool.remove_folder_check = FakeCheck(False)

    BurstSelectionTool._sync_output_format_controls(tool)

    assert tool.zip_output_check.enabled is True
    assert tool.zip_output_check.checked is True


def test_the_destination_follows_the_input() -> None:
    """`.pto` in, `.pto` out; anything else gets the companion folder.

    Called against a plain namespace rather than a half-built tool: the method
    reads one attribute, and `BurstSelectionTool.__new__` without `__init__`
    raises from PyQt when it is collected.
    """
    from types import SimpleNamespace

    decide = BurstSelectionTool._output_formats_for_inputs
    assert decide(SimpleNamespace(_file_paths=[Path("m000.pto")])) == ["pto"]
    assert decide(SimpleNamespace(_file_paths=[Path("m000.spc")])) == ["bur"]
    # Each measurement still gets the one destination it can use.
    assert decide(SimpleNamespace(_file_paths=[Path("a.pto"), Path("b.ptu")])) == ["pto", "bur"]
    # Nothing loaded: the container, which is what a fresh panel should say.
    assert decide(SimpleNamespace(_file_paths=[])) == ["pto"]


def test_selected_file_paths_support_multiple_selection() -> None:
    """The file list should return all queued selected paths."""
    path_a = Path("a.spc")
    path_b = Path("b.spc")

    class FakeItem:
        """Minimal selected file item stand-in."""

        def __init__(self, text: Path) -> None:
            self._text = str(text)

        def text(self) -> str:
            return self._text

    class FakeFileList:
        """Minimal file-list stand-in."""

        def selectedItems(self) -> list[FakeItem]:
            return [FakeItem(path_a), FakeItem(path_b)]

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool.file_list = FakeFileList()
    tool._file_paths = [path_a.resolve(), path_b.resolve()]

    assert BurstSelectionTool._selected_file_paths_from_list(tool) == [path_a, path_b]


def test_update_selected_files_stacks_cached_results() -> None:
    """Multiple selected files should stack their burst tables and histograms."""
    path_a = Path("a.spc")
    path_b = Path("b.spc")
    frame_a = pd.DataFrame({"Number of Photons": [10]})
    frame_b = pd.DataFrame({"Number of Photons": [20]})
    settings = default_analysis_settings()
    calls: list[str] = []

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._last_frames_by_file = {path_a.resolve(): frame_a, path_b.resolve(): frame_b}
    tool._fill_table = lambda df: calls.append(f"table:{len(df)}")
    tool._populate_feature_combo = lambda df: calls.append(f"features:{len(column_names(df))}")
    tool.update_histogram = lambda: calls.append("histogram")
    tool._load_tttr_for_plots = lambda selected_paths, current_settings: calls.append(
        f"diagnostics:{selected_paths[0].name}"
    )

    BurstSelectionTool._update_selected_files(tool, [path_a, path_b], settings)

    assert numeric_column(tool._last_frame, "Number of Photons").tolist() == [10, 20]
    assert tool._last_bur_frames == [frame_a, frame_b]
    assert calls == ["table:2", "features:10", "histogram", "diagnostics:a.spc"]


def test_filter_settings_change_updates_selected_file_plots() -> None:
    """A filter change re-searches the VISIBLE WINDOW, and nothing more.

    It used to run the full analysis of every selected file as well — the whole
    measurement re-searched on the GUI thread for one spin-box step, 3.0 s
    against the 66 ms the windowed diagnostics cost, and again on the next step
    of the same control. The diagnostics already answer the question the user is
    asking, and the burst table beside the plots is built from them.
    """
    path = Path("selected.spc")
    selected_item = type("FakeItem", (), {"text": lambda self: str(path)})()

    class FakeFileList:
        """Minimal file-list stand-in."""

        def selectedItems(self) -> list[object]:
            return [selected_item]

    class FakeSettings:
        """Minimal settings stand-in."""

    settings = FakeSettings()
    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool.file_list = FakeFileList()
    tool._file_paths = [path]
    tool._status_bar = type("FakeStatusBar", (), {"showMessage": lambda self, message: None})()
    tool._settings_from_controls = lambda: settings
    tool._analyze_selected_files = lambda selected_paths, current_settings: calls.append(
        ("analyze", selected_paths, current_settings)
    )
    tool._load_tttr_for_plots = lambda selected_paths, current_settings: calls.append(
        ("diagnostics", selected_paths, current_settings)
    )
    calls: list[tuple[str, list[Path], FakeSettings]] = []

    BurstSelectionTool._on_filter_settings_changed(tool)

    assert calls == [("diagnostics", [path], settings)], (
        "a filter change must not run the full analysis"
    )


def test_burst_plot_update_refreshes_embedded_filter_settings_plot(tmp_path: Path) -> None:
    """The filter-settings dT plot should mirror the current selected file."""

    class FakeDataItem:
        """Minimal pyqtgraph data item stand-in."""

        def __init__(self) -> None:
            self.args: tuple[object, ...] = ()
            self.kwargs: dict[str, object] = {}

        def setData(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

    class FakePlot:
        """Minimal plot widget stand-in."""

        def __init__(self) -> None:
            self.plots: list[dict[str, object]] = []
            self.cleared = False

        def clear(self) -> None:
            self.cleared = True

        def plot(self, *args: object, **kwargs: object) -> None:
            self.plots.append({"args": args, "kwargs": kwargs})

        def setYRange(self, *args: object, **kwargs: object) -> None:
            self.y_range = (args, kwargs)

        def setTitle(self, *args: object, **kwargs: object) -> None:
            self.title = (args, kwargs)

    class FakeSpinBox:
        """Minimal spin box stand-in."""

        def __init__(self, value: int = 0) -> None:
            self._value = value
            self.maximum = 0

        def value(self) -> int:
            return self._value

        def setValue(self, value: int) -> None:
            self._value = value

        def setMaximum(self, value: int) -> None:
            self.maximum = value

        def blockSignals(self, _blocked: bool) -> None:
            return

    class FakeLineEdit:
        """Minimal line edit stand-in."""

        def __init__(self) -> None:
            self.text = ""

        def setText(self, text: str) -> None:
            self.text = text

    class FakeHeader:
        """TTTR header stand-in with macro-time resolution."""

        macro_time_resolution = 0.001

    class FakeTTTR:
        """TTTR stand-in with macro times."""

        header = FakeHeader()
        macro_times = np.array([10, 15, 30, 31])

    class FakeWizard:
        """Embedded photon-filter widget stand-in."""

        def __init__(self) -> None:
            self.tttr_objects: dict[str, object] = {}
            self.settings: dict[str, object] = {"tttr_filenames": []}
            self.lineEdit = FakeLineEdit()
            self.spinBox_2 = FakeSpinBox()
            self.spinBox_3 = FakeSpinBox()
            self.spinBox_4 = FakeSpinBox()
            self.plot_selected = FakeDataItem()
            self.plot_unselected = FakeDataItem()
            self.plot_select = FakeDataItem()
            self.tttr = None

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._last_tttr = FakeTTTR()
    tool._last_selected = np.array([True, False, True, False])
    tool._last_start_stop = np.array([[0, 2]])
    tool._last_diagnostic_path = tmp_path / "selected.spc"
    tool.plot_min_spin = FakeSpinBox(0)
    tool.plot_max_spin = FakeSpinBox(3)
    tool.dt_plot = FakePlot()
    tool.filter_plot = FakePlot()
    tool.filter_settings_panel = object()
    tool.wizard = FakeWizard()
    tool._update_mcs_plot = lambda start, stop: None
    tool._update_decay_plot = lambda: None
    tool._update_burst_length_plot = lambda: None
    tool._status_bar = type("FakeStatusBar", (), {"showMessage": lambda self, message: None})()

    BurstSelectionTool.update_burst_plots(tool)

    selected_x = tool.wizard.plot_selected.kwargs["x"]
    selected_y = tool.wizard.plot_selected.kwargs["y"]
    assert selected_x.tolist() == [0, 2]
    assert selected_y.tolist() == [0.0, 15.0]
    assert tool.wizard.plot_select.kwargs["y"].tolist() == [1, 0, 1, 0]
    assert tool.wizard.settings["tttr_filenames"] == [str((tmp_path / "selected.spc").resolve())]
    assert tool.wizard.lineEdit.text == str((tmp_path / "selected.spc").resolve())


def test_plot_range_controls_follow_selected_file_photon_count() -> None:
    """Toolbar photon range should match the current selected file."""

    class FakeSpinBox:
        """Minimal spin box stand-in."""

        def __init__(self, value: int = 0) -> None:
            self._value = value
            self.range = (0, 0)
            self.blocked: list[bool] = []

        def value(self) -> int:
            return self._value

        def setValue(self, value: int) -> None:
            self._value = value

        def setRange(self, minimum: int, maximum: int) -> None:
            self.range = (minimum, maximum)

        def blockSignals(self, blocked: bool) -> None:
            self.blocked.append(blocked)

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool.plot_min_spin = FakeSpinBox(10)
    tool.plot_max_spin = FakeSpinBox(100_000)

    BurstSelectionTool._sync_plot_range_controls(tool, 42, reset=True)

    assert tool.plot_min_spin.value() == 0
    assert tool.plot_max_spin.value() == 41
    assert tool.plot_min_spin.range == (0, 41)
    assert tool.plot_max_spin.range == (0, 41)

    tool.plot_min_spin.setValue(12)
    tool.plot_max_spin.setValue(99)
    BurstSelectionTool._sync_plot_range_controls(tool, 30)

    assert tool.plot_min_spin.value() == 12
    assert tool.plot_max_spin.value() == 29
    assert tool.plot_min_spin.range == (0, 29)
    assert tool.plot_max_spin.range == (0, 29)


def test_mcs_plot_offsets_use_seconds_for_time_axis() -> None:
    """MCS time offsets must be converted from macro-time milliseconds to seconds."""

    class FakeCheck:
        """Minimal checkbox stand-in."""

        def __init__(self, checked: bool) -> None:
            self.checked = checked

        def isChecked(self) -> bool:
            return self.checked

    class FakeSpinBox:
        """Minimal spin box stand-in."""

        def value(self) -> float:
            return 0.25

    class FakePlot:
        """Plot stand-in that records plot calls."""

        def __init__(self) -> None:
            self.plots: list[dict[str, object]] = []

        def clear(self) -> None:
            self.plots.clear()

        def plot(self, *args: object, **kwargs: object) -> None:
            self.plots.append({"args": args, "kwargs": kwargs})

        def setLabel(self, *_args: object, **_kwargs: object) -> None:
            return

        def setTitle(self, *_args: object, **_kwargs: object) -> None:
            return

    class FakeHeader:
        """TTTR header stand-in."""

        macro_time_resolution = 0.001

    class FakeTTTR:
        """TTTR stand-in."""

        header = FakeHeader()
        macro_times = np.array([0, 1, 2])

        def __getitem__(self, _indices: np.ndarray) -> FakeTTTR:
            return self

        def get_intensity_trace(self, time_window_length: float) -> np.ndarray:
            return np.array([1.0])

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._last_diagnostics = [
        {"tttr": FakeTTTR(), "selected": np.ones(1, dtype=bool)},
        {"tttr": FakeTTTR(), "selected": np.ones(1, dtype=bool)},
    ]
    tool.mcs_bin_spin = FakeSpinBox()
    tool.mcs_plot = FakePlot()
    tool.mcs_show_all_check = FakeCheck(False)
    tool.mcs_show_selected_check = FakeCheck(True)

    BurstSelectionTool._update_mcs_plot(tool, 0, 2)

    assert tool.mcs_plot.plots[0]["args"][0].tolist() == [0.0]
    assert tool.mcs_plot.plots[1]["args"][0].tolist() == [0.002]


def test_mcs_plot_draws_all_before_selected_and_respects_toggles() -> None:
    """Selected MCS trace should be plotted last and disabled traces should not compute."""

    class FakeCheck:
        """Minimal checkbox stand-in."""

        def __init__(self, checked: bool) -> None:
            self.checked = checked

        def isChecked(self) -> bool:
            return self.checked

    class FakeSpinBox:
        """Minimal spin box stand-in."""

        def value(self) -> float:
            return 0.25

    class FakePlot:
        """Plot stand-in that records plot calls."""

        def __init__(self) -> None:
            self.plots: list[dict[str, object]] = []

        def clear(self) -> None:
            self.plots.clear()

        def plot(self, *args: object, **kwargs: object) -> None:
            self.plots.append({"args": args, "kwargs": kwargs})

        def setLabel(self, *_args: object, **_kwargs: object) -> None:
            return

        def setTitle(self, *_args: object, **_kwargs: object) -> None:
            return

    class FakeTTTR:
        """TTTR stand-in that distinguishes full and selected traces."""

        calls: list[list[int]] = []

        def __init__(self, label: str = "full") -> None:
            self.label = label

        def __getitem__(self, indices: np.ndarray) -> FakeTTTR:
            values = np.asarray(indices, dtype=int).tolist()
            FakeTTTR.calls.append(values)
            if values == [1, 2, 3]:
                return FakeTTTR("range")
            return FakeTTTR("selected")

        def get_intensity_trace(self, time_window_length: float) -> np.ndarray:
            assert time_window_length == 0.00025
            if self.label == "range":
                return np.array([1.0, 2.0, 3.0])
            if self.label == "selected":
                return np.array([10.0])
            return np.array([99.0])

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._last_tttr = FakeTTTR()
    tool._last_selected = np.array([False, False, True, False, True])
    tool.mcs_bin_spin = FakeSpinBox()
    tool.mcs_plot = FakePlot()
    tool.mcs_show_all_check = FakeCheck(True)
    tool.mcs_show_selected_check = FakeCheck(True)

    BurstSelectionTool._update_mcs_plot(tool, 1, 4)

    assert len(tool.mcs_plot.plots) == 2
    # The trace is drawn as a count *rate* in Hz, not as counts per bin: at the
    # 0.25 ms bin width above that is x 4000. Plotting counts made the y axis
    # depend on a display setting, so the same burst read 80 at 0.25 ms and 40
    # at 0.125 ms and no threshold could be quoted against it.
    assert tool.mcs_plot.plots[0]["args"][1].tolist() == [4000.0, 8000.0, 12000.0]
    assert tool.mcs_plot.plots[1]["args"][1].tolist() == [40000.0]
    assert FakeTTTR.calls == [[1, 2, 3], [2]]

    tool.mcs_show_all_check.checked = False
    FakeTTTR.calls.clear()
    BurstSelectionTool._update_mcs_plot(tool, 1, 4)

    assert len(tool.mcs_plot.plots) == 1
    assert tool.mcs_plot.plots[0]["args"][1].tolist() == [40000.0]
    assert FakeTTTR.calls == [[2]]


def test_shared_photon_toggles_apply_to_dt_and_filter_plots() -> None:
    """Toolbar photon toggles should control dT and filter diagnostic layers."""

    class FakeCheck:
        """Minimal checkbox stand-in."""

        def __init__(self, checked: bool) -> None:
            self.checked = checked

        def isChecked(self) -> bool:
            return self.checked

    class FakeSpinBox:
        """Minimal spin box stand-in."""

        def __init__(self, value: int) -> None:
            self._value = value

        def value(self) -> int:
            return self._value

        def setValue(self, value: int) -> None:
            self._value = value

        def setRange(self, _minimum: int, _maximum: int) -> None:
            return

        def blockSignals(self, _blocked: bool) -> None:
            return

    class FakePlot:
        """Plot stand-in that records plot calls."""

        def __init__(self) -> None:
            self.plots: list[dict[str, object]] = []

        def clear(self) -> None:
            self.plots.clear()

        def plot(self, *args: object, **kwargs: object) -> None:
            self.plots.append({"args": args, "kwargs": kwargs})

        def setYRange(self, *_args: object, **_kwargs: object) -> None:
            return

    class FakeHeader:
        """TTTR header stand-in."""

        macro_time_resolution = 0.001

    class FakeTTTR:
        """TTTR stand-in."""

        header = FakeHeader()
        macro_times = np.array([10, 15, 30, 31])

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._last_tttr = FakeTTTR()
    tool._last_selected = np.array([True, False, True, False])
    tool._last_start_stop = np.array([[0, 2]])
    tool.plot_min_spin = FakeSpinBox(0)
    tool.plot_max_spin = FakeSpinBox(3)
    tool.dt_plot = FakePlot()
    tool.filter_plot = FakePlot()
    tool.filter_settings_panel = None
    tool.show_all_photons_check = FakeCheck(True)
    tool.show_selected_photons_check = FakeCheck(True)
    tool._diagnostic_plot_features = {
        "Filter": {"initial_enabled": True, "check": FakeCheck(True), "widget": tool.filter_plot},
        "MCS": {"initial_enabled": False, "check": FakeCheck(False), "widget": object()},
        "Decay": {"initial_enabled": False, "check": FakeCheck(False), "widget": object()},
        "Burst length": {"initial_enabled": False, "check": FakeCheck(False), "widget": object()},
    }
    tool._closed_diagnostic_plots = set()
    tool._status_bar = type("FakeStatusBar", (), {"showMessage": lambda self, message: None})()

    BurstSelectionTool.update_burst_plots(tool)

    assert len(tool.dt_plot.plots) == 2
    assert tool.dt_plot.plots[0]["args"][0].tolist() == [0, 1, 2, 3]
    assert tool.dt_plot.plots[1]["args"][0].tolist() == [0, 2]
    assert tool.dt_plot.plots[0]["kwargs"]["pen"] != tool.dt_plot.plots[1]["kwargs"]["pen"]
    assert tool.filter_plot.plots[0]["args"][0].tolist() == [0, 1, 2, 3]
    assert tool.filter_plot.plots[1]["args"][0].tolist() == [0, 2]
    assert tool.filter_plot.plots[0]["kwargs"]["pen"] != tool.filter_plot.plots[1]["kwargs"]["pen"]
    assert tool.filter_plot.plots[0]["args"][1].tolist() == [0.0, 0.0, 0.0, 0.0]
    assert tool.filter_plot.plots[1]["args"][1].tolist() == [1.0, 1.0]

    tool.show_all_photons_check.checked = True
    tool.show_selected_photons_check.checked = False
    BurstSelectionTool.update_burst_plots(tool)

    assert len(tool.dt_plot.plots) == 1
    assert tool.dt_plot.plots[0]["args"][0].tolist() == [0, 1, 2, 3]
    assert tool.filter_plot.plots[0]["args"][0].tolist() == [0, 1, 2, 3]
    assert tool.filter_plot.plots[0]["args"][1].tolist() == [0.0, 0.0, 0.0, 0.0]


def test_dt_and_filter_plots_are_thinned_for_a_large_measurement(monkeypatch) -> None:
    """A merged multi-file .pto can hand this millions of photons at once.

    Regression: before chisurf.core.fio.decimate, `update_burst_plots` handed
    every visible photon straight to pyqtgraph's `.plot()` -- fine for one
    small vendor file, but the exact thing a merged .pto (several files
    packed into one measurement) or a long acquisition made common, and
    Qt laying out / repainting millions of points is where the reported lag
    in Burst Selection came from.
    """
    from chisurf.plugins.burst.burst_selection.gui.tool import BurstSelectionTool

    class FakeCheck:
        """Minimal checkbox stand-in."""

        def __init__(self, checked: bool) -> None:
            self.checked = checked

        def isChecked(self) -> bool:
            return self.checked

    class FakeSpinBox:
        """Minimal spin box stand-in."""

        def __init__(self, value: int) -> None:
            self._value = value

        def value(self) -> int:
            return self._value

        def setValue(self, value: int) -> None:
            self._value = value

        def setRange(self, _minimum: int, _maximum: int) -> None:
            return

        def blockSignals(self, _blocked: bool) -> None:
            return

    class FakePlot:
        """Plot stand-in that records plot calls."""

        def __init__(self) -> None:
            self.plots: list[dict[str, object]] = []

        def clear(self) -> None:
            self.plots.clear()

        def plot(self, *args: object, **kwargs: object) -> None:
            self.plots.append({"args": args, "kwargs": kwargs})

        def setYRange(self, *_args: object, **_kwargs: object) -> None:
            return

    class FakeHeader:
        """TTTR header stand-in."""

        macro_time_resolution = 0.001

    n_photons = 2_000_000

    class FakeTTTR:
        """TTTR stand-in with a huge, evenly-spaced macro-time stream."""

        header = FakeHeader()
        macro_times = np.arange(n_photons, dtype=np.int64)

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._last_tttr = FakeTTTR()
    tool._last_selected = np.ones(n_photons, dtype=bool)
    tool._last_start_stop = np.array([[0, n_photons - 1]])
    tool.plot_min_spin = FakeSpinBox(0)
    tool.plot_max_spin = FakeSpinBox(n_photons - 1)
    tool.dt_plot = FakePlot()
    tool.filter_plot = FakePlot()
    tool.filter_settings_panel = None
    tool.show_all_photons_check = FakeCheck(True)
    tool.show_selected_photons_check = FakeCheck(True)
    tool._diagnostic_plot_features = {
        "Filter": {"initial_enabled": True, "check": FakeCheck(True), "widget": tool.filter_plot},
        "MCS": {"initial_enabled": False, "check": FakeCheck(False), "widget": object()},
        "Decay": {"initial_enabled": False, "check": FakeCheck(False), "widget": object()},
        "Burst length": {"initial_enabled": False, "check": FakeCheck(False), "widget": object()},
    }
    tool._closed_diagnostic_plots = set()
    tool._status_bar = type("FakeStatusBar", (), {"showMessage": lambda self, message: None})()

    budget = 10_000
    monkeypatch.setattr(BurstSelectionTool, "_max_plot_points", staticmethod(lambda: budget))

    BurstSelectionTool.update_burst_plots(tool)

    all_calls = tool.dt_plot.plots + tool.filter_plot.plots
    assert all_calls, "the fixture must actually exercise the plotting calls"
    for call in all_calls:
        drawn = len(call["args"][0])
        assert drawn <= 2 * budget, f"drew {drawn} points against a budget of {budget}"
        assert drawn < n_photons


def test_shared_photon_toggles_apply_to_decay_plot() -> None:
    """Decay plotting should compute only enabled photon layers."""

    class FakeCheck:
        """Minimal checkbox stand-in."""

        def __init__(self, checked: bool) -> None:
            self.checked = checked

        def isChecked(self) -> bool:
            return self.checked

    class FakeSpinBox:
        """Minimal spin box stand-in."""

        def value(self) -> int:
            return 2

    class FakePlot:
        """Plot stand-in that records calls."""

        def __init__(self) -> None:
            self.plots: list[dict[str, object]] = []

        def clear(self) -> None:
            self.plots.clear()

        def plot(self, *args: object, **kwargs: object) -> None:
            self.plots.append({"args": args, "kwargs": kwargs})

    class FakeTTTR:
        """TTTR stand-in with separate all/selected histogram calls."""

        calls: list[str] = []

        def __init__(self, label: str = "all") -> None:
            self.label = label

        def __getitem__(self, _indices: np.ndarray) -> FakeTTTR:
            return FakeTTTR("selected")

        def get_microtime_histogram(self, coarse: int) -> tuple[np.ndarray, np.ndarray]:
            assert coarse == 2
            FakeTTTR.calls.append(self.label)
            return np.array([1.0, 0.0]), np.array([1.0, 2.0])

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._last_tttr = FakeTTTR()
    tool._last_selected = np.array([True, False, True])
    tool.decay_bins_spin = FakeSpinBox()
    tool.decay_plot = FakePlot()
    tool.show_all_photons_check = FakeCheck(False)
    tool.show_selected_photons_check = FakeCheck(True)

    BurstSelectionTool._update_decay_plot(tool)

    assert FakeTTTR.calls == ["selected"]

    tool.show_all_photons_check.checked = True
    tool.show_selected_photons_check.checked = False
    FakeTTTR.calls.clear()
    BurstSelectionTool._update_decay_plot(tool)

    assert FakeTTTR.calls == ["all"]


def test_update_burst_plots_skips_closed_mcs_dock() -> None:
    """Closed MCS docks should not trigger MCS trace computation."""

    class FakeSpinBox:
        """Minimal spin box stand-in."""

        def __init__(self, value: int) -> None:
            self._value = value

        def value(self) -> int:
            return self._value

    class FakePlot:
        """Minimal plot stand-in."""

        def clear(self) -> None:
            return

        def plot(self, *_args: object, **_kwargs: object) -> None:
            return

        def setYRange(self, *_args: object, **_kwargs: object) -> None:
            return

    class FakeCheck:
        """Minimal checkbox stand-in."""

        def __init__(self, checked: bool) -> None:
            self.checked = checked

        def isChecked(self) -> bool:
            return self.checked

    class FakeHeader:
        """TTTR header stand-in."""

        macro_time_resolution = 0.001

    class FakeTTTR:
        """TTTR stand-in."""

        header = FakeHeader()
        macro_times = np.array([1, 2, 4])

    calls = {"mcs": 0}
    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._last_tttr = FakeTTTR()
    tool._last_selected = np.array([True, False, True])
    tool.plot_min_spin = FakeSpinBox(0)
    tool.plot_max_spin = FakeSpinBox(2)
    tool.dt_plot = None
    tool.filter_settings_panel = None
    tool.filter_plot = FakePlot()
    tool._diagnostic_plot_features = {
        "Filter": {"initial_enabled": False, "check": FakeCheck(False), "widget": object()},
        "MCS": {
            "initial_enabled": True,
            "check": FakeCheck(True),
            "widget": object(),
            "dock_widget": object(),
        },
        "Decay": {"initial_enabled": False, "check": FakeCheck(False), "widget": object()},
        "Burst length": {"initial_enabled": False, "check": FakeCheck(False), "widget": object()},
    }
    tool._closed_diagnostic_plots = {"MCS"}
    tool._update_mcs_plot = lambda start, stop: calls.__setitem__("mcs", calls["mcs"] + 1)
    tool._status_bar = type("FakeStatusBar", (), {"showMessage": lambda self, message: None})()

    BurstSelectionTool.update_burst_plots(tool)

    assert calls["mcs"] == 0


def test_dock_context_menu_lists_closed_docks() -> None:
    """Dock context menu should offer closed diagnostic docks for reopening."""

    class FakeCheck:
        """Minimal checkbox stand-in."""

        def __init__(self, checked: bool) -> None:
            self.checked = checked

        def isChecked(self) -> bool:
            return self.checked

    class FakeSignal:
        """Minimal signal stand-in."""

        def connect(self, _slot: object) -> None:
            return

    class FakeAction:
        """Minimal action stand-in."""

        def __init__(self, text: str, submenu: FakeMenu | None = None) -> None:
            self._text = text
            self._submenu = submenu
            self.triggered = FakeSignal()

        def text(self) -> str:
            return self._text

        def menu(self) -> FakeMenu | None:
            return self._submenu

    class FakeMenu:
        """Minimal menu stand-in."""

        def __init__(self, title: str = "") -> None:
            self._title = title
            self._actions: list[FakeAction] = []

        def addSeparator(self) -> None:
            return

        def addMenu(self, title: str) -> FakeMenu:
            submenu = FakeMenu(title)
            self._actions.append(FakeAction(title, submenu))
            return submenu

        def addAction(self, title: str) -> FakeAction:
            action = FakeAction(title)
            self._actions.append(action)
            return action

        def actions(self) -> list[FakeAction]:
            return self._actions

        def title(self) -> str:
            return self._title

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._closed_diagnostic_plots = {"MCS", "Decay"}
    tool._diagnostic_plot_features = {
        "MCS": {"initial_enabled": True, "check": FakeCheck(False), "widget": object()},
        "Decay": {"initial_enabled": True, "check": FakeCheck(False), "widget": object()},
        "Filter": {"initial_enabled": True, "check": FakeCheck(True), "widget": object()},
    }

    menu = FakeMenu()
    BurstSelectionTool._add_dock_context_menu_actions(tool, menu, -1)

    submenus = [action.menu() for action in menu.actions() if action.menu() is not None]
    reopen_menu = next(submenu for submenu in submenus if submenu.title() == "Reopen closed docks")
    assert [action.text() for action in reopen_menu.actions()] == ["MCS", "Decay"]


def test_dock_configuration_enables_close_buttons() -> None:
    """Diagnostic dock tabs should expose close buttons."""

    class FakeDockArea:
        """Minimal dock-area stand-in."""

        def __init__(self) -> None:
            self.context_menu_enabled = False
            self.context_menu_mode = ""
            self.tabs_closable = False
            self.close_callback = None
            self.context_callback = None

        def setContextMenuEnabled(self, enabled: bool) -> None:
            self.context_menu_enabled = enabled

        def setContextMenuMode(self, mode: str) -> None:
            self.context_menu_mode = mode

        def setTabsClosable(self, closable: bool) -> None:
            self.tabs_closable = closable

        def setCloseTabCallback(self, callback: object) -> None:
            self.close_callback = callback

        def setContextMenuCallback(self, callback: object) -> None:
            self.context_callback = callback

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool.dock_area = FakeDockArea()
    tool.filter_plot = object()
    tool.filter_dock_widget = object()
    tool.plot_filter_check = object()
    tool.show_filter_plot = True
    tool.mcs_plot = object()
    tool.mcs_dock_widget = object()
    tool.plot_mcs_check = object()
    tool.show_mcs_plot = True
    tool.decay_plot = object()
    tool.decay_dock_widget = object()
    tool.plot_decay_check = object()
    tool.show_decay_plot = True
    tool.burst_plot = object()
    tool.burst_dock_widget = object()
    tool.plot_burst_check = object()
    tool.show_burst_plot = True

    BurstSelectionTool._configure_dock_context_menu(tool)

    assert tool.dock_area.context_menu_enabled is True
    assert tool.dock_area.context_menu_mode == "basic"
    assert tool.dock_area.tabs_closable is True
    assert tool.dock_area.close_callback is not None
    assert tool.dock_area.context_callback is not None


def test_dock_close_callback_hides_non_file_docks() -> None:
    """Burst dock callback should only remove the files dock."""

    class FakeDockArea:
        """Minimal dock-area stand-in for close callback behavior."""

        def __init__(self, widgets: list[object]) -> None:
            self.widgets = widgets
            self.hidden: list[int] = []
            self.removed: list[int] = []

        def widget(self, index: int) -> object:
            return self.widgets[index]

        def hideTab(self, index: int) -> None:
            self.hidden.append(index)

        def removeTab(self, index: int) -> None:
            self.removed.append(index)

    files_widget = object()
    dt_widget = object()
    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool.files_dock_widget = files_widget
    tool.dock_area = FakeDockArea([files_widget, dt_widget])
    tool._diagnostic_plot_features = {}

    BurstSelectionTool._on_dock_tab_close_requested(tool, 1)
    BurstSelectionTool._on_dock_tab_close_requested(tool, 0)

    assert tool.dock_area.hidden == [1]
    assert tool.dock_area.removed == [0]


def test_dock_visibility_menu_lists_available_docks() -> None:
    """Dock context menu should list all available docks with check states."""

    class FakeSignal:
        """Minimal signal stand-in."""

        def connect(self, slot: object) -> None:
            self.slot = slot

    class FakeAction:
        """Minimal action stand-in."""

        def __init__(self, text: str) -> None:
            self._text = text
            self.checkable = False
            self.checked = False
            self.enabled = True
            self.triggered = FakeSignal()

        def text(self) -> str:
            return self._text

        def setCheckable(self, checkable: bool) -> None:
            self.checkable = checkable

        def setChecked(self, checked: bool) -> None:
            self.checked = checked

        def setEnabled(self, enabled: bool) -> None:
            self.enabled = enabled

    class FakeMenu:
        """Minimal menu stand-in."""

        def __init__(self) -> None:
            self._actions: list[FakeAction] = []
            self.separators = 0

        def actions(self) -> list[FakeAction]:
            return self._actions

        def addSeparator(self) -> None:
            self.separators += 1

        def addAction(self, text: str) -> FakeAction:
            action = FakeAction(text)
            self._actions.append(action)
            return action

    dock_area = DockArea.__new__(DockArea)
    dock_area._all_widgets = [object(), object(), object()]
    dock_area._tab_names = {
        dock_area._all_widgets[0]: "Files",
        dock_area._all_widgets[1]: "MCS",
        dock_area._all_widgets[2]: "Decay",
    }
    dock_area.count = lambda: 3
    dock_area.tabText = lambda index: ["Files", "MCS", "Decay"][index]
    dock_area.isTabVisible = lambda index: index != 1
    dock_area.visibleCount = lambda: 2
    calls: list[tuple[int, bool]] = []
    dock_area._set_dock_visible = lambda index, visible: calls.append((index, visible))

    menu = FakeMenu()
    DockArea._add_dock_visibility_actions(dock_area, menu)

    assert [action.text() for action in menu.actions()] == ["Files", "MCS", "Decay"]
    assert [action.checkable for action in menu.actions()] == [True, True, True]
    assert [action.checked for action in menu.actions()] == [True, False, True]
    menu.actions()[1].triggered.slot(True)
    assert calls == [(1, True)]


def test_burst_durations_use_macro_time_resolution_ms() -> None:
    """Burst duration values should be reported in milliseconds."""

    class FakeHeader:
        """TTTR header stand-in."""

        macro_time_resolution = 0.002

    class FakeTTTR:
        """TTTR stand-in."""

        header = FakeHeader()
        macro_times = np.array([0, 5, 8, 20])

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._last_tttr = FakeTTTR()
    tool._last_start_stop = np.array([[0, 1], [1, 3]])

    durations = BurstSelectionTool._burst_durations_ms(tool)

    assert durations.tolist() == [10.0, 30.0]


def test_client_analyze_files_passes_detector_setup_context() -> None:
    """Detector setup context must be forwarded to the RPC analyze method."""

    class FakeClient:
        """Minimal client stub that records RPC calls."""

        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def call(self, method: str, params: dict[str, object]) -> dict[str, object]:
            self.calls.append((method, params))
            return {"ok": True, "result": {"dataframes": {}}}

    fake = FakeClient()
    client = BurstSelectionClient(fake)
    result = client.analyze_files(
        [Path("example.spc")],
        settings={"photon_filter": {"channels": [0, 8]}},
        windows={"prompt": [0, 2048]},
        detectors={"green": {"chs": [0, 8]}},
        filetype="SPC-130",
        output_dir=Path("burstwise_All 0.2000#60") / "bi4_bur",
        legacy_output=True,
        legacy_output_folder_name="burstwise_All 0.2000#60",
        selected_setup="Test",
        legacy_parameters={"decay_coarse": 8},
        mmfdb={
            "enabled": True,
            "sample_id": "sample_1",
            "source_artifact_ids": {"example.spc": "artifact_1"},
        },
    )
    assert result == {"dataframes": {}}
    assert fake.calls[0][0] == "burst_selection.jobs.analyze_files"
    assert fake.calls[0][1]["filetype"] == "SPC-130"
    assert fake.calls[0][1]["windows"] == {"prompt": [0, 2048]}
    assert fake.calls[0][1]["detectors"] == {"green": {"chs": [0, 8]}}
    assert fake.calls[0][1]["output_dir"] == "burstwise_All 0.2000#60/bi4_bur"
    assert fake.calls[0][1]["legacy_output"] is True
    assert fake.calls[0][1]["legacy_output_folder_name"] == "burstwise_All 0.2000#60"
    assert fake.calls[0][1]["selected_setup"] == "Test"
    assert fake.calls[0][1]["legacy_parameters"] == {"decay_coarse": 8}
    assert fake.calls[0][1]["mmfdb"] == {
        "enabled": True,
        "sample_id": "sample_1",
        "source_artifact_ids": {"example.spc": "artifact_1"},
    }


def test_client_load_diagnostics_accepts_unset_microtime_ranges() -> None:
    """Diagnostic loading should treat unset microtime ranges as unrestricted."""
    path = Path(__file__).resolve().parent / "data" / "bh_spc132_sm_dna" / "m000.spc"
    settings = default_analysis_settings()
    settings.photon_filter.channels = []
    settings.photon_filter.microtime_ranges = None

    diag = BurstSelectionClient().load_diagnostics(path, settings=asdict(settings))

    assert set(diag) >= {"tttr", "selected", "start_stop", "settings"}
    assert diag["settings"].photon_filter.microtime_ranges == []
    assert len(diag["selected"]) == len(diag["tttr"])


def test_plugin_uses_migrated_gui_by_default() -> None:
    """The plugin-level switch should select the migrated GUI."""
    assert USE_LEGACY_GUI is False
    assert BurstSelectionTool.__name__ == "BurstSelectionTool"


def test_analysis_worker_reports_per_file_progress_to_the_task() -> None:
    """The batch worker must give the task real per-file progress, not silence.

    Regression: `_analysis_worker` used to make a single opaque backend call
    with nothing reporting in between, so a multi-file batch showed a busy
    spinner (`maximum=0`) for its whole duration -- exactly the "somehow
    blocked" feel a merged/long-running batch produces even though the work
    was already off the GUI thread.
    """

    class FakeTask:
        """Minimal `TaskHandle` stand-in that records what it was told."""

        def __init__(self) -> None:
            self.progress_calls: list[tuple[int, object]] = []

        def set_progress(self, value: int, text: object = None) -> None:
            self.progress_calls.append((value, text))

    class FakeClient:
        """Client stub that drives the given progress_callback like the real one."""

        def analyze_files(self, file_paths, progress_callback=None, **kwargs):
            total = len(file_paths)
            for i, path in enumerate(file_paths):
                if progress_callback is not None:
                    progress_callback(i + 1, total, str(path))
            return {"dataframes": {}, "metadata": {}}

    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    tool._client = FakeClient()
    task = FakeTask()

    tool._analysis_worker(["a.spc", "b.spc"], {}, task)

    assert task.progress_calls == [
        (1, "a.spc (1/2)"),
        (2, "b.spc (2/2)"),
    ]
