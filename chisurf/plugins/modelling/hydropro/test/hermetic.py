"""Isolation for every HydroPro test and capture, and the guard that proves the owner's own state is untouched.

The Qt tool keeps its parameters in ``QSettings("ChiSurf", "HydroPRO")``. On macOS the native format is the plist
``~/Library/Preferences/com.chisurf.HydroPRO.plist`` and CFPreferences ignores ``$HOME``, so redirecting HOME is not
enough: :func:`isolate` switches ``QSettings`` to the INI format and points both scopes into a temporary folder,
before any ``QSettings`` object exists. :class:`RealState` snapshots the real plists and ``~/.chisurf`` (without
``logs/``, which every ChiSurf process writes) so a test can assert that nothing changed.
"""

from __future__ import annotations

import hashlib
import shutil
import os
from pathlib import Path

REAL_HOME = Path(os.path.expanduser("~"))
#: The real preference files a HydroPro Qt window can write (the tool's own and the dock tool's geometry).
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
    for name in ("settings", "mmfdb", "home", "qsettings"):
        (tmp / name).mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(tmp / "home"),
        "CHISURF_SETTINGS_DIR": str(tmp / "settings"),
        "MMFDB_SETTINGS_DIR": str(tmp / "mmfdb"),
        "MMFDB_DATABASE_PATH": str(tmp / "mmfdb.sqlite"),
        "XDG_CONFIG_HOME": str(tmp / "qsettings"),
    }


def isolate(tmp: Path) -> Path:
    """Make every ``QSettings("org", "app")`` of this process an INI file in *tmp*; returns the INI folder.

    Qt 5 on macOS ignores ``QSettings.setDefaultFormat`` for the two-argument constructor, so the class itself is
    replaced (in ``qtpy.QtCore`` and the binding) by a subclass that turns ``QSettings(org, app)`` into
    ``QSettings(IniFormat, UserScope, org, app)``, and the INI folders point into *tmp*. Must run before the code
    under test does ``from qtpy.QtCore import QSettings``. Verified by :func:`assert_isolated`.
    """
    import qtpy.QtCore as qtcore
    from qtpy import QtCore

    folder = Path(tmp) / "qsettings"
    folder.mkdir(parents=True, exist_ok=True)
    base = getattr(QtCore.QSettings, "_hydropro_real", QtCore.QSettings)
    QtCore.QSettings.setDefaultFormat(base.IniFormat)
    for scope in (base.UserScope, base.SystemScope):
        base.setPath(base.IniFormat, scope, str(folder))

    class IniSettings(base):  # type: ignore[valid-type, misc]
        _hydropro_real = base

        def __init__(self, *args, **kwargs):
            if len(args) >= 2 and all(isinstance(a, str) for a in args[:2]):
                super().__init__(base.IniFormat, base.UserScope, args[0], args[1], *args[2:], **kwargs)
            else:
                super().__init__(*args, **kwargs)

    qtcore.QSettings = IniSettings
    QtCore.QSettings = IniSettings
    try:
        import PyQt5.QtCore as _pyqt

        _pyqt.QSettings = IniSettings
    except Exception:
        pass
    assert_isolated(tmp)
    return folder


def assert_isolated(tmp: Path) -> None:
    """Raise if a ``QSettings("ChiSurf", "HydroPRO")`` would not be a file inside *tmp*."""
    from qtpy import QtCore

    probe = QtCore.QSettings("ChiSurf", "HydroPRO")
    name = Path(probe.fileName()).resolve()
    if not str(name).startswith(str(Path(tmp).resolve())) or name.suffix != ".ini":
        raise RuntimeError(f"QSettings is not isolated: {name}")
    if "Library/Preferences" in str(name):
        raise RuntimeError(f"QSettings would write the real preferences: {name}")


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
                if (rel.parts and rel.parts[0] == "logs") or "__pycache__" in rel.parts or not path.is_file():
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
    shutil.copytree(RECORDED, folder / "recorded", dirs_exist_ok=True)  # the fake looks for recorded/ beside itself
    return target
