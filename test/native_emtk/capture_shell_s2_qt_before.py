"""Capture the before-half of the W9 S2 migration: the Qt shell's data and fit docks.

Starts the Qt main window with scratch settings and private RPC ports, reads
``test/data/fcs/kristine/Kristine_with_error.cor`` with the FCS *Seidel Kristine*
reader, adds one *FCS (general: diffusion + bunching/anticorr)* fit, then grabs
the Read data, Datasets, Analysis and Plot settings docks and the fit window and
writes their :func:`migration_parity.control_inventory` next to the PNGs.
``test/native_emtk/shell_s2_qt_inventory.json`` is that inventory; the emtk side
is compared against it by ``test_emtk_shell_fits.py``.

Not a test (the Qt shell takes a minute to start). Run from the repository root::

    S=$(mktemp -d); QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=$S/settings HOME=$S/home \\
        python -u test/native_emtk/capture_shell_s2_qt_before.py

PNGs and ``qt_inventory.json`` go to ``$CHISURF_S2_BEFORE_DIR`` (``renders/w9_s2``).
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
DOCKS = ("dockWidgetReadData", "dockWidgetDatasets", "dockWidgetAnalysis", "dockWidgetPlot")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    """Drive the Qt shell into the S2 state and write the PNGs and the inventory."""
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
    # The file and sample dialogs are modal: answer them without showing them.
    gui_widgets.get_filename = lambda *args, **kwargs: str(DATA)
    fcs_widgets.show_sample_picker_dialog = lambda *args, **kwargs: None
    gui.toolButton_2.click()
    pump(3)
    # Pick the dataset before the model: a dataset change resets the model combo.
    selector = gui.dataset_selector
    selector.setCurrentIndex(selector.model().index(len(chisurf.imported_datasets) - 1, 0))
    pump(0.5)
    choose(gui.comboBox_Model, MODEL)
    gui.toolButton.click()
    pump(10)
    assert len(chisurf.fits) == 1, "the fit was not added"

    out = Path(os.environ.get("CHISURF_S2_BEFORE_DIR", REPO / "renders" / "w9_s2"))
    out.mkdir(parents=True, exist_ok=True)
    inventory = {}
    for name in DOCKS:
        dock = getattr(gui, name)
        dock.show()
        dock.raise_()
        pump(0.5)
        dock.grab().save(str(out / f"qt_{name}.png"))
        inventory[name] = control_inventory(dock)
    window = gui.mdiarea.subWindowList()[-1]
    window.grab().save(str(out / "qt_fit_window.png"))
    inventory["fit_window"] = control_inventory(window)
    gui.grab().save(str(out / "qt_main.png"))
    (out / "qt_inventory.json").write_text(json.dumps(inventory, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    os._exit(0)  # the Qt shell's post-show services keep the loop alive


if __name__ == "__main__":
    main()
