"""The hidden way in.

Lumis Quest is not in a menu. It is a game that teaches the documentation, and a
game listed beside the fitting tools reads as one of the tools -- so it is
`menu_hidden` in its manifest, like every other game shipped here, and until now
that meant it could only be opened by importing its widget from a console.

An easter egg is the honest version of that: not in a menu, and *reachable* --
by the sequence every player of the era already knows, typed anywhere in the
main window.

The sequence matching lives in :class:`CodeWatcher`, which knows nothing about
Qt: a code that only fires under a real key event is a code nobody can test.
:class:`EasterEggFilter` is the shell that feeds it key presses.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Callable, Optional, Sequence

_log = logging.getLogger(__name__)

__all__ = ["KONAMI", "CodeWatcher", "EasterEggFilter", "install", "open_lumis_quest"]

#: Up, up, down, down, left, right, left, right, B, A. Spelled as Qt key codes
#: at install time; the watcher itself compares whatever it is given.
KONAMI: tuple[str, ...] = (
    "Up", "Up", "Down", "Down", "Left", "Right", "Left", "Right", "B", "A",
)


class CodeWatcher:
    """Fires when a sequence of keys has been entered in order.

    Parameters
    ----------
    code : sequence
        What to watch for.
    on_complete : callable
        Called with no arguments when the sequence completes.

    Notes
    -----
    Matching is on the *last* keys entered rather than on a counter that a
    wrong key resets. The difference shows on ``Up Up Up Down Down …``, which
    contains the code and which is how people actually type it -- a counter
    that restarts on the mismatch has already thrown away the two Ups it
    needed, and fails for exactly the person who knows the code best.
    """

    def __init__(self, code: Sequence, on_complete: Callable[[], None]) -> None:
        self.code = tuple(code)
        self.on_complete = on_complete
        self.recent: deque = deque(maxlen=max(len(self.code), 1))

    @property
    def progress(self) -> int:
        """How much of the code the last keys already spell."""
        keys = tuple(self.recent)
        for length in range(len(keys), 0, -1):
            if keys[-length:] == self.code[:length]:
                return length
        return 0

    def feed(self, key) -> bool:
        """Offer one key. Returns whether the sequence just completed."""
        if not self.code:
            return False
        self.recent.append(key)
        if tuple(self.recent) != self.code:
            return False
        self.recent.clear()
        self.on_complete()
        return True


def open_lumis_quest() -> object | None:
    """Open the game, through the same path the plugin menu would use.

    Returns
    -------
    object or None
        The widget, or ``None`` if it could not be opened -- an easter egg
        that raises into the main window is a bug with a costume on.
    """
    try:
        from chisurf.plugins.misc.games.lumis_quest.gui.tool import LumisQuestWidget

        widget = LumisQuestWidget()
        widget.show()
        widget.raise_()
        widget.activateWindow()
        return widget
    except Exception:
        _log.exception("the hidden game could not be opened")
        return None


class EasterEggFilter:
    """A Qt event filter that feeds key presses to a :class:`CodeWatcher`.

    Built as a plain class with an ``eventFilter`` method and mixed onto
    ``QObject`` in :func:`install`, so importing this module costs no Qt.
    """

    def eventFilter(self, obj, event):  # noqa: N802 - Qt's spelling
        """Watch key presses; never consume them."""
        try:
            from qtpy import QtCore, QtGui

            if event.type() == QtCore.QEvent.KeyPress:
                self.watcher.feed(QtGui.QKeySequence(event.key()).toString())
        except Exception:
            pass
        return False


def install(app, on_complete: Optional[Callable[[], None]] = None):
    """Watch the whole application for the code.

    Parameters
    ----------
    app : QtWidgets.QApplication
        The application to filter. Installing on the *application* rather than
        on one window is what makes the code work wherever the focus is.
    on_complete : callable, optional
        What the code does. Defaults to opening the game.

    Returns
    -------
    object or None
        The installed filter, kept alive by the caller, or ``None`` when there
        is no application to install on.
    """
    if app is None:
        return None
    from qtpy import QtCore

    class _Filter(EasterEggFilter, QtCore.QObject):
        pass

    watcher = CodeWatcher(KONAMI, on_complete or open_lumis_quest)
    handler = _Filter()
    handler.watcher = watcher
    app.installEventFilter(handler)
    return handler
