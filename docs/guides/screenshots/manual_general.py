"""Manual figures of the main window, its docks, the Global View and the FCS hub.

The main-window figures (read data, datasets, fits, analysis dock, overview, fit windows tiled and tabbed,
VV/VH reading) are drawn by the emtk shell, driven on a private session with bundled data:

* the IBH sample decays (``test/data/tcspc/ibh_sample``), read through the real *Read data* dock (TCSPC,
  TXT/CSV, 0.0141 ns per channel), fitted with *Lifetime* against the measured prompt;
* the FCS hub's simulated example photon stream.

    pixi run -e test python docs/guides/screenshots/manual_general.py [shot ...]

The Global View save/load figures still come from a real Qt Main (a loaded link is applied through the
fitting server of that Main) and need a catalogue case directory as first argument:

    python -m test.project.scientific_catalogue_probe --case 0 /tmp/case0
    python docs/guides/screenshots/manual_general.py /tmp/case0 global_view_save_load

Writes into ``docs/manual/figures/``.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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


class Session:
    """A real Main with the IBH decays read through the Read data dock."""

    def __init__(self, case_dir: str) -> None:
        # Before anything else: chisurf's imports pull in the standard library's ``test`` package, which
        # would then shadow the repository's.
        from test.gui.fit_window_page_probe import _open_main

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
        """Lifetime fits of the donor-only (one lifetime) and the FRET decay (two), against the prompt, fitted."""
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


# -- the main window (emtk shell) -----------------------------------------------

def _datasets_dock(s, name: str, height: int = 460) -> None:
    """Float the Datasets dock into a box (both lists, Model, + Analysis) and write just that box."""
    from chisurf.emtk.fit_docks import DATASETS_KEY

    s.crop_dock(DATASETS_KEY, name, (10, 125, 480, height))


def _read_four(s) -> None:
    """Read the four IBH files through the Read data dock (text, 0.0141 ns per channel)."""
    for name in FILES:
        s.load_ibh(name)


def _dataset_row_point(s, position: int) -> tuple[float, float]:
    """A point on row *position* of the Datasets list, from the table's drawn box."""
    table = s.data.forms["datasets"].tables["dataset_rows"].control
    bx, by, bw, _bh = table._body_box
    return bx + bw / 3, by + table._row_h * (position + 0.5)


def _pointer(s, point, button: str = "left", modifiers: int = 0) -> None:
    """Press and release the pointer at *point* (``left`` or ``right``), drawing between the edges."""
    from emtk.events import LEFT_BUTTON, RIGHT_BUTTON

    code = RIGHT_BUTTON if button == "right" else LEFT_BUTTON
    surface = s.driver.surface
    surface.on_pointer_move(*point, 0, 0)
    s.driver.frame()
    surface.on_pointer_press(*point, code, modifiers)
    s.driver.frame()
    surface.on_pointer_release(*point, code, modifiers)
    s.driver.frame(2)


def _select_datasets(s, positions) -> None:
    """Click the first row of *positions* and ctrl-click the others in the Datasets list."""
    from emtk.events import CONTROL_MODIFIER

    for turn, position in enumerate(positions):
        _pointer(s, _dataset_row_point(s, position), "left", CONTROL_MODIFIER if turn else 0)


def _click_menu_entry(s, label: str) -> None:
    """Click the open context menu's entry *label* where it is drawn."""
    texts = [t for t in s.driver.painter.texts if t[5].strip() == label]
    x, y, w, h = texts[-1][:4]
    _pointer(s, (x + (w / 2 if w else 4), y + h / 2))


def _two_fits(s) -> None:
    """Lifetime fits of the donor-only (one lifetime) and the FRET decay (two), against the prompt, fitted."""
    for decay, lifetimes in (("Decay_577D.txt", 1), ("Decay_577D+577A+GTPgS.txt", 2)):
        s.ibh_fit(decay, lifetimes=lifetimes)
    s.page("Fit")


