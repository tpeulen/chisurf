"""Host adapter of the emtk Trace Browser: opens the tools its HMM, TW and NDX buttons hand a trace to.

The emtk app and its model know no Qt: a press on *HMM*, *TW* or *NDX* only records a request
(``open_intensity_trace``, ``open_time_window``, ``open_ndxplorer`` plus a payload) and passes it to
an ``on_request(name, payload)`` callback.  This module is that callback for ChiSurf.  Qt is allowed
here because the adapter only *hosts* the other tools' windows; it is imported lazily (by
:func:`~chisurf.plugins.tttr.trace_browser.gui.app.make_app`, and only when a Qt application runs),
never by ``gui.app`` or ``gui.model`` at import time.

The three requests open what the retired Qt Trace Browser opened:

* ``open_intensity_trace``: a new native Intensity Trace window
  (:class:`~chisurf.plugins.tttr.intensity_trace.gui.app.IntensityTraceApp` hosted in a Qt window)
  with its title, bin window and detector setup set, the file loaded and binned;
* ``open_time_window``: a new native Time Window app
  (:func:`~chisurf.plugins.tttr.tttr_time_windows.gui.controller.create_app` hosted in a Qt
  window; its controller is ``window.controller``) holding the file and the bin window;
* ``open_ndxplorer``: ChiSurf's ndX window
  (:func:`~chisurf.plugins.ndxplorer.window.build_ndxplorer_window`) on the burst-analysis folder
  the model wrote.

Every window is kept in :data:`WINDOWS` (so it is not garbage collected), shown, raised and
activated, and dropped from the list when it is closed.  A request that cannot be fulfilled raises;
the app turns the exception into its status line.
"""

from __future__ import annotations

import importlib.util
import logging
import pathlib
from collections.abc import Callable
from typing import Any

from qtpy import QtCore, QtWidgets

logger = logging.getLogger(__name__)

__all__ = [
    "WINDOWS",
    "default_request_handler",
    "open_intensity_trace",
    "open_ndxplorer",
    "open_time_window",
]

#: Strong references to the windows opened for the Trace Browser (the Qt tool kept the same lists).
WINDOWS: list[QtWidgets.QWidget] = []


def _keep(window: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Keep *window* alive, show it, bring it to the front and forget it when it is closed."""
    WINDOWS.append(window)
    original = window.closeEvent

    def close_event(event: Any) -> None:
        original(event)
        if event.isAccepted():
            # Drop the reference after the event is handled, never while Qt is inside it.
            QtCore.QTimer.singleShot(0, lambda: _forget(window))

    window.closeEvent = close_event
    window.show()
    window.raise_()
    window.activateWindow()
    return window


def _forget(window: QtWidgets.QWidget) -> None:
    if window in WINDOWS:
        WINDOWS.remove(window)


def _file(payload: dict) -> pathlib.Path:
    path = pathlib.Path(str(payload["file"]))
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist")
    return path


def open_intensity_trace(payload: dict) -> QtWidgets.QWidget:
    """Open a new Intensity Trace window on ``payload["file"]`` (the Qt ``_on_transfer_to_analysis``).

    Parameters
    ----------
    payload : dict
        ``file``, ``window_ms`` and ``setup_settings`` of the model's request (``selected_channels``
        is part of it; the Qt tool computed it and only logged it, so it is not applied here either).

    Returns
    -------
    QtWidgets.QWidget
        The window, holding the native app as ``window.app``; the file is read and binned on the
        app's worker (``window.app.wait()`` joins it).
    """
    from emtk.qt_host import ControlHost

    from chisurf.plugins.tttr.intensity_trace.gui.app import make_app

    path = _file(payload)
    app = make_app()
    app.model.window_ms = float(payload["window_ms"])
    setup = payload.get("setup_settings")
    if setup:
        app.model.setup = setup
        app.model.selected = []
        app.setup_name = str(setup.get("setup_name") or "Edited setup")
    app.open_file(str(path))
    window = ControlHost(app)
    window.app = app
    window.setWindowTitle(f"Intensity Trace Analysis - {path.name}")
    width, height = app.window_size
    window.resize(int(width), int(height))
    return _keep(window)


def open_time_window(payload: dict) -> QtWidgets.QWidget:
    """Open a new Time Window app holding ``payload["files"]`` and ``window_ms`` (the Qt ``_on_transfer_to_tw``)."""
    from emtk.qt_host import ControlHost

    from chisurf.plugins.tttr.tttr_time_windows.gui.controller import create_app

    files = [pathlib.Path(str(f)) for f in payload["files"]]
    if not files:
        raise ValueError("no file to open in the Time Window tool")
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(f"{path} does not exist")
    app = create_app()
    controller = app.tool
    controller.time_window_ms = float(payload["window_ms"])
    controller.add_paths(files)
    if not controller._file_paths:
        app.close()
        raise ValueError(f"{files[0].name} is not a TTTR file the Time Window tool reads")
    window = ControlHost(app)
    window.app = app
    window.controller = controller
    window.setWindowTitle(f"Time Window BID Generation: {files[0].name}")
    width, height = app.window_size
    window.resize(int(width), int(height))
    return _keep(window)


def open_ndxplorer(payload: dict) -> QtWidgets.QWidget:
    """Open ChiSurf's ndX window on ``payload["folder"]`` (the Qt ``_on_open_in_ndxplorer``, last step)."""
    folder = pathlib.Path(str(payload["folder"]))
    if not folder.is_dir():
        raise FileNotFoundError(f"{folder} does not exist")
    if importlib.util.find_spec("ndxplorer") is None:
        raise ImportError("ndX components are not available")
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    return _keep(build_ndxplorer_window(folder))


_OPENERS: dict[str, Callable[[dict], QtWidgets.QWidget]] = {
    "open_intensity_trace": open_intensity_trace,
    "open_time_window": open_time_window,
    "open_ndxplorer": open_ndxplorer,
}


def default_request_handler() -> Callable[[str, dict], QtWidgets.QWidget]:
    """The ``on_request(name, payload)`` that opens ChiSurf's own windows for the hand-offs.

    Needs a running ``QApplication`` when a request arrives.  An unknown request name or a window
    that cannot be built raises; the Trace Browser app shows the message in its status line.
    """

    def handle(name: str, payload: dict) -> QtWidgets.QWidget:
        opener = _OPENERS.get(name)
        if opener is None:
            raise ValueError(f"unknown request {name!r}")
        if QtWidgets.QApplication.instance() is None:
            raise RuntimeError("no Qt application is running")
        logger.info(
            "TraceBrowser: %s for %s",
            name,
            payload.get("file") or payload.get("files") or payload.get("folder"),
        )
        return opener(dict(payload))

    return handle
