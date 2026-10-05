from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import chisurf as cs
from chisurf import typing
from chisurf.core.actions._infra import canonical as _canon


def _json_fallback(value: typing.Any) -> str:
    """Return a text stand-in for a value JSON cannot represent.

    Action payloads legitimately carry live objects — ``dataset.add`` records
    the reader instance it was handed — and those cannot be encoded. Writing
    the repr keeps the surrounding event readable instead of failing the
    whole file.

    Parameters
    ----------
    value : object
        The value the encoder could not handle.

    Returns
    -------
    str
    """
    try:
        return f"<{type(value).__name__}: {value!r}>"[:500]
    except Exception:
        return f"<{type(value).__name__}>"


def json_safe_payload(payload: typing.Any, _depth: int = 0) -> typing.Any:
    """Return *payload* with anything JSON cannot encode replaced by text.

    History is a durable record: it is written to JSONL and embedded whole
    into a ``.cs.pto`` project. An action payload, however, holds whatever the
    caller passed — ``dataset.add`` is handed a live reader object — and one
    such value used to make **saving a project impossible**, because the
    events are serialised as part of it.

    Sanitising here rather than at each writer keeps every consumer safe and
    stops the live object being held alive by the event list.

    Parameters
    ----------
    payload : object
        The value to sanitise; usually the action payload dict.
    _depth : int
        Recursion guard for deeply nested structures.

    Returns
    -------
    object
        A structure containing only JSON-encodable values.

    Examples
    --------
    >>> json_safe_payload({"n": 1, "reader": object()})["n"]
    1
    >>> json_safe_payload({"reader": object()})["reader"].startswith("<object")
    True
    """
    if _depth > 12:
        return _json_fallback(payload)
    if payload is None or isinstance(payload, (str, int, float, bool)):
        return payload
    if isinstance(payload, dict):
        return {str(key): json_safe_payload(value, _depth + 1) for key, value in payload.items()}
    if isinstance(payload, (list, tuple, set)):
        return [json_safe_payload(item, _depth + 1) for item in payload]
    try:
        json.dumps(payload)
    except (TypeError, ValueError):
        return _json_fallback(payload)
    return payload


