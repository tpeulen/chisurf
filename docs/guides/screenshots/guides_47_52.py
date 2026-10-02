"""Screenshot grabs for guides 47 (ndX bridges) and 52 (send bursts to analysis).

make_screenshots.py style: the functions use the module constants ``FIG`` and
``_grab`` and the ``_SPC_FILE`` path. Both drive ndX -- the emtk app, given the
in-process ChiSurf RPC client as ChiSurf's ``Main → Tools → ndX`` gives it
(``ndx_emtk``) -- on a burst folder built from the real ``BH_SPC132.spc``
measurement.

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

    ndX is the emtk app, given ChiSurf's in-process RPC client as ChiSurf's
    ``Main → Tools → ndX`` gives it. Returns the capture driver
    (:mod:`ndx_emtk`). Axes: proximity ratio against the mean green micro time
    (an E-tau view); the gate keeps proximity ratio 0.35-1.0.
    """
    import ndx_emtk

    folder = _write_bur_folder(root)
    driver = ndx_emtk.replay(size=(1400, 860), chisurf=True)
    ndx_emtk.open_table(driver, folder)
    ndx_emtk.axes(driver, "Proximity Ratio", "tau green (ns)", "Number of Photons")
    panel = driver.app.panel
    panel.x_bins_2d = panel.y_bins_2d = 25
    panel.x_bins_1d = panel.y_bins_1d = 40
    panel.x_min, panel.x_max = 0.0, 1.0
    panel.y_min, panel.y_max = 0.0, 5.0
    driver.settle()
    from ndxplorer.core.data_source import RectangularDataSelection

    model = driver.app.model
    gate = RectangularDataSelection(
        parameter_idx=model.index_of("Proximity Ratio"), lower=0.35, upper=1.0
    )
    gate.name = "FRET"
    model.gates.add_selection(gate)
    model.invalidate()
    driver.settle(3)
    return driver


def _open_send_menu(driver):
    """Right-click the map and open its "Send selection to" submenu."""
    from emtk.widgets.menus import Menu

    selection = next(f for f in driver.app.features if f.name == "selection")
    x, y, w, h = driver.app.plots.rects["map"]
    selection.open_canvas_menu(x + 0.08 * w, y + 0.12 * h)
    driver.draw()
    popup, _choose = driver.app.popup
    row = next(rect for entry, rect in popup._rows
               if isinstance(entry, Menu) and entry.label.startswith("Send selection to"))
    rx, ry, rw, rh = row
    driver.click_at(rx + rw / 2.0, ry + rh / 2.0)
    driver.draw()
    sub = next(entry for entry, _rect in popup._rows
               if isinstance(entry, Menu) and entry.label.startswith("Send selection to"))
    pda = next((rect for entry, rect in sub._rows if getattr(entry, "label", "") == "PDA"),
               None)
    if pda is not None:  # the row the pointer is on
        px, py, pw, ph = pda
        driver.app.pointer_move(px + pw / 2.0, py + ph / 2.0)
    return driver.draw()


def _grab_52_send_menu():
    """Guide 52: the gated FRET population and the "Send selection to" submenu."""
    import ndx_emtk

    root = pathlib.Path(tempfile.mkdtemp(prefix="ndx52-"))
    driver = _ndx_with_gate(root)
    ndx_emtk.save(_open_send_menu(driver), FIG, "52_send_selection_menu.png")
    driver.app.close()


def _grab_47_pda_bridge():
    """Guide 47: the FRET gate sent to PDA; the status line reports the handoff."""
    import ndx_emtk
    from ndxplorer.analysis.burst_bridge import BurstAnalysisBridge, outcome_message

    root = pathlib.Path(tempfile.mkdtemp(prefix="ndx47-"))
    driver = _ndx_with_gate(root)
    model = driver.app.model
    bridge = BurstAnalysisBridge(driver.app.chisurf_rpc, model.source)
    reply = bridge.send("pda", model.gates.selections(),
                        channels=[[0, 8], [1, 9]], reading_routine="SPC-130")
    driver.app.show_status(outcome_message(reply, "pda"))
    driver.settle()
    curve = reply["result"]["curves"][0]
    print("pda:", reply["n_bursts"], "bursts,", curve.get("shape"))
    ndx_emtk.save(driver.draw(), FIG, "47_ndx_bridge_pda.png")
    driver.app.close()


if __name__ == "__main__":
    import chisurf.core.settings  # noqa: F401
    app = QApplication.instance() or QApplication([])
    _grab_52_send_menu()
    _grab_47_pda_bridge()
