"""Native reader forms retain the dialect and bind the original science owner."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from emtk.testing import Driver

from chisurf.core.dataspec import load_view_spec


def _reader(typed=False):
    """A declared form with real value callbacks, choices and model actions."""
    spec = {
        "sections": [{"type": "panel", "title": "Acquisition", "sections": [
            {"type": "value", "attr": "gain", "label": "Gain", "kind": "float",
             "minimum": 0, "maximum": 100, "call": "gain_changed",
             "description": "Acquisition gain."},
            {"type": "toggle", "attr": "enabled", "label": "Enabled",
             "description": "Enable acquisition."},
            {"type": "choice", "attr": "mode", "label": "Mode",
             "options_source": "modes", "description": "Acquisition mode."},
            {"type": "button_row", "buttons": [{"label": "Apply", "action": "apply",
             "description": "Apply the current reader settings."}]},
        ]}]
    }
    events = []
    model = SimpleNamespace(
        gain=3.25, enabled=False, mode="second", name="Native reader",
        modes=lambda: ["first", "second"], gain_changed=lambda value: events.append(value),
        apply=lambda: events.append("apply"), view_spec=lambda: load_view_spec(spec) if typed else spec,
    )
    return model, spec, events


@pytest.mark.parametrize("typed", [False, True])
def test_declared_values_callbacks_and_actions_use_the_original_reader(typed):
    """The native form never copies or resets values while constructing its controls."""
    from emtk.events import CONTROL_MODIFIER
    from emtk.keys import KEY_A, KEY_RETURN

    from chisurf.emtk.reader_settings import ReaderSettingsApp

    reader, _spec, events = _reader(typed)
    app = ReaderSettingsApp(reader)
    driver = Driver(app, (760, 480))
    driver.frame(2)
    assert app.model is reader
    assert reader.gain == 3.25 and reader.mode == "second"
    assert {"gain", "enabled", "mode", "apply"} <= set(app.item_rects)
    driver.click("enabled")
    assert reader.enabled
    driver.click("gain")
    driver.key(KEY_A, modifiers=CONTROL_MODIFIER)
    driver.type("4.75")
    driver.key(KEY_RETURN)
    assert reader.gain == 4.75
    assert events == [4.75]
    driver.click("apply")
    assert events == [4.75, "apply"]
    app.close()


def test_typed_conversion_preserves_nested_type_and_callback_metadata():
    """Use the existing section registry; asdict alone would lose every JSON type."""
    from chisurf.emtk.reader_settings import native_reader_spec

    reader, _spec, _events = _reader(typed=True)
    converted = native_reader_spec(reader.view_spec())
    panel = converted["sections"][0]
    assert panel["type"] == "panel"
    assert panel["sections"][0]["type"] == "value"
    assert panel["sections"][0]["call"] == "gain_changed"
    assert panel["sections"][2]["options_source"] == "modes"
    assert panel["sections"][3]["buttons"][0]["action"] == "apply"


@pytest.mark.parametrize("section", [
    {"type": "custom", "key": "unregistered"},
    {"type": "curve_input", "attr": "response"},
    {"type": "plot", "source": "series"},
])
def test_unsupported_declarations_fail_before_a_partial_form_is_built(section):
    """An unimplemented browse, dataset or custom field cannot disappear quietly."""
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    reader = SimpleNamespace(view_spec=lambda: {"sections": [section]})
    with pytest.raises(ValueError, match="unsupported"):
        ReaderSettingsApp(reader)


def test_no_declared_controls_is_an_explicit_error():
    """A malformed declaration cannot create a successful empty reader surface."""
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    with pytest.raises(ValueError, match="sections"):
        ReaderSettingsApp(SimpleNamespace(view_spec=lambda: {"sections": []}))


def test_raw_native_metadata_is_preserved_without_mutating_the_declaration():
    """Native layout fields never pass through the legacy dataclass loader."""
    from chisurf.emtk.reader_settings import native_reader_spec

    raw = {"sections": [{"type": "value", "attr": "gain", "kind": "float",
                         "weight": 2, "min_chars": 9, "wrap_before": True}]}
    converted = native_reader_spec(raw)
    assert converted == raw
    converted["sections"][0]["weight"] = 5
    assert raw["sections"][0]["weight"] == 2


def _file_reader(typed=False, callback=False):
    """A standard file input with an optional scientific owner setter."""
    reader = SimpleNamespace(filename="", changed=[])

    def selected(path):
        """Record which resolved path the real source factory delivered."""
        reader.filename = path
        reader.changed.append(path)

    reader.selected = selected
    section = {"type": "value", "attr": "filename", "kind": "file", "label": "Measurement",
               "description": "Input measurement file."}
    if callback:
        section["call"] = "selected"
    reader.view_spec = lambda: load_view_spec({"sections": [section]}) if typed else {"sections": [section]}
    return reader


@pytest.mark.parametrize("typed", [False, True])
def test_file_browse_delivers_the_chosen_path_through_the_declared_setter(tmp_path, typed):
    """The same native FileDialog powers raw JSON and legacy typed file declarations."""
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    source = tmp_path / "measurement.txt"
    source.write_text("1 10\n2 20\n")
    reader = _file_reader(typed=typed, callback=True)
    app = ReaderSettingsApp(reader)
    driver = Driver(app, (920, 640))
    driver.frame(2)
    driver.click("filename.browse")
    assert app.file_dialog is not None
    app.file_dialog.directory = str(tmp_path)
    driver.frame(2)
    driver.click(source.name)
    driver.click("Open")
    assert reader.filename == str(source)
    assert reader.changed == [str(source)]
    app.close()


def test_data_source_database_uses_the_existing_materialization_contract(tmp_path):
    """MMFDB resolves the selected object; the field receives its local path."""
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    source = tmp_path / "stored.txt"
    source.write_text("1 10\n2 20\n")
    calls = []

    class Client:
        """Only the same browse/open RPCs used by the production DatasetPicker."""

        def call(self, method, params):
            """Provide one registered measurement and materialize its real local file."""
            calls.append((method, params))
            if method == "mmfdb.datasets.browse":
                return {"datasets": [{"artifact_id": "measurement", "original_filename": "stored.txt",
                                      "artifact_kind": "raw_measurement", "data_format": "txt"}],
                        "total": 1}
            assert method == "mmfdb.datasets.open"
            return {"local_path": str(source)}

    reader = _file_reader(callback=True)
    reader.view_spec = lambda: {"sections": [{"type": "custom", "key": "data_source",
        "options": {"attr": "filename", "call": "selected", "label": "Measurement",
                    "description": "Registered measurement.", "mmfdb_kinds": ["raw_measurement"]}}]}
    app = ReaderSettingsApp(reader, dataset_client=Client())
    driver = Driver(app, (920, 640))
    driver.frame(2)
    driver.click("filename.database")
    assert app.picker is not None
    if app.picker._pending is not None:
        app.picker._pending.result(timeout=10)
    driver.frame(2)
    driver.click("stored.txt [raw_measurement] (txt)")
    driver.click("Open selected")
    if app.picker._pending is not None:
        app.picker._pending.result(timeout=10)
    driver.frame(2)
    assert reader.filename == str(source)
    assert reader.changed == [str(source)]
    assert [method for method, _params in calls] == ["mmfdb.datasets.browse", "mmfdb.datasets.open"]
    app.close()


def test_directory_input_has_a_native_folder_dialog_and_preserves_cancel(tmp_path):
    """A typed directory field remains a folder chooser rather than a plain text box."""
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    reader = SimpleNamespace(folder=str(tmp_path), view_spec=lambda: load_view_spec({"sections": [
        {"type": "value", "kind": "directory", "attr": "folder", "label": "Folder"}
    ]}))
    app = ReaderSettingsApp(reader)
    driver = Driver(app, (920, 640))
    driver.frame(2)
    driver.click("folder.browse")
    assert app.file_dialog.mode == "folder"
    driver.frame(2)
    driver.click("Cancel")
    assert app.file_dialog is None
    assert reader.folder == str(tmp_path)
    app.close()


def test_drops_use_the_same_input_setter_and_closing_never_closes_the_reader(tmp_path):
    """A drop changes the source once; closing the view preserves the scientific owner."""
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    reader = _file_reader(callback=True)
    reader.close = lambda: pytest.fail("the settings view does not own the reader")
    app = ReaderSettingsApp(reader)
    source = tmp_path / "drop.txt"
    source.write_text("1 10\n")
    assert app.on_files_dropped([str(source)])
    assert reader.filename == str(source) and reader.changed == [str(source)]
    app.close()
    app.close()
    assert app.closed


def test_source_drop_filters_do_not_reject_materialized_paths_or_clearing_the_input(tmp_path):
    """Extension rules are drop guards; a database's content-addressed path has no suffix."""
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    reader = _file_reader(callback=True)
    reader.view_spec = lambda: {"sections": [{"type": "custom", "key": "data_source",
        "options": {"attr": "filename", "call": "selected", "extensions": ["txt"]}}]}
    app = ReaderSettingsApp(reader)
    assert not app.on_files_dropped([str(tmp_path / "unexpected.bin")])
    app.sources["filename"].path = str(tmp_path / "materialized-object-sha256")
    app.sources["filename"].path = ""
    assert reader.filename == "" and len(reader.changed) == 2
    app.close()
    assert not app.on_files_dropped([str(tmp_path / "late.txt")])


