"""Screenshot is a main-window action: it copies the window to the clipboard, beside Reset layout.

It used to be a plugin that ran a script against whatever window looked like the
main one and popped a floating Qt label. Copying the host window is the host's
job, so the action lives on the main window, and the ribbon's Main › Window group
(which mirrors the toolbar) shows it.
"""

from __future__ import annotations


def _window(qapp):
    from qtpy import QtWidgets

    from chisurf.gui.screenshot_action import add_screenshot_action

    win = QtWidgets.QMainWindow()
    win.resize(320, 200)
    win.toolBar = QtWidgets.QToolBar(win)
    win.actionReset_layout = QtWidgets.QAction("Reset layout", win)
    win.actionExit_2 = QtWidgets.QAction("Exit", win)
    win.toolBar.addAction(win.actionReset_layout)
    win.toolBar.addAction(win.actionExit_2)
    add_screenshot_action(win, after=win.actionReset_layout)
    return win


def test_the_action_sits_right_after_reset_layout(qapp):
    win = _window(qapp)
    names = [a.objectName() or a.text() for a in win.toolBar.actions()]
    assert names == ["Reset layout", "actionScreenshot", "Exit"]


def test_triggering_it_puts_the_window_on_the_clipboard(qapp):
    from qtpy import QtWidgets

    win = _window(qapp)
    win.show()
    QtWidgets.QApplication.clipboard().clear()
    win.actionScreenshot.trigger()
    image = QtWidgets.QApplication.clipboard().image()
    assert not image.isNull() and image.width() > 0
    assert "copied" in win.statusBar().currentMessage()
