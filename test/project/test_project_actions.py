"""Action and scripting entrypoints must not silently use the bootstrap DB."""

from types import SimpleNamespace

import numpy as np
import pytest

import chisurf as cs
from chisurf.core.actions import project_actions
from chisurf.core.data import DataCurve
from chisurf.core.project import capture_session, storage


@pytest.fixture
def isolated_session(monkeypatch):
    curve = DataCurve(x=np.arange(4.0), y=np.arange(4.0) + 1, name="action-data")
    curve.ex = np.ones(4)
    curve.ey = np.ones(4)
    monkeypatch.setattr(cs, "imported_datasets", [curve])
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "cs", None)
    monkeypatch.setattr(cs, "api", None, raising=False)
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    monkeypatch.setattr(cs, "_project_gui", None, raising=False)
    monkeypatch.setattr(cs, "_project_authorizations", {}, raising=False)
    monkeypatch.setattr(cs, "_project_transition", None, raising=False)
    return curve


def test_archive_action_uses_file_without_real_database(isolated_session, monkeypatch, tmp_path):
    monkeypatch.setattr(
        cs.core.settings, "cs_settings", {**cs.core.settings.cs_settings, "mmfdb": {}}
    )
    monkeypatch.setattr(cs, "working_path", tmp_path)
    monkeypatch.setattr(storage, "_real_client", lambda: pytest.fail("file save imported MMFDB"))
    result = project_actions.archive_project._action_spec.handler("p1", "portable")
    assert result["ok"] is True
    assert result["backend"] == "file"
    project = storage.load_file(result["file_path"])
    assert project.datasets[isolated_session.unique_identifier]["name"] == "action-data"


def test_archive_action_uses_configured_store(isolated_session, monkeypatch):
    expected = {"ok": True, "project_id": "p1", "version_id": "v2"}
    calls = []
    monkeypatch.setattr(storage, "select_backend", lambda: "mmfdb")
    monkeypatch.setattr(
        storage,
        "save_database",
        lambda project, **kwargs: calls.append((project, kwargs)) or expected,
    )
    result = project_actions.archive_project._action_spec.handler("p1", "remote")
    assert result == expected
    assert calls[0][1]["project_id"] == "p1"
    assert calls[0][0].datasets[isolated_session.unique_identifier]["name"] == "action-data"


def test_close_action_reports_failure_before_resetting_identity(monkeypatch, isolated_session):
    main = SimpleNamespace(
        _current_project_name="live",
        _current_project_id="p1",
    )
    monkeypatch.setattr(
        "chisurf.macros.core_fit.restore_gui_from_fits",
        lambda *args: (_ for _ in ()).throw(OSError("cannot close fits")),
    )
    with pytest.raises(OSError, match="cannot close fits"):
        project_actions.close_project._action_spec.handler(main)
    assert main._current_project_id == "p1"
    assert cs.imported_datasets == [isolated_session]


def test_close_action_cancel_does_not_touch_science_or_identity(monkeypatch, isolated_session):
    from chisurf.core.project.lifecycle import ProjectDocument

    document = ProjectDocument(project_id="p1", version_id="v1", backend="mmfdb")
    main = SimpleNamespace(
        _guard_project_transition=lambda: False,
        _project_document=document,
        _current_project_id="p1",
        _current_project_version_id="v1",
    )

    result = project_actions.close_project._action_spec.handler(main, confirmed=False)

    assert result == {"ok": False, "cancelled": True}
    assert cs.imported_datasets == [isolated_session]
    assert document.project_id == "p1"


def test_restore_action_requires_real_database_before_constructing_client(monkeypatch):
    monkeypatch.setattr(storage, "select_backend", lambda: "file")
    with pytest.raises(storage.ProjectStorageError, match="configured"):
        project_actions.restore_project._action_spec.handler("ver_missing")


def test_restore_action_stages_exact_version_before_commit(monkeypatch, isolated_session):
    saved = capture_session([isolated_session], [], name="remote")
    received = []
    monkeypatch.setattr(storage, "_real_client", lambda *args: object())
    monkeypatch.setattr(storage, "select_backend", lambda: "mmfdb")
    result = {
        "ok": True,
        "project_id": "p1",
        "version_id": "ver_good",
        "project_payload": saved.to_dict(),
    }
    monkeypatch.setattr(
        storage,
        "load_database",
        lambda version_id, **kwargs: received.append(version_id) or (saved, result),
    )
    restored = project_actions.restore_project._action_spec.handler("ver_good")
    assert restored["ok"] is True
    assert received == ["ver_good"]
    assert cs.imported_datasets[0] is not isolated_session
    np.testing.assert_array_equal(cs.imported_datasets[0].y, isolated_session.y)


def test_restore_action_identity_validation_precedes_science_commit(monkeypatch, isolated_session):
    from chisurf.core.project.lifecycle import ProjectDocument

    saved = capture_session([isolated_session], [], name="remote")
    document = ProjectDocument(path=None, project_id="old", version_id="old-v", backend="mmfdb")
    document.stage_database_save = lambda *args: (_ for _ in ()).throw(
        ValueError("bad verified identity")
    )
    main = SimpleNamespace(
        _get_project_document=lambda: document,
        _guard_project_transition=lambda: True,
    )
    monkeypatch.setattr(cs, "cs", main)
    monkeypatch.setattr(storage, "select_backend", lambda: "mmfdb")
    monkeypatch.setattr(storage, "_real_client", lambda *args: object())
    monkeypatch.setattr(
        storage,
        "load_database",
        lambda *args, **kwargs: (
            saved,
            {"ok": True, "project_id": "p1", "version_id": "v1"},
        ),
    )
    committed = []
    monkeypatch.setattr(
        "chisurf.macros.core_fit.load_project_payload",
        lambda *args, **kwargs: committed.append(True),
    )

    with pytest.raises(ValueError, match="bad verified identity"):
        project_actions.restore_project._action_spec.handler("ver_v1")

    assert committed == []
    assert cs.imported_datasets == [isolated_session]
    assert document.project_id == "old"


