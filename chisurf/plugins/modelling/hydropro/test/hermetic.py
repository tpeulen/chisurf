"""Isolation for every HydroPro test and capture, and the guard that proves the owner's own state is untouched.

:func:`env_for` points HOME, the ChiSurf settings folder and MMFDB into a temporary folder; the native app persists
through the settings folder and runs HYDRO in ``~/.hydropp_gui``, so both stay inside it. :class:`RealState` snapshots
the real HydroPRO preference plists (written by the retired Qt tool; nothing may write them again) and ``~/.chisurf``
(without ``logs/``, which every ChiSurf process writes) so a test can assert that nothing changed.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

REAL_HOME = Path(os.path.expanduser("~"))
#: The real preference files the retired Qt HydroPro tool wrote (its own and the dock tool's geometry).
REAL_PLISTS = (
    REAL_HOME / "Library/Preferences/com.chisurf.HydroPRO.plist",
    REAL_HOME / "Library/Preferences/com.chisurf.ChisurfDockTool.plist",
    REAL_HOME / "Library/Preferences/com.chisurf.hydropro.plist",
)
REAL_CHISURF = REAL_HOME / ".chisurf"
DATA = Path(__file__).parent / "data"
FAKE_EXE = DATA / "fake_hydro.sh"
RECORDED = DATA / "recorded"


def env_for(tmp: Path) -> dict[str, str]:
    """Environment variables that put every ChiSurf, MMFDB and home folder into *tmp* (folders are created)."""
    for name in ("settings", "mmfdb", "home", "config"):
        (tmp / name).mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(tmp / "home"),
        "CHISURF_SETTINGS_DIR": str(tmp / "settings"),
        "MMFDB_SETTINGS_DIR": str(tmp / "mmfdb"),
        "MMFDB_DATABASE_PATH": str(tmp / "mmfdb.sqlite"),
        "XDG_CONFIG_HOME": str(tmp / "config"),
    }


def _digest(path: Path) -> tuple:
    if not path.is_file():
        return ("absent",)
    size = path.stat().st_size
    if size > 8_000_000:
        return ("big", size, path.stat().st_mtime_ns)
    return ("sha256", hashlib.sha256(path.read_bytes()).hexdigest())


class RealState:
    """Snapshot of the owner's real plists and ``~/.chisurf`` (without ``logs/``); :meth:`changes` lists differences."""

    def __init__(self, plists=REAL_PLISTS, chisurf: Path = REAL_CHISURF) -> None:
        self.plists, self.chisurf = tuple(plists), Path(chisurf)
        self.before = self.snapshot()

    def snapshot(self) -> dict:
        out = {str(p): _digest(p) for p in self.plists}
        if self.chisurf.exists():
            for path in sorted(self.chisurf.rglob("*")):
                rel = path.relative_to(self.chisurf)
                if (
                    (rel.parts and rel.parts[0] == "logs")
                    or "__pycache__" in rel.parts
                    or not path.is_file()
                ):
                    continue
                if (
                    path.suffix == ".pyc"
                ):  # ChiSurf keeps its bytecode cache here (a module edited meanwhile is recompiled)
                    continue
                if path.name.endswith(
                    ("-wal", "-shm")
                ):  # a running ChiSurf rewrites the MMFDB's SQLite journal
                    continue
                out[str(path)] = _digest(path)
        return out

    def changes(self) -> list[str]:
        after = self.snapshot()
        names = sorted(set(self.before) | set(after))
        return [n for n in names if self.before.get(n) != after.get(n)]


def install_fake_exe(folder: Path, name: str = "hydropro10.exe") -> Path:
    """Copy the fake executable into *folder* under *name* (the name decides HYDROPRO vs HYDRO++); returns its path."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    target.write_bytes(FAKE_EXE.read_bytes())
    target.chmod(0o755)
    shutil.copytree(
        RECORDED, folder / "recorded", dirs_exist_ok=True
    )  # the fake looks for recorded/ beside itself
    return target
