"""Modal message boxes that cannot hang a run with nobody at the keyboard.

``QMessageBox.critical(...)`` spins its own event loop until a button is
pressed. On the ``offscreen`` / ``minimal`` Qt platforms — every headless test
run, every CI job, every screenshot script — no button can ever be pressed, so a
dialog raised from an ``except`` branch does not report an error: it hangs the
process forever, with the traceback nowhere in sight.

The helpers here report through the log *always* and additionally raise the
dialog only when a person could actually dismiss it. In an interactive session
they behave exactly like the ``QMessageBox`` static they replace.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["is_interactive", "report_error", "report_warning", "report_information"]

#: Qt platform plugins that draw to nothing a user can click.
_HEADLESS_PLATFORMS = frozenset({"offscreen", "minimal", "vnc", ""})


def is_interactive() -> bool:
    """Whether a modal dialog would reach a person who can dismiss it.

    Returns
    -------
    bool
        ``True`` only when a ``QApplication`` exists *and* it is running on a
        platform with a real window system.
    """
    try:
        from qtpy.QtGui import QGuiApplication
        from qtpy.QtWidgets import QApplication
    except Exception:
        return False
    if QApplication.instance() is None:
        return False
    try:
        return str(QGuiApplication.platformName()).lower() not in _HEADLESS_PLATFORMS
    except Exception:
        return False


def _report(kind: str, parent, title: str, message: str, level: int) -> bool:
    """Log, then show the box when someone is there to see it.

    Parameters
    ----------
    kind : str
        ``QMessageBox`` static to call (``critical``/``warning``/``information``).
    parent : QWidget or None
        Dialog parent.
    title, message : str
        Dialog caption and body.
    level : int
        Logging level for the unconditional log record.

    Returns
    -------
    bool
        Whether the dialog was actually shown.
    """
    logger.log(level, "%s: %s", title, message)
    if not is_interactive():
        return False
    from qtpy import QtWidgets

    getattr(QtWidgets.QMessageBox, kind)(parent, title, message)
    return True


def report_error(parent, title: str, message: str) -> bool:
    """Log an error and show it as a modal box when a user is present."""
    return _report("critical", parent, title, message, logging.ERROR)


def report_warning(parent, title: str, message: str) -> bool:
    """Log a warning and show it as a modal box when a user is present."""
    return _report("warning", parent, title, message, logging.WARNING)


def report_information(parent, title: str, message: str) -> bool:
    """Log a notice and show it as a modal box when a user is present."""
    return _report("information", parent, title, message, logging.INFO)