def test_read_only_source_disables_browse_database_and_drop_without_changing_its_value():
    """The reader's immutable input remains readable and never opens a writer."""
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    reader = _file_reader(callback=True)
    reader.filename = "measured.txt"
    reader.view_spec = lambda: {"sections": [{"type": "custom", "key": "data_source",
        "options": {"attr": "filename", "call": "selected", "read_only": True}}]}
    app = ReaderSettingsApp(reader)
    driver = Driver(app, (760, 480))
    driver.frame(2)
    driver.click("filename.browse")
    driver.click("filename.database")
    assert app.file_dialog is None and app.picker is None
    assert not app.on_files_dropped(["other.txt"])
    assert reader.filename == "measured.txt" and reader.changed == []
    app.close()


def test_late_database_path_callback_cannot_change_a_closed_reader_view(tmp_path):
    """A queued picker delivery retains the original callback after the host closes."""
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    class Client:
        """Keep database access isolated while creating the production picker callback."""

        def call(self, method, params):
            """Return an empty catalogue; the test delivers the delayed resolved path."""
            assert method == "mmfdb.datasets.browse"
            return {"datasets": [], "total": 0}

    reader = _file_reader(callback=True)
    reader.filename = "measured.txt"
    app = ReaderSettingsApp(reader, dataset_client=Client())
    app.sources["filename"].database()
    deliver = app.picker.on_paths
    app.close()
    deliver([tmp_path / "late-materialized.txt"])
    assert reader.filename == "measured.txt"
    assert reader.changed == []
