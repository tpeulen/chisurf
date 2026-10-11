"""The retained wizard page hosts one actual native detector model and surface."""

from __future__ import annotations

import copy
import json
import socket
from pathlib import Path

import pytest
from qtpy import QtWidgets


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Keep all settings/stores scratch and reject external service connections."""
    for name, suffix in {
        "CHISURF_SETTINGS_DIR": "settings",
        "MMFDB_SETTINGS_DIR": "mmfdb",
        "MMFDB_DATABASE_PATH": "mmfdb.sqlite",
        "MMFDB_OBJECT_STORE_ROOT": "objects",
    }.items():
        monkeypatch.setenv(name, str(tmp_path / suffix))
    monkeypatch.chdir(tmp_path)
    from chisurf.core import settings, setup_channel_definition
    from chisurf.core.fio.lut_context import clear_active_setup_lut

    monkeypatch.setattr(settings, "chisurf_settings_path", tmp_path / "settings")
    monkeypatch.setattr(setup_channel_definition.CONFIG, "canonical_file", tmp_path / "setups.json")
    monkeypatch.setitem(settings.cs_settings, "mmfdb", {"default_user_id": "native-page-owner"})

    def forbidden(*args, **kwargs):
        raise AssertionError("Native detector page attempted an external connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    import zmq

    monkeypatch.setattr(zmq.Socket, "connect", forbidden)
    monkeypatch.setattr(zmq.Socket, "bind", forbidden)
    yield
    clear_active_setup_lut()


@pytest.fixture
def definition(tmp_path):
    """A complete portable detector definition with scientific metadata and physical timing."""
    from chisurf.core.setup_channel_definition import ChannelDefinition

    return ChannelDefinition(
        {
            "detectors": {
                "green": {
                    "chs": [8, 0],
                    "micro_time_ranges": [[0, 4095]],
                    "g_factor": 1.25,
                    "l1": 0.05,
                    "l2": 0.02,
                    "g_factor_channels": [850, 1850],
                    "g_factor_decay_uuid": "reference-id",
                    "g_factor_calibration_id": "calibration-id",
                    "unknown_detector": {"keep": [1, 2]},
                }
            },
            "windows": {"prompt": [700, 2000]},
            "tttr_reading": {
                "file_type": "SPC-130",
                "macro_time_resolution": 13.5,
                "micro_time_resolution": 3.2958984375,
                "micro_time_binning": 2,
            },
            "channel_luts": {"0": [0.0, 1.0, 2.0]},
            "channel_shifts": {"1": 2},
            "channel_lut_sources": {"0": "validation.lut"},
            "apply_lut": True,
            "optical_config": {"unknown_optical": {"keep": True}},
            "unknown_setup": {"keep": 7},
        },
        file_path=str(tmp_path / "library.json"),
    )


def _page(qtbot, **kwargs):
    """Construct the new retained QWizardPage host, not the legacy Qt form."""
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.native_page import DetectorWizardPage

    page = DetectorWizardPage(**kwargs)
    qtbot.addWidget(page)
    return page


def test_real_qwizard_owns_one_native_host_and_injected_model(qapp, qtbot, definition):
    """The page fits the existing wizard API without installing any Qt form controls."""
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.native_page import DetectorWizardPage
    from chisurf.plugins.core.setup_channel_definition.gui.app import SetupChannelDefinitionApp

    page = DetectorWizardPage(model=definition, allow_finish=False)
    wizard = QtWidgets.QWizard()
    qtbot.addWidget(wizard)
    wizard.addPage(page)
    try:
        assert isinstance(page, QtWidgets.QWizardPage)
        assert isinstance(page.app, SetupChannelDefinitionApp)
        assert page.model is definition is page.app.model is page.editor.model
        assert page.host.control is page.app and page.layout().count() == 1
        assert not page.findChildren(QtWidgets.QComboBox)
        assert not page.findChildren(QtWidgets.QLineEdit)
        assert not page.findChildren(QtWidgets.QTableWidget)
        assert not page.isComplete()
    finally:
        page.close()


def test_semantic_changes_noops_and_binning_signal_once(qapp, qtbot, definition):
    """Scientific setters retain metadata and do not recurse through unchanged G values."""
    page = _page(qtbot, model=definition)
    changed, bins = [], []
    page.detectorsChanged.connect(lambda: changed.append(True))
    page.micro_time_binningChanged.connect(bins.append)
    try:
        assert page.update_detector("green", {"g_factor": 1.25}) is False
        assert changed == []
        assert page.update_detector("green", {"g_factor": 1.7}) is True
        assert changed == [True] and definition.data["detectors"]["green"]["unknown_detector"] == {
            "keep": [1, 2]
        }
        page.micro_time_binning = 4
        assert bins == [4] and changed == [True]
        page.micro_time_binning = 4
        assert bins == [4] and changed == [True]
        assert page.effective_micro_time_resolution == 13.18359375
        assert page.excitation_period == 13.5
        assert page.micro_time_binning in page.binning_options
    finally:
        page.close()


def test_full_definition_and_preview_roundtrip_with_callback_once(qapp, qtbot, definition):
    """One actual model change reaches its previous callback and the Qt caller once."""
    import numpy as np

    callbacks = []
    definition.on_changed = callbacks.append
    page = _page(qtbot, model=definition)
    notices = []
    page.detectorsChanged.connect(lambda: notices.append(True))
    before = definition.get_settings()
    try:
        data = copy.deepcopy(before)
        data["windows"]["delayed"] = [2000, 4095]
        page.set_settings(data)
        assert len(callbacks) == len(notices) == 1
        assert page.get_settings() == definition.get_settings()
        for key in ("optical_config", "channel_luts", "channel_shifts", "unknown_setup"):
            assert page.get_settings()[key] == before[key]
        page.set_microtime_per_channel_data({8: [2, 4, 6], 0: [1, 2, 3]}, "actual-reference.spc")
        assert np.array_equal(page.get_preview()[8], [2, 4, 6])
        assert (
            page.get_settings()["_microtime_per_channel_decay"]["file_path"]
            == "actual-reference.spc"
        )
    finally:
        page.close()
    definition.changed()
    assert len(callbacks) == 3 and len(notices) == 2


def test_json_working_file_is_distinct_from_named_library_and_parent_forms(
    qapp, qtbot, definition, tmp_path
):
    """A standalone definition loads without overwriting or being replaced by its setup store."""
    raw = tmp_path / "working.json"
    raw.write_text(json.dumps(definition.get_settings()))
    library = tmp_path / "setups.json"
    stored = copy.deepcopy(definition.get_settings())
    stored["detectors"]["green"]["g_factor"] = 4.0
    library.write_text(json.dumps({"setups": {"Other": stored}, "last_used": "Other"}))
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.native_page import DetectorWizardPage

    page = DetectorWizardPage(str(raw), parent, setups_file=str(library))
    try:
        assert page.parent() is parent and page.model.file_path == str(library)
        assert page.detectors["green"]["g_factor"] == 1.25
        assert "Other" in page.available_setups()
        page.select_setup("Other")
        assert page.current_setup_name == page.setup_name == "Other"
        assert page.detectors["green"]["g_factor"] == 4.0
        page.filetype = None
        assert page.filetype is None
    finally:
        page.close()


def test_page_and_native_host_close_owned_app_once(qapp, qtbot, definition, monkeypatch):
    """Repeated closure shuts down the original native worker/host exactly once."""
    page = _page(qtbot, model=definition)
    calls = []
    prior = page.app.close

    def observed():
        calls.append(True)
        prior()

    monkeypatch.setattr(page.app, "close", observed)
    page.show()
    page.close()
    page.host.close()
    page.close()
    qapp.processEvents()
    assert calls == [True] and page.editor._closing


def test_enclosing_parent_close_releases_the_real_native_page(qapp, qtbot, definition, monkeypatch):
    """Embedded pages must release workers when their existing Qt owner closes."""
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.native_page import DetectorWizardPage

    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    page = DetectorWizardPage(None, parent, model=definition)
    calls = []
    prior = page.app.close

    def observed():
        calls.append(True)
        prior()

    monkeypatch.setattr(page.app, "close", observed)
    try:
        parent.close()
        qapp.processEvents()
        assert page.editor._closing and calls == [True]
        parent.close()
        page.close()
        assert calls == [True]
    finally:
        page.close()


def test_hidden_ancestor_reparenting_follows_its_new_owner(qapp, qtbot, definition):
    """Docking a hidden container must not leave lifetime bound to its former window."""
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.native_page import DetectorWizardPage

    outer = QtWidgets.QWidget()
    former = QtWidgets.QWidget()
    qtbot.addWidget(outer)
    qtbot.addWidget(former)
    page = DetectorWizardPage(None, former, model=definition)
    try:
        former.setParent(outer)
        qapp.processEvents()
        assert not page.editor._closing
        outer.close()
        qapp.processEvents()
        assert page.editor._closing
    finally:
        page.close()


def test_explicit_constructor_owner_survives_orphan_dock_reparenting(qapp, qtbot, definition):
    """A legacy tool remains responsible for a pane moved to its hidden orphan dock."""
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.native_page import DetectorWizardPage

    owner = QtWidgets.QWidget()
    orphan = QtWidgets.QWidget()
    qtbot.addWidget(owner)
    qtbot.addWidget(orphan)
    page = DetectorWizardPage(None, owner, model=definition)
    try:
        page.setParent(orphan)
        qapp.processEvents()
        assert owner not in [page.parent()] and not page.editor._closing
        owner.close()
        qapp.processEvents()
        assert page.editor._closing
    finally:
        page.close()


def test_visibility_flags_hide_real_declared_controls(qapp, qtbot, definition):
    """Old constructor flags act on the native page rather than being ignored kwargs."""
    from emtk.testing import Driver

    page = _page(
        qtbot,
        model=definition,
        show_edit_json=False,
        show_save=False,
        show_setups_file=False,
        show_setup_selection=False,
        show_help=False,
        show_tttr_reading=False,
        show_tables=False,
        show_add_inputs=False,
    )
    try:
        driver = Driver(page.app, (800, 700))
        driver.frame(3)
        assert not {
            "edit_json",
            "save_definition",
            "import_setups",
            "export_setups",
            "setup_choice",
            "save",
            "rename",
            "delete",
            "help",
            "page_help",
            "section_reading",
            "section_windows",
            "section_detectors",
            "add_window",
            "add_detector",
        } & set(driver.ids())
        assert page.model is definition
    finally:
        page.close()


def test_complete_definition_export_preserves_metadata_and_named_unknown_fields(
    definition, tmp_path
):
    """The portable writer exports complete state and merges an owned named setup losslessly."""
    from chisurf.core.fio import setup_store

    data = definition.get_settings()
    definition.current_name = "Validation"
    data["_owner"] = setup_store.resolve_active_user_id()
    data["detectors"]["green"]["stored_only"] = {"preserve": 9}
    definition.setups = {"Validation": data}
    target = tmp_path / "definition.json"
    definition.export_definition(target, update_named=True)
    written = json.loads(target.read_text())
    assert written == definition.get_settings()
    saved = json.loads(Path(definition.file_path).read_text())["setups"]["Validation"]
    assert saved["detectors"]["green"]["stored_only"] == {"preserve": 9}
    assert saved["detectors"]["green"]["g_factor_calibration_id"] == "calibration-id"


def test_named_definition_export_preserves_remaining_metadata_without_resurrecting_deleted_detector(
    definition, tmp_path
):
    """The working detector key set is authoritative even when its store has older rows."""
    from chisurf.core.fio import setup_store

    stored = definition.get_settings()
    stored["_owner"] = setup_store.resolve_active_user_id()
    stored["detectors"]["green"]["stored_only"] = {"keep": True}
    stored["detectors"]["deleted"] = copy.deepcopy(stored["detectors"]["green"])
    definition.current_name = "Validation"
    definition.setups = {"Validation": stored}
    definition.export_definition(tmp_path / "definition.json", update_named=True)
    saved = json.loads(Path(definition.file_path).read_text())["setups"]["Validation"]
    assert set(saved["detectors"]) == {"green"}
    assert saved["detectors"]["green"]["stored_only"] == {"keep": True}


def test_definition_export_serialization_failure_keeps_existing_file(definition, tmp_path):
    """A rejected full definition cannot truncate the previous exported bytes."""
    target = tmp_path / "definition.json"
    target.write_bytes(b"existing immutable bytes")
    definition.data["unknown_setup"]["not_json"] = object()
    with pytest.raises(TypeError):
        definition.export_definition(target)
    assert target.read_bytes() == b"existing immutable bytes"


def test_definition_export_rejects_its_named_library_target_before_writing(definition):
    """Definition and library exports cannot report success while overwriting one another."""
    from chisurf.core.fio import setup_store

    stored = definition.get_settings()
    stored["_owner"] = setup_store.resolve_active_user_id()
    definition.current_name = "Validation"
    definition.setups = {"Validation": stored}
    library = Path(definition.file_path)
    library.write_text(json.dumps({"setups": definition.setups}))
    before = library.read_bytes()
    with pytest.raises(ValueError, match="different"):
        definition.export_definition(library, update_named=True)
    assert library.read_bytes() == before


def test_actual_definition_picker_cancel_failure_and_success_control_finish(
    qapp, qtbot, definition, tmp_path, monkeypatch
):
    """Finish follows a completed real save, never merely opening or cancelling its picker."""
    from emtk.testing import Driver

    page = _page(qtbot, model=definition, show_save=True, allow_finish=False)
    finished = []
    page.completeChanged.connect(lambda: finished.append(True))
    driver = Driver(page.app, (1000, 800))
    try:
        driver.frame(3)
        driver.click("save_definition")
        assert page.editor.dialog is not None and not page.isComplete()
        driver.click("Cancel")
        assert not page.isComplete() and finished == []
        writer = definition.export_definition

        def failed(*args, **kwargs):
            raise OSError("controlled failed save")

        monkeypatch.setattr(definition, "export_definition", failed)
        driver.click("save_definition")
        page.editor.dialog.directory = str(tmp_path)
        driver.frame(2)
        driver.click([text[:4] for text in driver.painter.texts if text[5] == "Save"][-1])
        assert "controlled failed save" in page.editor.status
        assert not page.isComplete() and finished == []
        monkeypatch.setattr(definition, "export_definition", writer)
        driver.click("save_definition")
        page.editor.dialog.directory = str(tmp_path)
        driver.frame(2)
        driver.click([text[:4] for text in driver.painter.texts if text[5] == "Save"][-1])
        assert page.isComplete() and finished == [True]
        assert (
            json.loads((tmp_path / "detector_definition.json").read_text())
            == definition.get_settings()
        )
    finally:
        page.close()


def test_named_save_failure_leaves_finish_false_and_preserves_library(
    qapp, qtbot, definition, tmp_path, monkeypatch
):
    """A complete exported file alone cannot claim the requested named update succeeded."""
    from emtk.testing import Driver

    from chisurf.core.setup_channel_definition import ChannelDefinition

    stored = definition.get_settings()
    stored["_owner"] = "native-page-owner"
    library = Path(definition.file_path)
    library.write_text(json.dumps({"setups": {"Validation": stored}, "last_used": "Validation"}))
    definition.current_name = "Validation"
    previous_file = library.read_bytes()
    page = _page(qtbot, model=definition, show_save=True, allow_finish=False)
    driver = Driver(page.app, (1000, 800))

    def fail_store(self, *args, **kwargs):
        raise OSError("controlled named persistence failure")

    try:
        driver.frame(3)
        definition.refresh_setups()  # the page reads the library on a worker thread; settle it before the snapshot
        before = copy.deepcopy(definition.setups)
        monkeypatch.setattr(ChannelDefinition, "_persist", fail_store)
        driver.click("save_definition")
        page.editor.dialog.directory = str(tmp_path)
        driver.frame(2)
        driver.click([text[:4] for text in driver.painter.texts if text[5] == "Save"][-1])
        assert "controlled named persistence failure" in page.editor.status
        assert not page.isComplete()
        assert definition.setups == before and library.read_bytes() == previous_file
        assert (tmp_path / "detector_definition.json").is_file()
    finally:
        page.close()


def test_supplied_filtered_preview_does_not_reread_existing_measurement(
    qapp, qtbot, definition, tmp_path, monkeypatch
):
    """A scientific caller's filtered histograms cannot be replaced by another file read."""
    import shutil

    import numpy as np

    source = Path(__file__).resolve().parents[2] / "test/data/tttr/BH/132/BH_SPC132.spc"
    target = tmp_path / "real-reference.spc"
    shutil.copy2(source, target)
    page = _page(qtbot, model=definition)
    reads = []
    prior = page.editor.read

    def observed(*args, **kwargs):
        reads.append(args)
        return prior(*args, **kwargs)

    monkeypatch.setattr(page.editor, "read", observed)
    try:
        page.set_microtime_per_channel_data({0: [99, 5, 7], 8: [3, 1, 2]}, str(target))
        page.poll_read()
        assert not reads and not page.read_running
        assert np.array_equal(page.get_preview()[0], [99, 5, 7])
    finally:
        page.close()


