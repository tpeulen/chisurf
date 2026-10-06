"""Figures of the manual's anisotropy pages: the Anisotropy wizard and the fits it builds.

The data are the stacked VV/VH recording bundled in ``test/data/tcspc/Jordi``: a
water-scatter IRF (``H2O_8-0 ps_2048 ch.dat``) and a dye decay
(``02_18-577+7.5uM(577)UP_8ps.dat``), 2048 channels of 8 ps each, the VV
channel followed by the VH channel in one column. For the "two single files"
layout the same measurement is written as four two-column files (time, counts)
into a scratch folder first.

    python docs/guides/screenshots/manual_anisotropy.py wizard
    python docs/guides/screenshots/manual_anisotropy.py main

Writes into ``docs/manual/figures/``. Run from the repository root, offscreen.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
# Before anything else: chisurf's imports pull in the standard library's ``test``
# package, which would then shadow the repository's.
# isort: off
from test.gui.fit_window_page_probe import _frames  # noqa: E402,F401
import numpy as np  # noqa: E402
# isort: on

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "docs" / "manual" / "figures"
DATA = ROOT / "test" / "data" / "tcspc" / "Jordi"
IRF = DATA / "H2O_8-0 ps_2048 ch.dat"
DECAY = DATA / "02_18-577+7.5uM(577)UP_8ps.dat"
#: Channel width of the recording, ns.
BIN = 0.008
#: A second recording of the same dye (9 ps channels): the "second sample" of the joint fit.
IRF2 = DATA / "H2O_9-1 ps_2048 ch.dat"
DECAY2 = DATA / "02_18-577+7.5uM(577)UP_9ps.dat"
BIN2 = 0.009
#: The corrections the manual's first pass starts from.
CORRECTIONS = {"g_factor": 1.16, "l1": 0.12, "l2": 0.44}


def _say(name: str) -> None:
    print("wrote", name, flush=True)


def _shot(ui, name: str) -> None:
    """Park the pointer over empty space (no hover tooltip), then grab *name*."""
    ui.app.pointer_move(120.0, float(ui.size[1]) - 60.0)
    ui.draw(3)
    ui.screenshot(OUT / name)
    _say(name)


def _hermetic() -> pathlib.Path:
    """A scratch settings folder with the corrections the manual quotes (g 1.16, l1 0.12, l2 0.44)."""
    import json

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="manual-anisotropy-"))
    os.environ["CHISURF_SETTINGS_DIR"] = str(scratch / "settings")
    os.environ["MMFDB_SETTINGS_DIR"] = str(scratch / "mmfdb")
    (scratch / "settings").mkdir(parents=True, exist_ok=True)
    (scratch / "settings" / "anisotropy_corrections.json").write_text(
        json.dumps({"g_factor": 1.16, "l1": 0.12, "l2": 0.44})
    )
    return scratch


def split_into_two_column_files(folder: pathlib.Path) -> dict:
    """Write the stacked recording as four ``time counts`` files (the two-file layout)."""
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, path in (("irf", IRF), ("data", DECAY)):
        counts = np.loadtxt(path)
        half = len(counts) // 2
        x = np.arange(half) * BIN
        for channel, part in (("vv", counts[:half]), ("vh", counts[half:])):
            target = folder / f"{name}_{channel.upper()}.txt"
            np.savetxt(target, np.column_stack((x, part)), fmt=["%.3f", "%d"])
            out[f"{name}_{channel}"] = str(target)
    return out


def wizard() -> None:
    """The six steps of the Anisotropy wizard (its emtk window), driven with the bundled data."""
    scratch = _hermetic()
    import chisurf.core.settings as settings

    settings.chisurf_settings_path = scratch / "settings"
    from chisurf.plugins.emtk_test_input import Driver
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.app import make_app

    OUT.mkdir(parents=True, exist_ok=True)
    size = (1100, 720)

    ui = Driver(make_app(), size=size)
    ui.draw()
    ui.click_name("Data")
    _shot(ui, "anisotropy_wizard_data_empty.png")

    # two single files with a time column
    # a short, readable folder: the paths are shown in the fields
    files = split_into_two_column_files(pathlib.Path("/tmp/chisurf_anisotropy_example"))
    m = ui.app.model
    m.stacked_files = False
    m.first_column_is_time = True
    m.use_header = False
    m.skiprows = 0
    for key, path in files.items():
        setattr(m, key + "_path", path)
    ui.draw()
    _shot(ui, "anisotropy_wizard_two_files.png")

    # the stacked VV/VH layout: one IRF file, one data file
    ui = Driver(make_app(), size=size)
    ui.draw()
    ui.click_name("Data")
    m = ui.app.model
    m.stacked_files = True
    m.first_column_is_time = False
    m.use_header = False
    m.bin_width = BIN
    m.irf_vv_path = str(IRF)
    m.data_vv_path = str(DECAY)
    ui.draw()
    _shot(ui, "anisotropy_wizard_stacked.png")

    ui.click_name("Normalize IRF")
    ui.click_text("Load / reload data")
    ui.draw(4)
    _shot(ui, "anisotropy_wizard_normalize_irf.png")

    ui.click_name("Corrections")
    _shot(ui, "anisotropy_wizard_corrections.png")

    ui.click_name("Components")
    _shot(ui, "anisotropy_wizard_components.png")


    # re-using calibrated corrections on a new sample: values typed into the steps
    m.g_factor, m.l1, m.l2 = 1.01, 0.0437, 0.349
    m.lifetime_spectrum = [[0.7, 2.6], [0.3, 1.6]]
    m.rotation_spectrum = [[0.38, 10.0]]
    ui.click_name("Components")
    _shot(ui, "anisotropy_wizard_components_reuse.png")

    # the Wizards hub (Tools -> Calculators -> Wizards) with the anisotropy wizard selected
    from chisurf.plugins.core.wizards.gui.app import make_app as make_hub

    hub = Driver(make_hub(), size=(1200, 760))
    hub.draw()
    try:
        hub.click_text("Anisotropy")
    except Exception as exc:
        print("hub:", exc, flush=True)
    _shot(hub, "anisotropy_wizards_hub.png")
    os._exit(0)


def _open_main(scratch: pathlib.Path):
    """An isolated Main (settings in *scratch*), with its ribbon, and no project."""
    from qtpy import QtCore, QtWidgets

    import chisurf as cs
    import chisurf.gui as gui
    from chisurf.core.api import ChiSurfAPI
    from chisurf.core.plugin.client import InProcessClient
    from chisurf.core.project.lifecycle import SaveDecision
    from chisurf.core.project.project import ResourceContext
    from chisurf.gui.main import Main
    from chisurf.gui.widgets.fitting.fitting_client import install_fitting_client
    from chisurf.server.dispatcher import ServiceDispatcher

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    settings_type = QtCore.QSettings

    class IsolatedSettings(settings_type):
        """Keep the window state out of the user's preferences."""

        def __init__(self, *args, **kwargs):
            super().__init__(str(scratch / "main.ini"), settings_type.IniFormat)

    QtCore.QSettings = IsolatedSettings
    cs.fits, cs.imported_datasets, gui.fit_windows = [], [], []
    cs.__client__ = None
    cs.project_resources = ResourceContext()
    cs.console = gui.widgets.ipython.QIPythonWidget()
    cs.console.history_widget = None
    main = Main()
    cs.cs = main
    main.init_setups()
    main.define_actions()
    main.arrange_widgets()
    main._save_decision = lambda: SaveDecision.DISCARD
    main.resize(1600, 960)
    main.show()
    api = ChiSurfAPI(mode="local")
    dispatcher = ServiceDispatcher(api._state)
    dispatcher._build_default_registry()
    install_fitting_client(InProcessClient(dispatcher))
    for _ in range(5):
        app.processEvents()
    return app, main


