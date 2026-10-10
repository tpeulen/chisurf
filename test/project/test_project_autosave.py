"""The silent project autosave: when it writes, where, and what it never touches."""

from __future__ import annotations

import math
import pathlib
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.project import storage
from chisurf.core.project.lifecycle import Autosave, ProjectDocument, snapshot_fingerprint


def _project(name="analysis"):
    """A real, storable snapshot: one dataset captured through the session codec."""
    from chisurf.core.data import DataCurve
    from chisurf.core.project import capture_session

    curve = DataCurve(x=np.arange(4.0), y=np.arange(4.0) + 1.0, name="data")
    return capture_session([curve], [], name=name)


def _edit(project):
    """Change persisted content without breaking the record's validity."""
    project.description = f"{project.description}x"


def test_due_respects_interval_and_enabled():
    autosave = Autosave(interval_s=10, enabled=True)
    assert autosave._last_time == -math.inf
    assert autosave.due(0.0)
    autosave._last_time = 100.0
    assert not autosave.due(105.0)
    assert autosave.due(110.0)
    assert not Autosave(interval_s=10, enabled=False).due(1e9)


def test_target_is_a_sibling_of_a_saved_document(tmp_path):
    document = ProjectDocument(name="analysis", path=tmp_path / "work" / "analysis.cs.pto")
    target = Autosave.target(document, tmp_path / "elsewhere")
    assert target == tmp_path / "work" / "analysis.autosave.cs.pto"
    assert str(target).endswith(".cs.pto")


def test_target_of_an_unsaved_document_goes_to_the_working_path(tmp_path):
    target = Autosave.target(ProjectDocument(name="untitled"), tmp_path)
    assert target == tmp_path / "autosave" / "untitled.autosave.cs.pto"
    assert str(target).endswith(".cs.pto")


def test_run_writes_a_loadable_project_then_skips_unchanged(tmp_path):
    autosave = Autosave(interval_s=0, enabled=True)
    document = ProjectDocument()
    project = _project()
    calls = []

    def save(project, path):
        calls.append(Path(path))
        return storage.save_file(project, path)

    written = autosave.run(project, save, document, tmp_path, now=1.0)
    assert written is not None and written.is_file()
    assert snapshot_fingerprint(storage.load_file(written)) == snapshot_fingerprint(project)
    # Unchanged content: no second write, however often the timer fires.
    assert autosave.run(project, save, document, tmp_path, now=2.0) is None
    assert len(calls) == 1
    # Changed content is written again.
    _edit(project)
    assert autosave.run(project, save, document, tmp_path, now=3.0) == written
    assert len(calls) == 2
    assert snapshot_fingerprint(storage.load_file(written)) == snapshot_fingerprint(project)


def test_autosave_is_not_a_save(tmp_path):
    """The document's accepted baseline is never moved by an autosave."""
    project = _project()
    document = ProjectDocument()
    document.record_file_save(project, tmp_path / "analysis.cs.pto")
    baseline = document._saved_fingerprint
    _edit(project)
    Autosave(interval_s=0).run(project, storage.save_file, document, tmp_path, now=0.0)
    assert document._saved_fingerprint == baseline
    assert document.is_modified(project)


def test_run_skips_before_the_interval(tmp_path):
    autosave = Autosave(interval_s=60)
    project = _project()
    assert autosave.run(project, storage.save_file, ProjectDocument(), tmp_path, now=0.0)
    _edit(project)
    assert autosave.run(project, storage.save_file, ProjectDocument(), tmp_path, now=30.0) is None


def test_failed_save_leaves_no_temporary_file_and_retries(tmp_path):
    autosave = Autosave(interval_s=0)
    document = ProjectDocument()
    project = _project()

    def failing(project, path):
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        autosave.run(project, failing, document, tmp_path, now=0.0)
    assert list(tmp_path.rglob("*.tmp")) == []
    assert autosave._last_fingerprint is None
    # The next tick writes, because nothing was recorded as written.
    assert autosave.run(project, storage.save_file, document, tmp_path, now=1.0) is not None


def test_storage_failure_mid_write_leaves_no_temporary_file(tmp_path, monkeypatch):
    """A write that fails after the temporary exists cleans it up, target untouched."""
    import chisurf.core.project.pto as pto

    project = _project()
    target = Autosave.target(ProjectDocument(), tmp_path)

    def broken_readback(path):
        assert pathlib.Path(path).exists(), "the temporary was not written"
        raise pto.ProjectPtoError("read-back mismatch")

    monkeypatch.setattr(pto, "read_project", broken_readback)
    with pytest.raises(storage.ProjectStorageError):
        Autosave(interval_s=0).run(project, storage.save_file, ProjectDocument(), tmp_path, 0.0)
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []
    assert not target.exists()
