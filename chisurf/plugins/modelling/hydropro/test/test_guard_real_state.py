"""Guard: HydroPro captures and tests never write the owner's real preferences or ``~/.chisurf``.

An earlier capture pressed Run in the (since retired) Qt tool, whose ``_save_persisted`` wrote the real
``~/Library/Preferences/com.chisurf.HydroPRO.plist`` (macOS CFPreferences ignores ``$HOME``). The native app persists
through the ChiSurf settings folder instead. This guard snapshots the real plists and ``~/.chisurf`` (without
``logs/``) before and after the capture path and a settings round trip run as child processes with the isolation of
:mod:`.hermetic`, and asserts byte equality. It fails loudly if isolation ever regresses.
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


def _env(tmp_path):
    env = dict(os.environ)
    env.update(PYTHONPATH=f"{REPO}{os.pathsep}{Path.home() / 'dev/emtk'}")
    env.update(hermetic.env_for(tmp_path))
    return env


def test_the_native_settings_land_in_the_isolated_settings_folder(tmp_path):
    """The native app's remembered values are a file under the temporary settings folder, never the real one."""
    code = (
        "from chisurf.emtk import state\n"
        "from chisurf.plugins.modelling.hydropro.gui.model import HydroProModel\n"
        "m = HydroProModel(); m.aer = 4.8\n"
        "assert state.save_settings('hydropro', m.export_settings())\n"
        "assert state.load_settings('hydropro')['aer'] == 4.8\n"
        "print(state._path('hydropro', 'settings'))\n"
    )
    state = hermetic.RealState()
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    name = Path(done.stdout.strip().splitlines()[-1])
    assert tmp_path in name.parents and name.exists() and "4.8" in name.read_text()
    assert state.changes() == []


@pytest.mark.skipif(
    not (REPO / "test/data/atomic_coordinates/pdb_files/148l.pdb").exists(), reason="no 148l.pdb"
)
def test_the_capture_path_leaves_the_real_state_byte_equal(tmp_path):
    """The capture presses Run in the native app (HYDRO works in ~/.hydropp_gui); the real state stays equal."""
    state = hermetic.RealState()
    out = tmp_path / "out"
    out.mkdir()
    done = subprocess.run(
        [sys.executable, str(CAPTURE), str(out), "emtk", "guard"],
        cwd=REPO,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert "EMTK Finished: 1 file(s)." in done.stdout
    assert (out / "guard_1200x800.png").exists()
    assert state.changes() == []
