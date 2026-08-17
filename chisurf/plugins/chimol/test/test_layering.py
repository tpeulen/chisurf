"""The import graph obeys the layering, and never grows a new cycle.

``tools/deps.py`` in the chimol repo owns the rule (the ``LAYERS`` table)
and a frozen baseline of today's exceptions (``tools/import_graph_baseline.json``).
This test runs it: an edge outside the layers that is not in the baseline
fails; a baseline entry that is no longer needed fails too, so the baseline
only ever shrinks. Only module-scope imports count.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

_TOOLS = pathlib.Path(__import__("chimol").__file__).resolve().parents[1] / "tools"


@pytest.mark.skipif(not (_TOOLS / "deps.py").exists(), reason="the chimol repo's tools/ are not beside the package")
def test_the_import_graph_respects_the_layers_and_the_baseline_only_shrinks():
    proc = subprocess.run(
        [sys.executable, str(_TOOLS / "deps.py"), "--check"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
