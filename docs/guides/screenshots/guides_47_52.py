"""Screenshot grabs for guides 47 (ndX bridges) and 52 (send bursts to analysis).

make_screenshots.py style: the functions use the module constants ``FIG`` and
``_grab`` and the ``_SPC_FILE`` path. Both drive the real ndX window that
ChiSurf's ``Main → Tools → ndX`` opens (``make_ndxplorer``, with the in-process
ChiSurf RPC client injected), on a burst folder built from the real
``BH_SPC132.spc`` measurement.

Run standalone::

    QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=<scratch> \
    PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \
    python grabs_47_52.py
"""

from __future__ import annotations

from common import FIG, _SPC_FILE, _grab, _pump  # noqa: F401,E402

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
from qtpy.QtWidgets import QApplication  # noqa: E402

if __name__ == "__main__":  # standalone: mirror make_screenshots.py's constants
    FIG = pathlib.Path("docs/guides/figures")
    _SPC_FILE = pathlib.Path("test") / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"

    def _grab(widget, name):
        """Show *widget*, process events, and save a PNG grab into ``figures/``."""
        widget.show()
        QApplication.instance().processEvents()
        widget.grab().save(str(FIG / name))
        print("wrote", name)


def _write_bur_folder(root: pathlib.Path) -> pathlib.Path:
    """Burst-search ``BH_SPC132.spc`` and write a Seidel-style burst folder.

    Returns the folder (``<root>/burstwise/bi4_bur/BH_SPC132.bur``). The table
    is zero-interleaved like every ``.bur`` and carries the provenance columns
    (``First File``/``Last File``/``First Photon``/``Last Photon``) the bridge
    needs. ``First File`` holds the absolute path: the bridge passes it to the
    analysis unresolved, so a bare file name only works from the data folder.
    """
    import tttrlib

    spc = pathlib.Path(_SPC_FILE).resolve()
    t = tttrlib.TTTR(str(spc), "SPC-130")
    mt = np.asarray(t.macro_times) * t.header.macro_time_resolution
    ut = np.asarray(t.micro_times) * t.header.micro_time_resolution * 1e9
    ch = np.asarray(t.routing_channels)
    ss = np.asarray(t.burst_search(30, 10, 1e-3)).reshape(-1, 2)
    ut0 = float(ut[np.isin(ch, (0, 8))].min())
    cols = ["First Photon", "Last Photon", "Duration (ms)", "Mean Macro Time (ms)",
            "Number of Photons", "Count Rate (KHz)", "First File", "Last File",
            "Number of Photons (green)", "Number of Photons (red)", "Proximity Ratio",
            "tau green (ns)"]
    folder = root / "burstwise"
    (folder / "bi4_bur").mkdir(parents=True, exist_ok=True)
    zero = "\t".join(["0"] * len(cols)) + "\n"
    with open(folder / "bi4_bur" / "BH_SPC132.bur", "w") as fh:
        fh.write("\t".join(cols) + "\t\n")
        fh.write(zero)
        for a, b in ss:
            sl = slice(a, b + 1)
            c = ch[sl]
            g = np.isin(c, (0, 8))
            ng, nr = int(g.sum()), int(np.isin(c, (1, 9)).sum())
            dur = (mt[b] - mt[a]) * 1e3
            tau = float(ut[sl][g].mean() - ut0) if ng else 0.0
            row = [a, b, dur, mt[sl].mean() * 1e3, b - a + 1, (b - a + 1) / dur,
                   str(spc), str(spc), ng, nr, nr / max(ng + nr, 1), tau]
            fh.write("\t".join(v if isinstance(v, str) else f"{v:.6f}" for v in row) + "\n")
            fh.write(zero)
    return folder


