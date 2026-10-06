"""Guard: HydroPro captures and tests never write the owner's real preferences or ``~/.chisurf``.

An earlier capture pressed Run in the Qt tool, whose ``_save_persisted`` wrote the real
``~/Library/Preferences/com.chisurf.HydroPRO.plist`` (macOS CFPreferences ignores ``$HOME``). This guard snapshots the
real plists and ``~/.chisurf`` (without ``logs/``) before and after the Qt capture path runs as a child process with
the isolation of :mod:`.hermetic`, and asserts byte equality. It fails loudly if isolation ever regresses.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from . import hermetic

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
CAPTURE = REPO / "okf/plugins/emtk-ports/hydropro/scripts/capture_populated.py"


def _run(script_args, tmp_path):
    env = dict(os.environ)
    env.update(
        QT_QPA_PLATFORM="offscreen", PYTHONPATH=f"{REPO}{os.pathsep}{Path.home() / 'dev/emtk'}"
    )
    env.update(hermetic.env_for(tmp_path))  # the child additionally isolates QSettings itself
    out = tmp_path / "out"
    out.mkdir()
    return subprocess.run(
        [sys.executable, str(CAPTURE), str(out), *script_args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    ), out


def test_isolation_helper_refuses_a_native_settings_path(tmp_path):
    """After ``isolate`` a QSettings("ChiSurf", "HydroPRO") is an INI file in the temp folder, never a plist."""
    code = (
        "import sys; from pathlib import Path\n"
        "from chisurf.plugins.modelling.hydropro.test import hermetic\n"
        "from qtpy import QtCore\n"
        f"tmp = Path({str(tmp_path)!r})\n"
        "hermetic.isolate(tmp)\n"
        "s = QtCore.QSettings('ChiSurf', 'HydroPRO'); s.setValue('probe', 1); s.sync()\n"
        "print(s.fileName())\n"
    )
    state = hermetic.RealState()
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(REPO))
    env.update(hermetic.env_for(tmp_path))
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stderr
    name = Path(done.stdout.strip().splitlines()[-1])
    assert name.suffix == ".ini" and tmp_path in name.parents and name.exists()
    assert state.changes() == []


@pytest.mark.skipif(
    not (REPO / "test/data/atomic_coordinates/pdb_files/148l.pdb").exists(), reason="no 148l.pdb"
)
def test_qt_baseline_capture_path_leaves_the_real_state_byte_equal(tmp_path):
    """The Qt capture presses Run (which calls ``_save_persisted``); the real plist and ``~/.chisurf`` stay equal."""
    state = hermetic.RealState()
    done, out = _run(["qt", "guard_qt"], tmp_path)
    assert done.returncode == 0, done.stderr[-2000:]
    line = next(ln for ln in done.stdout.splitlines() if ln.startswith("QSETTINGS "))
    ini = Path(line.split(" ", 1)[1])
    assert ini.suffix == ".ini" and "Library/Preferences" not in str(ini) and ini.exists()
    # The tool's QSettings did get the run's parameters: in the isolated INI file, not in the real plist.
    assert "hydro_exe" in ini.read_text() and "hp.aer" in ini.read_text()
    assert (
        "1.047e-06" in done.stdout.lower() or "N/A" not in done.stdout
    )  # the recorded report was parsed
    assert (out / "guard_qt.png").exists()
    assert state.changes() == []
