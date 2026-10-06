"""After-half of the plot-settings migration: grab each page's emtk settings dock.

Mirror of ``capture_controllers.py`` (the before-half, Qt controllers). For one
produced catalogue case (``python -m test.project.scientific_catalogue_probe
--case N DIR``) it opens the real Main, makes every page current once, and
writes ``<Class>_settings.png`` (the *Plot settings* dock) and
``<Class>_page.png`` (the page on the fit-window surface), plus
``settings_<case>.json`` with the names of every field/action the form drew
(``FormState.rects``) for the control-inventory comparison.

    python okf/validation/fit-window-settings/capture_settings.py CASE_DIR OUT_DIR CASE [Class ...]
"""
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, os.getcwd())
from test.gui.fit_window_page_probe import _frames, _open_main  # noqa: E402

directory, out, case = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
only = set(sys.argv[4:])
out.mkdir(parents=True, exist_ok=True)
report = {}
try:
    from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow

    app, main_window, result = _open_main(directory)
    for sub in main_window.mdiarea.subWindowList():
        if not isinstance(sub, FitSubWindow):
            continue
        main_window.mdiarea.setActiveSubWindow(sub)
        area = sub.plot_tab_widget
        for index in range(area.count()):
            cls = sub._plot_specs[index][0].__name__
            if cls in report or (only and cls not in only):
                continue
            plot = sub.ensure_plot_created(index)
            area.setCurrentIndex(index)
            sub.refresh_current_plot()
            sub.show_plot_settings()
            host = sub.plot_settings
            host.resize(440, 640)
            for _ in range(6):
                _frames(app, area, 1)
                host.host.repaint()
            host.grab().save(str(out / f"{cls}_settings.png"))
            area.host.grab().save(str(out / f"{cls}_page.png"))
            form = getattr(plot, "_settings_form", None)
            report[cls] = {
                "case": case,
                "fields": sorted((getattr(form, "rects", None) or {}).keys()),
            }
except Exception:
    report["__error__"] = traceback.format_exc()[-3000:]
(out / f"settings_{case}.json").write_text(json.dumps(report, indent=1, default=str))
os._exit(0)
