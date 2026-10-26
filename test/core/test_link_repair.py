"""Locate missing data and make a project self-contained (the *Project data* tool's model).

Real files and real linked datasets; the session is a small in-memory :class:`LinkSource`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chisurf.core.data import LinkedDataset
from chisurf.core.project import links
from chisurf.core.project.link_repair import LinkRepairModel


class _Source:
    def __init__(self, datasets, project_path=None):
        self.datasets, self.path, self.changes = list(datasets), project_path, 0

    def linked_datasets(self):
        return self.datasets

    def project_path(self):
        return self.path

    def changed(self):
        self.changes += 1


def _file(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture
def study(tmp_path):
    """Two linked images; the second moves away to a backup disk."""
    here = _file(tmp_path / "study" / "data" / "a.tif", b"A" * 100)
    gone = _file(tmp_path / "study" / "data" / "b.tif", b"B" * 200)
    datasets = [
        LinkedDataset(str(here), data_kind="image", name="a"),
        LinkedDataset(str(gone), data_kind="image", name="b"),
    ]
    backup = tmp_path / "backup" / "2026" / "b.tif"
    backup.parent.mkdir(parents=True)
    gone.rename(backup)
    _file(tmp_path / "backup" / "old" / "b.tif", b"B" * 150)  # same name, other file
    return datasets, backup, tmp_path


def test_the_table_lists_found_and_missing_links(study):
    datasets, _, _ = study
    model = LinkRepairModel(_Source(datasets))
    model.refresh()
    states = {r["name"]: r["state"] for r in model.rows}
    assert states == {"a": "ok", "b": "missing"}
    assert [r["name"] for r in model.unresolved] == ["b"]
    assert "1 not found" in model.summary_text


def test_search_in_folder_proposes_the_same_size_first_and_relinks_it(study):
    datasets, backup, tmp_path = study
    source = _Source(datasets)
    model = LinkRepairModel(source)
    model.refresh()
    model.select_dataset(next(r for r in model.rows if r["name"] == "b"))
    assert model.can_search()
    found = model.search(tmp_path / "backup")
    assert found[0]["path"] == str(backup) and found[0]["match"] == "same size"
    assert model.use_candidate()
    assert datasets[1].address == str(backup.resolve()) and datasets[1].link_status == "ok"
    assert not model.unresolved and source.changes == 1  # one relink, one change


def test_a_different_file_needs_use_anyway_which_records_its_checksum(study):
    datasets, _, tmp_path = study
    model = LinkRepairModel(_Source(datasets))
    model.refresh()
    model.select_dataset(next(r for r in model.rows if r["name"] == "b"))
    other = tmp_path / "backup" / "old" / "b.tif"
    assert not model.replace(other)
    assert model.can_use_anyway() and "different file" in model.status_text
    assert model.use_anyway()
    assert datasets[1].link["size"] == 150 and "checksum is recorded" in model.status_text


def test_make_self_contained_routes_unresolved_links_to_locating_first(study):
    datasets, backup, tmp_path = study
    model = LinkRepairModel(_Source(datasets))
    assert model.make_self_contained() == ["b"]
    assert not any(links.is_embedded(d.link) for d in datasets)  # nothing half-embedded
    assert "Locate these first" in model.status_text
    model.select_dataset(next(r for r in model.rows if r["name"] == "b"))
    model.replace(backup)
    assert model.make_self_contained() == []
    assert all(links.is_embedded(d.link) for d in datasets) and model.self_contained


def test_a_project_file_is_repaired_and_made_self_contained_on_disk(study):
    from chisurf.core.project.link_repair import ProjectFileSource
    from chisurf.core.project.project import Project
    from chisurf.core.project.session import capture_session

    datasets, backup, tmp_path = study
    project_path = tmp_path / "study" / "study.cs.pto"
    capture_session(datasets, []).save(project_path)
    source = ProjectFileSource(project_path)
    model = LinkRepairModel(source)
    model.refresh()
    model.select_dataset(next(r for r in model.rows if r["name"] == "b"))
    model.search(tmp_path / "backup")
    assert model.use_candidate()
    assert model.make_self_contained() == [] and source.dirty
    source.save()
    (tmp_path / "study" / "data" / "a.tif").unlink()
    backup.unlink()
    records = Project.load(project_path).datasets.values()
    assert all(r["link"]["embedded"] for r in records)
    reopened = LinkRepairModel(ProjectFileSource(project_path))
    reopened.refresh()
    assert reopened.self_contained and not reopened.unresolved
