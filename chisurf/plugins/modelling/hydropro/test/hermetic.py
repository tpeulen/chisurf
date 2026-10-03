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


_PATCHED: list = []  # (module, the QSettings class it held)
_REAL: list = []  # the binding's own QSettings: the class that writes the real preferences


def _binding_qsettings():
    """The Qt binding's QSettings (``PyQt5.QtCore.QSettings``...): what ``QSettings(org, app)`` has always been."""
    import sys

    import qtpy

    for name in (f"{qtpy.API_NAME}.QtCore", "PyQt5.QtCore", "PySide2.QtCore", "PyQt6.QtCore", "PySide6.QtCore"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "QSettings"):
            return module.QSettings
    raise RuntimeError("no Qt binding loaded")


def _holders(known) -> list:
    import sys

    found = []
    for module in list(sys.modules.values()):
        try:
            if getattr(module, "QSettings", None) in known:
                found.append(module)
        except Exception:  # lazy modules that raise on attribute access
            continue
    return found


def isolate(tmp: Path) -> Path:
    """Make every ``QSettings`` of this process an INI file in *tmp*; returns the INI folder.

    Qt 5 on macOS ignores ``QSettings.setDefaultFormat`` for the two-argument constructor, so the class itself is
    replaced (as ``chisurf.gui.gui_tweaks.isolate_qsettings_for_qa`` does at import for a QA run, which a module imported
    earlier can miss) by a subclass of the BINDING's class that FORCES the INI format: ``QSettings(org, app)`` becomes
    ``QSettings(IniFormat, UserScope, org, app)`` and an explicit ``NativeFormat`` becomes INI too, so no construction
    path can reach a plist. The INI folders point into *tmp*. Every imported module holding the binding's class or a
    QA replacement under the name ``QSettings`` is rebound (``from qtpy.QtCore import QSettings`` binds at import).
    :func:`restore` undoes it; :func:`assert_no_leaks` and :func:`assert_isolated` verify it.
    """
    from qtpy import QtCore

    restore()
    if not _REAL:
        _REAL.append(_binding_qsettings())
    base = _REAL[0]
    folder = Path(tmp) / "qsettings"
    folder.mkdir(parents=True, exist_ok=True)
    base.setDefaultFormat(base.IniFormat)
    for scope in (base.UserScope, base.SystemScope):
        base.setPath(base.IniFormat, scope, str(folder))

    class IniSettings(base):  # type: ignore[valid-type, misc]
        def __init__(self, *args, **kwargs):
            args = list(args)
            if len(args) >= 2 and all(isinstance(a, str) for a in args[:2]):
                args = [base.IniFormat, base.UserScope, *args]
            elif len(args) == 1 and isinstance(args[0], str):
                args = [base.IniFormat, base.UserScope, args[0]]
            elif args and args[0] == base.NativeFormat:
                args[0] = base.IniFormat
            elif len(args) >= 2 and args[1] == base.NativeFormat:
                args[1] = base.IniFormat
            super().__init__(*args, **kwargs)

    known = {base, QtCore.QSettings}
    for module in _holders(known):
        _PATCHED.append((module, module.QSettings))
        module.QSettings = IniSettings
    assert_isolated(tmp)
    return folder


def restore() -> None:
    """Undo :func:`isolate`: every rebound module holds the class it held before."""
    while _PATCHED:
        module, previous = _PATCHED.pop()
        module.QSettings = previous


def assert_isolated(tmp: Path) -> None:
    """Raise if a ``QSettings("ChiSurf", "HydroPRO")`` would not be a file inside *tmp*."""
    from qtpy import QtCore

    probe = QtCore.QSettings("ChiSurf", "HydroPRO")
    name = Path(probe.fileName()).resolve()
    if not str(name).startswith(str(Path(tmp).resolve())) or name.suffix != ".ini":
        raise RuntimeError(f"QSettings is not isolated: {name}")
    if "Library/Preferences" in str(name):
        raise RuntimeError(f"QSettings would write the real preferences: {name}")


def assert_no_leaks() -> None:
    """Raise if any imported module still holds a ``QSettings`` that could write the real preferences."""
    if not _REAL:
        raise RuntimeError("isolate() was never called")
    leaks = [m.__name__ for m in _holders({_REAL[0]})]
    if leaks:
        raise RuntimeError(f"modules still use the real QSettings: {leaks}")


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
                if path.suffix == ".pyc":  # ChiSurf keeps its bytecode cache here (a module edited meanwhile is recompiled)
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