def test_rejected_wizard_close_preserves_native_surface(qapp, qtbot):
    """An existing dialog may refuse closure without losing its native worker/surface."""
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.native_page import DetectorWizard

    class RefusingWizard(DetectorWizard):
        allow_close = False

        def reject(self):
            """Exercise a real QDialog close rejection, not a fake parent."""
            if self.allow_close:
                super().reject()

    wizard = RefusingWizard()
    qtbot.addWidget(wizard)
    try:
        wizard.show()
        qapp.processEvents()
        wizard.close()
        qapp.processEvents()
        assert wizard.isVisible() and not wizard.detector_page.editor._closing
    finally:
        wizard.allow_close = True
        wizard.close()


@pytest.mark.parametrize(
    "flags,present,absent",
    [
        (
            {"show_edit_json": True, "show_help": False, "show_setup_selection": False},
            {"edit_json"},
            {"help", "page_help", "setup_choice"},
        ),
        (
            {"show_save": True, "show_setup_selection": False},
            {"save_definition"},
            {"setup_choice", "save"},
        ),
        (
            {"show_add_inputs": False, "show_tables": True},
            {"section_detectors"},
            {"add_window", "add_detector"},
        ),
    ],
)
def test_mixed_positive_visibility_flags_are_independent(
    qapp, qtbot, definition, flags, present, absent
):
    """Independent constructor flags cannot hide an unrelated declared action or section."""
    from emtk.testing import Driver

    page = _page(qtbot, model=definition, **flags)
    try:
        driver = Driver(page.app, (1000, 800))
        driver.frame(3)
        assert present <= set(driver.ids())
        assert not absent & set(driver.ids())
    finally:
        page.close()


