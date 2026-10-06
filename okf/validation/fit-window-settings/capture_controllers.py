"""Grab every fit-window page's plot-settings panel (legacy Qt controller) of one case."""
import json, os, sys, traceback
from pathlib import Path
sys.path.insert(0, os.getcwd())
from test.gui.fit_window_page_probe import _open_main, _frames
from test.gui.migration_parity import control_inventory

directory, out, case = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
out.mkdir(parents=True, exist_ok=True)
report = {}
try:
    from qtpy import QtWidgets
    from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow
    app, main_window, result = _open_main(directory)
    for number, sub in enumerate(main_window.mdiarea.subWindowList()):
        if not isinstance(sub, FitSubWindow):
            continue
        main_window.mdiarea.setActiveSubWindow(sub)
        area = sub.plot_tab_widget
        for index in range(area.count()):
            plot = sub.ensure_plot_created(index)
            cls = type(plot).__name__
            if cls in report:
                continue
            area.setCurrentIndex(index); sub.refresh_current_plot(); _frames(app, area)
            ctrl = plot.plot_controller
            tabs = ctrl if isinstance(ctrl, QtWidgets.QTabWidget) else None
            shots = []
            for t in range(tabs.count() if tabs else 1):
                if tabs: tabs.setCurrentIndex(t)
                ctrl.setParent(None); ctrl.resize(440, 640); ctrl.show()
                for _ in range(4): app.processEvents()
                png = out / f"{cls}_{t}.png"; ctrl.grab().save(str(png)); shots.append(str(png))
            report[cls] = {"case": case, "pngs": shots, "inventory": control_inventory(ctrl)}
except Exception:
    report["__error__"] = traceback.format_exc()[-3000:]
(out / f"ctrl_{case}.json").write_text(json.dumps(report, indent=1, default=str))
os._exit(0)
