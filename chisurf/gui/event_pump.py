"""One safe way to let the UI repaint during a blocking operation.

ChiSurf tools do real work on the GUI thread (reading a burst folder, computing
2CDE) and want their status line and progress bar to stay alive while they do.
The usual spelling for that — ``QCoreApplication.processEvents()`` sprinkled
through the status helpers — is what made a burst run crash:

``processEvents`` **dispatches queued work**, including the queued
``status_logged`` signal a worker thread just emitted. That slot is Python, it
writes the status bar, and it pumps again. Each round pushed another
``PyQtSlotProxy::qt_metacall`` → Python → ``notifyInternal2`` frame onto the C
stack; a report from the field shows five levels before
``QCoreApplication::postEvent`` died with ``SIGBUS`` on a garbage receiver.

The guard has to be **process-wide**, not per-widget: the hazard is the shared C
stack, and the pumps sit in different objects (the navigation shell's status bar,
:class:`~chisurf.gui.progress.ChiSurfProgress`, individual tools). Any pump that
starts while another is running is simply skipped — the outer one is already
draining the same queue.

Call sites that must stay clickable (anything showing a Cancel button) pump with
``allow_input=True`` (the default). Passive repaints — a caption update driven by
a log record — pass ``allow_input=False``, so a click cannot be delivered into
the middle of a running analysis and destroy the widgets it is still writing to.
"""

from __future__ import annotations

__all__ = ["pump_ui", "is_pumping"]

_pumping = False


def is_pumping() -> bool:
    """Whether a UI pump is currently running on this process."""
    return _pumping


def pump_ui(*, allow_input: bool = True) -> bool:
    """Process pending UI events once, unless a pump is already running.

    Parameters
    ----------
    allow_input : bool
        Whether clicks and key presses may be delivered. Keep the default for
        loops offering a Cancel button; pass ``False`` for a passive repaint,
        which must not let the user tear down the running operation's widgets.

    Returns
    -------
    bool
        ``True`` if events were processed, ``False`` if the call was skipped
        (a pump was already running, or Qt is unavailable — headless CLI).
    """
    global _pumping
    if _pumping:
        return False
    try:
        from qtpy import QtCore
    except Exception:
        return False
    app = QtCore.QCoreApplication.instance()
    if app is None:
        return False
    _pumping = True
    try:
        if allow_input:
            QtCore.QCoreApplication.processEvents()
        else:
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
    except Exception:
        return False
    finally:
        _pumping = False
    return True