def test_retained_lut_shift_stays_numeric_and_painted_after_narrow_resize(qapp, qtbot, definition):
    """Resizing the native surface cannot replace the physical +2 shift with a stale row."""
    from emtk.testing import Driver

    definition.data["detectors"]["green"]["chs"] = [0, 1, 8]
    page = _page(qtbot, model=definition)
    driver = Driver(page.app, (1100, 950))
    try:
        for width in (1100, 800):
            driver.draw(size=(width, 950), frames=3)
            control = page.editor._lut_table.control
            index = next(i for i, row in enumerate(control.records) if row["id"] == "1")
            assert control.records[index]["shift"] == definition.data["channel_shifts"]["1"] == 2
            x = control._header_box[0]
            for column, cell_width in zip(control._shown, control._widths):
                if column.key == "shift":
                    break
                x += cell_width
            y = control._body_box[1] + control.order().index(index) * control._row_h
            assert any(
                text[5] == "2"
                and x <= text[0] < x + cell_width
                and y <= text[1] < y + control._row_h
                for text in driver.painter.texts
            )
    finally:
        page.close()


def test_reentrant_detector_notice_close_does_not_request_another_frame(
    qapp, qtbot, definition, monkeypatch
):
    """A caller closing its real page from a signal ends subsequent native dispatch."""
    page = _page(qtbot, model=definition)
    frames = []
    monkeypatch.setattr(page.app, "request_frame", lambda: frames.append(True))
    page.detectorsChanged.connect(page.close)
    page.update_detector("green", {"g_factor": 2.0})
    assert page.editor._closing and frames == []


