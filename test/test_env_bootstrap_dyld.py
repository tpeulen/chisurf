"""Importing chisurf must not export ``DYLD_LIBRARY_PATH``.

``DYLD_LIBRARY_PATH`` is searched *before* the paths an extension module was
linked against, and dyld reads it once at process start. Setting it therefore
does nothing for the process that sets it and silently overrides library
resolution for **every child process** it later spawns -- where the first thing
to break is Qt's font engine, with a bus error rather than an exception.

``DYLD_FALLBACK_LIBRARY_PATH`` is the safe half: consulted only after normal
resolution fails, so it can rescue a library that would not be found and cannot
hijack one that would. Prepending to that is fine and this test allows it.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


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
    env["PYTHONPATH"] = os.pathsep.join(
        ["modules/mmfdb/src", "modules/chinet", "modules/imp-tricks/src", "."]
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300, env=env
    )
    assert result.returncode == 0, result.stderr[-2000:]
    line = next(
        (line for line in result.stdout.splitlines() if line.startswith("{")), ""
    )
    assert line, f"probe printed nothing usable:\n{result.stdout[-500:]}"
    import json

    seen = json.loads(line)
    assert seen["before"] is None
    assert seen["after"] is None, (
        "importing chisurf set DYLD_LIBRARY_PATH="
        f"{seen['after']!r}; every subprocess now resolves libraries against it "
        "and a Qt icon render in a child bus-errors. Use "
        "DYLD_FALLBACK_LIBRARY_PATH instead."
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="dyld is macOS-only")
def test_icon_rendering_survives_a_prepended_dyld_library_path():
    """Guard the failure this protects against, so the reason stays visible.

    Rendering an icon in a child that inherits ``DYLD_LIBRARY_PATH`` pointed at
    the environment's ``lib`` is what crashed; if a future change makes that
    survivable this test says so and the bootstrap could be revisited.
    """
    prefix = os.environ.get("CONDA_PREFIX") or sys.prefix
    lib = os.path.join(prefix, "lib")
    if not os.path.isdir(lib):
        pytest.skip("no environment lib directory to point dyld at")
    code = (
        "import os;"
        "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen');"
        "from qtpy import QtWidgets;"
        "app = QtWidgets.QApplication([]);"
        "from chisurf.plugins.icon_utils import create_emoji_icon;"
        "print('ICON', not create_emoji_icon('\\N{PAGE FACING UP}').isNull())"
    )
    env = dict(os.environ)
    env["DYLD_LIBRARY_PATH"] = lib
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = os.pathsep.join(
        ["modules/mmfdb/src", "modules/chinet", "modules/imp-tricks/src", "."]
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300, env=env
    )
    if result.returncode == 0 and "ICON True" in result.stdout:
        pytest.skip(
            "a prepended DYLD_LIBRARY_PATH no longer breaks Qt font rendering here"
        )
    assert result.returncode != 0, result.stdout
