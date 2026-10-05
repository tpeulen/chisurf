from __future__ import annotations

import json

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.project import Project, ProjectArchive, load_project, save_project
from chisurf.core.project.pto import (
    PROFILE,
    PROJECT_SUFFIX,
    ProjectPtoError,
    write_project,
)


def _project() -> Project:
    """Exercise the transport with reconstructible scientific objects and links."""
    from chisurf.core.data import DataCurve, DataCurveGroup
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.fitting.parameter import FittingParameter
    from chisurf.core.models.description import tcspc_lifetime
    from chisurf.core.project import capture_session

    curves = DataCurveGroup(
        [
            DataCurve(
                x=np.array([0.0, 1.0, 2.0]),
                y=np.array([10.0, 6.0, 3.0]),
                unique_identifier="dataset-decay",
            ),
            DataCurve(
                x=np.array([0.0, 1.0, 2.0]),
                y=np.array([12.0, 8.0, 4.0]),
                unique_identifier="dataset-correlation",
            ),
        ],
        name="paired measurements",
    )
    fit = FitGroup(data=curves, model_class=tcspc_lifetime)
    fit.unique_identifier = "global-fit"
    shared = FittingParameter(name="R0", value=5.4)
    fit._model.append_global_parameter(shared)
    for member in fit.grouped_fits:
        parameter = next(p for p in member.model.parameters_all if not p.is_output)
        parameter.link = shared
    project = capture_session([curves], [fit], name="heterogeneous")
    project.description = "PTO round trip"
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
    state = next(obj for obj in objects if obj.kind == "chisurf.project" and obj.name == "project")
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


def test_write_project_validates_before_creating_candidate(tmp_path, monkeypatch):
    target = tmp_path / "analysis.cs.pto"
    save_project(_project(), target)
    old = target.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("candidate path created before payload validation")

    monkeypatch.setattr("chisurf.core.project.pto._temporary_path", forbidden)
    payload = Project(name="invalid", project_format_version=4).to_dict()
    with pytest.raises(ValueError, match="Unsupported project format version"):
        write_project(target, payload)

    assert target.read_bytes() == old
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_write_project_rejects_malformed_session_before_staging(tmp_path, monkeypatch):
    target = tmp_path / "analysis.cs.pto"
    save_project(_project(), target)
    old = target.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("candidate path created before session validation")

    monkeypatch.setattr("chisurf.core.project.pto._temporary_path", forbidden)
    payload = Project(
        name="invalid-session",
        metadata={"session_codec": "detached-v2"},
        fits=[{"uid": "fit-without-members"}],
    ).to_dict()
    with pytest.raises(ValueError, match="has no members"):
        write_project(target, payload)

    assert target.read_bytes() == old
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_project_save_rejects_invalid_payload_before_staging(tmp_path, monkeypatch):
    target = tmp_path / "analysis.cs.pto"
    save_project(_project(), target)
    old = target.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("candidate path created before Project.save validation")

    monkeypatch.setattr("chisurf.core.project.pto._temporary_path", forbidden)
    with pytest.raises(ValueError, match="Unsupported project format version"):
        save_project(Project(name="invalid", project_format_version=4), target)

    assert target.read_bytes() == old
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_write_project_write_failure_preserves_target_and_cleans_temp(tmp_path, monkeypatch):
    target = tmp_path / "analysis.cs.pto"
    save_project(_project(), target)
    old = target.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("write failed")

    monkeypatch.setattr("chisurf.core.project.pto._payload_bytes", fail)
    with pytest.raises(OSError, match="write failed"):
        write_project(target, Project(name="replacement").to_dict())

    assert target.read_bytes() == old
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_write_project_readback_validation_failure_preserves_target_and_cleans_temp(
    tmp_path, monkeypatch
):
    target = tmp_path / "analysis.cs.pto"
    save_project(_project(), target)
    old = target.read_bytes()
    import chisurf.core.project.pto as project_pto

    original = project_pto._validate_project_payload
    calls = 0

    def fail_second(payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("staged payload rejected")
        return original(payload)

    monkeypatch.setattr(project_pto, "_validate_project_payload", fail_second)
    with pytest.raises(ValueError, match="staged payload rejected"):
        write_project(target, _project().to_dict())

    assert target.read_bytes() == old
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_write_project_replace_failure_preserves_target_and_cleans_temp(tmp_path, monkeypatch):
    target = tmp_path / "analysis.cs.pto"
    save_project(_project(), target)
    old = target.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr("chisurf.core.project.pto.os.replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        write_project(target, Project(name="replacement").to_dict())

    assert target.read_bytes() == old
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


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
