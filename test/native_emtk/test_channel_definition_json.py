"""Complete native JSON edits preserve portable settings and never write a saved setup implicitly."""

from __future__ import annotations

import copy
import json
import socket

import pytest


@pytest.fixture
def editor(tmp_path, monkeypatch):
    """Use the actual native host app over a scratch definition and isolated stores."""
    for key, path in {
        "CHISURF_SETTINGS_DIR": tmp_path / "settings",
        "MMFDB_SETTINGS_DIR": tmp_path / "mmfdb",
        "MMFDB_DATABASE_PATH": tmp_path / "db.sqlite",
        "MMFDB_OBJECT_STORE": tmp_path / "objects",
    }.items():
        monkeypatch.setenv(key, str(path))

    def forbidden(*args, **kwargs):
        raise AssertionError("Native JSON editor attempted an external connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    from emtk.testing import Driver

    from chisurf.core.fio import setup_store
    from chisurf.core.fio.lut_context import clear_active_setup_lut
    from chisurf.core.setup_channel_definition import ChannelDefinition
    from chisurf.plugins.core.setup_channel_definition.gui.app import SetupChannelDefinitionApp

    monkeypatch.setattr(setup_store, "resolve_active_user_id", lambda: "validation-owner")
    settings = {
        "setup_name": "Validation",
        "_owner": "validation-owner",
        "_is_public": False,
        "detectors": {
            "donor": {
                "chs": [0, 1],
                "micro_time_ranges": [[0, 32]],
                "g_factor": 1.25,
                "l1": 0.05,
                "l2": 0.02,
                "g_factor_channels": [7, 20],
                "g_factor_decay_uuid": "b04555d2-22f2-4a73-8fca-c47627d21131",
                "g_factor_calibration_id": "db530c47-e9c7-41bb-ad9b-f145838e6cde",
                "future_detector_metadata": {"untouched": [1, 2]},
            }
        },
        "windows": {"prompt": [0, 32]},
        "tttr_reading": {
            "file_type": "SPC-130",
            "macro_time_resolution": 25.0,
            "micro_time_resolution": 50.0,
            "micro_time_binning": 2,
        },
        "channel_luts": {"0": [0, 1, 2, 3]},
        "channel_shifts": {"0": 2},
        "channel_lut_sources": {"0": "validation-lut.dat"},
        "apply_lut": False,
        "optical_config": {"unknown_optical_metadata": {"preserve": True}},
        "future_metadata": {"version": 7},
        "_microtime_per_channel_decay": {
            "file_path": "validation-preview.spc",
            "channels": {"0": [2, 4, 6], "1": [1, 2, 3]},
        },
        "_raw_microtime_per_channel_decay": {"channels": {"0": [2, 4, 6]}},
    }
    path = tmp_path / "setups.json"
    path.write_text(json.dumps({"setups": {"Validation": settings}, "last_used": "Validation"}))
    model = ChannelDefinition(settings, file_path=path)
    model.setups = {"Validation": copy.deepcopy(settings)}
    model.last_used = "Validation"
    notices: list[dict] = []
    app = SetupChannelDefinitionApp(model=model, autoload=False, on_changed=notices.append)
    ui = Driver(app, (1200, 850))
    yield app, ui, notices, path
    app.close()
    clear_active_setup_lut()


def replace_json(app, ui, text):
    """Deliver select-all and a real multi-character text-input event to the native editor."""
    from chisurf.plugins.emtk_test_input import CTRL

    ui.click("json_text")
    app.key(0x41, "a", CTRL)
    ui.draw(1)
    app.key(0, text)
    ui.draw(2)


def test_live_complete_definition_json_control_is_reachable(editor):
    app, ui, _, _ = editor
    ui.draw(2)
    assert "edit_json" in app.item_rects
    ui.click("edit_json")
    assert app.page.json_window.open
    assert json.loads(app.page.json_text) == app.model.get_settings()
    assert {"json_text", "apply_json", "cancel_json"} <= app.item_rects.keys()


def test_real_json_apply_preserves_metadata_ids_stores_and_refreshes_cells(editor):
    app, ui, notices, path = editor
    model, data, setups, original_file = (
        app.model,
        app.model.data,
        app.model.setups,
        path.read_bytes(),
    )
    before = model.get_settings()
    app.page.detector_rows()
    edited = copy.deepcopy(before)
    edited["detectors"]["donor"].update(l1=0.071, l2=0.042, g_factor_channels=[8, 18])
    edited["future_metadata"]["user_edit"] = "kept"
    ui.click("edit_json")
    replace_json(app, ui, json.dumps(edited, indent=2))
    ui.click("apply_json")
    assert not app.page.json_window.open
    assert app.model is model and app.model.data is not data
    assert model.setups is setups and model.last_used == "Validation"
    assert model.file_path == path and path.read_bytes() == original_file
    assert len(notices) == 1
    detector = model.get_settings()["detectors"]["donor"]
    assert detector["l1"] == 0.071 and detector["l2"] == 0.042
    assert detector["g_factor_channels"] == [8, 18]
    for key in ("g_factor_decay_uuid", "g_factor_calibration_id", "future_detector_metadata"):
        assert detector[key] == before["detectors"]["donor"][key]
    for key in (
        "_owner",
        "_is_public",
        "channel_luts",
        "channel_lut_sources",
        "optical_config",
        "_microtime_per_channel_decay",
        "_raw_microtime_per_channel_decay",
    ):
        assert model.get_settings()[key] == before[key]
    assert model.get_settings()["future_metadata"]["user_edit"] == "kept"
    assert model.get_settings()["tttr_reading"]["effective_micro_time_resolution"] == 100.0
    row = app.page.detector_rows()[0]
    assert [row["l1"], row["l2"], row["gch"]] == ["0.071", "0.042", "8-18"]


@pytest.mark.parametrize(
    "text", ['{"detectors":', "[]", '{"windows": {"broken": []}}', '{"tttr_reading": "broken"}']
)
def test_invalid_json_keeps_draft_error_and_entire_previous_definition(editor, text):
    app, ui, notices, path = editor
    previous = {
        "data": copy.deepcopy(app.model.data),
        "last_used": app.model.last_used,
        "preview_path": app.model.preview_path,
        "preview": app.model.preview,
    }
    file_bytes = path.read_bytes()
    ui.click("edit_json")
    replace_json(app, ui, text)
    ui.click("apply_json")
    assert app.page.json_window.open and app.page.json_error
    assert app.page.json_text == text
    assert app.model.data == previous["data"] and app.model.last_used == previous["last_used"]
    assert not notices and path.read_bytes() == file_bytes
    assert app.model.preview_path == previous["preview_path"]
    assert app.model.preview is previous["preview"]


def test_cancel_reopen_and_readonly_never_apply_a_draft(editor):
    app, ui, notices, path = editor
    previous, file_bytes = app.model.get_settings(), path.read_bytes()
    ui.click("edit_json")
    replace_json(app, ui, '{"future_metadata": {"cancelled": true}}')
    ui.click("cancel_json")
    assert not app.page.json_window.open and app.model.get_settings() == previous
    ui.click("edit_json")
    assert json.loads(app.page.json_text) == previous
    app.page.read_only = True
    replace_json(app, ui, "{}")
    ui.click("apply_json")
    assert app.model.get_settings() == previous and not notices
    ui.click("cancel_json")
    ui.click("edit_json")
    assert not app.page.json_window.open
    assert path.read_bytes() == file_bytes


def test_declared_json_editor_description_is_a_real_hover_tooltip(editor):
    """Hover the actual editor rectangle, rather than inspecting its schema alone."""
    import time

    app, ui, _, _ = editor
    ui.click("edit_json")
    x, y, width, height = ui.rect("json_text")
    app.pointer_move(x + width / 2, y + height / 2)
    ui.draw(2)
    time.sleep(0.65)
    painted = " ".join(ui.draw(2).strings)
    assert "Raw complete detector setup JSON" in painted
    assert "calibration identifiers" in painted and "unknown metadata" in painted
