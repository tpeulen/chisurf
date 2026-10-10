"""ChiSurf Update & Conda Manager Plugin

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

The windows are the native emtk apps in :mod:`.gui.app` (updater) and :mod:`.gui.package_app`
(package manager); this package imports no Qt.
"""

from __future__ import annotations

from .updater import (
    ChiSurfUpdater,
    build_installed_vs_latest_changelog,
    check_for_updates,
    update_chisurf,
)

__all__ = [
    "ChiSurfUpdater",
    "build_installed_vs_latest_changelog",
    "check_for_updates",
    "update_chisurf",
]
