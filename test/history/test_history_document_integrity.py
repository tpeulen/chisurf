"""History ownership and fail-closed persistence regressions."""

import json

import pytest

from chisurf.history.core import OperationHistory


def test_event_boundaries_detach_authoritative_payload():
    """Callers and independent subscribers cannot mutate the owned log."""
    history = OperationHistory()
    observed = []
    history.subscribe(lambda event: event["payload"].update(new_value=999))
    history.subscribe(lambda event: observed.append(event["payload"]["new_value"]))
    supplied = {"new_value": 3.0, "nested": [1]}
    returned = history.record("parameter.value", "before", supplied, persist=False)
    supplied["nested"].append(2)
    returned["payload"]["new_value"] = 777
    listed = history.list_events()
    listed[0]["payload"]["new_value"] = 666
    history.tail()[0]["payload"]["nested"].append(3)
    assert history.list_events()[0]["payload"] == {"new_value": 3.0, "nested": [1]}
    assert observed == [3.0]


@pytest.mark.parametrize(
    "bad",
    [
        7,
        [],
        None,
        {"event_id": 1, "timestamp": "today", "action_type": {}, "summary": "x", "payload": {}},
    ],
)
def test_validation_rejects_non_events_without_raising(bad):
    """Validation is total and enforces types rather than coercing values."""
    assert OperationHistory().validate_event(bad) is False


@pytest.mark.parametrize("damage", ["scalar", "malformed", "version", "duplicate", "event"])
@pytest.mark.parametrize("replace", [True, False])
def test_load_is_atomic_fail_closed(tmp_path, damage, replace):
    """Invalid input never repairs, replaces or partly extends live history."""
    history = OperationHistory()
    event = history.record("live", "keep me", {"nested": [2]}, persist=False)
    history.set_checkpoint_capture(lambda: {"science": [1]})
    history.create_checkpoint(0)
    original = history.list_events()
    checkpoint = history.get_checkpoint_before(0)
    lock = history._lock
    header = {"history_version": history.HISTORY_VERSION, "event_count": 1}
    row = dict(event, event_id="incoming")
    lines = [json.dumps(row)]
    if damage == "scalar":
        lines.append("7")
    elif damage == "malformed":
        lines.append("{")
    elif damage == "version":
        header["history_version"] = "999"
    elif damage == "duplicate":
        lines.append(json.dumps(row))
    else:
        lines.append('{"payload":{}}')
    path = tmp_path / "bad.jsonl"
    path.write_text("# CHISURF HISTORY METADATA: " + json.dumps(header) + "\n" + "\n".join(lines))
    result = history.load_jsonl(path, replace=replace)
    assert result["success"] is False
    assert result["loaded_events"] == 0
    assert result["errors"]
    assert history.list_events() == original
    assert history.get_checkpoint_before(0) == checkpoint
    assert history._lock is lock


def test_load_events_validates_duplicates_and_detaches(tmp_path):
    """Direct transport installation follows the same atomic validation rules."""
    history = OperationHistory()
    event = history.record("live", "keep me", persist=False)
    with pytest.raises(ValueError):
        history.load_events([event, event])
    assert history.list_events() == [event]
    other = OperationHistory()
    other.load_events([event])
    event["payload"]["evil"] = 1
    assert other.list_events()[0]["payload"] == {}


