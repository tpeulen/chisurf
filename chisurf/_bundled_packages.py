"""Expose bundled Python packages when ChiSurf runs from a source checkout."""

from __future__ import annotations

import sys
from pathlib import Path

_BUNDLED_PACKAGE_PATHS = (
    ("mmfdb", "src"),
    ("chinet", None),
    ("ndxplorer", None),
    ("SARibbon-pyqt5", "src"),
)


def bootstrap_bundled_packages() -> tuple[Path, ...]:
    """Prepend available in-tree package roots and return those added.

    Installed ChiSurf distributions contain ``mmfdb`` and ``chinet`` as normal
    packages, so their installation needs no path adjustment. A source checkout
    keeps those packages below ``modules/``; prepending their roots ensures the
    checkout consistently uses the matching bundled versions instead of a stale
    environment installation.
    """
    project_root = Path(__file__).resolve().parent.parent
    existing = {
        Path(entry).resolve()
        for entry in sys.path
        if entry
    }
    added: list[Path] = []

    for module_name, source_dir in _BUNDLED_PACKAGE_PATHS:
        package_root = project_root / "modules" / module_name
        if source_dir:
            package_root /= source_dir
        package_root = package_root.resolve()
        if package_root.is_dir() and package_root not in existing:
            added.append(package_root)
            existing.add(package_root)

    if added:
        sys.path[0:0] = [str(path) for path in added]
    return tuple(added)
