"""History through the real Main window, for test_project_history_restore.

Stage A: edit a free parameter through its generated control, Undo and Redo through
the menu actions, save. Stage B (fresh interpreter): open the file, Undo and Redo.
Each stage writes what it measured to <out>/<stage>.json.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

out = Path(sys.argv[1])
stage = sys.argv[2]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
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


def pump(n=15):
    for _ in range(n):
        app.processEvents()


pump()


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(os.getcwd(), rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


report = {}


def hist():
    h = cs.history
    ev = h.list_events() if hasattr(h, "list_events") else []
    return {
        "n": len(ev),
        "cursor": getattr(h, "_cursor", None),
        "types": [e.get("action_type") for e in ev][-6:],
        "can_undo": main.actionHistoryUndo.isEnabled(),
        "can_redo": main.actionHistoryRedo.isEnabled(),
        "browser_rows": (
            main.historyBrowser.list_widget.count()
            if hasattr(main.historyBrowser, "list_widget")
            else None
        ),
    }


def param():
    m = cs.fits[0].grouped_fits[0].model
    p = next(p for p in m.parameters_all if not getattr(p, "is_output", False) and not p.fixed)
    return p


if stage == "A":
    tcspc = load("tcspc_visual", "test/gui/test_tcspc_project_visual_roundtrip.py")
    from chisurf.core.experiments.tcspc.reader import TCSPCReader

    exp = cs.experiment["TCSPC"]
    reader = TCSPCReader(record_provenance=False)
    exp.add_reader(reader)
    fit = tcspc._simulated_fit()
    fit.name = "hist"
    for mem in fit.grouped_fits:
        mem.data.experiment = exp
        mem.data.data_reader = reader
    cs.fits.append(fit)
    cs.imported_datasets.extend(mem.data for mem in fit.grouped_fits)
    main._open_fit_subwindow(fit)
    main.dataset_selector.update()
    main.fit_selector.update()
    pump()
    p = param()
    report["param"] = p.name
    v0 = float(p.value)
    report["v0"] = v0
    report["before_edit"] = hist()
    probe = load("sdprobe", "test/gui/scientific_document_gui_probe.py")
    try:
        probe._edit_control(main, app, p.unique_identifier, v0 * 1.5 + 0.1)
    except Exception as e:
        report["edit_error"] = repr(e)[:300]
    pump()
    v1 = float(param().value)
    report["v1"] = v1
    report["after_edit"] = hist()
    main.actionHistoryUndo.trigger()
    pump()
    report["after_undo_value"] = float(param().value)
    report["after_undo"] = hist()
    _hb = main.historyBrowser
    _hb.resize(900, 420)
    _hb.show()
    pump()
    _hb.grab().save(str(out / "history-after-undo.png"))
    main.actionHistoryRedo.trigger()
    pump()
    report["after_redo_value"] = float(param().value)
    report["after_redo"] = hist()
    from chisurf.macros.core_fit import save_project

    save_project(str(out / "hist.cs.pto"))
    report["saved"] = True
else:
    from chisurf.macros.core_fit import load_project

    r = load_project(str(out / "hist.cs.pto"))
    report["load_ok"] = r.get("ok")
    pump()
    report["reopened_value"] = float(param().value)
    report["reopened"] = hist()
    main.actionHistoryUndo.trigger()
    pump()
    report["reopened_undo_value"] = float(param().value)
    report["reopened_after_undo"] = hist()
    main.actionHistoryRedo.trigger()
    pump()
    report["reopened_redo_value"] = float(param().value)
(out / f"{stage}.json").write_text(json.dumps(report, indent=1, default=str))
main.grab().save(str(out / f"{stage}.png"))
print("done", stage, flush=True)
os._exit(0)
