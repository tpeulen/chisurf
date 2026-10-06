"""Manual figures of the main window, its docks, the Global View and the FCS hub.

Replaces the screenshots the historical Word manual carried (``kind: legacy
screenshot`` in ``docs/references/figures.yaml``) on the general pages of
``docs/manual`` -- overview, data import, creating fits, the analysis dock, the
MDI, Global View and the correlator overview -- with grabs of the current
program, driven with bundled data:

* the IBH sample decays (``test/data/tcspc/ibh_sample``), read through the real
  *Read data* dock (TCSPC, TXT/CSV, 10 header rows, 14.1 ps/channel) into a real
  Main, fitted with *Lifetime* against the measured prompt;
* the FCS hub's simulated example photon stream.

    python -m test.project.scientific_catalogue_probe --case 0 /tmp/case0
    python docs/guides/screenshots/manual_general.py /tmp/case0 [shot ...]

The case directory only configures the Main (isolated settings, the project
machinery); its own science is closed before the IBH data is read. Writes into
``docs/manual/figures/``.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
# Before anything else: chisurf's imports pull in the standard library's ``test``
# package, which would then shadow the repository's.
from test.gui.fit_window_page_probe import _open_main  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "docs" / "manual" / "figures"
IBH = ROOT / "test" / "data" / "tcspc" / "ibh_sample"
#: The IBH sample files, in the order they are read.
FILES = ("Decay_577D.txt", "Decay_577D+577A+GTPgS.txt", "Prompt.txt", "whitelight.txt")


def _pump(app, n: int = 6) -> None:
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


def _save(widget, name: str) -> None:
    widget.grab().save(str(OUT / name))
    print("wrote", name, flush=True)


def _raise_dock(main, object_name: str) -> None:
    from qtpy import QtWidgets

    dock = main.findChild(QtWidgets.QDockWidget, object_name)
    dock.show()
    dock.raise_()


class Session:
    """A real Main with the IBH decays read through the Read data dock."""

    def __init__(self, case_dir: str) -> None:
        import chisurf as cs

        self.cs = cs
        self.app, self.main, _result = _open_main(pathlib.Path(case_dir))
        for window in self.main.mdiarea.subWindowList():
            window.close_confirm = False
            window.close()
            self.main.mdiarea.removeSubWindow(window)  # a tabbed view lists hidden ones too
            window.deleteLater()
        cs.fits[:] = []
        cs.imported_datasets[:] = []
        self.main.resize(1500, 950)
        self.main._refresh_experiment_ui()
        self.main._refresh_setup_ui()
        _pump(self.app)
        self.reader = self.main.current_setup
        self.reader.skiprows = 10
        self.reader.dt = 0.0141
        self.reader.rep_rate = 10.0
        controller = getattr(self.reader, "controller", None)
        rebuild = getattr(controller, "_rebuild_settings_form", None)
        if callable(rebuild):  # the form shows the reader's values
            rebuild()
        csv = getattr(controller, "csv_widget", None)
        if csv is not None:  # show the value; its own handler rewrites the whole setup
            csv.spinBox.blockSignals(True)
            csv.spinBox.setValue(10)
            csv.spinBox.blockSignals(False)
        self.reader.skiprows = 10
        self.main.dataset_selector.update()
        _pump(self.app)

    def read_files(self) -> None:
        import chisurf.macros as macros

        for name in FILES:
            macros.add_dataset(experiment_reader=self.reader, filename=str(IBH / name))
            self.cs.imported_datasets[-1].name = name  # the list shows the file name
        self.main.dataset_selector.update()
        _pump(self.app)

    def add_fits(self) -> None:
        """Lifetime fits of the donor-only and the FRET decay, against the prompt, fitted."""
        import chisurf.macros as macros

        cs = self.cs
        prompt = cs.imported_datasets[2]
        for index in (0, 1):
            macros.add_fit(dataset_indices=[index], model_name="Lifetime")
            _pump(self.app)
            fit = cs.fits[-1]
            for member in getattr(fit, "grouped_fits", [fit]):
                member.model.set_dataset("response", prompt)
                member.fit_range = (522, 3793)
            fit.update()
            fit.run()
        self.main.fit_selector.update()
        _pump(self.app, 10)
        for window in self.main.mdiarea.subWindowList():
            window.close_confirm = False
            window.plot_tab_widget.setCurrentIndex(0)  # the Fit page
            window.refresh_current_plot()
        _pump(self.app, 10)

    def console(self, *lines: str) -> None:
        for line in lines:
            self.cs.console.execute(line, echo=True)
            _pump(self.app, 4)


# -- the main window ------------------------------------------------------------


def read_data_dock(s: Session) -> None:
    """The Read data dock: experiment TCSPC, file type TXT/CSV and its file parameters."""
    _raise_dock(s.main, "dockWidgetReadData")
    _pump(s.app)
    _save(s.main, "main_read_data_dock.png")


def datasets_loaded(s: Session) -> None:
    """The Datasets dock after the four IBH files were read (or dropped onto the list)."""
    _raise_dock(s.main, "dockWidgetDatasets")
    _pump(s.app)
    _save(s.main, "main_datasets_loaded.png")


def datasets_context_menu(s: Session) -> None:
    """The dataset list's context menu (Save, Load, Remove, Group, Ungroup, Refresh)."""
    from qtpy import QtCore, QtGui, QtWidgets

    _raise_dock(s.main, "dockWidgetDatasets")
    selector = s.main.dataset_selector
    selector.setCurrentItem(selector.topLevelItem(1))
    _pump(s.app)
    rect = selector.visualItemRect(selector.topLevelItem(1))
    local = rect.center() + QtCore.QPoint(40, 0)
    captured = {}
    original = QtWidgets.QMenu.exec_

    def capture(menu, *args, **kwargs):
        menu.adjustSize()
        captured["image"] = menu.grab()
        return None

    QtWidgets.QMenu.exec_ = capture
    try:
        event = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, local,
                                        selector.viewport().mapToGlobal(local))
        selector.contextMenuEvent(event)
    finally:
        QtWidgets.QMenu.exec_ = original
    image = s.main.grab()
    at = selector.viewport().mapTo(s.main, local)
    painter = QtGui.QPainter(image)
    painter.drawPixmap(at, captured["image"])
    painter.setPen(QtGui.QPen(QtGui.QColor(90, 90, 90)))
    painter.drawRect(QtCore.QRect(at, captured["image"].size()).adjusted(0, 0, -1, -1))
    painter.end()
    image.save(str(OUT / "main_datasets_context_menu.png"))
    print("wrote main_datasets_context_menu.png", flush=True)


