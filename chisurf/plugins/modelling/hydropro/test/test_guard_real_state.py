"""Guard: HydroPro tests never write the owner's real preferences or ``~/.chisurf``.

The retired Qt tool's ``_save_persisted`` wrote the real ``~/Library/Preferences/com.chisurf.HydroPRO.plist`` (macOS
CFPreferences ignores ``$HOME``). The native app persists through the ChiSurf settings folder instead. This guard
snapshots the real plists and ``~/.chisurf`` (without ``logs/``) before and after a settings round trip run as a child
process with the isolation of :mod:`.hermetic`, and asserts byte equality. It fails loudly if isolation ever regresses.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import hermetic

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())


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

