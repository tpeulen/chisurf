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

_PREAMBLE = '''
import json, os, sys
import numpy as np


def emit(key, value):
    """Report one result back to the parent."""
    print(f"{key}={value}")


def open_app(size=(900, 600)):
    """Build the toolkit-free viewer, offscreen."""
    from chisurf.plugins.chimol.chimol.host.run import ChimolApp

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
        if "=" in line and not line.startswith(" ")
    }
    if not results:
        tail = (result.stdout + result.stderr)[-3000:]
        if "no WebGPU adapter" in tail or "could not create a renderer" in tail:
            pytest.skip("no offscreen WebGPU renderer on this machine")
        pytest.fail(f"the probe produced nothing:\n{tail}")
    return results
