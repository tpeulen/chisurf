"""1:1 restore probe: stage A builds+saves, stage B opens in a fresh process; both measure."""

import json
import os
import sys
from pathlib import Path

out = Path(sys.argv[1])
stage = sys.argv[2]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
for k in [k for k in sys.modules if k == "test" or k.startswith("test.")]:
    del sys.modules[k]
from qtpy import QtCore, QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class IsolatedSettings(QtCore.QSettings):
    def __init__(self, *a, **k):
        super().__init__(str(out / f"{stage}.ini"), QtCore.QSettings.IniFormat)


QtCore.QSettings = IsolatedSettings

import chisurf as cs
import chisurf.gui as cs_gui
from chisurf.core.project.lifecycle import SaveDecision
from chisurf.core.project.project import ResourceContext
from chisurf.gui.main import Main

cs.fits[:] = []
cs.imported_datasets[:] = []
cs.__client__ = None
cs.project_resources = ResourceContext()
cs_gui.fit_windows = []
if getattr(cs, "console", None) is None:
    cs.console = cs_gui.widgets.ipython.QIPythonWidget()
    cs.console.history_widget = None
main = Main()
cs.cs = main
main.resize(1500, 950)
main.init_setups()
main.define_actions()
main.arrange_widgets()
main.show()
main._save_decision = lambda: SaveDecision.DISCARD
for _ in range(5):
    app.processEvents()


def measure():
    for _ in range(10):
        app.processEvents()
    m = {
        "main_geometry": [
            main.geometry().x(),
            main.geometry().y(),
            main.geometry().width(),
            main.geometry().height(),
        ],
        "main_maximized": main.isMaximized(),
        "docks": {
            d.objectName(): {
                "visible": d.isVisible(),
                "area": int(main.dockWidgetArea(d)),
                "floating": d.isFloating(),
            }
            for d in main.findChildren(QtWidgets.QDockWidget)
            if d.objectName()
        },
        "mdi_view_mode": int(main.mdiarea.viewMode()),
    }
    act = main.mdiarea.activeSubWindow()
    m["active_fit"] = getattr(getattr(act, "fit", None), "name", None)
    m["stacking"] = [
        getattr(getattr(w, "fit", None), "name", None)
        for w in main.mdiarea.subWindowList(QtWidgets.QMdiArea.StackingOrder)
    ]
    wins = {}
    for w in main.mdiarea.subWindowList():
        g = w.geometry()
        name = w.fit.name
        rec = {
            "geometry": [g.x(), g.y(), g.width(), g.height()],
            "maximized": w.isMaximized(),
            "minimized": w.isMinimized(),
            "current_plot_index": int(w.plot_tab_widget.currentIndex()),
        }
        try:
            rec["code_shown"] = bool(w.plot_tab_widget.code_shown())
        except Exception as e:
            rec["code_shown"] = repr(e)
        try:
            rec["dock_layout"] = w.get_fit_dock_layout_state()
        except Exception as e:
            rec["dock_layout"] = repr(e)
        ps = {}
        for i, p in enumerate(getattr(w, "_plots_all", []) or []):
            if p is None:
                continue
            entry = {}
            for k, obj in (("plot", p), ("controller", getattr(p, "plot_controller", None))):
                f = getattr(obj, "get_state", None)
                if callable(f):
                    try:
                        entry[k] = f()
                    except Exception as e:
                        entry[k] = repr(e)
            panels = getattr(p, "_panels", None)
            # Ranges only for the plot on screen; a never-drawn tab has none yet,
            # and a zoom on any tab is part of the plot's own saved state above.
            if panels and i == rec["current_plot_index"]:
                entry["view_ranges"] = [
                    [[round(v, 6) for v in r] for r in panel.get_range()] for panel in panels
                ]
            ps[str(i)] = entry
        rec["plots"] = ps
        wins[name] = rec
    m["windows"] = wins
    return m


if stage == "A":
    import importlib.util as _iu

    from chisurf.core.experiments.tcspc.reader import TCSPCReader

    _spec = _iu.spec_from_file_location(
        "tcspc_visual", os.path.join(os.getcwd(), "test/gui/test_tcspc_project_visual_roundtrip.py")
    )
    _mod = _iu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _simulated_fit = _mod._simulated_fit
    from chisurf.gui.plots.lineplot.lineplot import LinePlot
    from chisurf.macros.core_fit import save_project

    exp = cs.experiment["TCSPC"]
    reader = TCSPCReader(record_provenance=False)
    exp.add_reader(reader)
    fits = []
    for name in ("first", "second"):
        fit = _simulated_fit()
        fit.name = name
        for mem in fit.grouped_fits:
            mem.data.experiment = exp
            mem.data.data_reader = reader
        cs.fits.append(fit)
        cs.imported_datasets.extend(mem.data for mem in fit.grouped_fits)
        main._open_fit_subwindow(fit)
        fits.append(fit)
    main.dataset_selector.update()
    main.fit_selector.update()
    app.processEvents()
    main.setGeometry(40, 30, 1460, 930)
    w1, w2 = main.mdiarea.subWindowList()
    w1.setGeometry(20, 15, 760, 560)
    w2.setGeometry(420, 200, 820, 600)
    n = w1.plot_tab_widget.count() if hasattr(w1.plot_tab_widget, "count") else 0
    if n > 1:
        w1.plot_tab_widget.setCurrentIndex(n - 1)
    plot = next(
        (
            w2.ensure_plot_created(i)
            for i in range(len(w2._plot_specs))
            if isinstance(w2.ensure_plot_created(i), LinePlot)
        ),
        None,
    )
    data_panel = plot._panels[2]
    (x0, x1), (y0, y1) = data_panel.get_range()
    data_panel.set_range(x=(x0 + 0.2 * (x1 - x0), x0 + 0.6 * (x1 - x0)), padding=0.0)
    st = plot.plot_controller.get_state()
    bk = [k for k, v in st.items() if type(v) is bool]
    if bk:
        st[bk[0]] = not st[bk[0]]
        plot.plot_controller.set_state(st)
    main.mdiarea.setActiveSubWindow(w1)
    variant = os.environ.get("CHISURF_RESTORE_VARIANT", "")
    if variant == "maximized":
        w2.showMaximized()
        main.mdiarea.setActiveSubWindow(w2)
    elif variant == "tabbed":
        main.mdiarea.setViewMode(QtWidgets.QMdiArea.TabbedView)
        main.mdiarea.setActiveSubWindow(w2)
    before = measure()
    (out / "A.json").write_text(json.dumps(before, indent=1, default=str))
    main.grab().save(str(out / "A.png"))
    save_project(str(out / "session.cs.pto"))
else:
    from chisurf.macros.core_fit import load_project

    r = load_project(str(out / "session.cs.pto"))
    assert r.get("ok") is True, r
    after = measure()
    (out / "B.json").write_text(json.dumps(after, indent=1, default=str))
    main.grab().save(str(out / "B.png"))
print("stage", stage, "done")
os._exit(0)