def datasets_with_fits(s: Session) -> None:
    """The Datasets dock with two Lifetime fits in the fit list."""
    _raise_dock(s.main, "dockWidgetDatasets")
    s.main.mdiarea.tileSubWindows()
    _pump(s.app)
    _save(s.main, "main_datasets_fits.png")


def analysis_dock(s: Session) -> None:
    """The Analysis dock of the active fit beside its fit window."""
    _raise_dock(s.main, "dockWidgetAnalysis")
    windows = s.main.mdiarea.subWindowList()
    s.main.mdiarea.setActiveSubWindow(windows[0])
    s.main.mdiarea.tileSubWindows()
    _pump(s.app, 10)
    _save(s.main, "main_analysis_dock.png")


def overview(s: Session) -> None:
    """The whole window: docks, two fit windows tiled, the console after a few commands."""
    _raise_dock(s.main, "dockWidgetAnalysis")
    s.main.mdiarea.tileSubWindows()
    s.console("fit = cs.fits[0]", "fit.name", "round(fit.chi2r, 3)")
    _pump(s.app, 10)
    _save(s.main, "main_overview.png")


def mdi_tiled_and_tabbed(s: Session) -> None:
    """The fit windows tiled, then tabbed, with the toolbar's Tile / Tab Windows actions."""
    s.main.actionTile_windows.trigger()
    _pump(s.app, 8)
    _save(s.main, "main_mdi_tiled.png")
    s.main.actionTab_windows.trigger()
    _pump(s.app, 8)
    _save(s.main, "main_mdi_tabbed.png")
    s.main.actionTile_windows.trigger()
    _pump(s.app, 4)


