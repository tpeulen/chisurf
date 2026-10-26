"""The export gate: a record whose ChiSurf project only links its data does not upload as it is.

The record of the deposit tests gains an analysis project that links a data file outside the record.
Upload stays locked and refuses even a direct call; ticking the override box and confirming
records the override in the record's log and the deposit's notes (which never name the container
format); *Make projects self-contained* stores the data in the project instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mmfdb.deposit")

from chisurf.core.data import LinkedDataset  # noqa: E402
from chisurf.core.project.session import capture_session  # noqa: E402
from chisurf.plugins.core.zenodo_deposit.test.test_model import (  # noqa: E402
    _fill_metadata,
    _wait,
)


def _with_project(model, tmp_path: Path) -> Path:
    """A project in the record linking a data file that stays outside it."""
    outside = tmp_path / "raw" / "m000.tif"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"pixels" * 500)
    root = tmp_path / "records" / "t4l-demo" / "analysis"
    root.mkdir(parents=True)
    project = root / "fit.cs.pto"
    capture_session([LinkedDataset(str(outside), data_kind="image", name="m000")], []).save(project)
    return project


def _ready(model) -> None:
    """Everything mmfdb's own gate asks for: metadata, package, every item approved."""
    model.select_record(model.records[0])
    _fill_metadata(model)
    model.build_package()
    _wait(model)
    for row in model.items:
        model.select_item(row)
        model.note = "checked"
        model.approve_item()


def test_a_linking_project_locks_the_upload_and_a_direct_call_is_refused(model, fake, tmp_path):
    _with_project(model, tmp_path)
    _ready(model)
    assert model.link_gates() and "only link their data" in model.links_text
    assert any("project fit:" in line for line in model._blockers())
    assert not model.enabled("upload_draft")
    assert "Make the projects self-contained" in model.next_step
    model.upload_draft()
    assert model.message.startswith("upload refused") and not fake.files


def test_the_override_needs_the_box_and_is_recorded_in_log_and_notes(model, tmp_path):
    _with_project(model, tmp_path)
    _ready(model)
    assert not model.enabled("confirm_linked_override")
    model.accept_linked_data = True
    assert model.enabled("confirm_linked_override")
    model.confirm_linked_override()
    entry = model.record.log[-1]
    assert entry["event"] == "linked_data_override" and entry["data"] == ["fit:m000"]
    notes = model.record.metadata["notes"]
    assert "fit (m000.tif)" in notes and "pto" not in notes.lower()
    assert not any("project fit:" in line for line in model._blockers())
    assert "Overridden" in model.links_text
    # The notes changed: the metadata is reviewed again before anything is sent.
    assert not model.enabled("upload_draft") and "review the changed metadata" in model.message
    model.refresh_records()
    assert model.records[0]["state"] != "projects link data"


def test_making_the_projects_self_contained_opens_the_gate(model, tmp_path):
    project = _with_project(model, tmp_path)
    _ready(model)
    model.make_projects_self_contained()
    _wait(model)
    assert not model.link_gates(), model.message
    from chisurf.core.project.project import Project

    record = next(iter(Project.load(project).datasets.values()))
    assert record["link"]["embedded"]
    assert "review the changed items again" in model.message


def test_the_record_list_and_the_batch_upload_honour_the_gate(model, fake, tmp_path):
    _with_project(model, tmp_path)
    _ready(model)
    model.refresh_records()
    (row,) = model.records
    assert row["state"] == "projects link data"
    model.picked = {row["name"]}
    assert not model._picked_uploads()  # not cleared: the batch leaves it
    model.upload_checked()
    _wait(model)
    assert not fake.files
