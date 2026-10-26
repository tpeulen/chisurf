"""The session starts with a blank temporary ``.cs.pto`` that data can be embedded in from the first drop.

Until the user saves it somewhere it lives in the temp folder (here redirected with
``CHISURF_PROJECT_TEMP_DIR``); Save asks for a location and removes the temporary file; giving the
work up removes it; abandoned temporary projects of earlier sessions are cleaned or kept for recovery.
The window title names the project file first.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest
from emtk.testing import Driver

from chisurf.core.project import temp_project
from test.native_emtk.test_emtk_shell_fits import (  # noqa: F401  (the fixture and the helpers)
    SHOTS,
    _idle,
    _settle,
    shell,
)

REPO = Path(__file__).resolve().parents[2]
SPC = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"


@pytest.fixture(autouse=True)
def _temp_dir(tmp_path, monkeypatch):
    root = tmp_path / "temp-projects"
    monkeypatch.setenv("CHISURF_PROJECT_TEMP_DIR", str(root))
    return root


def _started(driver, shell):  # noqa: F811
    _settle(
        driver,
        lambda: shell.project.temporary and not shell.project.busy,
        "the temporary project",
    )
    return Path(shell.project.document.path)


def test_the_session_starts_with_a_blank_temporary_project(shell, _temp_dir):  # noqa: F811
    driver = Driver(shell, (1300, 900))
    driver.frame(4)
    path = _started(driver, shell)
    assert path.parent == _temp_dir and path.is_file()
    assert path.name.startswith("untitled-") and path.name.endswith(".cs.pto")
    assert oct(_temp_dir.stat().st_mode & 0o777) == "0o700"
    title = shell.window_title
    assert title.startswith(path.name) and "temporary" in title and title.endswith("ChiSurf")
    driver.frame(2)
    assert "project_badge" in shell.item_rects
    driver.screenshot(SHOTS / "temp_project_start.png")


def test_embedding_works_from_the_first_drop(shell, tmp_path):  # noqa: F811
    driver = Driver(shell, (1300, 900))
    driver.frame(4)
    path = _started(driver, shell)
    empty = path.stat().st_size
    shell.data.read.import_mode = "embed"
    try:
        target = tmp_path / "m003.spc"
        shutil.copy(SPC, target)
        assert shell.on_files_dropped([str(target)])
        _settle(
            driver,
            lambda: (
                _idle(shell)
                and any(r.get("kind") == "photons" for r in shell.data.datasets.datasets)
            ),
            "the photon dataset",
        )
    finally:
        shell.data.read.import_mode = "link"
    shell.project.autosave_now()
    _settle(driver, lambda: not shell.project.busy, "the temporary project written")
    # The photons are inside the temporary project now (the embed needs no save location).
    assert path.stat().st_size >= empty + SPC.stat().st_size
    marker = json.loads(Path(f"{path}{temp_project.MARKER_SUFFIX}").read_text())
    assert marker["has_content"] is True and marker["pid"] == os.getpid()
    driver.frame(4)
    assert "•" in shell.window_title  # unsaved work
    driver.screenshot(SHOTS / "temp_project_after_drop.png")


def test_save_asks_for_a_location_and_removes_the_temporary_file(shell, tmp_path):  # noqa: F811
    driver = Driver(shell, (1300, 900))
    driver.frame(4)
    temp = _started(driver, shell)
    project = shell.project
    project.save()
    driver.frame(2)
    assert project.file_dialog is not None and project.file_dialog.mode == "save"
    chosen = tmp_path / "kept.cs.pto"
    project.choose_file(chosen)
    _settle(driver, lambda: not project.busy and chosen.is_file(), "the save")
    assert not project.temporary and Path(project.document.path) == chosen
    assert not temp.exists() and not Path(f"{temp}{temp_project.MARKER_SUFFIX}").exists()
    assert shell.window_title == "kept.cs.pto — ChiSurf"


def test_quitting_gives_the_temporary_project_up(shell):  # noqa: F811
    driver = Driver(shell, (1300, 900))
    driver.frame(4)
    temp = _started(driver, shell)
    shell.project.quit_confirmed = False
    shell.project._drop_temporary()  # what the confirmed quit runs (empty, or Don't Save)
    assert not temp.exists() and not shell.project.temporary


def test_abandoned_temporary_projects_are_cleaned_or_kept_for_recovery(_temp_dir):
    root = temp_project.temp_root()
    empty = root / "untitled-20200101-000000.cs.pto"
    work = root / "untitled-20200101-000001.cs.pto"
    old = root / "untitled-20200101-000002.cs.pto"
    for path, content in ((empty, False), (work, True), (old, True)):
        path.write_bytes(b"x")
        Path(f"{path}{temp_project.MARKER_SUFFIX}").write_text(
            json.dumps({"pid": 999_999_999, "has_content": content})
        )
    ancient = time.time() - (temp_project.KEEP_DAYS + 1) * 86400
    os.utime(old, (ancient, ancient))
    alive = root / "untitled-20200101-000003.cs.pto"
    alive.write_bytes(b"x")
    temp_project.mark(alive, has_content=False)  # this process: in use, never touched
    kept = temp_project.clean_abandoned()
    assert kept == [work]
    assert not empty.exists() and not old.exists() and work.exists() and alive.exists()


def test_only_temporary_paths_are_ever_removed(tmp_path, _temp_dir):
    elsewhere = tmp_path / "mine.cs.pto"
    elsewhere.write_bytes(b"x")
    temp_project.remove(elsewhere)
    assert elsewhere.exists()
    assert not temp_project.is_temporary(elsewhere)
    assert temp_project.is_temporary(temp_project.new_path())
