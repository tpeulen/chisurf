"""*Screenshot*: copy the main window to the clipboard, from the window's own action.

Copying the host window is a function of the host, not a tool with a window of its
own, so it is an action beside *Reset layout* rather than a plugin. The ribbon's
Main › Window group mirrors the toolbar, so the action appears there too.
"""

from __future__ import annotations

from qtpy import QtWidgets

__all__ = ["add_screenshot_action", "copy_screenshot_to_clipboard"]


def copy_screenshot_to_clipboard(window) -> bool:
    """Copy a picture of *window* to the clipboard and say so in its status bar.

    Parameters
    ----------
    window : QtWidgets.QMainWindow
        The window to grab.

    Returns
    -------
    bool
        Whether a non-empty picture reached the clipboard.
    """
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app.processEvents()  # paint what is pending before the grab
    pixmap = window.grab()
    clipboard = QtWidgets.QApplication.clipboard()
    if pixmap.isNull() or clipboard is None:
        window.statusBar().showMessage("Screenshot failed: the window could not be grabbed.", 5000)
        return False
    clipboard.setPixmap(pixmap)
    window.statusBar().showMessage("Screenshot copied to clipboard.", 3000)
    return True


def add_screenshot_action(window, after=None):
    """Add the *Screenshot* action to *window*'s toolbar, right after *after*.

    Parameters
    ----------
    window : QtWidgets.QMainWindow
        The main window; the action is kept as ``window.actionScreenshot``.
    after : QtWidgets.QAction, optional
        The toolbar action to follow (the window-layout actions). At the end
        when absent.

    Returns
    -------
    QtWidgets.QAction
        The new action.
    """
    action = QtWidgets.QAction("Screenshot", window)
    action.setObjectName("actionScreenshot")
    action.setToolTip("Copy a picture of the ChiSurf window to the clipboard.")
    action.triggered.connect(lambda: copy_screenshot_to_clipboard(window))
    window.actionScreenshot = action
    toolbar = getattr(window, "toolBar", None)
    if toolbar is not None:
        actions = toolbar.actions()
        index = actions.index(after) + 1 if after in actions else len(actions)
        toolbar.insertAction(actions[index] if index < len(actions) else None, action)
    return action
