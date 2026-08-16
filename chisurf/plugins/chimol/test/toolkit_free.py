"""Run a probe against the toolkit-free viewer, in a child process.

Why a subprocess
----------------
``MolView`` binds its base class **once, at import time**, from
``CHIMOL_TOOLKIT``: a ``QWidget`` where Qt is chosen, a plain object where it is
not. So a test that wants the toolkit-free host cannot simply set that variable
-- pytest imports every test module into one process at collection, so the
setting reaches modules that expect Qt and they fail with things like
*"'MolView' object has no attribute 'deleteLater'"* while passing perfectly on
their own.

Two other approaches were tried first and are worth recording so they are not
tried again:

* setting the variable only when ``renderer.view`` is not yet imported -- which
  is *always* true at collection time, so it changed nothing;
* creating a ``QApplication`` and letting ``MolView`` be a ``QWidget`` -- which
  **aborts the interpreter**, because a Qt-bound viewer with an offscreen
  rendercanvas is not a combination that works.

A child process is the honest answer, and it is what
``test_wheel_routing`` and ``test_engine_is_portable`` already do.

Use
---
    from .toolkit_free import probe

    results = probe('''
        app = open_app(size=(900, 600))
        app.cmd.do("fetch 148L")
        emit("residues", len(app.viewer._residue_ids))
    ''')
    assert int(results["residues"]) == 163

The script runs with ``open_app`` and ``emit`` already defined. ``emit(key,
value)`` writes one ``key=value`` line, which is what comes back in the dict.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

#: The repository root, for the child's working directory.
ROOT = pathlib.Path(__file__).resolve().parents[4]

#: Test data, for scripts that need a structure or a trajectory.
DATA = ROOT / "test" / "data"

#: Sample-data directories injected into every probe viewer, matching what
#: the chisurf plugin injects at load -- so ``load 148l.pdb`` resolves in a
#: probe the way it does in the application.
_DATA_DIRS = (
    DATA / "atomic_coordinates" / "pdb_files",
    DATA / "atomic_coordinates" / "trajectory" / "hgbp1",
)

_PREAMBLE = f'''
import json, os, sys
import numpy as np


def emit(key, value):
    """Report one result back to the parent."""
    # The leading newline is load-bearing: the PDB reader can write a
    # ``WARNING ...`` to stdout with no trailing newline, and a plain print
    # would merge this result onto that line -- the parent would never see
    # ``key=value`` as a line of its own.
    print(f"\\n{{key}}={{value}}", flush=True)


#: Sample-data directories this repository carries -- resolved in the parent
#: (the child runs as ``<string>`` and has no ``__file__``), injected into the
#: viewer the same way the chisurf plugin injects them, so a probe script
#: that says ``load 148l.pdb`` works regardless of which host imported the
#: package first.
from chimol.demos.catalog import set_data_dirs as _set_data_dirs

_set_data_dirs(
    {str(_DATA_DIRS[0])!r},
    {str(_DATA_DIRS[1])!r},
)


def open_app(size=(900, 600)):
    """Build the toolkit-free viewer, offscreen."""
    from chimol.host.run import ChimolApp

    return ChimolApp(backend="offscreen", size=size)
'''


def probe(script: str, *, timeout: int = 300) -> dict[str, str]:
    """Run *script* against the toolkit-free viewer and return what it emitted.

    Parameters
    ----------
    script : str
        Python, dedented for you. ``open_app`` and ``emit`` are in scope.
    timeout : int, optional
        Seconds before the child is killed.

    Returns
    -------
    dict
        Every ``key=value`` line the script emitted.
    """
    pytest.importorskip("rendercanvas", reason="the canvas host needs rendercanvas")

    env = dict(os.environ)
    env["CHIMOL_TOOLKIT"] = "none"
    env["CHIMOL_CANVAS"] = "offscreen"
    # Never write into the developer's own settings while testing.
    env.setdefault(
        "CHIMOL_SETTINGS_DIR", str(ROOT / "build" / "test-chimol-settings")
    )

    source = _PREAMBLE + textwrap.dedent(script)
    try:
        result = subprocess.run(
            [sys.executable, "-c", source],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:  # pragma: no cover - a hung child
        pytest.fail(f"the probe did not finish within {timeout}s")

    results = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in result.stdout.splitlines()
        if "=" in line
        and not line.startswith(" ")
        # A bare ``key=`` at the line start: chimol's progress rendering can
        # emit output without a trailing newline, and an ``emit`` that lands
        # on the same line as it ("Computing…n_av=5") must not become a key
        # -- a real key is an identifier at the start of its own line.
        and line.split("=", 1)[0].replace("_", "a").isalnum()
    }
    if not results:
        tail = (result.stdout + result.stderr)[-3000:]
        if "no WebGPU adapter" in tail or "could not create a renderer" in tail:
            pytest.skip("no offscreen WebGPU renderer on this machine")
        pytest.fail(f"the probe produced nothing:\n{tail}")
    return results
