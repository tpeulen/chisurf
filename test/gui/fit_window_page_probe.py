"""Open one produced science project in Main; record what each fit-window page draws.

Child process of ``test_fit_window_pages_all_models.py``::

    python -m test.gui.fit_window_page_probe <case dir> <out dir> <case>

Writes ``<out dir>/<case>.json`` with, per page, the plot class, whether the
page object is a Qt widget (``is_widget``; it must not be), whether it declares
nothing the surface can draw (``missing``), whether its *Plot settings* drew
(``settings_error``), and a PNG of every page and of its settings.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path


def _open_main(directory: Path):
    """An isolated Main with the project of *directory* loaded through the API."""
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
        """Keep the probe's window state out of the user's preferences."""

        def __init__(self, *args, **kwargs):
            super().__init__(str(directory / "page-probe-main.ini"), settings_type.IniFormat)

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
    main.resize(1500, 950)
    main.show()
    api = ChiSurfAPI(mode="local")
    dispatcher = ServiceDispatcher(api._state)
    dispatcher._build_default_registry()
    install_fitting_client(InProcessClient(dispatcher))
    result = api.load_project(str(directory / "science-0.cs.pto"))
    for _ in range(5):
        app.processEvents()
    return app, main, result


def _frames(app, area, n: int = 4) -> None:
    for _ in range(n):
        app.processEvents()
        area.host.repaint()


def main() -> None:
    """Record every page of every fit window of one case."""
    directory, out, case = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    report = {"case": case, "pages": [], "errors": []}
    try:
        from qtpy import QtWidgets

        from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow

        app, main_window, result = _open_main(directory)
        report["load_ok"] = result.get("ok")
        for number, sub in enumerate(main_window.mdiarea.subWindowList()):
            if not isinstance(sub, FitSubWindow):
                continue
            sub.resize(900, 650)
            main_window.mdiarea.setActiveSubWindow(sub)
            area = sub.plot_tab_widget
            for index in range(area.count()):
                title = area.tabText(index)
                record = {"window": number, "index": index, "title": title}
                try:
                    area.setCurrentIndex(index)
                    sub.ensure_plot_created(index)
                    sub.refresh_current_plot()
                    _frames(app, area)
                    body = area.surface.page_body(index)
                    page = area.widget(index)
                    record["plot_class"] = type(page).__name__
                    record["is_widget"] = isinstance(page, QtWidgets.QWidget)
                    record["missing"] = sorted(set(body.missing)) if body else ["<no body>"]
                    _frames(app, area, 3)
                    name = title.replace(" ", "_").replace("/", "_")
                    png = out / f"{case}_w{number}_p{index}_{name}.png"
                    sub.grab().save(str(png))
                    record["png"] = str(png)
                    sub.show_plot_settings()
                    host = sub.plot_settings
                    host.resize(440, 640)
                    host.host.repaint()
                    error = host.surface.last_error
                    record["settings_error"] = None if error is None else repr(error)
                    host.grab().save(str(out / f"{case}_w{number}_p{index}_{name}_settings.png"))
                except Exception:
                    record["error"] = traceback.format_exc()[-1500:]
                report["pages"].append(record)
    except Exception:
        report["errors"].append(traceback.format_exc()[-3000:])
    (out / f"{case}.json").write_text(json.dumps(report, indent=1))
    os._exit(0)


if __name__ == "__main__":
    main()
