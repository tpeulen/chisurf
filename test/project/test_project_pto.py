from __future__ import annotations

import json

import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.project import Project, ProjectArchive, load_project, save_project
from chisurf.core.project.pto import PROFILE, PROJECT_SUFFIX, ProjectPtoError


def _project() -> Project:
    project = Project(name="heterogeneous", description="PTO round trip")
    project.datasets["decay"] = {"uid": "dataset-decay", "noise": "poisson"}
    project.datasets["correlation"] = {"uid": "dataset-correlation", "noise": "default"}
    project.fits = [
        {
            "uid": "global-fit",
            "members": ["dataset-decay", "dataset-correlation"],
            "shared_parameter": "R0",
        }
    ]
    project.parameters = {"global-fit": [{"uid": "R0", "value": 5.4}]}
    return project


def test_core_project_round_trip_is_a_ptolib_container(tmp_path):
    project = _project()
    saved = save_project(project, tmp_path / "analysis")

    assert saved.name == f"analysis{PROJECT_SUFFIX}"
    assert tttrlib.is_pto_file(str(saved))

    reader = tttrlib.PtoFile()
    assert reader.open(str(saved)), reader.error()
    assert any(tag.name == "chisurf.profile" and tag.text == PROFILE for tag in reader.tags_for(0))
    objects = list(reader.objects())
    state = next(
        obj for obj in objects if obj.kind == "chisurf.project-entry" and obj.name == "project.json"
    )
    assert (
        json.loads(bytes(reader.read(state.uid)).decode("utf-8"))["meta"]["name"] == "heterogeneous"
    )
    reader.close()

    loaded = load_project(saved)
    assert loaded.to_dict() == project.to_dict()


def test_save_failure_keeps_the_previous_valid_project(tmp_path, monkeypatch):
    target = tmp_path / "analysis.cs.pto"
    original = _project()
    save_project(original, target)

    import chisurf.core.project.pto as project_pto

    monkeypatch.setattr(
        project_pto, "read_entries", lambda _: (_ for _ in ()).throw(ProjectPtoError("bad temp"))
    )
    with pytest.raises(ProjectPtoError, match="bad temp"):
        save_project(Project(name="replacement"), target)

    monkeypatch.undo()
    assert load_project(target).name == original.name


def test_archive_adapter_keeps_history_and_embedded_data_as_pto_objects(tmp_path):
    archive = ProjectArchive()
    archive.write_text("project.json", json.dumps(_project().to_dict()))
    archive.write_bytes("history.jsonl", b'{"transaction_id":"t1"}\n')
    archive.write_bytes("data/reference.bin", b"reference-data")

    path = archive.save(tmp_path / "complete.cs.pto")
    reopened = ProjectArchive.open(path)

    assert reopened.list_entries() == ["project.json", "history.jsonl", "data/reference.bin"]
    assert reopened.read_bytes("history.jsonl") == b'{"transaction_id":"t1"}\n'
    assert reopened.read_bytes("data/reference.bin") == b"reference-data"
