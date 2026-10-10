"""Shell hook: rebuild the main window's plugin toolbar.

The plugin manager (a Qt-free emtk app) calls :func:`refresh_plugin_toolbar` after it saved
a changed toolbar list, so the open main window follows without a restart. The Qt access is
here, in the shell, rather than in the plugin.
"""

from __future__ import annotations


def refresh_plugin_toolbar() -> None:
    """Rebuild the plugin toolbar of the main window, if one is up.

    Returns
    -------
    None
        Nothing happens without a running Qt application or a main window that offers
        ``load_toolbar_plugins``.
    """
    from qtpy import QtWidgets

    for widget in QtWidgets.QApplication.topLevelWidgets():
        loader = getattr(widget, "load_toolbar_plugins", None)
        if callable(loader):
            toolbar = getattr(widget, "plugins_toolbar", None)
            if toolbar is not None:
                toolbar.clear()
            loader()