def _pump(app, n: int = 10) -> None:
    for _ in range(n):
        app.processEvents()


def _wizard_model(irf, decay, lifetimes=None, rotations=None, corrections=None, bin_width=BIN):
    """The wizard's model with the stacked files loaded and the IRF background corrected."""
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.model import NativeAnisotropyModel

    m = NativeAnisotropyModel()
    m.stacked_files = True
    m.first_column_is_time = False
    m.use_header = False
    m.bin_width = bin_width
    # one excitation period spans the 2048 channels of a polarisation
    m.rep_rate = 1000.0 / (2048 * bin_width)
    m.irf_vv_path = str(irf)
    m.data_vv_path = str(decay)
    if lifetimes is not None:
        m.lifetime_spectrum = [list(p) for p in lifetimes]
    if rotations is not None:
        m.rotation_spectrum = [list(p) for p in rotations]
    for key, value in (corrections or {}).items():
        setattr(m, key, value)
    m.load_data()
    return m


def _create_fits(app, main, model):
    """*Create fits* of the wizard, and their windows.

    In the application the wizard's ``fit.added`` events reach the Main over the
    shared event bus, which opens a window per fit; here the Main has no bus, so
    the windows are opened the way its event handler opens them.
    """
    model.create_fits()
    print("status:", model.status, flush=True)
    vv, vh, global_fit = model.fit_groups
    for fit in (global_fit, vv, vh):
        main._open_fit_subwindow(fit)
        _pump(app, 5)
    return vv, vh, global_fit