def save_listing(s: Session) -> None:
    """Save the current fit into a scratch folder and print what was written."""
    import chisurf.macros as macros

    target = pathlib.Path(tempfile.mkdtemp(prefix="manual-save-"))
    s.main.mdiarea.setActiveSubWindow(s.main.mdiarea.subWindowList()[0])
    _pump(s.app)
    try:
        macros.save_fit(target_path=str(target))
    except Exception as exc:  # report what was written before it failed
        print("save failed:", repr(exc), flush=True)
    _pump(s.app)
    for path in sorted(target.rglob("*")):
        if path.is_file():
            print("saved:", path.relative_to(target), flush=True)


def datasets_grouped(s: Session) -> None:
    """Datasets 0 and 1 grouped: one tree entry, unfolded; the console lists the group."""
    import chisurf.macros as macros

    _raise_dock(s.main, "dockWidgetDatasets")
    macros.group_datasets([0, 1])
    s.main.dataset_selector.update()
    s.main.dataset_selector.expandAll()
    s.console("[d.name for d in cs.imported_datasets]",
              "[d.name for d in cs.imported_datasets[2]]")
    _pump(s.app, 8)
    _save(s.main, "main_datasets_grouped.png")


def read_data_vvvh(s: Session) -> None:
    """Read data with the VV/VH (stacked) options of a polarisation-resolved file."""
    reader = s.reader
    reader.is_vv_vh, reader.polarization = True, "vv/vh"
    reader.controller._rebuild_settings_form()
    _raise_dock(s.main, "dockWidgetReadData")
    _pump(s.app)
    _save(s.main, "main_read_data_vvvh.png")


# -- Global View ------------------------------------------------------------------


def _global_fits():
    """Four lifetime fits sharing one donor lifetime (the guide-60 fixture, plus one)."""
    import numpy as np

    from chisurf.core.data import DataCurve, DataCurveGroup
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.models.description import tcspc_lifetime

    def make(name, tau):
        x = np.linspace(0.1, 25, 256)
        y = 1000.0 * np.exp(-x / tau) + 1.0
        return FitGroup(data=DataCurveGroup([DataCurve(x=x, y=y, ey=np.sqrt(y), name=name)], name=name),
                        model_class=tcspc_lifetime)

    fits = [make("Donor-only", 4.0), make("FRET-low", 2.4), make("FRET-mid", 1.8), make("FRET-high", 1.3)]
    source = fits[0].model.parameters_all_dict["t0"]
    for fit in fits[1:]:
        fit.model.parameters_all_dict["t0"].link = source
    return fits


def global_view(app) -> None:
    """The Global View on four fits sharing a lifetime: the network, then include fixed."""
    import chisurf
    from chisurf.gui.widgets.fitting.fitting_client import (
        get_fitting_client,
        install_fitting_client,
    )
    from chisurf.plugins.core.globalview.gui.tool import GraphWizard

    fits = _global_fits()
    saved = chisurf.fits, get_fitting_client()
    install_fitting_client(None)
    chisurf.fits = fits
    tool = GraphWizard(fit_list=fits, remember_layout=False)
    tool.resize(1150, 760)
    tool.show()
    tool.model.rebuild(force=True)
    _pump(app, 10)
    _save(tool, "globalview_tool.png")
    tool.surface.docks.focus("View")
    _pump(app, 10)
    _save(tool, "globalview_view_tab.png")

    tool.model.include_fixed = True
    tool.model.node_size = 9
    tool.model.apply_node_size()
    tool.model.rebuild(force=True)
    _pump(app, 10)
    _save(tool, "globalview_include_fixed.png")
    tool.close()
    chisurf.fits = saved[0]
    install_fitting_client(saved[1])