def _ndx_with_gate(root: pathlib.Path):
    """Open ndX as ChiSurf does, load the burst folder, gate the FRET population.

    Returns ``(window, settle)``. Axes: proximity ratio against the mean green
    micro time (an E-tau view); the gate keeps proximity ratio 0.35-1.0.
    """
    from qtpy.QtCore import QEventLoop, QTimer

    ndx = str(pathlib.Path("modules/ndxplorer").resolve())
    if ndx not in sys.path:
        sys.path.insert(0, ndx)
    from chisurf.plugins.ndxplorer.rpc_bridge import make_ndxplorer
    from ndxplorer.core.data_source import RectangularDataSelection

    import chisurf.core.settings  # noqa: F401
    app = QApplication.instance() or QApplication([])

    def settle(ms=100):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec_()
        app.processEvents()

    folder = _write_bur_folder(root)
    win = make_ndxplorer()
    win.resize(1400, 860)
    win.show()
    settle(300)
    win.open_files(file_handles=[str(folder)], file_type="burst_dir")
    for _ in range(50):
        settle(100)
        ds = win.data_source
        if ds is not None and not ds.empty and "Proximity Ratio" in ds.parameter_names:
            break
    names = win.data_source.parameter_names
    control = win.plot_control
    control.update(update_comboboxes=True, update_plots=False)
    control.comboBoxSelX.setCurrentIndex(names.index("Proximity Ratio"))
    control.comboBoxSelY.setCurrentIndex(names.index("tau green (ns)"))
    control.comboBoxSelZ.setCurrentIndex(names.index("Number of Photons"))
    control.spinBoxBin2DX.setValue(25)
    control.spinBoxBin2DY.setValue(25)
    control.spinBoxBin1DX.setValue(40)
    control.spinBoxBin1DY.setValue(40)
    win.update_plots()
    settle(200)
    control.xmin, control.xmax = 0.0, 1.0
    control.ymin, control.ymax = 0.0, 5.0
    win.update_plots()
    settle(300)
    gate = RectangularDataSelection(
        parameter_idx=names.index("Proximity Ratio"), lower=0.35, upper=1.0
    )
    gate.name = "FRET"
    control.add_selection_object(gate)
    win.update_plots()
    settle(400)
    return win, settle


def _compose_menu(win, settle, target_name):
    """Grab *win* with the canvas context menu and its send submenu drawn over it.

    A ``QMenu`` popup is its own top-level window, so a window grab never shows
    it; build the menu the canvas builds, grab each level, and paint both onto
    the window grab at the cursor position.
    """
    from qtpy import QtCore, QtGui, QtWidgets

    from ndxplorer.analysis.send_menu import add_send_menu

    canvas = win.g_2dplot.canvas()
    menu = QtWidgets.QMenu(canvas)
    for label in ("Copy 2D Histogram (CSV)", "Copy 1D Histograms (CSV)", "Send to Napari"):
        menu.addAction(label)
    menu.addSeparator()
    menu.addAction("Fit gate to the population here")
    menu.addSeparator()
    sub = add_send_menu(menu, win)
    pos = canvas.mapTo(win, QtCore.QPoint(int(canvas.width() * 0.08), int(canvas.height() * 0.12)))
    menu.popup(win.mapToGlobal(pos))
    settle(150)
    sub.popup(menu.mapToGlobal(menu.actionGeometry(sub.menuAction()).topRight()))
    settle(150)
    settle(100)
    pda = [a for a in sub.actions() if a.objectName() == "actionSendTo_pda"]
    hover = {menu: menu.actionGeometry(sub.menuAction()),
             sub: sub.actionGeometry(pda[0]) if pda else QtCore.QRect()}
    base = win.grab()
    painter = QtGui.QPainter(base)
    sub_pos = pos + menu.actionGeometry(sub.menuAction()).topRight()
    for widget, at in ((menu, pos), (sub, sub_pos)):
        # Offscreen popups grab with a transparent background: paint the menu
        # panel and a frame first, then the items over it.
        rect = QtCore.QRect(at, widget.size())
        painter.fillRect(rect, QtGui.QColor(246, 246, 246))
        if not hover[widget].isNull():  # the row the pointer is on
            painter.fillRect(hover[widget].translated(at), QtGui.QColor(190, 215, 245))
        painter.setPen(QtGui.QColor(120, 120, 120))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.drawPixmap(at, widget.grab())
    painter.end()
    base.save(str(FIG / target_name))
    print("wrote", target_name)
    sub.hide()
    menu.hide()


def _grab_52_send_menu():
    """Guide 52: the gated FRET population and the "Send selection to" submenu."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="ndx52-"))
    win, settle = _ndx_with_gate(root)
    _compose_menu(win, settle, "52_send_selection_menu.png")
    win.close()


def _grab_47_pda_bridge():
    """Guide 47: the FRET gate sent to PDA; the status line reports the handoff."""
    from ndxplorer.analysis.send_menu import send_selection

    root = pathlib.Path(tempfile.mkdtemp(prefix="ndx47-"))
    win, settle = _ndx_with_gate(root)
    reply = send_selection(win, "pda", channels=[[0, 8], [1, 9]], reading_routine="SPC-130")
    settle(200)
    curve = reply["result"]["curves"][0]
    print("pda:", reply["n_bursts"], "bursts,", curve.get("shape"), win.statusBar().currentMessage())
    _grab(win, "47_ndx_bridge_pda.png")
    win.close()


if __name__ == "__main__":
    import chisurf.core.settings  # noqa: F401
    app = QApplication.instance() or QApplication([])
    _grab_52_send_menu()
    _grab_47_pda_bridge()
