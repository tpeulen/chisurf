"""Detector-definition export: the portable writer and the named library stay lossless.

The Qt wizard page that hosted these is gone; the emtk detector page is covered by
``test/native_emtk/test_channel_definition*.py``.
"""

from __future__ import annotations

import copy
import json
import socket
from pathlib import Path

import pytest


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