def global_view_save_load(s: Session) -> None:
    """Save the IBH session's network, unlink, load it back: the link returns.

    Driven on the Main's own fits: a loaded link is applied through the fitting
    server, which knows the session's fits (a standalone fixture has none).
    """
    from chisurf.plugins.core.globalview.gui.tool import GraphWizard

    fits = s.cs.fits
    master = fits[0].model.parameters_all_dict["t0"]
    fits[1].model.parameters_all_dict["t0"].link = master
    tool = GraphWizard(fit_list=fits, remember_layout=False)
    tool.resize(1150, 760)
    tool.show()
    tool.model.rebuild(force=True)
    _pump(s.app, 10)
    path = pathlib.Path(tempfile.mkdtemp(prefix="manual-gml-")) / "network.gml"
    tool.model.ask_save_path = lambda *a, **k: str(path)
    tool.model.save_network()
    print("graphml:", *path.read_text(encoding="utf-8").splitlines()[:14], sep="\n", flush=True)
    fits[1].model.parameters_all_dict["t0"].link = None
    tool.model.rebuild(force=True)
    _pump(s.app, 10)
    _save(tool, "globalview_before_load.png")
    tool.model.load_network(str(path))
    tool.model.rebuild(force=True)
    _pump(s.app, 10)
    print("after load:", tool.model.status, flush=True)
    _save(tool, "globalview_after_load.png")
    tool.close()


# -- FCS hub ----------------------------------------------------------------------


def _native(app, name: str, frames: int = 6, size=(1200, 800)) -> None:
    from emtk.pil_painter import PilPainter

    for _ in range(frames):
        painter = PilPainter(*size)
        app.draw(painter, 0, 0, *size)
    painter.frame.save(OUT / name)
    print("wrote", name, flush=True)


def fcs_hub() -> None:
    """The FCS hub: the workflow rail on the example stream, then its photon filter."""
    from chisurf.plugins.fcs.fcs_toolbox.gui.app import make_app

    hub = make_app()
    files = hub.select("files")
    files.add_example()
    files.use_filter = True
    _native(hub, "fcs_hub_files.png")
    hub.select("filter")
    _native(hub, "fcs_hub_filter.png", frames=10)
    hub.close()


def tools_montage() -> None:
    """Four companion tools side by side, from their guides' current figures."""
    from PIL import Image, ImageDraw

    figures = ROOT / "docs" / "guides" / "figures"
    panels = [
        ("Burst-wise single-molecule (ndXplorer)", figures / "ndxplorer_gaussian_populations.png"),
        ("Fluorescence correlation (FCS hub)", OUT / "fcs_hub_files.png"),
        ("Lifetime imaging (TTTR Image Browser)", figures / "image_browser_setup.png"),
        ("Photon streams (Histogram-Microtime)", figures / "decay_gap_filter.png"),
    ]
    tile = (720, 480)
    sheet = Image.new("RGB", (tile[0] * 2 + 12, tile[1] * 2 + 12 + 2 * 26), (30, 32, 38))
    draw = ImageDraw.Draw(sheet)
    for i, (title, path) in enumerate(panels):
        image = Image.open(path).convert("RGB")
        image.thumbnail(tile)
        x = (i % 2) * (tile[0] + 12)
        y = (i // 2) * (tile[1] + 12 + 26)
        draw.text((x + 4, y + 6), title, fill=(230, 232, 238))
        sheet.paste(image, (x + (tile[0] - image.width) // 2, y + 26))
    sheet.save(OUT / "tools_montage.png")
    print("wrote tools_montage.png", flush=True)


#: In order. The VV/VH shot is last: switching the reader to stacked VV/VH also
#: switches its header and dt-scaling, which would change how the files read.
MAIN_SHOTS = [read_data_dock, datasets_loaded, datasets_context_menu,
              "fits", datasets_with_fits, analysis_dock, overview, mdi_tiled_and_tabbed,
              save_listing, global_view_save_load, datasets_grouped, read_data_vvvh]


def main(case_dir: str, only: set[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    session = Session(case_dir)

    def want(name: str) -> bool:
        return not only or name in only

    for step in MAIN_SHOTS:
        if step == "fits":
            session.read_files() if not session.cs.imported_datasets else None
            session.add_fits()
            continue
        if step is datasets_loaded or step is datasets_context_menu:
            if not session.cs.imported_datasets:
                session.read_files()
        if want(step.__name__):
            step(session)
    if want("global_view"):
        global_view(session.app)
    if want("fcs_hub"):
        fcs_hub()
    if want("tools_montage"):
        tools_montage()
    os._exit(0)


if __name__ == "__main__":
    main(sys.argv[1], set(sys.argv[2:]))
