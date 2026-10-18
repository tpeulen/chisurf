"""Importing chisurf must not export ``DYLD_LIBRARY_PATH``.

``DYLD_LIBRARY_PATH`` is searched *before* the paths an extension module was
linked against, and dyld reads it once at process start. Setting it therefore
does nothing for the process that sets it and silently overrides library
resolution for **every child process** it later spawns -- where the first thing
to break is a native library load, with a bus error rather than an exception.

``DYLD_FALLBACK_LIBRARY_PATH`` is the safe half: consulted only after normal
resolution fails, so it can rescue a library that would not be found and cannot
hijack one that would. Prepending to that is fine and this test allows it.
"""

from __future__ import annotations

import os
import subprocess
import sys


def test_import_does_not_set_dyld_library_path():
    """A fresh interpreter importing chisurf leaves DYLD_LIBRARY_PATH alone."""
    code = (
        "import os, json;"
        "before = os.environ.get('DYLD_LIBRARY_PATH');"
        "import chisurf.core.settings;"
        "print(json.dumps({'before': before,"
        " 'after': os.environ.get('DYLD_LIBRARY_PATH')}))"
    )
    env = dict(os.environ)
    env.pop("DYLD_LIBRARY_PATH", None)
    env["PYTHONPATH"] = os.pathsep.join(["modules/mmfdb/src", "modules/imp-tricks/src", "."])
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300, env=env
    )
    assert result.returncode == 0, result.stderr[-2000:]
    line = next((line for line in result.stdout.splitlines() if line.startswith("{")), "")
    assert line, f"probe printed nothing usable:\n{result.stdout[-500:]}"
    import json

    seen = json.loads(line)
    assert seen["before"] is None
    assert seen["after"] is None, (
        "importing chisurf set DYLD_LIBRARY_PATH="
        f"{seen['after']!r}; every subprocess now resolves libraries against it "
        "and a native library load in a child bus-errors. Use "
        "DYLD_FALLBACK_LIBRARY_PATH instead."
    )
