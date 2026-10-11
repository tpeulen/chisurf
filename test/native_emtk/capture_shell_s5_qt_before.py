"""Capture the before-half of the W9 S5 migration: the Qt shell's ribbon.

Starts the Qt main window with scratch settings and private RPC ports (no data is
needed: the ribbon is built from the plugin manifests and the main window's
actions) and records, for every ribbon tab in order:

* ``tabs``: tab title -> panels in order -> buttons in order, each button with its
  text, tooltip, whether it has an icon, whether it is enabled and its size
  (``large`` when its icon sits above the text, else ``small``);
* ``quick_access``: the quick-access buttons' texts and tooltips;
* ``right``: the buttons in the ribbon's right corner (the language switcher);

and a PNG of each tab at 1440 px and of the Spectroscopy tab at 800 px (where the
Qt ribbon scrolls its panels).

``test/native_emtk/shell_s5_qt_inventory.json`` is that record; the emtk side is
compared against it by ``test_emtk_shell_ribbon.py``.

Not a test (the Qt shell takes a minute to start). Run from the repository root::

    S=$(mktemp -d); QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=$S/settings HOME=$S/home \\
        python -u test/native_emtk/capture_shell_s5_qt_before.py

PNGs and ``qt_inventory.json`` go to ``$CHISURF_S5_BEFORE_DIR`` (``renders/w9_s5``).
"""

from __future__ import annotations

import faulthandler
import json
import os
import socket
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _button_record(button) -> dict:
    from qtpy import QtCore

    style = button.toolButtonStyle()
    return {
        "text": button.text().replace("&", ""),
        "tooltip": button.toolTip(),
        "icon": not button.icon().isNull(),
        "enabled": bool(button.isEnabled()),
        "size": "large" if style == QtCore.Qt.ToolButtonTextUnderIcon else "small",
    }


def main() -> None:
    """Start the Qt shell and write the ribbon inventory and PNGs."""
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

    pump(2)
    wizard = QtWidgets.QApplication.activeModalWidget()
    if wizard is not None:
        wizard.reject()
        pump(0.5)
    integration = gui._ribbon_integration
    assert integration is not None, "the ribbon is not enabled"
    bar = integration.ribbon_bar
    out = Path(os.environ.get("CHISURF_S5_BEFORE_DIR", REPO / "renders" / "w9_s5"))
    out.mkdir(parents=True, exist_ok=True)
    record: dict = {"tabs": {}, "quick_access": [], "right": []}

    print("stage: tabs", flush=True)
    for title, category in bar.categories().items():
        panels = {}
        for panel_title, panel in category.panels().items():
            buttons = [
                _button_record(button)
                for button in panel.findChildren(QtWidgets.QToolButton)
                if button.text() and button.parent() is not None
            ]
            panels[panel_title] = buttons
        record["tabs"][title] = panels
        bar.setCurrentCategory(category)
        bar.showRibbon()
        pump(0.3)
        bar.grab().save(str(out / f"qt_ribbon_{title.replace(' ', '_')}.png"))
    for button in bar.quickAccessToolBar().findChildren(QtWidgets.QToolButton):
        if button.defaultAction() is not None:
            record["quick_access"].append(_button_record(button))
    for widget in bar.rightToolBar().findChildren(QtWidgets.QWidget):
        name = type(widget).__name__
        if name not in ("QToolBarExtension", "QToolBarSeparator") and widget.isVisible():
            record["right"].append({"class": name, "tooltip": widget.toolTip()})

    print("stage: narrow", flush=True)
    spectroscopy = bar.categories().get("Spectroscopy")
    if spectroscopy is not None:
        gui.resize(800, 900)
        bar.setCurrentCategory(spectroscopy)
        pump(0.5)
        bar.grab().save(str(out / "qt_ribbon_Spectroscopy_narrow.png"))
    gui.resize(1440, 900)
    pump(0.3)
    gui.grab().save(str(out / "qt_main.png"))
    (out / "qt_inventory.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(f"wrote {out}: {len(record['tabs'])} tabs", flush=True)
    sys.stdout.flush()
    os._exit(0)  # the Qt shell's post-show services keep the loop alive


if __name__ == "__main__":
    main()
