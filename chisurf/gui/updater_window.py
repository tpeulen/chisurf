"""Shell hook: open the updater as a window of the Qt main application.

The updater is a native emtk app (:mod:`chisurf.plugins.core.updater.gui.app`); the Qt shell only
*hosts* it in an ``emtk.qt_host.ControlHost``. The start-up update prompt opens it quietly
(``suppress_initial_notification``) so the user is not asked a second time.
"""

from __future__ import annotations

from typing import Any


def open_updater_window(suppress_initial_notification: bool = False) -> Any:
    """Create, show and return the updater window.

    Parameters
    ----------
    suppress_initial_notification : bool
        Do not repeat the "Update Available" notice the caller already showed.

    Returns
    -------
    QWidget
        The host window; the caller keeps a reference so it is not garbage collected.
    """
    from emtk.qt_host import ControlHost

    from chisurf.emtk.i18n import install
    from chisurf.plugins.core.updater.gui.app import UpdaterApp
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    install()
    host = ControlHost(
        UpdaterApp(UpdaterModel(suppress_initial_notification=suppress_initial_notification))
    )
    host.is_emtk_native_host = True
    host.setWindowTitle("Updates & Packages")
    host.show()
    return host
