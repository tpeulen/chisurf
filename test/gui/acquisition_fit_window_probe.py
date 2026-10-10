"""Open the Acquisition plugin in a real Main; record what its fit window shows.

Child process of ``test_acquisition_fit_window_screenshot.py``::

    python -m test.gui.acquisition_fit_window_probe <out dir>

Writes ``<out dir>/report.json`` (dock titles, per-page drawn series) and
``<out dir>/acquisition.png`` (the grabbed fit window).
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path


def main() -> None:
    """Start Main, load the plugin, wait for the stream, grab the Acquisition window."""
    out = Path(sys.argv[1])
    report = {"errors": []}
    try:
        from qtpy import QtCore, QtWidgets

        import chisurf as cs
        import chisurf.gui as gui
        from chisurf.core.project.project import ResourceContext
        from chisurf.gui.main import Main
        from chisurf.gui.widgets.fitting import FitSubWindow

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        settings_type = QtCore.QSettings

        class IsolatedSettings(settings_type):
            """Keep the probe's window state out of the user's preferences."""

            def __init__(self, *args, **kwargs):
                super().__init__(str(out / "main.ini"), settings_type.IniFormat)

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
        main.resize(1500, 950)
        main.show()
        main.load_and_show_plugin("chisurf.plugins.core.acq")
        deadline = time.monotonic() + 40
        sub = None
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.05)
            subs = [s for s in main.mdiarea.subWindowList() if isinstance(s, FitSubWindow)]
            if subs:
                sub = subs[0]
                break
        report["fit_window"] = sub is not None
        if sub is not None:
            sub.resize(1000, 700)
            main.mdiarea.setActiveSubWindow(sub)
            area = sub.plot_tab_widget
            from chisurf.core.models.acquisition import acquisition_dataset

            dataset = acquisition_dataset(sub.fit)
            end = time.monotonic() + 40
            while dataset is not None and time.monotonic() < end:
                app.processEvents()
                time.sleep(0.05)
                if not dataset.streaming and dataset.snapshot is not None:
                    break
            for _ in range(20):  # let the last snapshot reach the pages
                app.processEvents()
                time.sleep(0.05)
            report["title"] = sub.windowTitle()
            report["docks"] = [area.tabText(i) for i in range(area.count())]
            report["photons"] = None if dataset is None else int(dataset.snapshot["total_photons"])
            pages = {}
            for index in range(area.count()):
                area.setCurrentIndex(index)
                page = sub.ensure_plot_created(index)
                sub.refresh_current_plot()
                for _ in range(4):
                    app.processEvents()
                    area.host.repaint()
                title = area.tabText(index)
                if hasattr(page, "series_key"):
                    live = page.live()
                    pages[title] = {
                        "series": [(label, int(len(x))) for label, x, _y in
                                   live.series.get(page.series_key, [])],
                        "state": page.state,
                    }
                    sub.grab().save(str(out / f"page_{index}_{title.replace(' ', '_')}.png"))
            report["pages"] = pages
            area.setCurrentIndex(0)
            for _ in range(4):
                app.processEvents()
            sub.grab().save(str(out / "acquisition.png"))
            main.grab().save(str(out / "main.png"))
    except Exception:
        report["errors"].append(traceback.format_exc()[-3000:])
    (out / "report.json").write_text(json.dumps(report, indent=1))
    os._exit(0)


if __name__ == "__main__":
    main()