def run_shell_shots(names: list[str]) -> None:
    """The main-window figures, drawn by the emtk shell on a private session (one fresh shell each)."""
    from manual_shell import ManualShell

    from chisurf.emtk.fit_docks import ANALYSIS_KEY, DATASETS_KEY, READ_KEY

    for name in names:
        s = ManualShell(size=(1500, 950))
        if name == "read_data_dock":
            s.app.docks.focus(READ_KEY)
            read = s.data.read
            read.experiment = "TCSPC"
            read.experiment_changed("TCSPC")
            read.setup = "TXT/CSV"
            read.reader().dt = 0.0141
            s.crop_dock(READ_KEY, "main_read_data_dock.png", (10, 125, 520, 640))
        elif name == "datasets_loaded":
            _read_four(s)
            _datasets_dock(s, "main_datasets_loaded.png", 330)
        elif name == "datasets_context_menu":
            _read_four(s)
            s.app.docks.focus(DATASETS_KEY)
            s.driver.frame(3)
            _select_datasets(s, (1, 2))
            _pointer(s, _dataset_row_point(s, 2), "right")
            s.driver.frame(3)
            s.save("main_datasets_context_menu.png", crop=(0, 120, 480, 470))
        elif name == "datasets_grouped":
            _read_four(s)
            s.app.docks.focus(DATASETS_KEY)
            s.driver.frame(3)
            _select_datasets(s, (1, 2))
            _pointer(s, _dataset_row_point(s, 2), "right")
            s.driver.frame(3)
            _click_menu_entry(s, "Group")
            s.settle(lambda: s.idle() and any(r.get("group") for r in s.data.datasets.datasets), "the group")
            table = s.data.forms["datasets"].tables["dataset_rows"].control
            for row in s.data.datasets.datasets:
                if row.get("group"):
                    table.set_expanded(row["uid"], True)
            s.driver.hover((1495.0, 5.0))
            s.driver.frame(3)
            _console(s, "[d['name'] for d in api.list_datasets()]")
            s.save("main_datasets_grouped.png", crop=(0, 120, 1500, 950))
        elif name == "datasets_with_fits":
            _read_four(s)
            _two_fits(s)
            s.app.docks.focus(DATASETS_KEY)
            s.save("main_datasets_fits.png", crop=(0, 120, 1500, 800))
        elif name == "analysis_dock":
            _read_four(s)
            _two_fits(s)
            s.show_analysis()
            s.folds("Convolution", fit=True)
            s.save("main_analysis_dock.png", crop=(0, 120, 1500, 950))
        elif name == "overview":
            _read_four(s)
            _two_fits(s)
            s.show_analysis()
            s.folds(fit=True)
            _console(s, "fits = api.list_fits(statistics=True)", "fits[0]['name']", "round(fits[0]['chi2r'], 3)")
            s.save("main_overview.png")
        elif name == "mdi_tiled_and_tabbed":
            _read_four(s)
            _two_fits(s)
            s.show_analysis()
            keys = [w.key for w in s.data.windows.values()]
            docks = s.app.docks
            half = (415.0, 150.0, 540.0, 560.0), (960.0, 150.0, 535.0, 560.0)
            for key, box in zip(keys, half):
                docks.undock(key, box)
            s.driver.frame(6)
            s.save("main_mdi_tiled.png", crop=(0, 120, 1500, 740))
            for key in keys:
                docks.dock(key, "center")
            docks.focus(keys[0])
            s.driver.frame(6)
            s.save("main_mdi_tabbed.png", crop=(0, 120, 1500, 740))
        elif name == "read_data_vvvh":
            s.app.docks.focus(READ_KEY)
            read = s.data.read
            read.experiment = "TCSPC"
            read.experiment_changed("TCSPC")
            read.setup = "TXT/CSV"
            reader = read.reader()
            reader.dt = 0.0141
            reader.filename = ""
            reader.is_vv_vh, reader.polarization = True, "vv/vh"
            s.driver.frame(4)
            s.crop_dock(READ_KEY, "main_read_data_vvvh.png", (10, 125, 520, 760))
        s.close()


def _console(s, *lines: str) -> None:
    """Type *lines* into the Console dock, as a person does, one Return each."""
    from emtk.keys import KEY_RETURN

    s.app.docks.focus("console")
    s.driver.frame(3)
    s.driver.click(s.app.console.item_rects["console.input"])
    for line in lines:
        s.app.console.set_input("")
        s.driver.type(line)
        s.driver.press(KEY_RETURN)
        s.driver.frame(8)


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
    files.load_example()
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


#: The Qt-driven figures that are still current (a loaded link is applied through the fitting server of a real Main).
QT_SHOTS = {"global_view_save_load"}
#: The emtk shell's figures of the main window, in order. The VV/VH shot is last: switching the reader to
#: stacked VV/VH also switches its header and dt-scaling, which would change how the files read.
SHELL_SHOTS = ["read_data_dock", "datasets_loaded", "datasets_context_menu", "datasets_grouped", "datasets_with_fits", "analysis_dock",
               "overview", "mdi_tiled_and_tabbed", "read_data_vvvh"]


def main(case_dir: str | None, only: set[str]) -> None:
    """Write the figures named in *only* (all when empty); *case_dir* is only needed by the Qt-driven ones."""
    OUT.mkdir(parents=True, exist_ok=True)

    def want(name: str) -> bool:
        return not only or name in only

    if any(want(name) for name in SHELL_SHOTS):
        run_shell_shots([name for name in SHELL_SHOTS if want(name)])
    if want("global_view_save_load") and case_dir:
        session = Session(case_dir)
        session.read_files()
        session.add_fits()
        global_view_save_load(session)
    if want("global_view"):
        from qtpy import QtWidgets

        global_view(QtWidgets.QApplication.instance() or QtWidgets.QApplication([]))
    if want("fcs_hub"):
        fcs_hub()
    if want("tools_montage"):
        tools_montage()
    os._exit(0)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 and "/" in sys.argv[1] else None,
         {a for a in sys.argv[1:] if "/" not in a})
