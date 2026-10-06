"""Screenshots of the FCS chapters of the manual (``docs/manual/``), of today's ChiSurf.

They replace the pictures extracted from the historical Word manual. Each
``grab_*`` function drives the real application offscreen with data bundled in
the repository and writes into ``docs/manual/figures/``::

    CHISURF_SETTINGS_DIR=$(mktemp -d) MMFDB_SETTINGS_DIR=$(mktemp -d) \
    PYTHONPATH="modules/chimol:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \
    python docs/guides/screenshots/manual_fcs.py grab_fcs_walkthrough

Run one function per process (each builds its own main window). Read every
PNG afterwards: a grab that ran is not a figure that looks right.

The A488 walkthrough of ``fit_of_a_fcs_curve.md`` needs several measurements of
one free dye. The repository bundles three Zeiss Confocor3 measurements of
Alexa 488 (``test/data/fcs/confocor3``); the autocorrelation of detector 1 of
each is written as a Seidel *Kristine* ``.cor`` file into a scratch folder and
loaded through the GUI, as the manual's text describes.
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
import test.gui.fit_window_page_probe  # noqa: E402,F401

OUT = pathlib.Path(__file__).resolve().parents[2] / "manual" / "figures"
CONFOCOR3 = pathlib.Path("test/data/fcs/confocor3/Zeiss_Confocor3_A488+GFP")


def _save(widget, name: str) -> None:
    """Grab *widget* into ``OUT/name``."""
    OUT.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(OUT / name))
    print("wrote", name, flush=True)


def _native_shot(app, name: str, frames: int = 6, size=(1200, 800)) -> None:
    """Draw a native emtk app a few frames and save the last into ``OUT``."""
    from emtk.pil_painter import PilPainter

    OUT.mkdir(parents=True, exist_ok=True)
    painter = None
    for _ in range(frames):
        painter = PilPainter(*size)
        app.draw(painter, 0, 0, *size)
    painter.frame.save(OUT / name)
    print("wrote", name, flush=True)


# --------------------------------------------------------------------------
# Correlator workflow (FCS hub)
# --------------------------------------------------------------------------


def grab_correlator_steps() -> None:
    """The FCS hub's Correlator and FCS Merger steps on its simulated example.

    *Files & Steps* adds the hub's simulated two-channel TTTR example with the
    merger step switched on; the correlator splits it into 6 subsets
    (Laurence algorithm), the merger then lists the subsets and their merged
    curve.
    """
    import time

    from emtk.pil_painter import PilPainter

    from chisurf.plugins.fcs.fcs_toolbox.gui.app import make_app

    hub = make_app()
    files = hub.select("files")
    files.add_example()
    files.use_merger = True
    hub._files_changed()
    corr = hub.select("correlator")
    corr.model.channel_a, corr.model.channel_b, corr.model.n_splits = "0", "1", 6
    corr.model.method = "laurence"
    corr.correlate(wait=True)
    _native_shot(hub, "fcs_correlator_step.png")
    merger = hub.select("merger")
    end = time.time() + 60
    while time.time() < end:
        hub.draw(PilPainter(1200, 800), 0, 0, 1200, 800)
        rows = getattr(getattr(merger, "model", None), "rows", None)
        if rows:
            break
        time.sleep(0.05)
    _native_shot(hub, "fcs_merger_step.png")
    hub.close()


# --------------------------------------------------------------------------
# A real main window
# --------------------------------------------------------------------------


def _main_window(size=(1500, 950)):
    """An isolated ChiSurf main window with an in-process fitting server.

    Window state goes to a scratch INI, never the user's preferences.
    """
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
    ini = pathlib.Path(tempfile.mkdtemp(prefix="manual-fcs-")) / "main.ini"
    base = QtCore.QSettings

    class IsolatedSettings(base):
        """Keep the screenshot window's state out of the user's preferences."""

        def __init__(self, *args, **kwargs):
            super().__init__(str(ini), base.IniFormat)

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
    main.resize(*size)
    main.show()
    # The session's fits are ``cs.fits``: a server with a state of its own
    # would fit copies the windows never see.
    api = ChiSurfAPI(mode="local")
    api._state.fits = cs.fits
    api._state.datasets = cs.imported_datasets
    dispatcher = ServiceDispatcher(api._state)
    dispatcher._build_default_registry()
    install_fitting_client(InProcessClient(dispatcher))
    # The running app delivers ``fit.updated`` / ``parameter.*`` from the shared
    # event bus to the main window, which redraws the fit windows; so here.
    import types

    from chisurf.server.eventbus import InProcessEventBus

    bus = InProcessEventBus()
    cs.__chisurf_rpc_server__ = types.SimpleNamespace(event_bus=bus)
    for topic in ("fit.updated", "fit.ran", "parameter.*"):
        bus.subscribe(topic, main._on_server_event)
    _pump(app, 6)
    return app, main


def _pump(app, n: int = 4) -> None:
    for _ in range(n):
        app.processEvents()


def _select_experiment(main, experiment: str, setup: str) -> None:
    """Choose *experiment* and its *setup* (file type) in the Read data dock."""
    combo = main.comboBox_experimentSelect
    combo.setCurrentIndex(combo.findText(experiment))
    main._refresh_experiment_ui()
    combo = main.comboBox_setupSelect
    combo.setCurrentIndex(combo.findText(setup))
    main._refresh_setup_ui()


def _raise_dock(main, name: str) -> None:
    from qtpy import QtWidgets

    dock = main.findChild(QtWidgets.QDockWidget, name)
    dock.show()
    dock.raise_()


def _a488_kristine_files() -> list[str]:
    """The AC1 curve of each bundled Confocor3 A488 measurement, as Kristine ``.cor``."""
    import numpy as np

    from chisurf.core.fio.fluorescence.fcs.confocor3 import read_zeiss_fcs
    from chisurf.core.fio.fluorescence.fcs.kristine import write_kristine

    work = pathlib.Path(tempfile.mkdtemp(prefix="a488-"))
    paths = []
    for number, source in enumerate(sorted(CONFOCOR3.glob("00*_A488.fcs")), 1):
        curve = read_zeiss_fcs(str(source))[0]  # detector 1 autocorrelation
        path = work / f"A488_ACF_{number}.cor"
        write_kristine(
            filename=str(path),
            correlation_time=curve["correlation_times"],
            correlation_amplitude=curve["correlation_amplitudes"],
            correlation_amplitude_uncertainty=1.0 / np.asarray(curve["correlation_amplitude_weights"]),
            acquisition_time=curve["acquisition_time"],
            mean_countrate=curve["mean_count_rate"],
            verbose=False,
        )
        paths.append(str(path))
    return paths


def _combo_with(root, item: str):
    """The visible combo box under *root* that offers *item*."""
    from qtpy import QtWidgets

    for combo in root.findChildren(QtWidgets.QComboBox):
        if combo.isVisible() and combo.findText(item) >= 0:
            return combo
    raise LookupError(f"no combo box offers {item!r}")


def _button(root, text: str):
    """The visible button under *root* whose text contains *text*."""
    from qtpy import QtWidgets

    for button in root.findChildren(QtWidgets.QAbstractButton):
        if button.isVisible() and text in button.text():
            return button
    raise LookupError(f"no button {text!r}")


def _run_fit(app, main) -> None:
    """Press the *▶ Fit* button of the Analysis dock and wait for it."""
    from qtpy import QtWidgets

    buttons = [b for b in main.dockWidgetAnalysis.findChildren(QtWidgets.QAbstractButton, "button_fit")
               if b.isVisible()]
    buttons[0].click()
    _pump(app, 30)


def _window_of(main, name_end: str):
    """The fit window whose title ends with *name_end*."""
    for window in main.mdiarea.subWindowList():
        if window.windowTitle().endswith(name_end):
            return window
    raise LookupError(name_end)


def _activate(app, main, window) -> None:
    main.mdiarea.setActiveSubWindow(window)
    _raise_dock(main, "dockWidgetAnalysis")
    _pump(app, 6)


def _choose_formula(app, main, name: str) -> None:
    combo = _combo_with(main.dockWidgetAnalysis, name)
    combo.setCurrentIndex(combo.findText(name))
    _pump(app, 6)


def _fit_controller(main):
    from chisurf.gui.widgets.fitting.fit_controller import FittingControllerWidget

    return next(c for c in main.findChildren(FittingControllerWidget) if c.isVisible())


def _parameter_table(main):
    from chisurf.gui.autoform.sections.parameter_table import ParameterGroupTableWidget

    return next(t for t in main.dockWidgetAnalysis.findChildren(ParameterGroupTableWidget) if t.isVisible())


def _row_of(table, name: str) -> int:
    model = table._model
    return next(r for r in range(model.rowCount()) if getattr(model.param_at(r), "name", None) == name)


def _compose(images, gap: int = 8, background=(240, 240, 240)):
    """Images side by side, top-aligned, on one canvas."""
    from qtpy import QtGui

    width = sum(i.width() for i in images) + gap * (len(images) - 1)
    height = max(i.height() for i in images)
    canvas = QtGui.QImage(width, height, QtGui.QImage.Format_RGB32)
    canvas.fill(QtGui.QColor(*background))
    painter = QtGui.QPainter(canvas)
    x = 0
    for image in images:
        painter.drawImage(x, 0, image)
        x += image.width() + gap
    painter.end()
    return canvas


def _menu_chain(app, menu, path: list[str]):
    """Show *menu* and the submenus named by *path*; return their grabs and the last action."""
    shots = []
    current = menu
    action = None
    for step in path + [None]:
        current.show()
        _pump(app, 2)
        current.resize(current.sizeHint())
        _pump(app, 2)
        shots.append(current.grab().toImage())
        if step is None:
            break
        action = next(a for a in current.actions() if a.text().replace("&", "").strip() == step)
        if action.menu() is not None:
            current.hide()
            current = action.menu()
        else:
            current.hide()
            break
    current.hide()
    return shots, action


def grab_fcs_walkthrough() -> None:
    """``fit_of_a_fcs_curve.md``: load, add fits, choose the model, fit, link, global fit."""
    import chisurf as cs

    app, main = _main_window()
    _select_experiment(main, "FCS", "Seidel Kristine")
    _pump(app)
    _save(main, "fcs_main_window.png")

    for path in _a488_kristine_files():
        cs.core.actions.dispatch(name="dataset.add", payload={"filename": path, "experiment_reader": None})
        _pump(app, 2)
    _save(main, "fcs_datasets_added.png")

    _raise_dock(main, "dockWidgetDatasets")
    tree = main.dataset_selector
    for row in (1, 2, 3):
        tree.topLevelItem(row).setSelected(True)
    main.comboBox_Model.setCurrentIndex(main.comboBox_Model.findText("Parse-Model"))
    _pump(app)
    _save(main, "fcs_add_analysis.png")

    main.onAddFit(data_idx=[1, 2, 3])
    _pump(app, 12)
    _save(main, "fcs_fit_windows.png")
    main.onTabWindows()
    _pump(app, 6)
    _save(main, "fcs_fit_windows_tabbed.png")
    main.onTileWindows()
    _pump(app, 6)
    _save(main, "fcs_fit_windows_tiled.png")

    first = _window_of(main, "A488_ACF_1")
    _activate(app, main, first)
    first.showMaximized()
    _pump(app, 6)
    combo = _combo_with(main.dockWidgetAnalysis, "3D Gauss, 1 bunching")
    combo.setCurrentIndex(combo.findText("3D Gauss, 1 bunching"))
    _pump(app, 6)
    _save(main, "fcs_model_3d_gauss_bunching.png")
    _save(main.dockWidgetAnalysis, "fcs_model_parameters.png")

    _run_fit(app, main)
    _save(main, "fcs_first_fit.png")

    # the first point carries detector afterpulsing, the long-lag tail is noise:
    # start at the second point and end the fit range at ~100 ms
    controller = _fit_controller(main)
    x = cs.fits[0].data.x
    last = int(abs(x - 100.0).argmin())
    controller.onFitRangeChanged(None, xmin=1, xmax=last)
    _pump(app, 6)
    _save(main, "fcs_fit_range.png")
    _run_fit(app, main)
    _save(main, "fcs_second_fit.png")

    first.showNormal()
    for name_end in ("A488_ACF_2", "A488_ACF_3"):
        _activate(app, main, _window_of(main, name_end))
        _choose_formula(app, main, "3D Gauss, 1 bunching")
        _fit_controller(main).onFitRangeChanged(None, xmin=1, xmax=last)
        _run_fit(app, main)
    main.onTileWindows()
    _pump(app, 6)
    _save(main, "fcs_all_fitted.png")

    # link td, s and bt of curve 2 to curve 1 through each row's menu
    _activate(app, main, _window_of(main, "A488_ACF_2"))
    table = _parameter_table(main)
    menu = table.context_menu(_row_of(table, "td"))
    shots, _ = _menu_chain(app, menu, ["🔗 Link td to", "Parse-Model - A488_ACF_1"])
    dock = main.dockWidgetAnalysis.grab().toImage()
    _compose([dock] + shots).save(str(OUT / "fcs_link_menu.png"))
    print("wrote fcs_link_menu.png", flush=True)
    for window in ("A488_ACF_2", "A488_ACF_3"):
        _activate(app, main, _window_of(main, window))
        for name in ("td", "s", "bt"):
            table = _parameter_table(main)
            menu = table.context_menu(_row_of(table, name))
            _shots, action = _menu_chain(
                app, menu, [f"🔗 Link {name} to", "Parse-Model - A488_ACF_1", "Parameters", name])
            action.trigger()
            _pump(app, 4)
    _save(main.dockWidgetAnalysis, "fcs_linked_parameters.png")

    # a global fit over the three curves
    _raise_dock(main, "dockWidgetDatasets")
    tree = main.dataset_selector
    tree.clearSelection()
    tree.setCurrentItem(tree.topLevelItem(0))  # as a click: the model list follows
    _pump(app, 4)
    main.comboBox_Model.setCurrentIndex(main.comboBox_Model.findText("Global fit"))
    _pump(app, 4)
    _save(main, "fcs_add_global_fit.png")
    # The global fit's own editor is not pictured: its "➕ Add"/"➖ Remove"
    # buttons raise (GlobalFitModel.add_selected_fit calls self.fit.append_fit,
    # which only the model has), its "Local fits" table does not refresh, and the
    # member windows do not redraw after a global fit -- all reported.

    # File -> save fit results
    bar = main.menuBar if not callable(main.menuBar) else main.menuBar()
    file_menu = bar.actions()[0].menu()
    shots, _ = _menu_chain(app, file_menu, ["Fits"])
    _compose(shots).save(str(OUT / "fcs_file_menu.png"))
    print("file menu", [a.text() for a in file_menu.actions()], flush=True)
    print("wrote fcs_file_menu.png", flush=True)
    return app, main


def main(names: list[str]) -> None:
    """Run the named ``grab_*`` functions, then leave without Qt's teardown."""
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])  # noqa: F841
    for name in names:
        globals()[name]()
    os._exit(0)


if __name__ == "__main__":
    main(sys.argv[1:])
