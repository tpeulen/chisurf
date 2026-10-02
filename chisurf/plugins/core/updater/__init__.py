"""
ChiSurf Update & Conda Manager Plugin

This plugin provides:
- Update checker and installer for ChiSurf (via conda)
- A simple Conda Package Manager UI to search/install/update/remove packages,
  manage environments (list/create/remove/clone/export/import), and manage
  channels (list/add/remove)

It supports Windows, macOS, and Linux. On Windows, elevated privileges are
handled when required by the updater.

Notes:
- Updating ChiSurf may close all ChiSurf windows and continue in a separate window.
  After completion, restart ChiSurf manually.
- The update URL is configured in the settings or defaults to the one specified in info.py.

The package imports no Qt: the native emtk app (``gui/app.py``) lives beside the legacy Qt widgets
(``qt_widget.py``, ``package_widget.py``), which are loaded on first use of their names
(``UpdaterWidget``, ``PackageManagerDialog``, ...) so that every existing caller keeps working.
"""

from __future__ import annotations

import importlib

from .updater import ChiSurfUpdater, check_for_updates, update_chisurf

__all__ = [
    "ChiSurfUpdater",
    "check_for_updates",
    "update_chisurf",
    "UpdaterWidget",
    "UpdaterWorker",
    "PackageManagerDialog",
    "build_installed_vs_latest_changelog",
]


def __getattr__(name: str):
    """Load the Qt widgets lazily (PEP 562): ``from chisurf.plugins.core.updater import UpdaterWidget`` still works."""
    if name.startswith("__"):
        raise AttributeError(name)
    module = importlib.import_module(".qt_widget", __name__)
    try:
        return getattr(module, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
