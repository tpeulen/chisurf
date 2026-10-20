"""The example scripts in ``examples/`` must run as their docstrings say.

An example that no longer runs is worse than none, and the only way to know is
to run it. Each script runs in a subprocess from a scratch directory, so the
figure it saves (an :mod:`emtk.figure`, drawn without a window) lands there. They are sized to
finish in seconds (about 20 s for all five), so none is marked slow.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
REPO_ROOT = Path(__file__).resolve().parents[4]


def _examples() -> list[Path]:
    return sorted(EXAMPLES_DIR.glob("[0-9][0-9]_*.py"))


def test_there_are_examples() -> None:
    names = [p.stem for p in _examples()]
    assert names[:4] == [
        "01_donor_quenching",
        "02_fret_pair",
        "03_labeling_scan",
        "04_et_distance_distribution",
    ]


@pytest.mark.parametrize("script", _examples(), ids=lambda p: p.stem)
def test_example_explains_itself(script: Path) -> None:
    source = script.read_text(encoding="utf-8")
    assert source.lstrip().startswith('"""'), f"{script.name} has no module docstring"
    assert f"python chisurf/plugins/quenching_estimator/examples/{script.name}" in source
    # Linear tutorials: read top to bottom, no entry-point boilerplate.
    assert "__main__" not in source


@pytest.mark.parametrize("script", _examples(), ids=lambda p: p.stem)
def test_example_runs(script: Path, tmp_path: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(REPO_ROOT), env.get("PYTHONPATH", "")) if p
    )
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        f"{script.name} exited {result.returncode}\n"
        f"stdout:\n{result.stdout[-2000:]}\nstderr:\n{result.stderr[-3000:]}"
    )
    assert result.stdout.strip(), f"{script.name} printed nothing"
    assert (tmp_path / f"{script.stem}.png").is_file(), f"{script.name} saved no figure"
