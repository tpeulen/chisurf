"""The existing import header targets native reader sources without a Qt controller."""

from pathlib import Path
from types import SimpleNamespace

from emtk.testing import Driver

from chisurf.core.experiments.tcspc import TCSPCReader
from chisurf.emtk.reader_settings import ReaderSettingsApp
from chisurf.gui.main import Main

SOURCE = Path("test/data/tcspc/ibh_sample/Decay_577D.txt").resolve()


def test_import_header_reads_the_native_selected_file_with_the_original_reader(monkeypatch):
    """A selected native source imports once, with the scientific owner unchanged."""
    import chisurf.core.actions as actions

    reader = TCSPCReader(filename=str(SOURCE), skiprows=10, record_provenance=False)
    seen = []

    def dispatch(name, payload):
        """Exercise actual file decoding through the owner delivered by the header."""
        assert name == "dataset.add"
        assert payload["experiment_reader"] is reader
        group = payload["experiment_reader"].get_data(filename=payload["filename"])
        seen.append(group)
        return {"ok": True}

    monkeypatch.setattr(actions, "dispatch", dispatch)
    Main.onAddDataset(SimpleNamespace(current_setup=reader))
    assert len(seen) == 1 and len(seen[0]) == 1
    assert seen[0][0].data_reader is reader


def test_empty_native_source_opens_the_existing_picker_and_dispatches_only_after_selection(
    monkeypatch, tmp_path
):
    """The asynchronous chooser neither imports early nor retargets a later reader."""
    import chisurf.core.actions as actions

    source = tmp_path / "measurement.txt"
    source.write_text("0 10\n1 20\n")
    reader = TCSPCReader(record_provenance=False)
    app = ReaderSettingsApp(reader)
    driver = Driver(app, (900, 1050))
    driver.frame(2)
    main = SimpleNamespace(
        current_setup=reader,
        _native_reader_settings_hosts={id(reader): SimpleNamespace(control=app)},
    )
    seen = []
    monkeypatch.setattr(actions, "dispatch", lambda name, payload: seen.append((name, payload)))
    Main.onAddDataset(main)
    assert app.file_dialog is not None and not seen
    # Changing the active setup cannot reinterpret the outstanding input selection.
    main.current_setup = TCSPCReader(record_provenance=False)
    app.file_dialog.directory = str(tmp_path)
    driver.frame(2)
    driver.click(source.name)
    driver.click("Open")
    assert len(seen) == 1
    assert seen[0][1]["experiment_reader"] is reader
    assert seen[0][1]["filename"] == str(source)
    driver.frame(2)
    assert len(seen) == 1
    app.close()


def test_legacy_controller_filename_path_is_retained(monkeypatch):
    """The untouched controller path still supplies its filename in the same way."""
    import chisurf.core.actions as actions

    calls = []
    controller = SimpleNamespace(get_filename=lambda: SOURCE)
    main = SimpleNamespace(current_setup=SimpleNamespace(controller=controller))
    monkeypatch.setattr(actions, "dispatch", lambda name, payload: calls.append((name, payload)))
    Main.onAddDataset(main)
    assert calls == [("dataset.add", {"filename": SOURCE.as_posix(), "experiment_reader": None})]
