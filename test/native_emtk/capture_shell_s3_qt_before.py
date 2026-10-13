"""Capture the before-half of the W9 S3 migration: the Qt shell's session menus, shortcuts and dialogs.

Starts the Qt main window with scratch settings and private RPC ports, reads
``test/data/fcs/kristine/Kristine_with_error.cor`` with the FCS *Seidel Kristine*
reader and adds one *FCS (general: diffusion + bunching/anticorr)* fit, so the
session has unsaved work. Then it records:

* ``menus``: every menu of the menu bar, walked recursively -- each action's text,
  shortcut and whether it is checkable -- with a PNG of each menu;
* ``shortcuts``: every action of the window that carries a shortcut, text -> key
  sequence (``configure_project_shortcuts`` and the ``.ui`` actions);
* ``dialogs``: the control inventory (:func:`migration_parity.control_inventory`)
  and a PNG of ``SaveProjectDialog``, ``CollisionDialog`` and of the three
  message boxes the session asks -- the unsaved-changes question when the window
  closes, the fit window's close question and the quit question of an empty
  session. The message boxes are caught at ``exec`` and answered with the safe
  button, so the window and the fit survive.

``test/native_emtk/shell_s3_qt_inventory.json`` is that record; the emtk side is
compared against it by ``test_emtk_shell_session.py``.

Not a test (the Qt shell takes a minute to start). Run from the repository root::

    S=$(mktemp -d); QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=$S/settings HOME=$S/home \\
        python -u test/native_emtk/capture_shell_s3_qt_before.py

PNGs and ``qt_inventory.json`` go to ``$CHISURF_S3_BEFORE_DIR`` (``renders/w9_s3``).
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
DATA = REPO / "test" / "data" / "fcs" / "kristine" / "Kristine_with_error.cor"
MODEL = "FCS (general: diffusion + bunching/anticorr)"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _menu_record(menu, out: Path, name: str, grabs: list) -> list:
    """The actions of *menu* (submenus recursively), grabbing each menu as a PNG."""
    rows = []
    menu.adjustSize()
    grabs.append((menu, out / f"qt_menu_{name}.png"))
    for action in menu.actions():
        if action.isSeparator():
            rows.append({"separator": True})
            continue
        row = {
            "text": action.text().replace("&", ""),
            "shortcut": action.shortcut().toString(),
            "checkable": bool(action.isCheckable()),
            "enabled": bool(action.isEnabled()),
            "visible": bool(action.isVisible()),
        }
        sub = action.menu()
        if sub is not None:
            row["menu"] = _menu_record(sub, out, f"{name}_{len(rows)}", grabs)
        rows.append(row)
    return rows


def main() -> None:
    """Drive the Qt shell into the S3 state and write the PNGs and the inventory."""
    faulthandler.enable()
    faulthandler.dump_traceback_later(300, exit=True)
    sys.path.insert(0, str(REPO / "test" / "gui"))
    from mmfdb.security import credentials

    # The OS keystore is the user's: startup's autologin would write a session token there.
    credentials.store_session_token = lambda *args, **kwargs: False
    credentials.load_session_token = lambda *args, **kwargs: None

    from migration_parity import control_inventory
    from qtpy import QtWidgets

    import chisurf
    import chisurf.gui
    import chisurf.gui.widgets as gui_widgets
    import chisurf.gui.widgets.experiments.fcs as fcs_widgets
    from chisurf.core import settings
    from chisurf.gui import dialogs

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

    def choose(combo, text: str) -> None:
        combo.setCurrentIndex([combo.itemText(i) for i in range(combo.count())].index(text))
        pump(0.5)

    choose(gui.comboBox_experimentSelect, "FCS")
    choose(gui.comboBox_setupSelect, "Seidel Kristine")
    gui_widgets.get_filename = lambda *args, **kwargs: str(DATA)
    fcs_widgets.show_sample_picker_dialog = lambda *args, **kwargs: None
    gui.toolButton_2.click()
    pump(3)
    selector = gui.dataset_selector
    selector.setCurrentIndex(selector.model().index(len(chisurf.imported_datasets) - 1, 0))
    pump(0.5)
    choose(gui.comboBox_Model, MODEL)
    gui.toolButton.click()
    pump(10)
    assert len(chisurf.fits) == 1, "the fit was not added"

    out = Path(os.environ.get("CHISURF_S3_BEFORE_DIR", REPO / "renders" / "w9_s3"))
    out.mkdir(parents=True, exist_ok=True)
    record: dict = {"menus": {}, "shortcuts": {}, "dialogs": {}}

    print("stage: menus", flush=True)
    # -- menus ---------------------------------------------------------------- #
    grabs: list = []
    for action in gui.menuBar.actions():  # the .ui names its QMenuBar "menuBar"
        menu = action.menu()
        if menu is None:
            continue
        title = action.text().replace("&", "")
        record["menus"][title] = _menu_record(menu, out, title.replace(" ", "_"), grabs)
    for menu, path in grabs:
        menu.popup(gui.mapToGlobal(gui.rect().topLeft()))
        pump(0.2)
        menu.grab().save(str(path))
        menu.hide()

    print("stage: shortcuts", flush=True)
    # -- shortcuts ------------------------------------------------------------ #
    for action in gui.findChildren(QtWidgets.QAction):
        keys = action.shortcut().toString()
        if keys:
            record["shortcuts"][action.text().replace("&", "")] = keys

    print("stage: project dialogs", flush=True)
    # -- project dialogs -------------------------------------------------------- #
    from chisurf.gui.widgets.project_dialogs import CollisionDialog, SaveProjectDialog

    save = SaveProjectDialog(current_name="Kristine_with_error", parent=gui)
    save.show()
    pump(0.3)
    save.grab().save(str(out / "qt_save_project_dialog.png"))
    record["dialogs"]["SaveProjectDialog"] = control_inventory(save)
    save.reject()
    collision = CollisionDialog(
        {"datasets": ["ds-1", "ds-2"], "fits": ["fit-1"]},
        {"project_id": "proj_x", "version_number": 3},
        gui,
    )
    collision.show()
    pump(0.3)
    collision.grab().save(str(out / "qt_collision_dialog.png"))
    record["dialogs"]["CollisionDialog"] = control_inventory(collision)
    collision.reject()

    print("stage: message boxes", flush=True)
    # -- message boxes: caught at exec, answered with the safe button ----------- #
    caught: list[tuple[str, object]] = []

    def caught_exec(box):
        box.show()
        pump(0.3)
        name = ("close_guard", "fit_close", "quit")[min(len(caught), 2)]
        box.grab().save(str(out / f"qt_box_{name}.png"))
        inventory = control_inventory(box)
        inventory["title"] = box.windowTitle()
        inventory["text"] = box.text()
        caught.append((name, inventory))
        box.hide()
        # A choice() box reads clickedButton(): nothing clicked answers None, which is Cancel.
        for safe in (QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.No):
            if box.button(safe) is not None:
                return safe
        return QtWidgets.QMessageBox.Cancel

    QtWidgets.QMessageBox.exec_ = caught_exec
    QtWidgets.QMessageBox.exec = caught_exec
    dialogs.is_interactive = lambda: True
    gui.close()  # the unsaved-changes question (Cancel keeps the window)
    pump(0.5)
    window = gui.mdiarea.subWindowList()[-1]
    window.close()  # the fit window's question (No keeps the fit)
    pump(0.5)
    gui._project_has_content = lambda: False
    gui._guard_project_transition = lambda: True
    gui.close()  # the quit question of an empty session (No keeps the window)
    pump(0.5)
    for name, inventory in caught:
        record["dialogs"][name] = inventory
    gui.grab().save(str(out / "qt_main.png"))
    (out / "qt_inventory.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(f"wrote {out}: {len(caught)} message boxes")
    os._exit(0)  # the Qt shell's post-show services keep the loop alive


if __name__ == "__main__":
    main()
