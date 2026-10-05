"""Undo and Redo work on a real edit, and still work after the project is reopened.

Stage A edits a fit parameter through its generated control in the real Main
window, presses Undo and Redo through the menu actions and saves a ``.cs.pto``;
stage B is a fresh interpreter that opens it and presses Undo and Redo again. One
press reverts or reapplies the whole edit (its recompute is part of the same step).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("restore_probe") / "history_probe.py"


def _run(stage: str, out: Path) -> dict:
    env = os.environ.copy()
    env.update(
        QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg", CHISURF_SETTINGS_DIR=str(out / "settings")
    )
    result = subprocess.run(
        [sys.executable, str(PROBE), str(out), stage],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return json.loads((out / f"{stage}.json").read_text())


def test_undo_redo_revert_and_reapply_an_edit_before_and_after_reopening(tmp_path):
    a = _run("A", tmp_path)
    assert "edit_error" not in a, a.get("edit_error")
    assert a["v1"] != a["v0"], "the generated control did not change the parameter"
    assert a["after_edit"]["can_undo"]
    assert a["after_undo_value"] == a["v0"]
    assert a["after_undo"]["can_redo"]
    assert a["after_redo_value"] == a["v1"]

    b = _run("B", tmp_path)
    assert b["load_ok"] is True
    assert b["reopened_value"] == a["v1"]
    assert b["reopened"]["n"] == a["after_redo"]["n"]
    assert b["reopened"]["can_undo"]
    assert b["reopened_undo_value"] == a["v0"]
    assert b["reopened_redo_value"] == a["v1"]