def test_save_failure_preserves_existing_destination(tmp_path, monkeypatch):
    """A failed atomic publication leaves the existing durable bytes intact."""
    import os

    history = OperationHistory()
    history.record("live", "value", persist=False)
    destination = tmp_path / "history.jsonl"
    destination.write_bytes(b"previous durable bytes")

    def fail_replace(*args):
        """Inject a publication fault after complete serialization."""
        raise OSError("disk publication failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="publication failed"):
        history.save_jsonl(destination)
    assert destination.read_bytes() == b"previous durable bytes"
    assert list(tmp_path.iterdir()) == [destination]


def test_suppression_is_nested_thread_local_and_replay_idempotent():
    """Replay suppresses its own recording without losing another thread's edit."""
    from concurrent.futures import ThreadPoolExecutor

    history = OperationHistory()
    history.record("value", "original", {"n": 1}, persist=False)
    with history.suppress_recording():
        with history.suppress_recording():
            assert history.record("value", "suppressed", persist=False) == {}
        with ThreadPoolExecutor(1) as pool:
            event = pool.submit(
                history.record, "value", "other thread", {}, None, None, False
            ).result(timeout=5)
        assert event["summary"] == "other thread"
        assert history.record("value", "still suppressed", persist=False) == {}
    before = history.list_events()

    def replay_handler(event):
        """Exercise handlers that ordinarily emit scientific action events."""
        history.record("value", "replayed", event["payload"], persist=False)
        event["payload"]["n"] = 999

    assert history.replay({"value": replay_handler})["replayed"] == 2
    assert history.list_events() == before


def test_checkpoints_are_detached_and_indices_are_validated():
    """A checkpoint describes state after exactly its indexed event."""
    history = OperationHistory()
    history.record("value", "original", persist=False)
    snapshot = {"parameters": {"u": {"value": [2]}}}
    history.set_checkpoint_capture(lambda: snapshot)
    assert history.create_checkpoint(0)
    snapshot["parameters"]["u"]["value"].append(3)
    returned = history.get_checkpoint_before(0)
    returned["snapshot"]["parameters"]["u"]["value"].append(4)
    state, events = history.get_events_from_checkpoint(0)
    state["parameters"]["u"]["value"].append(5)
    assert events == []
    assert history.get_checkpoint_before(0)["snapshot"]["parameters"]["u"]["value"] == [2]
    assert history.create_checkpoint(20) is False
    assert history.create_checkpoint(-2) is False
    for index in [-2, 1, True, 0.5]:
        with pytest.raises(ValueError):
            history.get_events_from_checkpoint(index)


def test_compaction_refuses_to_destroy_indispensable_replay_source():
    """An audit checkpoint is insufficient authority to discard science history."""
    history = OperationHistory()
    for n in range(20):
        history.record("parameter.value", "audit only", {"new_value": n}, persist=False)
    history.set_checkpoint_capture(lambda: {"names": ["not scientific state"]})
    history.create_checkpoint(4)
    original = history.list_events()
    report = history.compact_history(keep_recent=10)
    assert report["compaction_successful"] is False
    assert report["events_removed"] == 0
    assert history.list_events() == original


@pytest.mark.parametrize(
    "fields",
    [
        dict(action_type="", summary="x"),
        dict(action_type="value", summary="x", payload=["bad"]),
        dict(action_type="value", summary="x", payload={"value": float("nan")}),
    ],
)
def test_record_rejects_invalid_event_without_mutation(fields):
    """Record is subject to the same event contract as import."""
    history = OperationHistory()
    before = history.export_state()
    with pytest.raises(ValueError):
        history.record(**fields, persist=False)
    assert history.export_state() == before


def test_event_limit_fails_atomically_instead_of_unbounded_snapshot_growth():
    """Limits require explicit safe compaction rather than silently erasing rows."""
    history = OperationHistory()
    history.set_memory_limits(max_events=100)
    for n in range(100):
        history.record("audit", str(n), persist=False)
    before = history.export_state()
    with pytest.raises(ValueError, match="limit"):
        history.record("audit", "too many", persist=False)
    assert history.export_state() == before


def test_science_resources_exclude_audit_history_to_prevent_snapshot_recursion():
    """Archived audit data is never nested inside a scientific restoration state."""
    from chisurf.core.project import capture_session
    from chisurf.core.project.project import ResourceContext
    from chisurf.history.science import decode_science, encode_science

    project = capture_session(
        [],
        [],
        resources=ResourceContext(
            entries={"history.jsonl": b"previous history envelope", "attachment.bin": b"required"},
            sources={"measurement.csv": b"0,1\n"},
        ),
    )
    encoded = encode_science(project)
    assert "history.jsonl" not in encoded["resources"]["entries"]
    restored = decode_science(encoded)
    assert restored.resources.entries == {"attachment.bin": b"required"}
    assert restored.resources.sources == {"measurement.csv": b"0,1\n"}


def test_explicit_repair_removes_duplicates_and_invalidates_indexed_science():
    """Opt-in audit salvage reports that old scientific indices are unusable."""
    history = OperationHistory()
    event = history.record("audit", "first", persist=False)
    history._events.append(event)
    history._events.append(7)
    history._checkpoints[0] = {"event_index": 0, "snapshot": {"old": [1]}}
    report = history.repair_history()
    assert report["repair_successful"] is True
    assert report["events_removed"] == 2
    assert report["scientific_restoration_discarded"] is True
    assert history.list_events() == [event]
    assert history.checkpoint_count() == 0
    assert history.cursor_index() == 0


@pytest.mark.parametrize(
    "damage", ["missing_version", "missing_envelope", "count_type", "checkpoint_count"]
)
def test_jsonl_requires_complete_v2_metadata(tmp_path, damage):
    """Audit-only legacy rows never masquerade as scientific durable history."""
    history = OperationHistory()
    history.record("audit", "keep existing state", persist=False)
    path = tmp_path / "history.jsonl"
    history.save_jsonl(path)
    original = history.export_state()
    lines = path.read_text().splitlines()
    header = json.loads(lines[0].split(": ", 1)[1])
    if damage == "missing_version":
        lines = lines[1:]
    else:
        if damage == "missing_envelope":
            header.pop("state")
        elif damage == "count_type":
            header["event_count"] = True
        else:
            header["checkpoint_count"] = 99
        lines[0] = "# CHISURF HISTORY METADATA: " + json.dumps(header)
    path.write_text("\n".join(lines))
    assert history.load_jsonl(path)["success"] is False
    assert history.export_state() == original


def test_checkpoint_capture_cannot_label_current_state_as_an_old_event():
    """Checkpoint labels are acknowledged cursor indices, never arbitrary offsets."""
    history = OperationHistory()
    history.set_checkpoint_capture(lambda: {"state": "current"})
    history.record("audit", "first", persist=False)
    history.record("audit", "second", persist=False)
    assert history.create_checkpoint(0) is False
    for index in ["0", True, -2, 99]:
        with pytest.raises(ValueError):
            history.get_checkpoint_before(index)


def test_import_enforces_declared_event_bound_atomically():
    """Loaded scientific envelopes cannot bypass the in-memory event limit."""
    source = OperationHistory()
    for n in range(101):
        source.record("audit", str(n), persist=False)
    target = OperationHistory()
    target.set_memory_limits(max_events=100)
    before = target.export_state()
    with pytest.raises(ValueError, match="limit"):
        target.import_state(source.export_state())
    assert target.export_state() == before
