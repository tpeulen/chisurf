"""Execute the MMFDB example notebooks headlessly as a regression guard.

Each example under ``modules/mmfdb/examples/`` (and the H2MM plugin example) is
run end-to-end; any cell that raises fails the test. These are marked ``slow``
(excluded from the default suite) because each notebook spins up a demo MMFDB
server, simulates photons, and runs real analyses.

Run them with::

    pytest -m slow test/plugins/burst/test_mmfdb_example_notebooks.py

The notebooks are executed in a **subprocess** (``python -m nbconvert --execute``)
so the kernel re-bootstraps chisurf's native-library environment itself, rather
than inheriting a half-initialised one from the pytest parent. ``-m nbconvert``
(not ``-m jupyter nbconvert``) is used so the run stays in *this* interpreter's
environment instead of dispatching to whatever ``jupyter`` is first on PATH. The
absolute local-module sources are put on ``PYTHONPATH`` because the kernel runs
with the notebook's directory as its working directory.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _available(module: str) -> bool:
    """Return True if a module is importable, without importing it here."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


for _required in ("tttrlib", "mmfdb", "nbconvert", "jupyter_client"):
    if not _available(_required):
        pytest.skip(f"{_required} not available", allow_module_level=True)

_REPO = Path(__file__).resolve().parents[3]
_EXAMPLES = _REPO / "modules" / "mmfdb" / "examples"
_H2MM = _REPO / "chisurf" / "plugins" / "burst" / "burst_h2mm" / "examples"

# Absolute local-module sources; the notebook kernel runs with the notebook dir
# as CWD, so relative PYTHONPATH entries would not resolve.
_KERNEL_PATHS = [
    _REPO,
    _REPO / "modules" / "mmfdb" / "src",
    _REPO / "modules" / "chinet",
    _REPO / "modules" / "imp-tricks" / "src",
]

# notebook path -> extra importable modules it needs (skipped if missing)
NOTEBOOKS = {
    _EXAMPLES / "mmfdb_00_overview.ipynb": (),
    _EXAMPLES / "mmfdb_01_burst_selection.ipynb": (),
    _EXAMPLES / "mmfdb_02_bva.ipynb": (),
    _EXAMPLES / "mmfdb_03_h2mm.ipynb": (),
    _EXAMPLES / "mmfdb_04_fcs.ipynb": (),
    _EXAMPLES / "mmfdb_05_imaging.ipynb": (),
    _EXAMPLES / "mmfdb_06_external_tool_provenance.ipynb": ("fretbursts", "phconvert"),
    _EXAMPLES / "mmfdb_07_deposition.ipynb": (),
    _EXAMPLES / "mmfdb_08_standalone_no_lockin.ipynb": ("fretbursts", "phconvert"),
    _H2MM / "H2MM_02_MMFDB_GroundTruth.ipynb": (),
}


def _subprocess_env() -> dict[str, str]:
    """Return a subprocess env for running a notebook in this interpreter's env.

    chisurf's env-bootstrap (already run in the pytest parent via the hermetic
    conftest fixture) points ``DYLD_*_LIBRARY_PATH`` at the *base* mambaforge
    lib; inherited by a child in a different conda env, that shadows its own
    zlib and breaks Pillow (``_zng_deflateInit2`` missing). Drop those so the
    child resolves native libraries from its own environment.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("DYLD_")}
    absolute = [str(p) for p in _KERNEL_PATHS if p.exists()]
    env["PYTHONPATH"] = os.pathsep.join(absolute)
    return env


@pytest.mark.slow
@pytest.mark.parametrize(
    "notebook, requires",
    [pytest.param(p, r, id=p.name) for p, r in NOTEBOOKS.items()],
)
def test_example_notebook_executes(notebook: Path, requires: tuple[str, ...]) -> None:
    """The example notebook runs top to bottom without any cell raising."""
    if not notebook.exists():
        pytest.skip(f"missing notebook: {notebook}")
    for module in requires:
        if not _available(module):
            pytest.skip(f"{module} not available")

    result = subprocess.run(
        [
            sys.executable, "-m", "nbconvert",
            "--to", "notebook", "--execute", "--stdout",
            "--ExecutePreprocessor.timeout=600",
            notebook.name,
        ],
        cwd=str(notebook.parent),
        env=_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert result.returncode == 0, f"notebook failed:\n{result.stderr[-3000:]}"
