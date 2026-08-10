"""One dock widget for every ChiSurf tool panel.

A tool that builds its panels out of bare ``QDockWidget`` gets whatever the
platform style happens to do with a dock title bar, which is why the same panel
looks different in two windows. :class:`ChisurfDock` is the one dock the tools
use: it fixes the title-bar chrome, derives a stable ``objectName`` from the
title (so ``saveState``/``restoreState`` can find the dock again across
versions), and offers a checkable toggle action a View menu can show directly.

It is deliberately thin. A dock is a frame around someone else's widget; the
value here is that every tool gets the *same* frame.
"""

from __future__ import annotations

import re

from qtpy import QtCore, QtWidgets

__all__ = ["ChisurfDock"]


def _slug(text: str) -> str:
    """Return *text* as a lowercase identifier usable as an object name.

    Parameters
    ----------
    text : str

    Returns
    -------
    str
    """
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_") or "dock"


class ChisurfDock(QtWidgets.QDockWidget):
    """A tool panel docked into a ChiSurf tool window.

    Parameters
    ----------
    title : str
        The dock's visible title; also the basis of its ``objectName``.
    widget : QtWidgets.QWidget, optional
        The panel this dock frames.
    parent : QtWidgets.QWidget, optional
    namespace : str, optional
        Prefix for the object name, so two tools can each have an "Output"
        dock without their saved layouts colliding.
    areas : QtCore.Qt.DockWidgetAreas, optional
        Where the dock may be dropped. Defaults to every side.
    """

    def __init__(
        self,
        title: str,
        widget: QtWidgets.QWidget | None = None,
        parent: QtWidgets.QWidget | None = None,
        *,
        namespace: str = "",
        areas: QtCore.Qt.DockWidgetAreas | None = None,
    ) -> None:
        super().__init__(title, parent)
        name = f"{_slug(namespace)}_{_slug(title)}_dock" if namespace else f"{_slug(title)}_dock"
        self.setObjectName(name)
        self.setAllowedAreas(areas if areas is not None else QtCore.Qt.AllDockWidgetAreas)
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable
            | QtWidgets.QDockWidget.DockWidgetFloatable
            | QtWidgets.QDockWidget.DockWidgetClosable
        )
        if widget is not None:
            self.setWidget(widget)

    def toggle_action(self, shortcut: str | None = None) -> QtWidgets.QAction:
        """Return the dock's checkable show/hide action, ready for a menu.

        Parameters
        ----------
        shortcut : str, optional
            A key sequence to attach, e.g. ``"Ctrl+Shift+K"``.

        Returns
        -------
        QtWidgets.QAction
        """
        action = self.toggleViewAction()
        action.setToolTip(f"Show or hide the {self.windowTitle()} panel")
        if shortcut:
            action.setShortcut(shortcut)
        return action

    def show_raised(self) -> None:
        """Make the dock visible and bring it in front of any tabbed siblings."""
        self.setVisible(True)
        self.raise_()
