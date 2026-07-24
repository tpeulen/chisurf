"""Bring shipped example scripts into the automated test suite (PRD-46).

Every file in ``examples/scripts/*.py`` is discovered and, depending on its
ChiSurf endpoint shebang (``# !chisurf: process | console | ipython``), either

* run as a subprocess and checked for a clean exit (``process`` / no shebang), or
* skipped with a clear reason (``console`` / ``ipython``) — headless execution of
  the interactive endpoints needs the experiment registry and ``cs.macros`` to be
  bootstrapped without Qt, which does not exist yet (tracked in PRD-46).

Adding a new script to ``examples/scripts/`` automatically adds a test node — no
manual registration. Scripts are copied into a temporary directory before running
so their output files land in the tmp dir instead of the source tree (each script
writes next to its own ``__file__``).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "examples" / "scripts"

# Local module sources that are on PYTHONPATH rather than installed as packages.
_EXTRA_PATHS = [
    REPO_ROOT / "modules" / "mmfdb" / "src",
    REPO_ROOT / "modules" / "chinet",
    REPO_ROOT / "modules" / "imp-tricks" / "src",
    REPO_ROOT,
]

# Endpoint shebangs that require an interactive ChiSurf session (Console/IPython).
_INTERACTIVE_SHEBANGS = {"console", "ipython"}

SCRIPTS = sorted(SCRIPTS_DIR.glob("*.py"))


def _endpoint(script: Path) -> str:
    """Return the endpoint declared by a ``# !chisurf: <endpoint>`` shebang.

    Defaults to ``"process"`` when the script has no endpoint shebang.
    """
    try:
        first = script.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return "process"
    marker = "# !chisurf:"
    if first.startswith(marker):
        return first[len(marker):].strip().split()[0].lower()
    return "process"


def _subprocess_env() -> dict:
    """Environment for the subprocess with the local module sources on PYTHONPATH."""
    env = dict(os.environ)
    extra = os.pathsep.join(str(p) for p in _EXTRA_PATHS)
    env["PYTHONPATH"] = extra + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _run_isolated(script: Path, workdir: Path) -> subprocess.CompletedProcess:
    """Copy ``script`` into ``workdir`` and run it there so outputs stay local."""
    local = workdir / script.name
    shutil.copy2(script, local)
    return subprocess.run(
        [sys.executable, str(local)],
        env=_subprocess_env(),
        cwd=str(workdir),
        capture_output=True,
        text=True,
        timeout=600,
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=[s.name for s in SCRIPTS])
def test_example_script_runs(script: Path, tmp_path: Path) -> None:
    """Each headless (``process``) example script runs to a clean exit."""
    endpoint = _endpoint(script)
    if endpoint in _INTERACTIVE_SHEBANGS:
        pytest.skip(
            f"'{endpoint}' endpoint needs a headless experiment/macros bootstrap "
            "that does not exist yet (PRD-46)"
        )
    proc = _run_isolated(script, tmp_path)
    assert proc.returncode == 0, (
        f"{script.name} exited {proc.returncode}\n"
        f"--- stdout tail ---\n{proc.stdout[-2000:]}\n"
        f"--- stderr tail ---\n{proc.stderr[-2000:]}"
    )


def test_protein_unfolding_fret_line_numeric(tmp_path: Path) -> None:
    """The FRET-line script writes physically sensible numeric output.

    Assertions are invariants that hold for the model (not the naive
    "larger Lc lowers E at f=1", which is false — WLC FRET depends on both the
    contour length and the ratio Lp/Lc, so E is non-monotonic in Lc):

    * folded state (f=0) is high FRET, WLC-unfolded state (f=1) is lower FRET;
    * E decreases monotonically as the unfolded fraction increases;
    * in the Lc x Lp sweep the fully-folded (f=0) FRET is independent of the WLC
      parameters and equals the main line's f=0 value.
    """
    script = SCRIPTS_DIR / "protein_unfolding_fret_line.py"
    if not script.exists():
        pytest.skip("protein_unfolding_fret_line.py not present")

    proc = _run_isolated(script, tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]

    line = np.genfromtxt(tmp_path / "unfolding_fret_line.txt")
    frac, e_fret = line[:, 0], line[:, 1]
    assert frac[0] == pytest.approx(0.0) and frac[-1] == pytest.approx(1.0)
    assert e_fret[0] > 0.85, f"folded E should be high, got {e_fret[0]}"
    assert e_fret[-1] < 0.75, f"unfolded E should be lower, got {e_fret[-1]}"
    assert np.all(np.diff(e_fret) < 0), "E must decrease as fraction-unfolded rises"

    sweep = np.genfromtxt(tmp_path / "wlc_sweep_fret_lines.txt", skip_header=1)
    f, e = sweep[:, 2], sweep[:, 3]
    assert sweep.shape[1] == 5 and len(sweep) > 0
    assert np.all((e >= 0.0) & (e <= 1.0)), "FRET efficiencies must be in [0, 1]"
    e_folded = e[f == f.min()]
    assert np.ptp(e_folded) < 1e-6, "folded (f=0) FRET must not depend on WLC params"
    assert e_folded[0] == pytest.approx(e_fret[0], abs=1e-6), (
        "folded FRET must match between the main line and the sweep"
    )
