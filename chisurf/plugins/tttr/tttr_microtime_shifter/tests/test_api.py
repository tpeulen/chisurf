"""Tests for the Micro-time Shifter API layer."""

from __future__ import annotations

import json
from typing import Any

from chisurf.plugins.tttr.tttr_microtime_shifter.api.contract import (
    CONTRACT_VERSION,
    contract_descriptor,
    service_success,
    shift_request_from_payload,
    shift_request_to_payload,
    shift_result_to_payload,
)
from chisurf.plugins.tttr.tttr_microtime_shifter.api.models import (
    MMFDBContext,
    ShiftRequest,
    ShiftResult,
)


def test_contract_descriptor_defines_workflow_io() -> None:
    """Contract defines microtime_shift.apply input/output."""
    desc = contract_descriptor()
    assert desc["plugin_id"] == "microtime_shifter"
    assert desc["contract_version"] == CONTRACT_VERSION
    assert "Apply" in desc["inputs"]
    assert "ShiftResult" in desc["outputs"]


def test_shift_request_payload_roundtrip() -> None:
    """Shift request round-trips through JSON."""
    original = ShiftRequest(
        files=["/data/test.ptu"],
        global_shift=2,
        channel_shifts={0: 1, 1: -1},
        filetype="ptu",
        output_dir="/output",
        mmfdb=MMFDBContext(enabled=True, sample_id="sample_001"),
    )
    payload = shift_request_to_payload(original)
    restored = shift_request_from_payload(payload)
    assert restored.files == original.files
    assert restored.global_shift == original.global_shift
    assert restored.channel_shifts == original.channel_shifts
    assert restored.filetype == original.filetype
    assert restored.output_dir == original.output_dir
    assert restored.mmfdb.enabled == original.mmfdb.enabled
    assert restored.mmfdb.sample_id == original.mmfdb.sample_id


def test_shift_result_payload_is_json_safe() -> None:
    """ShiftResult serializes to a JSON-safe dict."""
    result = ShiftResult(
        output_paths_by_file={"/data/test.ptu": "/output/test_shifted.ptu"},
        applied_shifts_by_file={
            "/data/test.ptu": {
                "global_shift": 2,
                "channel_shifts": {0: 1, 1: 3},
            },
        },
        mmfdb_artifacts={"input_artifacts": {}, "output_artifacts": {}},
        warnings=[],
    )
    payload = shift_result_to_payload(result)
    json.dumps(payload)  # must not raise


def test_shift_request_from_payload_accepts_nested_mmfdb() -> None:
    """MMFDB context is properly parsed from nested payload."""
    payload: dict[str, Any] = {
        "files": ["/data/test.ptu"],
        "global_shift": 1,
        "channel_shifts": {"0": 2, "1": -1},
        "mmfdb": {
            "enabled": True,
            "sample_id": "s1",
            "register_missing_inputs": False,
            "setup_id": "setup_01",
            "setup_version": 1,
        },
    }
    request = shift_request_from_payload(payload)
    assert request.mmfdb.enabled is True
    assert request.mmfdb.sample_id == "s1"
    assert request.mmfdb.register_missing_inputs is False


def test_shift_request_from_payload_normalizes_channel_shifts() -> None:
    """Channel shift keys are normalized to int."""
    payload: dict[str, Any] = {
        "files": ["/data/test.ptu"],
        "channel_shifts": {"0": 5, "3": -2},
    }
    request = shift_request_from_payload(payload)
    assert request.channel_shifts == {0: 5, 3: -2}


def test_service_success_wraps_result() -> None:
    """Service success envelope wraps ShiftResult correctly."""
    result = ShiftResult(output_paths_by_file={"/a.ptu": "/a_shifted.ptu"})
    envelope = service_success(result)
    assert envelope["ok"] is True
    assert envelope["result"]["output_paths_by_file"]["/a.ptu"] == "/a_shifted.ptu"


def test_service_success_wraps_dict() -> None:
    """Service success envelope wraps plain dict correctly."""
    envelope = service_success({"path": "/test.ptu"})
    assert envelope["ok"] is True
    assert envelope["result"]["path"] == "/test.ptu"


def test_contract_descriptor_is_json_safe() -> None:
    """Contract descriptor is JSON-serializable."""
    desc = contract_descriptor()
    json.dumps(desc)
