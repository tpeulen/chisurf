"""Behavioral contract for project identity and destructive transitions."""

import pytest

from chisurf.core.project import Project


def test_cancel_never_saves_or_accepts_transition():
    from chisurf.core.project.lifecycle import SaveDecision, confirm_transition

    calls = []
    assert not confirm_transition(
        has_content=True,
        prompt=lambda: SaveDecision.CANCEL,
        save=lambda: calls.append("save"),
    )
    assert calls == []


@pytest.mark.parametrize("result", [False, None, {}, "saved"])
def test_save_must_explicitly_succeed_to_accept_transition(result):
    from chisurf.core.project.lifecycle import SaveDecision, confirm_transition

    assert not confirm_transition(
        has_content=True, prompt=lambda: SaveDecision.SAVE, save=lambda: result
    )


def test_successful_save_authorizes_transition():
    from chisurf.core.project.lifecycle import SaveDecision, confirm_transition

    assert confirm_transition(has_content=True, prompt=lambda: SaveDecision.SAVE, save=lambda: True)


def test_discard_does_not_call_save():
    from chisurf.core.project.lifecycle import SaveDecision, confirm_transition

    def unexpected():
        pytest.fail("discard must not invoke save")

    assert confirm_transition(
        has_content=True, prompt=lambda: SaveDecision.DISCARD, save=unexpected
    )


def test_empty_session_does_not_prompt():
    from chisurf.core.project.lifecycle import confirm_transition

    def unexpected():
        pytest.fail("empty session must not invoke prompt or save")

    assert confirm_transition(has_content=False, prompt=unexpected, save=unexpected)


def test_save_error_cannot_be_reported_as_accepted_transition():
    from chisurf.core.project.lifecycle import SaveDecision, confirm_transition

    def failed_save():
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        confirm_transition(has_content=True, prompt=lambda: SaveDecision.SAVE, save=failed_save)


def test_file_identity_only_records_a_verified_save(tmp_path):
    from chisurf.core.project.lifecycle import ProjectDocument

    project = Project(name="analysis", datasets={"d": {"name": "data"}})
    doc = ProjectDocument()
    assert doc.path is None
    assert doc.is_modified(project)
    doc.record_file_save(project, tmp_path / "analysis.cs.pto")
    assert doc.path == tmp_path / "analysis.cs.pto"
    assert doc.name == "analysis"
    assert doc.backend == "file"
    assert not doc.is_modified(project)
    project.datasets["d"]["name"] = "edited"
    assert doc.is_modified(project)


def test_save_bookkeeping_and_creation_time_do_not_make_project_dirty():
    from chisurf.core.project.lifecycle import snapshot_fingerprint

    first = Project(name="analysis", created="2026-10-03T19:00:00")
    second = Project(name="analysis", created="2026-10-03T20:00:00")
    second.extra = {"history_events": [{"action": "save"}], "action_catalog": {}}
    assert snapshot_fingerprint(first) == snapshot_fingerprint(second)


def test_database_save_records_version_identity_and_switches_backend(tmp_path):
    from chisurf.core.project.lifecycle import ProjectDocument

    project = Project(name="analysis")
    doc = ProjectDocument()
    doc.record_file_save(project, tmp_path / "analysis.cs.pto")
    doc.record_database_save(
        project,
        {"ok": True, "project_id": "proj_123", "version_id": "ver_456", "visibility": "public"},
    )
    assert doc.backend == "mmfdb"
    assert doc.path is None
    assert doc.project_id == "proj_123"
    assert doc.version_id == "ver_456"
    assert doc.visibility == "public"
    assert not doc.is_modified(project)


@pytest.mark.parametrize(
    "result",
    [
        {"ok": False, "project_id": "proj_123", "version_id": "ver_456"},
        {"ok": True, "project_id": "proj_123"},
        {"ok": True, "version_id": "ver_456"},
    ],
)
def test_failed_database_result_preserves_document_identity(tmp_path, result):
    from chisurf.core.project.lifecycle import ProjectDocument

    project = Project(name="analysis")
    doc = ProjectDocument()
    doc.record_file_save(project, tmp_path / "analysis.cs.pto")
    before = dict(doc.__dict__)
    with pytest.raises(ValueError):
        doc.record_database_save(Project(name="wrong"), result)
    assert doc.__dict__ == before


def test_invalid_file_identity_preserves_previous_document(tmp_path):
    from chisurf.core.project.lifecycle import ProjectDocument

    doc = ProjectDocument()
    project = Project(name="analysis")
    doc.record_file_save(project, tmp_path / "analysis.cs.pto")
    before = dict(doc.__dict__)
    with pytest.raises(ValueError):
        doc.record_file_save(Project(name="wrong"), tmp_path / "bad.csp")
    assert doc.__dict__ == before


def test_reset_forgets_destination_and_baseline(tmp_path):
    from chisurf.core.project.lifecycle import ProjectDocument

    doc = ProjectDocument()
    project = Project(name="analysis")
    doc.record_file_save(project, tmp_path / "analysis.cs.pto")
    doc.reset()
    assert doc.path is None
    assert doc.project_id is None
    assert doc.version_id is None
    assert doc.name == "untitled"
    assert doc.is_modified(project)


def test_file_identity_can_be_staged_without_mutating_live_document(tmp_path):
    from chisurf.core.project.lifecycle import ProjectDocument

    old = Project(name="old")
    new = Project(name="new")
    doc = ProjectDocument()
    doc.record_database_save(
        old,
        {"ok": True, "project_id": "p1", "version_id": "v1"},
    )

    staged = doc.stage_file_save(new, tmp_path / "new.cs.pto")

    assert doc.backend == "mmfdb"
    assert doc.project_id == "p1"
    doc.adopt(staged)
    assert doc.backend == "file"
    assert doc.path == tmp_path / "new.cs.pto"
    assert doc.project_id is None
    assert doc.version_id is None
    assert not doc.is_modified(new)


def test_database_identity_can_be_staged_without_mutating_live_document(tmp_path):
    from chisurf.core.project.lifecycle import ProjectDocument

    old = Project(name="old")
    new = Project(name="new")
    doc = ProjectDocument()
    doc.record_file_save(old, tmp_path / "old.cs.pto")

    staged = doc.stage_database_save(
        new,
        {"ok": True, "project_id": "p2", "version_id": "v2"},
    )

    assert doc.path == tmp_path / "old.cs.pto"
    doc.adopt(staged)
    assert doc.backend == "mmfdb"
    assert doc.path is None
    assert doc.project_id == "p2"
    assert doc.version_id == "v2"