def test_load_action_retargets_document_and_clears_database_identity(
    monkeypatch, isolated_session, tmp_path
):
    from chisurf.core.project.lifecycle import ProjectDocument

    loaded_curve = DataCurve(x=np.arange(3.0), y=np.arange(3.0) + 9, name="loaded")
    loaded_curve.ex = np.ones(3)
    loaded_curve.ey = np.ones(3)
    project = capture_session([loaded_curve], [], name="file-b")
    target = tmp_path / "b.cs.pto"
    document = ProjectDocument()
    document.record_database_save(
        capture_session([isolated_session], [], name="db-a"),
        {"ok": True, "project_id": "p1", "version_id": "v1"},
    )
    guard_calls = []
    main = SimpleNamespace(
        _guard_project_transition=lambda: guard_calls.append("confirm") or True,
        _get_project_document=lambda: document,
        _current_project_path=None,
        _current_project_id="p1",
        _current_project_version_id="v1",
        _current_project_name="db-a",
    )
    monkeypatch.setattr(cs, "cs", main)
    monkeypatch.setattr(cs, "_project_gui", main, raising=False)
    monkeypatch.setattr(storage, "load_file", lambda path: project)

    result = project_actions.load_project._action_spec.handler(str(target))

    assert result["ok"] is True
    assert document.path == target
    assert document.project_id is None
    assert document.version_id is None
    assert main._current_project_path == target
    assert main._current_project_id is None
    assert main._current_project_version_id is None
    assert cs.imported_datasets[0].name == "loaded"
    assert guard_calls and set(guard_calls) == {"confirm"}


def test_save_action_retargets_document_to_saved_file(monkeypatch, isolated_session, tmp_path):
    from chisurf.core.project.lifecycle import ProjectDocument

    document = ProjectDocument(project_id="p1", version_id="v1", backend="mmfdb")
    main = SimpleNamespace(
        _get_project_document=lambda: document,
        _current_project_path=None,
        _current_project_id="p1",
        _current_project_version_id="v1",
        _current_project_name="remote",
    )
    monkeypatch.setattr(cs, "cs", main)
    target = tmp_path / "saved.cs.pto"
    saved = capture_session([isolated_session], [], name="saved")
    monkeypatch.setattr("chisurf.macros.core_fit.save_project", lambda **kwargs: target)
    monkeypatch.setattr(storage, "load_file", lambda path: saved)

    result = project_actions.save_project._action_spec.handler(str(target), "saved")

    assert result["ok"] is True
    assert document.path == target
    assert document.project_id is None
    assert main._current_project_path == target
    assert main._current_project_id is None


def test_load_action_failure_after_identity_staging_publishes_no_identity(
    monkeypatch, isolated_session, tmp_path
):
    """Identity is staged first but adopted only when the whole load succeeded.

    The file and its identity validate; the restore then fails while presenting
    the restored fits. The document must still be the database project it was,
    the legacy identity fields untouched, and the live science unchanged.

    Two layers give this: the staged identity is adopted only after presentation,
    and a failure restores a snapshot of the document and GUI identity. Either
    alone keeps the contract; the test fails only when both are broken (checked
    by mutating replace_project).
    """
    from chisurf.core.project.lifecycle import ProjectDocument
    from chisurf.macros import core_fit

    loaded_curve = DataCurve(x=np.arange(3.0), y=np.arange(3.0) + 9, name="loaded")
    loaded_curve.ex = np.ones(3)
    loaded_curve.ey = np.ones(3)
    project = capture_session([loaded_curve], [], name="file-b")
    document = ProjectDocument()
    document.record_database_save(
        capture_session([isolated_session], [], name="db-a"),
        {"ok": True, "project_id": "p1", "version_id": "v1"},
    )
    main = SimpleNamespace(
        _guard_project_transition=lambda: True,
        _get_project_document=lambda: document,
        _current_project_path=None,
        _current_project_id="p1",
        _current_project_version_id="v1",
        _current_project_name="db-a",
    )
    monkeypatch.setattr(cs, "cs", main)
    monkeypatch.setattr(cs, "_project_gui", main, raising=False)
    monkeypatch.setattr(storage, "load_file", lambda path: project)
    staged = []
    original_stage = document.stage_file_save
    monkeypatch.setattr(
        document,
        "stage_file_save",
        lambda *args: staged.append(args) or original_stage(*args),
    )

    presented = []

    def failing_presentation(*args, **kwargs):
        presented.append(True)
        raise RuntimeError("presentation failed after science was staged")

    monkeypatch.setattr(core_fit, "restore_gui_from_fits", failing_presentation)

    try:
        result = project_actions.load_project._action_spec.handler(str(tmp_path / "b.cs.pto"))
    except RuntimeError as exc:
        assert "presentation failed" in str(exc)
    else:
        assert result.get("ok") is not True, result

    assert staged, "the failure must happen after identity staging to test publication"
    assert presented, "the restore must reach presentation for the failure to be real"
    assert document.path is None
    assert (document.project_id, document.version_id) == ("p1", "v1")
    assert main._current_project_path is None
    assert (main._current_project_id, main._current_project_version_id) == ("p1", "v1")
    assert main._current_project_name == "db-a"
    assert cs.imported_datasets == [isolated_session]
