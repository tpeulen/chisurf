"""Capture the before-half of the W9 S5 status strip: the Qt shell's status bar.

Starts the Qt main window with scratch settings and private RPC ports and records
what its status bar shows in each state a user meets it in:

* ``idle``: after the post-show startup stages ended (the *Ready* label);
* ``message``: a ``chisurf`` log record at WARNING (the root handler the Qt shell
  installs writes INFO and up into the bar, translated and truncated, but the
  shipped ``log_level`` is 30, so by default only warnings and errors get there);
* ``startup``: a post-show startup stage under way
  (:class:`chisurf.gui.background_startup.BackgroundStartupRunner` sets the stage
  label and shows its progress bar);
* ``task``: an operation reporting progress with a known step count and a cancel
  (:func:`chisurf.gui.progress.progress` started from the main window lands in
  the status bar's progress host: label, bar, ✕);
* ``busy``: the same with an unknown step count (busy indicator), no cancel.

Each state is a list of the visible controls, ``{"kind", "text", "tooltip",
"value", "maximum"}`` with ``kind`` one of ``message`` (the bar's transient
message), ``label``, ``progress`` and ``button``; and a PNG of the bar.

``test/native_emtk/shell_s5_status_qt_inventory.json`` is that record; the emtk
side is compared against it by ``test_emtk_shell_status_strip.py``.

Not a test (the Qt shell takes a minute to start). Run from the repository root::

    S=$(mktemp -d); QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=$S/settings HOME=$S/home \\
        python -u test/native_emtk/capture_shell_s5_status_qt_before.py

PNGs and ``qt_status_inventory.json`` go to ``$CHISURF_S5_BEFORE_DIR`` (``renders/w9_s5``).
"""

from __future__ import annotations

import faulthandler
import json
import logging
import os
import socket
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: The texts the states are driven with (the emtk test drives the same ones).
MESSAGE = "The IRF file has no header; the bin width is guessed."
STAGE = ("Loading plugins", 2, 7)
TASK = ("Fitting fit 1…", 100, 40)
BUSY = "Reading the fits…"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _controls(status) -> list[dict]:
    """The status bar's visible controls, in reading order (left to right)."""
    from qtpy import QtWidgets

    found: list[tuple[int, dict]] = []
    message = status.currentMessage()
    if message:
        found.append((-1, {"kind": "message", "text": message, "tooltip": ""}))
    for widget in status.findChildren(QtWidgets.QWidget):
        if not widget.isVisibleTo(status) or not widget.isVisible():
            continue
        x = widget.mapTo(status, widget.rect().topLeft()).x()
        if isinstance(widget, QtWidgets.QProgressBar):
            record = {
                "kind": "progress",
                "text": "",
                "tooltip": widget.toolTip(),
                "value": int(widget.value()),
                "maximum": int(widget.maximum()),
            }
        elif isinstance(widget, QtWidgets.QToolButton):
            record = {"kind": "button", "text": widget.text(), "tooltip": widget.toolTip()}
        elif isinstance(widget, QtWidgets.QLabel):
            if not widget.text():
                continue
            record = {"kind": "label", "text": widget.text(), "tooltip": widget.toolTip()}
        else:
            continue
        found.append((x, record))
    return [record for _x, record in sorted(found, key=lambda item: item[0])]


def main() -> None:
    """Start the Qt shell and write the status bar inventory and PNGs."""
    faulthandler.enable()
    faulthandler.dump_traceback_later(300, exit=True)
    from mmfdb.security import credentials

    # The OS keystore is the user's: startup's autologin would write a session token there.
    credentials.store_session_token = lambda *args, **kwargs: False
    credentials.load_session_token = lambda *args, **kwargs: None

    from qtpy import QtWidgets

    import chisurf
    import chisurf.gui
    from chisurf.core import settings

    settings.cs_settings.setdefault("mmfdb", {}).update(
        cmd_port=_free_port(), pub_port=_free_port()
    )
    app = chisurf.gui.get_app()
    gui = chisurf.cs
    gui.resize(1440, 900)

    def pump(seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)

    pump(8)  # the post-show stages run on the GUI thread one after the other
    wizard = QtWidgets.QApplication.activeModalWidget()
    if wizard is not None:
        wizard.reject()
        pump(0.5)
    status = gui.status
    out = Path(os.environ.get("CHISURF_S5_BEFORE_DIR", REPO / "renders" / "w9_s5"))
    out.mkdir(parents=True, exist_ok=True)
    record: dict = {"states": {}, "height": int(status.height())}

    def take(name: str) -> None:
        pump(0.4)
        record["states"][name] = _controls(status)
        status.grab().save(str(out / f"qt_status_{name}.png"))
        print(f"stage: {name}: {record['states'][name]}", flush=True)

    status.clearMessage()
    take("idle")

    logging.getLogger("chisurf.capture").warning(MESSAGE)
    take("message")
    status.clearMessage()

    from chisurf.gui.background_startup import BackgroundStartupRunner
    from chisurf.startup.services import AppStartupServiceManager

    runner = BackgroundStartupRunner(gui, AppStartupServiceManager())
    runner._set_status(*STAGE)
    take("startup")
    runner._set_ready()
    status.clearMessage()

    from chisurf.gui.progress import progress

    cancelled: list[bool] = []
    handle = progress(gui, TASK[0], TASK[1], cancel=lambda: cancelled.append(True))
    handle.setValue(TASK[2])
    take("task")
    handle.close()

    handle = progress(gui, BUSY, 0, cancellable=False)
    take("busy")
    handle.close()
    status.clearMessage()

    gui.grab().save(str(out / "qt_status_main.png"))
    (out / "qt_status_inventory.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(f"wrote {out}", flush=True)
    sys.stdout.flush()
    os._exit(0)  # the Qt shell's post-show services keep the loop alive


if __name__ == "__main__":
    main()