class OperationHistory:
    """Document-owned audit events and acknowledged scientific restoration states."""

    # Version management
    HISTORY_VERSION = "2.0"
    SUPPORTED_VERSIONS = ["2.0"]

    DEFAULT_CHECKPOINT_INTERVAL = 50
    DEFAULT_MAX_CHECKPOINTS = 20  # cap in-memory snapshots; 0 disables eviction

    def __init__(
        self,
        checkpoint_interval: int = DEFAULT_CHECKPOINT_INTERVAL,
        max_checkpoints: int = DEFAULT_MAX_CHECKPOINTS,
    ):
        self._events: typing.List[typing.Dict[str, typing.Any]] = []
        self._lock = threading.RLock()
        self._subscribers: typing.List[typing.Callable[[typing.Dict[str, typing.Any]], None]] = []
        self._state_subscribers: list[typing.Callable[[dict[str, typing.Any]], None]] = []
        self._checkpoints: typing.Dict[int, typing.Dict[str, typing.Any]] = {}
        self._checkpoint_interval = max(1, int(checkpoint_interval))
        # Bound the optional audit projection cache. Scientific restoration
        # retains its complete canonical sources separately in _science_states;
        # those sources are never evicted as if audit events could rebuild them.
        self._max_checkpoints = max(0, int(max_checkpoints))
        self._checkpoint_capture_fn: typing.Optional[
            typing.Callable[[], typing.Dict[str, typing.Any]]
        ] = None
        self._recording_context = threading.local()
        self._cursor = -1
        self._science_states: dict[int, dict[str, typing.Any]] = {}
        self._baseline: dict[str, typing.Any] | None = None
        self._science_capture = None
        self._science_publish = None
        # Memory management settings
        self._max_events = 10000  # Maximum number of events to keep in memory
        self._auto_compact_threshold = 5000  # Compact when exceeding this number of events

    def record(
        self,
        action_type: str,
        summary: str,
        payload: typing.Optional[typing.Dict[str, typing.Any]] = None,
        source_uid: typing.Optional[str] = None,
        target_uid: typing.Optional[str] = None,
        persist: bool = True,
    ) -> typing.Dict[str, typing.Any]:
        with self._lock:
            if getattr(self._recording_context, "depth", 0):
                return {}
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_type": str(action_type),
            "source_uid": None if source_uid is None else str(source_uid),
            "target_uid": None if target_uid is None else str(target_uid),
            "payload": json_safe_payload(payload or {}),
            "summary": str(summary),
        }
        self._validated_events([event])
        with self._lock:
            length = self._cursor + 1 if self._science_capture is not None else len(self._events)
            if length >= self._max_events:
                raise ValueError(
                    "History event limit reached; explicit scientific compaction required"
                )
            state = None
            if self._science_capture is not None:
                from chisurf.history.science import encode_science, science_fingerprint

                state = encode_science(self._science_capture())
                current = (
                    self._baseline if self._cursor == -1 else self._science_states.get(self._cursor)
                )
                unchanged = current is not None and science_fingerprint(
                    current
                ) == science_fingerprint(state)
                if unchanged and self._cursor < len(self._events) - 1:
                    if len(self._events) >= self._max_events:
                        raise ValueError("History event limit reached")
                    # Audit inspection inserts a logical row at the acknowledged
                    # cursor; retain the exact scientific redo branch after it.
                    index = self._cursor + 1
                    self._science_states = {
                        (old + 1 if old >= index else old): value
                        for old, value in self._science_states.items()
                    }
                    checkpoints = {}
                    for old, checkpoint in self._checkpoints.items():
                        shifted = old + 1 if old >= index else old
                        checkpoints[shifted] = dict(checkpoint, event_index=shifted)
                    self._checkpoints.clear()
                    self._checkpoints.update(checkpoints)
                    self._events.insert(index, event)
                    self._science_states[index] = state
                    self._cursor = index
                    subscribers = list(self._subscribers)
                    event_index = index
                    state = None
                else:
                    event_index = -1
                # Acknowledged edits from a historical cursor replace the redo branch.
                if event_index == -1:
                    del self._events[self._cursor + 1 :]
                    for index in list(self._science_states):
                        if index > self._cursor:
                            del self._science_states[index]
                    for index in list(self._checkpoints):
                        if index > self._cursor:
                            del self._checkpoints[index]
            else:
                event_index = -1
            if event_index == -1:
                self._events.append(event)
                event_index = len(self._events) - 1
                self._cursor = event_index
                if state is not None:
                    self._science_states[event_index] = state
                subscribers = list(self._subscribers)
        self._maybe_create_checkpoint(event_index)
        for callback in subscribers:
            try:
                callback(copy.deepcopy(event))
            except Exception:
                pass
        self._emit_log(event)
        # Durable, best-effort projection into MMFDB. The in-memory list above is
        # authoritative for the live session; this is a no-op without a database
        # (local mode), so history works identically offline. ``persist=False``
        # is used when re-inserting events on restore/replay to stay idempotent.
        if persist:
            self._persist_event(event)
        self._notify_state()
        return copy.deepcopy(event)

    def configure_science(self, capture, publish) -> None:
        """Bind canonical owner capture and acknowledged transactional publication.

        Bind before the first scientific edit; audit-only events cannot infer a
        pre-edit baseline. Callbacks are runtime resources and never serialized.
        """
        from chisurf.history.science import encode_science

        if not callable(capture) or not callable(publish):
            raise TypeError("Scientific history requires capture and publication callbacks")
        with self._lock:
            if self._baseline is None:
                current = encode_science(capture())
                if self._events:
                    self._science_states[self._cursor] = current
                else:
                    self._baseline = current
            self._science_capture = capture
            self._science_publish = publish

    def cursor_index(self) -> int:
        """Return the last acknowledged event, or -1 for the initial state."""
        with self._lock:
            return self._cursor

    def can_navigate(self, index: int) -> bool:
        """Whether the requested cursor has complete canonical science."""
        with self._lock:
            return (
                type(index) is int
                and -1 <= index < len(self._events)
                and (self._baseline is not None if index == -1 else index in self._science_states)
            )

    def navigate(self, index: int):
        """Publish exact science and move the cursor only after owner acknowledgement."""
        from chisurf.history.science import decode_science

        with self._lock, self.suppress_recording(), self._suppress_notifications():
            if not self.can_navigate(index) or self._science_publish is None:
                raise ValueError("History cursor has no complete scientific restoration source")
            state = self._baseline if index == -1 else self._science_states[index]
            project = decode_science(state)
            # The owner may install these audit rows during science publication.
            # Retain the complete in-memory scientific history across that install.
            saved = copy.deepcopy(
                (
                    self._events,
                    self._checkpoints,
                    self._science_states,
                    self._baseline,
                    self._cursor,
                )
            )
            project.extra["history_events"] = copy.deepcopy(self._events)
            envelope = self.export_state()
            envelope["cursor"] = index
            self.validate_state(envelope)
            project.extra["history_state"] = envelope
            try:
                result = self._science_publish(project)
                if not isinstance(result, dict) or result.get("ok") is not True:
                    raise RuntimeError("Scientific history publication was not acknowledged")
            except Exception:
                self._restore_owned_state(saved)
                raise
            self._restore_owned_state(saved)
            self._cursor = index
        self._notify_state()
        return result

    def apply_edit(
        self,
        edit,
        action_type,
        summary,
        payload=None,
        *,
        source_uid=None,
        target_uid=None,
        persist=True,
    ):
        """Stage an edit of detached canonical science before owner publication.

        ``edit`` receives a RestoredSession, never the live owner. Failed edits,
        validation, rendering and acknowledgement preserve the current branch.
        The publisher must implement the canonical owner transaction contract.
        """
        from chisurf.core.project import capture_session, restore_session
        from chisurf.history.science import decode_science, encode_science

        with self._lock, self.suppress_recording(), self._suppress_notifications():
            if self._science_capture is None or self._science_publish is None:
                raise ValueError("Scientific history has no configured owner")
            if self._cursor + 1 >= self._max_events:
                raise ValueError(
                    "History event limit reached; explicit scientific compaction required"
                )
            current = encode_science(self._science_capture())
            project = decode_science(current)
            detached = restore_session(project)
            edit(detached)
            candidate = capture_session(
                detached.datasets,
                detached.fits,
                experiments=detached.experiments,
                ui_state=project.ui_state,
                name=project.name,
                resources=project.resources,
            )
            after = encode_science(candidate)
            decode_science(after)
            event = {
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action_type": action_type,
                "summary": summary,
                "payload": json_safe_payload(payload or {}),
                "source_uid": source_uid,
                "target_uid": target_uid,
            }
            self._validated_events([event])
            saved = self.export_state()
            staged = copy.deepcopy(saved)
            index = self._cursor + 1
            staged["events"] = staged["events"][:index] + [event]
            staged["states"] = [row for row in staged["states"] if row["event_index"] < index]
            staged["states"].append({"event_index": index, "state": after})
            staged["checkpoints"] = [
                row for row in staged["checkpoints"] if row["event_index"] < index
            ]
            staged["cursor"] = index
            saved_owned = self.validate_state(saved)
            staged_owned = self.validate_state(staged)
            candidate.extra["history_events"] = copy.deepcopy(staged["events"])
            candidate.extra["history_state"] = copy.deepcopy(staged)
            try:
                result = self._science_publish(candidate)
                if not isinstance(result, dict) or result.get("ok") is not True:
                    raise RuntimeError("Scientific edit publication was not acknowledged")
            except Exception:
                self._restore_owned_state(saved_owned)
                raise
            self._restore_owned_state(staged_owned)
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(copy.deepcopy(event))
            except Exception:
                pass
        self._emit_log(event)
        if persist:
            self._persist_event(copy.deepcopy(event))
        self._notify_state()
        return copy.deepcopy(event)

    def _restore_owned_state(self, state):
        """Restore bounded data only, preserving locks, callbacks and subscribers."""
        events, checkpoints, science, baseline, cursor = state
        self._events[:] = events
        self._checkpoints.clear()
        self._checkpoints.update(checkpoints)
        self._science_states.clear()
        self._science_states.update(science)
        self._baseline = baseline
        self._cursor = cursor

    def export_state(self):
        """Export owned history data without callbacks, locks or nested history."""
        with self._lock:
            state = {
                "history_version": self.HISTORY_VERSION,
                "events": self.list_events(),
                "cursor": self._cursor,
                "baseline": self._baseline,
                "states": [
                    {"event_index": index, "state": value}
                    for index, value in sorted(self._science_states.items())
                ],
                "checkpoints": [value for _, value in sorted(self._checkpoints.items())],
            }
            json.dumps(state, allow_nan=False)
            return copy.deepcopy(state)

    def validate_state(self, state):
        """Stage a complete envelope, rejecting any invalid row or scientific graph."""
        from chisurf.history.science import decode_science

        fields = {"history_version", "events", "cursor", "baseline", "states", "checkpoints"}
        if not isinstance(state, dict) or set(state) != fields:
            raise ValueError("Invalid history envelope fields")
        if state["history_version"] not in self.SUPPORTED_VERSIONS:
            raise ValueError("Unsupported history envelope version")
        json.dumps(state, allow_nan=False)
        candidate = copy.deepcopy(state)
        events = self._validated_events(candidate["events"])
        cursor = candidate["cursor"]
        if type(cursor) is not int or not -1 <= cursor < len(events):
            raise ValueError("Invalid history cursor")
        baseline = candidate["baseline"]
        if baseline is not None:
            decode_science(baseline)
        states = {}
        if not isinstance(candidate["states"], list):
            raise ValueError("History states must be a list")
        for row in candidate["states"]:
            if not isinstance(row, dict) or set(row) != {"event_index", "state"}:
                raise ValueError("Invalid history scientific state row")
            index = row["event_index"]
            if type(index) is not int or not 0 <= index < len(events) or index in states:
                raise ValueError("Invalid or duplicate scientific state index")
            decode_science(row["state"])
            states[index] = row["state"]
        if baseline is not None and set(states) != set(range(len(events))):
            raise ValueError("Scientific history has missing restoration states")
        if states and (cursor not in states if cursor >= 0 else baseline is None):
            raise ValueError("Scientific cursor has no restoration state")
        checkpoints = {}
        if not isinstance(candidate["checkpoints"], list):
            raise ValueError("History checkpoints must be a list")
        for row in candidate["checkpoints"]:
            if not isinstance(row, dict) or set(row) != {"event_index", "snapshot", "timestamp"}:
                raise ValueError("Invalid history checkpoint fields")
            index = row["event_index"]
            if type(index) is not int or not 0 <= index < len(events) or index in checkpoints:
                raise ValueError("Invalid or duplicate history checkpoint index")
            if not isinstance(row["snapshot"], dict):
                raise ValueError("Invalid checkpoint snapshot")
            if not isinstance(row["timestamp"], str):
                raise ValueError("Invalid checkpoint timestamp")
            timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("Checkpoint timestamp requires timezone")
            checkpoints[index] = row
        return events, checkpoints, states, baseline, cursor

    def import_state(self, state):
        """Atomically install validated data while retaining runtime identities."""
        staged = self.validate_state(state)
        with self._lock:
            self._restore_owned_state(staged)
        self._notify_state()

    def subscribe_state(self, callback):
        """Subscribe to acknowledged history changes, including load and clear."""
        with self._lock:
            if callback not in self._state_subscribers:
                self._state_subscribers.append(callback)

    def unsubscribe_state(self, callback):
        """Detach a state subscriber without disturbing event subscriptions."""
        with self._lock:
            self._state_subscribers[:] = [cb for cb in self._state_subscribers if cb != callback]

    def _notify_state(self):
        """Notify observers with independent cursor values on acknowledged changes."""
        if getattr(self._recording_context, "notification_depth", 0):
            return
        with self._lock:
            callbacks = list(self._state_subscribers)
            state = {"cursor": self._cursor, "event_count": len(self._events)}
        for callback in callbacks:
            try:
                callback(copy.deepcopy(state))
            except Exception:
                pass

    @contextmanager
    def _suppress_notifications(self):
        """Hide tentative owner history installation until publication commits."""
        depth = getattr(self._recording_context, "notification_depth", 0)
        self._recording_context.notification_depth = depth + 1
        try:
            yield
        finally:
            self._recording_context.notification_depth = depth

    def _persist_event(self, event: typing.Dict[str, typing.Any]) -> None:
        """Best-effort durable append of ``event`` to the MMFDB event log."""
        try:
            from mmfdb.lifecycle import event_log

            event_log.append_event(event, history_version=self.HISTORY_VERSION)
        except Exception:
            pass

    @contextmanager
    def suppress_recording(self):
        """Context manager to temporarily disable operation recording."""
        depth = getattr(self._recording_context, "depth", 0)
        self._recording_context.depth = depth + 1
        try:
            yield
        finally:
            self._recording_context.depth = depth

    def clear(self) -> None:
        """Clear events only after staging the current scientific baseline."""
        with self._lock:
            baseline = None
            if self._science_capture is not None:
                from chisurf.history.science import encode_science

                baseline = encode_science(self._science_capture())
            self._events.clear()
            self._checkpoints.clear()
            self._science_states.clear()
            self._baseline = baseline
            self._cursor = -1
        self._notify_state()

    def load_events(
        self, events: typing.List[typing.Dict[str, typing.Any]], replace: bool = True
    ) -> None:
        """Load a list of history events directly."""
        rows = self._validated_events(events)
        with self._lock:
            if not replace and (self._baseline is not None or self._science_states):
                raise ValueError(
                    "Cannot append audit rows to scientific history; use a staged edit"
                )
            candidate = rows if replace else self._validated_events(self._events + rows)
            self._events[:] = candidate
            if replace:
                self._checkpoints.clear()
                self._science_states.clear()
                self._baseline = None
            self._cursor = len(self._events) - 1
        self._notify_state()

    def _validated_events(self, events):
        """Return detached validated rows or reject the entire transport."""
        if not isinstance(events, list):
            raise ValueError("History events must be a list")
        if len(events) > self._max_events:
            raise ValueError("History event limit exceeded")
        rows = copy.deepcopy(events)
        seen = set()
        for index, event in enumerate(rows):
            if not self.validate_event(event):
                raise ValueError(f"Invalid history event at index {index}")
            if event["event_id"] in seen:
                raise ValueError(f"Duplicate history event ID at index {index}")
            seen.add(event["event_id"])
        return rows

    def subscribe(self, callback: typing.Callable[[typing.Dict[str, typing.Any]], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: typing.Callable[[typing.Dict[str, typing.Any]], None]) -> None:
        with self._lock:
            self._subscribers = [cb for cb in self._subscribers if cb is not callback]

    def list_events(self, source: str = "memory") -> typing.List[typing.Dict[str, typing.Any]]:
        """Return history events.

        ``source="memory"`` (default) returns the in-memory log — the authoritative
        live-session view. ``source="mmfdb"`` reads the durable event log from the
        database (the projection's backing store); it returns ``[]`` when no MMFDB
        is available, so callers degrade gracefully offline.
        """
        if source == "mmfdb":
            from mmfdb.lifecycle import event_log

            return event_log.read_events()
        with self._lock:
            return copy.deepcopy(self._events)

    def tail(self, n: int = 100) -> typing.List[typing.Dict[str, typing.Any]]:
        if n <= 0:
            return []
        with self._lock:
            return copy.deepcopy(self._events[-n:])

    def save_jsonl(self, filename: typing.Union[str, Path], include_metadata: bool = True) -> Path:
        """Atomically save complete v2 history; metadata=False exports audit rows only."""
        path = Path(filename).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            rows = self._validated_events(self._events)
            metadata = {
                "history_version": self.HISTORY_VERSION,
                "event_count": len(rows),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checkpoint_count": len(self._checkpoints),
            }
            envelope = self.export_state()
            envelope.pop("events")
            metadata["state"] = envelope
        # Serialize before opening any durable destination, then publish once.
        content = ""
        if include_metadata:
            content = "# CHISURF HISTORY METADATA: " + json.dumps(metadata, sort_keys=True) + "\n"
        content += "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as fp:
                temp_path = Path(fp.name)
                fp.write(content)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return path

    def load_jsonl(
        self, filename: typing.Union[str, Path], replace: bool = True
    ) -> typing.Dict[str, typing.Any]:
        """Load history from JSONL file with version validation and integrity checking."""
        path = Path(filename).resolve()
        if not path.exists():
            raise FileNotFoundError(f"History file not found: {path}")
        result: dict[str, typing.Any] = {
            "success": False,
            "loaded_events": 0,
            "file_version": None,
            "compatibility": "unknown",
            "errors": [],
        }
        try:
            rows: list[typing.Any] = []
            metadata = None
            with path.open("r", encoding="utf-8") as fp:
                for line_number, line in enumerate(fp, 1):
                    text = line.strip()
                    if not text:
                        continue
                    if text.startswith("# CHISURF HISTORY METADATA: "):
                        if metadata is not None or rows:
                            raise ValueError("History metadata must occur once before events")
                        metadata = json.loads(text[len("# CHISURF HISTORY METADATA: ") :])
                        if not isinstance(metadata, dict):
                            raise ValueError("Invalid history metadata")
                        version = metadata.get("history_version")
                        result["file_version"] = version
                        if version not in self.SUPPORTED_VERSIONS:
                            result["compatibility"] = "incompatible"
                            raise ValueError(f"Unsupported history version: {version}")
                        result["compatibility"] = "compatible"
                    else:
                        try:
                            rows.append(json.loads(text))
                        except ValueError as exc:
                            raise ValueError(f"Invalid JSON at line {line_number}") from exc
            rows = self._validated_events(rows)
            if metadata is None or "state" not in metadata:
                raise ValueError(
                    "Complete versioned history envelope required; use explicit audit import"
                )
            if type(metadata.get("event_count")) is not int or metadata["event_count"] != len(rows):
                raise ValueError("History event_count mismatch")
            if type(metadata.get("checkpoint_count")) is not int or metadata[
                "checkpoint_count"
            ] != len(metadata["state"].get("checkpoints", [])):
                raise ValueError("History checkpoint_count mismatch")
            if metadata is not None and "state" in metadata:
                if not replace:
                    raise ValueError("Scientific envelope append requires an explicit branch merge")
                state = metadata["state"]
                if not isinstance(state, dict):
                    raise ValueError("Invalid history envelope metadata")
                state = dict(state, events=rows)
                self.import_state(state)
            else:
                self.load_events(rows, replace=replace)
            result.update(success=True, loaded_events=len(rows))
        except Exception as exc:
            result["errors"].append(f"Load failed: {exc}")
        return result

    def create_backup(
        self, backup_dir: typing.Optional[typing.Union[str, Path]] = None
    ) -> typing.Dict[str, typing.Any]:
        """Create a backup of the current history."""
        result: dict[str, typing.Any] = {"success": False, "backup_path": None, "error": None}

        try:
            if backup_dir is None:
                backup_dir = Path("history_backups")
            else:
                backup_dir = Path(backup_dir) if isinstance(backup_dir, str) else backup_dir

            backup_dir.mkdir(parents=True, exist_ok=True)

            # Create timestamped backup filename
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_filename = f"history_backup_{timestamp}_{len(self._events)}_events.jsonl"
            backup_path = backup_dir / backup_filename

            # Save with full metadata
            self.save_jsonl(backup_path, include_metadata=True)

            result["success"] = True
            result["backup_path"] = str(backup_path)
            result["event_count"] = len(self._events)
            result["timestamp"] = timestamp

        except Exception as e:
            result["error"] = str(e)

        return result

    def restore_from_backup(
        self, backup_path: typing.Union[str, Path]
    ) -> typing.Dict[str, typing.Any]:
        """Restore history from a backup file."""
        return self.load_jsonl(backup_path, replace=True)

    def get_history_stats(self) -> typing.Dict[str, typing.Any]:
        """Get statistics about the current history."""
        with self._lock:
            return {
                "event_count": len(self._events),
                "checkpoint_count": len(self._checkpoints),
                "oldest_event": self._events[0]["timestamp"] if self._events else None,
                "newest_event": self._events[-1]["timestamp"] if self._events else None,
                "action_types": list(set(event["action_type"] for event in self._events))
                if self._events
                else [],
            }

    def set_memory_limits(
        self, max_events: int = 10000, auto_compact_threshold: int = 5000
    ) -> None:
        """Set memory management limits for history."""
        with self._lock:
            self._max_events = max(100, int(max_events))  # Minimum 100 events
            self._auto_compact_threshold = max(50, int(auto_compact_threshold))  # Minimum 50 events

    def get_memory_limits(self) -> typing.Dict[str, typing.Any]:
        """Get current memory management limits."""
        with self._lock:
            return {
                "max_events": self._max_events,
                "auto_compact_threshold": self._auto_compact_threshold,
                "current_event_count": len(self._events),
            }

    def compact_history(self, keep_recent: int = 500) -> typing.Dict[str, typing.Any]:
        """Compact history by removing older events while keeping recent ones."""
        with self._lock:
            report: dict[str, typing.Any] = {
                "events_before": len(self._events),
                "events_after": len(self._events),
                "events_removed": 0,
                "compaction_successful": False,
            }
            if type(keep_recent) is not int or keep_recent < 1:
                raise ValueError("keep_recent must be a positive integer")
            cut = len(self._events) - keep_recent
            if cut <= 0:
                return report
            if (
                self._baseline is None
                or self._cursor < cut - 1
                or set(self._science_states) != set(range(len(self._events)))
            ):
                report["reason"] = "Complete scientific baseline and retained cursor required"
                return report
            # State after cut-1 is now the explicit initial state of the retained
            # history. Cache indices and the cursor shift by the same offset.
            self._baseline = copy.deepcopy(self._science_states[cut - 1])
            self._science_states = {
                index - cut: state for index, state in self._science_states.items() if index >= cut
            }
            checkpoints = {}
            for index, checkpoint in self._checkpoints.items():
                if index >= cut:
                    checkpoints[index - cut] = dict(checkpoint, event_index=index - cut)
            self._checkpoints.clear()
            self._checkpoints.update(checkpoints)
            del self._events[:cut]
            self._cursor -= cut
            report.update(
                events_after=len(self._events), events_removed=cut, compaction_successful=True
            )
        self._notify_state()
        return report

    def auto_compact_if_needed(self) -> typing.Dict[str, typing.Any]:
        """Automatically compact history if it exceeds the auto-compact threshold."""
        with self._lock:
            if len(self._events) <= self._auto_compact_threshold:
                return {
                    "compaction_performed": False,
                    "current_event_count": len(self._events),
                    "threshold": self._auto_compact_threshold,
                }

            # Perform compaction (keep half of auto_compact_threshold)
            keep_recent = self._auto_compact_threshold // 2
            return self.compact_history(keep_recent)

    def get_estimated_memory_usage(self) -> typing.Dict[str, typing.Any]:
        """Estimate memory usage of the history."""
        import sys

        with self._lock:
            # Estimate event sizes
            if self._events:
                sample_event = self._events[0]
                approx_event_size = sys.getsizeof(str(sample_event))
                estimated_events_size = len(self._events) * approx_event_size
            else:
                approx_event_size = 0
                estimated_events_size = 0

            # Estimate checkpoint sizes
            if self._checkpoints:
                sample_checkpoint = next(iter(self._checkpoints.values()))
                approx_checkpoint_size = sys.getsizeof(str(sample_checkpoint))
                estimated_checkpoints_size = len(self._checkpoints) * approx_checkpoint_size
            else:
                approx_checkpoint_size = 0
                estimated_checkpoints_size = 0

            return {
                "event_count": len(self._events),
                "approx_event_size_bytes": approx_event_size,
                "estimated_events_memory_bytes": estimated_events_size,
                "checkpoint_count": len(self._checkpoints),
                "approx_checkpoint_size_bytes": approx_checkpoint_size,
                "estimated_checkpoints_memory_bytes": estimated_checkpoints_size,
                "total_estimated_memory_bytes": estimated_events_size + estimated_checkpoints_size,
            }

    @staticmethod
    def _emit_log(event: typing.Dict[str, typing.Any]) -> None:
        line = f"# HIST {event.get('action_type', '?')}: {event.get('summary', '')}"
        try:
            log_fn = getattr(cs, "log", None)
            if callable(log_fn):
                log_fn(line)
            else:
                cs.logging.info(line)
        except Exception:
            pass

    def set_checkpoint_capture(
        self,
        capture_fn: typing.Optional[typing.Callable[[], typing.Dict[str, typing.Any]]],
    ) -> None:
        """Set the function used to capture domain state for checkpoints.

        The capture function should return a JSON-serializable dict representing
        the current scientific state (datasets, fits, parameters, links, etc.).
        """
        with self._lock:
            self._checkpoint_capture_fn = capture_fn

    def create_checkpoint(self, event_index: int) -> bool:
        """Create a checkpoint at the given event index.

        Returns True if checkpoint was created, False if capture function not set
        or capture failed.
        """
        if self._checkpoint_capture_fn is None:
            return False
        with self._lock:
            if (
                type(event_index) is not int
                or not 0 <= event_index < len(self._events)
                or event_index != self._cursor
            ):
                return False
        try:
            snapshot = self._checkpoint_capture_fn()
            if not isinstance(snapshot, dict):
                return False
            with self._lock:
                self._checkpoints[event_index] = {
                    "event_index": event_index,
                    "snapshot": copy.deepcopy(snapshot),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self._evict_checkpoints_locked()
            return True
        except Exception:
            return False

    def _evict_checkpoints_locked(self) -> None:
        """Bound ``self._checkpoints`` to ``_max_checkpoints`` (caller holds lock).

        Retain the earliest audit checkpoint plus recent entries. Scientific
        restoration uses canonical state records, independently of this cache.
        """
        cap = self._max_checkpoints
        if cap <= 0 or len(self._checkpoints) <= cap:
            return
        indices = sorted(self._checkpoints)
        recent = set(indices[-(cap - 1) :]) if cap > 1 else set()
        keep = {indices[0]} | recent
        for idx in indices:
            if idx not in keep:
                del self._checkpoints[idx]

    def get_checkpoint_before(
        self, event_index: int
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        """Get the nearest checkpoint at or before the given event index.

        Returns None if no checkpoint exists before the index.
        """
        with self._lock:
            if type(event_index) is not int or not -1 <= event_index < len(self._events):
                raise ValueError("Invalid history checkpoint event index")
            if not self._checkpoints:
                return None
            candidates = [idx for idx in self._checkpoints.keys() if idx <= event_index]
            if not candidates:
                return None
            nearest = max(candidates)
            return copy.deepcopy(self._checkpoints[nearest])

    def clear_checkpoints(self) -> None:
        """Remove all checkpoints."""
        with self._lock:
            self._checkpoints.clear()

    def checkpoint_count(self) -> int:
        """Return the number of stored checkpoints."""
        with self._lock:
            return len(self._checkpoints)

    def validate_event(self, event: typing.Dict[str, typing.Any]) -> bool:
        """Validate that an event has the required structure and fields."""
        required_fields = {"event_id", "timestamp", "action_type", "summary", "payload"}

        # Check all required fields are present
        if not isinstance(event, dict) or not required_fields.issubset(event):
            return False

        # Validate field types
        try:
            if any(not isinstance(event[key], str) for key in required_fields - {"payload"}):
                return False
            if not event["event_id"] or not event["action_type"]:
                return False
            timestamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                return False
            if any(
                event.get(key) is not None and not isinstance(event[key], str)
                for key in ("source_uid", "target_uid")
            ):
                return False
            if not isinstance(event["payload"], dict):
                return False
            json.dumps(event, allow_nan=False)
            return True
        except (KeyError, ValueError, TypeError):
            return False

    def validate_history_integrity(self) -> typing.Dict[str, typing.Any]:
        """Validate the integrity of the entire history."""
        report: dict[str, typing.Any] = {
            "total_events": 0,
            "valid_events": 0,
            "invalid_events": [],
            "corruption_detected": False,
            "missing_event_ids": [],
        }

        with self._lock:
            report["total_events"] = len(self._events)

            for idx, event in enumerate(self._events):
                if not self.validate_event(event):
                    report["invalid_events"].append(idx)
                    report["corruption_detected"] = True
                else:
                    report["valid_events"] += 1

            # Check for duplicate event IDs (only for valid events)
            event_ids = []
            for idx, event in enumerate(self._events):
                if idx not in report["invalid_events"]:  # Only check valid events
                    try:
                        eid = str(event.get("event_id", ""))
                        if eid in event_ids:
                            report["corruption_detected"] = True
                            report["invalid_events"].append(idx)
                        else:
                            event_ids.append(eid)
                    except Exception:
                        report["corruption_detected"] = True
                        report["invalid_events"].append(idx)

        return report

    def repair_history(self) -> typing.Dict[str, typing.Any]:
        """Attempt to repair corrupted history by removing invalid events."""
        report: dict[str, typing.Any] = {
            "events_before": 0,
            "events_after": 0,
            "events_removed": 0,
            "repair_successful": False,
        }

        with self._lock:
            report["events_before"] = len(self._events)

            # Filter out invalid events
            valid_events = []
            removed_indices = []
            seen = set()

            for idx, event in enumerate(self._events):
                if self.validate_event(event) and event["event_id"] not in seen:
                    valid_events.append(event)
                    seen.add(event["event_id"])
                else:
                    removed_indices.append(idx)

            if len(removed_indices) > 0:
                self._events[:] = valid_events
                self._checkpoints.clear()
                self._science_states.clear()
                self._baseline = None
                self._cursor = len(self._events) - 1
                report["scientific_restoration_discarded"] = True
                report["events_after"] = len(self._events)
                report["events_removed"] = len(removed_indices)
                report["repair_successful"] = True
                report["removed_indices"] = removed_indices
            else:
                report["events_after"] = report["events_before"]
                report["repair_successful"] = False

        self._notify_state()
        return report

    def _maybe_create_checkpoint(self, event_index: int) -> None:
        """Create a checkpoint if the interval has been reached."""
        if self._checkpoint_interval <= 0:
            return
        if self._checkpoint_capture_fn is None:
            return
        if event_index > 0 and event_index % self._checkpoint_interval == 0:
            self.create_checkpoint(event_index)

    def get_events_from_checkpoint(
        self,
        target_event_index: int,
    ) -> typing.Tuple[
        typing.Optional[typing.Dict[str, typing.Any]], typing.List[typing.Dict[str, typing.Any]]
    ]:
        """Get snapshot and events needed to reach target_event_index.

        Returns a tuple of (checkpoint_snapshot, events_to_replay).
        If no checkpoint exists before target, snapshot is None and all events
        up to target are returned.
        """
        with self._lock:
            if type(target_event_index) is not int or not -1 <= target_event_index < len(
                self._events
            ):
                raise ValueError("Invalid history event index")
            checkpoint = self.get_checkpoint_before(target_event_index)
            if checkpoint is None:
                events = copy.deepcopy(self._events[: target_event_index + 1])
                return None, events
            start_index = checkpoint["event_index"] + 1
            events = copy.deepcopy(self._events[start_index : target_event_index + 1])
            return checkpoint["snapshot"], events

    def replay(
        self,
        handlers: typing.Dict[str, typing.Callable[[typing.Dict[str, typing.Any]], None]],
        stop_on_error: bool = False,
        events: typing.Optional[typing.List[typing.Dict[str, typing.Any]]] = None,
    ) -> typing.Dict[str, typing.Any]:
        """Replay history events using provided handlers.

        Args:
            handlers: Dict mapping action_type to handler callable.
            stop_on_error: If True, stop replaying on first handler error.
            events: Optional explicit event list to replay; defaults to the
                in-memory log. Handler keys and event ``action_type`` are matched
                under the separator-normal form (see
                :func:`chisurf.core.actions.canonical`), so dotted and underscored
                spellings are interchangeable.

        Returns:
            Dict with:
                - total: total events processed
                - replayed: events with handlers called
                - skipped: events without handlers
                - errors: list of (event_index, error_message) tuples
        """
        with self._lock, self.suppress_recording():
            replay_events = copy.deepcopy(self._events if events is None else events)
            total = len(replay_events)
            replayed = 0
            skipped = 0
            errors: typing.List[typing.Tuple[int, str]] = []

            canon_handlers = {_canon(k): v for k, v in handlers.items()}

            for i, event in enumerate(replay_events):
                action_type = _canon(str(event.get("action_type", "")))
                handler = canon_handlers.get(action_type)

                if handler is None:
                    skipped += 1
                    continue

                try:
                    handler(event)
                    replayed += 1
                except Exception as e:
                    error_msg = str(e)
                    errors.append((i, error_msg))
                    if stop_on_error:
                        break

            return {
                "total": total,
                "replayed": replayed,
                "skipped": skipped,
                "errors": errors,
            }
