"""Find the ChiSurf host adapter without importing Qt.

The emtk app must stay Qt-free: it can run in a process that blocks Qt altogether.  This module
decides, from ``sys.modules`` alone, whether a Qt application is already running, and only then
imports :mod:`.host` (the adapter, which does import Qt).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any


def default_request_handler() -> Callable[[str, dict], Any] | None:
    """The adapter's ``on_request(name, payload)``, or ``None`` when no Qt application is running.

    Qt is never imported here: the adapter is resolved only if ``qtpy.QtWidgets`` is already loaded
    (by ChiSurf's main window, or by a test) *and* a ``QApplication`` exists.  A process that blocks
    Qt, or runs the app on its own, therefore stays Qt-free and the hand-off buttons stay greyed.
    """
    widgets = sys.modules.get("qtpy.QtWidgets")
    if widgets is None:
        return None
    application = widgets.QApplication.instance()
    if application is None or not isinstance(application, widgets.QApplication):
        return None
    from .host import default_request_handler as adapter

    return adapter()