def test_named_export_callback_closure_cannot_enable_finish(qapp, qtbot, definition, tmp_path):
    """An external save callback may close the page before its success hook runs."""
    from emtk.testing import Driver

    stored = definition.get_settings()
    stored["_owner"] = "native-page-owner"
    Path(definition.file_path).write_text(json.dumps({"setups": {"Validation": stored}}))
    definition.current_name = "Validation"
    owner = {}

    def close_from_callback(settings):
        owner["page"].close()

    definition.on_changed = close_from_callback
    page = _page(qtbot, model=definition, show_save=True, allow_finish=False)
    owner["page"] = page
    finished = []
    page.completeChanged.connect(lambda: finished.append(True))
    driver = Driver(page.app, (1000, 800))
    driver.frame(3)
    definition.refresh_setups()  # the library is read on a worker thread; the named save needs it settled
    driver.click("save_definition")
    page.editor.dialog.directory = str(tmp_path)
    driver.frame(2)
    driver.click([text[:4] for text in driver.painter.texts if text[5] == "Save"][-1])
    assert page.editor._closing and (tmp_path / "detector_definition.json").is_file()
    assert not page.isComplete() and finished == []


def test_real_enclosing_wizard_allocates_native_page_height(qapp, qtbot):
    """The existing onboarding layout must allocate the actual editor beyond its header."""
    from chisurf.plugins.core.setup_channel_definition.wizard import ChisurfWizard

    wizard = ChisurfWizard()
    qtbot.addWidget(wizard)
    try:
        wizard.resize(1400, 1000)
        wizard.show()
        qapp.processEvents()
        assert wizard.filter.height() > 600
        assert wizard.filter.host.height() > 600
    finally:
        wizard.close()


def test_public_wizard_exports_are_native_and_legacy_forms_are_absent(qapp):
    """Fresh source routes retain real native hosts without the former Qt implementations."""
    import importlib.util

    from chisurf.gui.widgets import wizard
    from chisurf.gui.widgets.wizard import tttr_channeldefinition as package
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import native_page

    assert package.DetectorWizardPage is wizard.DetectorWizardPage is native_page.DetectorWizardPage
    assert package.DetectorWizard is wizard.DetectorWizard is native_page.DetectorWizard
    folder = Path(native_page.__file__).parent
    for name in ("tttr_channel_definition", "tttr_channel_definition_json_dialog", "shift_dialog"):
        assert not (folder / (name + ".py")).exists()
        assert importlib.util.find_spec(package.__name__ + "." + name) is None
    assert not (folder / "detector_wizard_page.ui").exists()
    assert not hasattr(package, "JsonEditorDialog")
