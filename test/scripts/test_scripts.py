"""Bring shipped example scripts into the automated test suite (PRD-46).

Every file in ``examples/scripts/*.py`` is discovered and, depending on its
ChiSurf endpoint shebang (``# !chisurf: process | console | ipython``), run as a
subprocess and checked for a clean exit — either directly (``process`` / no
shebang) or through :mod:`_headless_runner`, which injects the ``cs`` namespace
and registers the experiments the interactive endpoints expect
(``console`` / ``ipython``).

The interactive endpoints stay in a subprocess because registering the Qt model
classes needs an off-screen ``QApplication``, which must not leak into this
Qt-free suite.

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
from _headless_runner import EXIT_NO_QT

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "examples" / "scripts"
HEADLESS_RUNNER = Path(__file__).resolve().with_name("_headless_runner.py")

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
    """Copy ``script`` into ``workdir`` and run it there so outputs stay local.

    Interactive endpoints (``console`` / ``ipython``) are run through
    :mod:`_headless_runner`, which supplies the ``cs`` namespace and the
    experiment registry they expect; every other script is run directly.
    """
    local = workdir / script.name
    shutil.copy2(script, local)
    if _endpoint(script) in _INTERACTIVE_SHEBANGS:
        command = [sys.executable, str(HEADLESS_RUNNER), str(local)]
    else:
        command = [sys.executable, str(local)]
    env = _subprocess_env()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return subprocess.run(
        command,
        env=env,
        cwd=str(workdir),
        capture_output=True,
        text=True,
        timeout=600,
    )


def _assert_clean_exit(script: Path, proc: subprocess.CompletedProcess) -> None:
    """Fail with the captured output unless ``proc`` exited cleanly.

    A :data:`EXIT_NO_QT` exit skips instead — the machine has no Qt binding, so
    the interactive endpoints cannot be exercised at all.
    """
    if proc.returncode == EXIT_NO_QT:
        pytest.skip(f"{script.name}: no Qt binding available for the interactive endpoint")
    assert proc.returncode == 0, (
        f"{script.name} exited {proc.returncode}\n"
        f"--- stdout tail ---\n{proc.stdout[-2000:]}\n"
        f"--- stderr tail ---\n{proc.stderr[-2000:]}"
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=[s.name for s in SCRIPTS])
def test_example_script_runs(script: Path, tmp_path: Path) -> None:
    """Each example script runs to a clean exit on its declared endpoint."""
    _assert_clean_exit(script, _run_isolated(script, tmp_path))


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
    _assert_clean_exit(script, proc)

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


def test_protein_unfolding_gui_matches_headless(tmp_path: Path) -> None:
    """The interactive script's FRET line equals the pure-core script's.

    Both scripts describe the same two-state model with the same numbers; the
    interactive one reaches it through ``add_fit``, i.e. through the *widget*
    model classes.  Those used to discard the arguments of
    ``gaussians.append(mean=..., sigma=...)`` and silently keep the editor
    defaults, which flattened the FRET line from 0.91 -> 0.58 to 0.580 -> 0.584
    without failing anything.
    """
    gui_script = SCRIPTS_DIR / "protein_unfolding_gui.py"
    core_script = SCRIPTS_DIR / "protein_unfolding_fret_line.py"
    if not (gui_script.exists() and core_script.exists()):
        pytest.skip("protein-unfolding example scripts not present")

    proc = _run_isolated(gui_script, tmp_path)
    _assert_clean_exit(gui_script, proc)

    # The printed table is "f_unfold  E_FRET  <tau> ns" over 11 fractions.
    rows = []
    for raw in proc.stdout.splitlines():
        fields = raw.split()
        if len(fields) != 3:
            continue
        try:
            rows.append([float(value) for value in fields])
        except ValueError:
            continue
    table = np.array(rows)
    assert table.shape == (11, 3), f"expected an 11-point FRET line, got {table.shape}"

    frac, e_fret = table[:, 0], table[:, 1]
    assert frac[0] == pytest.approx(0.0) and frac[-1] == pytest.approx(1.0)
    assert np.all(np.diff(e_fret) < 0), "E must decrease as fraction-unfolded rises"

    core_proc = _run_isolated(core_script, tmp_path)
    _assert_clean_exit(core_script, core_proc)
    core_line = np.genfromtxt(tmp_path / "unfolding_fret_line.txt")
    core_e = np.interp(frac, core_line[:, 0], core_line[:, 1])
    np.testing.assert_allclose(
        e_fret,
        core_e,
        atol=1e-4,
        err_msg="the widget model path must give the same FRET line as the core one",
    )
