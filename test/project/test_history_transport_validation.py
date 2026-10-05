"""Invalid document history is rejected before PTO/database publication."""

from __future__ import annotations

import copy

import pytest

from chisurf.core.project import capture_session
from chisurf.core.project.storage import ProjectStorageError, save_database, save_file
from chisurf.history.core import OperationHistory


def malformed_history_project(damage):
    """Create a genuine canonical project with one invalid typed history field."""
    project = capture_session([], [], name="invalid timeline")
    envelope = OperationHistory().export_state()
    if damage == "version":
        envelope["history_version"] = "unsupported-version"
    elif damage == "cursor":
        envelope["cursor"] = 0
    elif damage == "fields":
        del envelope["events"]
    else:
        raise AssertionError(damage)
    project.extra["history_state"] = copy.deepcopy(envelope)
    return project


@pytest.mark.parametrize("damage", ["version", "cursor", "fields"])
def test_invalid_history_file_save_retains_previous_valid_document(tmp_path, damage):
    """Malformed history must never replace an existing valid document."""
    destination = save_file(capture_session([], [], name="previous"), tmp_path / "document.cs.pto")
    previous = destination.read_bytes()
    with pytest.raises(ProjectStorageError, match="[Hh]istory"):
        save_file(malformed_history_project(damage), destination)
    assert destination.read_bytes() == previous


@pytest.mark.parametrize("damage", ["version", "cursor", "fields"])
def test_invalid_history_is_rejected_before_configured_database_call(damage):
    """Shared canonical validation precedes any authenticated publication RPC."""
    calls = []

    class ForbiddenTransport:
        """A spy only for proving the invalid-input boundary makes no RPC."""

        def save_project(self, **kwargs):
            calls.append(kwargs)
            raise RuntimeError("REMOTE_PUBLICATION_REACHED")

    settings = {
        "client": {
            "mode": "remote",
            "base_url": "http://127.0.0.1:4001",
            "allow_insecure_http": True,
        }
    }
    with pytest.raises(ProjectStorageError, match="[Hh]istory"):
        save_database(
            malformed_history_project(damage), mmfdb_settings=settings, client=ForbiddenTransport()
        )
    assert calls == []
