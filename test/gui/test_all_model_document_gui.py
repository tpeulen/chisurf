"""Fail-closed actual-Main acceptance for every independently configured entry.

Science production and each native GUI lifetime are separate bounded processes.
An alias is a separate case even when it resolves to the same model class.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = json.loads((ROOT / "test/project/fixtures/scientific_model_catalogue.json").read_text())


def _run_child(command, directory, stage, timeout):
    """Keep a failed producer distinguishable from GUI publication failures."""
    environment = os.environ.copy()
    environment.update(
        QT_QPA_PLATFORM="offscreen",
        MPLBACKEND="Agg",
        MPLCONFIGDIR=str(directory.parent / "matplotlib-cache"),
        CHISURF_SETTINGS_DIR=str(directory / stage / "settings"),
        MMFDB_SETTINGS_DIR=str(directory / stage / "mmfdb"),
    )
    Path(environment["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
    child = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = child.communicate(timeout=timeout)
        code = child.returncode
    except subprocess.TimeoutExpired:
        # The canonical producer itself verifies in nested fresh interpreters.
        # Retire this entire owned process group, including a stuck native child.
        os.killpg(child.pid, signal.SIGKILL)
        output, _ = child.communicate(timeout=5)
        output = f"{stage} exceeded {timeout}s\n{output}"
        code = 124
    (directory / f"{stage}.log").write_text(output)
    (directory / f"{stage}-outcome.json").write_text(
        json.dumps(
            {"stage": stage, "command": command, "returncode": code, "timeout_seconds": timeout},
            indent=2,
        )
    )
    return code, f"{stage} failed ({code}); evidence: {directory}\n{output}"


@pytest.mark.parametrize("entry", CATALOGUE, ids=[e["configured_path"] for e in CATALOGUE])
def test_configured_model_actual_main_scientific_persistence(tmp_path, entry):
    """Restore real science, edit its exposed control, save, and fresh-restore."""
    assert len(CATALOGUE) == 42
    (tmp_path / "entry.json").write_text(json.dumps(entry, indent=2))
    code, error = _run_child(
        [
            sys.executable,
            "-m",
            "test.project.scientific_catalogue_probe",
            "--case",
            str(CATALOGUE.index(entry)),
            str(tmp_path),
        ],
        tmp_path,
        "science-producer",
        90,
    )
    assert code == 0, error
    failures = []
    code, error = _run_child(
        [
            sys.executable,
            "-m",
            "test.gui.scientific_document_gui_probe",
            str(tmp_path),
            "canonical",
        ],
        tmp_path,
        "canonical",
        120,
    )
    if code:
        failures.append(error)
    code, error = _run_child(
        [sys.executable, "-m", "test.gui.scientific_document_gui_probe", str(tmp_path), "package"],
        tmp_path,
        "group-packaging",
        90,
    )
    if code:
        failures.append(error)
        assert not failures, "\n\n".join(failures)
    for stage in ("before", "restored", "edited"):
        code, error = _run_child(
            [sys.executable, "-m", "test.gui.scientific_document_gui_probe", str(tmp_path), stage],
            tmp_path,
            stage,
            120,
        )
        if code:
            failures.append(error)
            break
    assert not failures, "\n\n".join(failures)
