"""V5 project schema tests; legacy formats are intentionally unsupported."""

import json

import numpy as np
import pytest

from chisurf.core.project import Project, ProjectArchive, load_project, save_project


def test_v5_format_roundtrip_and_deterministic_dataset_order(tmp_path):
    from chisurf.core.data import DataCurve
    from chisurf.core.project import capture_session

    curves = [
        DataCurve(x=np.array([0.0, 1.0]), y=np.array([2.0, 1.0]), unique_identifier=uid)
        for uid in ("z-dataset", "a-dataset", "m-dataset")
    ]
    project = capture_session(curves, [], name="v5_project")
    project.description = "portable"

    archive_path = save_project(project, tmp_path / "project")
    archive = ProjectArchive.open(archive_path)
    raw = json.loads(archive.read_text("project.json"))
    archive.close()

    assert archive_path.name == "project.cs.pto"
    assert raw["project_format_version"] == 5
    assert list(raw["datasets"]) == ["a-dataset", "m-dataset", "z-dataset"]

    loaded = load_project(archive_path)
    assert loaded.project_format_version == 5
    assert loaded.name == project.name
    assert loaded.datasets == project.datasets


def test_uid_helpers_are_stable_and_sorted():
    project = Project(name="test", project_format_version=5)
    project.datasets.update({"uid2": {"name": "two"}, "uid1": {"name": "one"}})
    project.fits.extend([{"uid": "fit2"}, {"uid": "fit1"}])

    assert project.get_dataset("uid1")["name"] == "one"
    assert project.get_dataset("missing") is None
    assert project.get_fit("fit1")["uid"] == "fit1"
    assert project.get_fit("missing") is None
    assert project.list_dataset_uids() == ["uid1", "uid2"]
    assert project.list_fit_uids() == ["fit1", "fit2"]


@pytest.mark.parametrize("version", [1, 2, 3, 4, 6])
def test_non_v5_payloads_fail_closed(version):
    with pytest.raises(ValueError, match="requires v5"):
        Project.from_dict({"project_format_version": version})