def _parameter(fit, canonical_id):
    """The parameter *canonical_id* of a fit group's model."""
    return next(p for p in fit.model.parameters_all if p.canonical_id == canonical_id)


def _window_of(main, fit):
    from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow

    return next(w for w in main.mdiarea.subWindowList() if isinstance(w, FitSubWindow) and w.fit is fit)


def _dock(main, name):
    from qtpy import QtWidgets

    dock = main.findChild(QtWidgets.QDockWidget, name)
    dock.show()
    dock.raise_()
    return dock


def _activate(app, main, fit):
    window = _window_of(main, fit)
    main.mdiarea.setActiveSubWindow(window)
    _pump(app, 10)
    return window


def _grab(app, widget, name, height=None):
    _pump(app, 10)
    pixmap = widget.grab()
    if height is not None:  # drop the empty dock below the content
        pixmap = pixmap.copy(0, 0, pixmap.width(), min(int(height * pixmap.devicePixelRatio()),
                                                       pixmap.height()))
    pixmap.save(str(OUT / name))
    _say(name)


def _refresh(app, *fits):
    import chisurf.gui as gui

    for fit in fits:
        fit.update()
    for window in list(getattr(gui, "fit_windows", []) or []):
        try:
            window.refresh_current_plot()
        except Exception:
            pass
    _pump(app, 10)
    for fit in fits:
        print(" ", getattr(fit, "name", "?"), "chi2r", round(float(getattr(fit, "chi2r", float("nan"))), 3),
              flush=True)


def main_window() -> None:
    """The Main window with the fits the wizard builds, and the global fit across two samples."""
    scratch = _hermetic()
    import chisurf.core.settings as settings

    settings.chisurf_settings_path = scratch / "settings"
    OUT.mkdir(parents=True, exist_ok=True)
    app, main = _open_main(scratch)
    main.load_tools()
    _pump(app)

    # where the wizard is: Tools -> Calculators -> Wizards
    ribbon = getattr(main._ribbon_integration, "ribbon_bar", None)
    try:
        ribbon.setCurrentCategory(ribbon.category("Tools"))
    except Exception as exc:
        print("ribbon tab:", exc, flush=True)
    _grab(app, main, "anisotropy_ribbon_tools.png")

    # first sample: the wizard's fits, with the corrections the manual starts from
    m = _wizard_model(IRF, DECAY, corrections=CORRECTIONS)
    vv, vh, global1 = _create_fits(app, main, m)
    main.mdiarea.tileSubWindows()
    _pump(app, 20)
    _grab(app, main, "anisotropy_fit_windows.png")

    analysis = _dock(main, "dockWidgetAnalysis")
    _activate(app, main, vv)
    _grab(app, analysis, "anisotropy_analysis_vv.png")
    _activate(app, main, vh)
    _grab(app, analysis, "anisotropy_analysis_vh.png")

    # step 1: each polarisation fitted alone, corrections fixed
    vv.run()
    vh.run()
    _refresh(app, vv, vh, global1)
    _activate(app, main, vv)
    _grab(app, main, "anisotropy_step1_vv_fit.png")

    # step 2: corrections free (on VV; VH follows through its links), then the joint fit
    for name in ("anisotropy.g", "anisotropy.l1", "anisotropy.l2"):
        _parameter(vv, name).fixed = False
    _activate(app, main, vv)
    main.resize(1600, 2600)  # tall enough for the editor to reach its anisotropy rows
    _pump(app, 10)
    _grab(app, analysis, "anisotropy_step2_corrections_free.png", height=1240)
    main.resize(1600, 960)
    _pump(app, 10)
    global1.run()
    _refresh(app, vv, vh, global1)
    _activate(app, main, global1)
    _grab(app, main, "anisotropy_step2_global_fit.png")
    print("sample 1:", {n: round(float(_parameter(vv, n).value), 4)
                        for n in ("anisotropy.g", "anisotropy.l1", "anisotropy.l2")}, flush=True)

    # the second sample, the same way: six windows (its fits as created, not yet fitted)
    m2 = _wizard_model(IRF2, DECAY2, corrections=CORRECTIONS, bin_width=BIN2)
    _create_fits(app, main, m2)
    main.mdiarea.tileSubWindows()
    _pump(app, 20)
    _grab(app, main, "anisotropy_two_samples.png")
    os._exit(0)


if __name__ == "__main__":
    {"wizard": wizard, "main": main_window}[sys.argv[1]]()
