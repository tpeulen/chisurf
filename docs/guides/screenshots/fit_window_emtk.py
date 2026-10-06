"""Figures of a fit window and its *Plot settings* dock, both drawn by emtk.

Opens a real Main (configured as for produced catalogue science, case 0), adds
a fitted lifetime analysis of the IBH sample decay with its prompt
(``test/data/tcspc/ibh_sample``), makes a page current, raises the *Plot
settings* dock and grabs the whole window, so the figure shows the page and its
settings side by side, as a user sees them.

    python -m test.project.scientific_catalogue_probe --case 0 /tmp/case0
    python docs/guides/screenshots/fit_window_emtk.py /tmp/case0

Writes into ``docs/manual/figures/``.
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
# Before anything else: chisurf's imports pull in the standard library's ``test``
# package, which would then shadow the repository's.
from test.gui.fit_window_page_probe import _frames, _open_main  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "manual" / "figures"

def _scan(page) -> None:
    """Scan the first free parameter over its scan range (default +-5 %) in 30 steps."""
    page.parameter_name = page.parameter_names()[0]
    page.scan_steps = 30
    page.scan_parameter()


#: ``(file, tab title, settings change)``: the page to show and what to set first
#: (attribute values on the settings model, or a callable taking the page).
SHOTS = (
    ("fit_window_plot_settings.png", "Fit", None),
    ("fit_window_reference_settings.png", "Fit", {"reference_mode": "raw", "log_x": True}),
    ("fit_window_info_settings.png", "Info", None),
    ("fit_window_parameter_scan.png", "Parameter scan", _scan),
)


def _ibh_fit():
    """A two-lifetime fit of the IBH sample decay with its measured prompt."""
    import numpy as np

    import chisurf as cs
    from chisurf.core.data import DataCurve, DataCurveGroup
    from chisurf.core.experiments.tcspc.reader import TCSPCReader
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.models.description import tcspc_lifetime

    root = pathlib.Path("test/data/tcspc/ibh_sample")
    decay = np.loadtxt(root / "Decay_577D.txt", skiprows=9)
    prompt = np.loadtxt(root / "Prompt.txt", skiprows=9)
    x = np.arange(len(decay), dtype=float) * 0.0141
    data = DataCurve(x=x, y=decay[:, 1], ey=np.sqrt(np.maximum(decay[:, 1], 1)),
                     name="Decay_577D")
    experiment = cs.experiment["TCSPC"]
    data.experiment = experiment
    data.data_reader = TCSPCReader(record_provenance=False)
    fit = FitGroup(data=DataCurveGroup([data], name="IBH sample"), model_class=tcspc_lifetime)
    fit.fit_range = (522, 3793)
    fit.model.set_dataset("response", DataCurve(x=x, y=prompt[:, 1], name="Prompt"))
    fit.update()
    fit.run()
    return fit


def main(case_dir: str) -> None:
    """Grab every figure of :data:`SHOTS` from the case in *case_dir*."""
    from qtpy import QtWidgets

    from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow

    OUT.mkdir(parents=True, exist_ok=True)
    app, main_window, _result = _open_main(pathlib.Path(case_dir))
    main_window.resize(1500, 900)
    for window in main_window.mdiarea.subWindowList():
        window.close_confirm = False
        window.close()
    fit = _ibh_fit()
    import chisurf as cs

    cs.fits.append(fit)
    main_window._open_fit_subwindow(fit)
    app.processEvents()
    sub = next(w for w in main_window.mdiarea.subWindowList()
               if isinstance(w, FitSubWindow) and w.fit is fit)
    main_window.mdiarea.setActiveSubWindow(sub)
    sub.showMaximized()
    dock = main_window.findChild(QtWidgets.QDockWidget, "dockWidgetPlot")
    dock.show()
    dock.raise_()
    area = sub.plot_tab_widget
    for name, title, change in SHOTS:
        index = next(i for i in range(area.count()) if area.tabText(i) == title)
        area.setCurrentIndex(index)
        page = sub.ensure_plot_created(index)
        sub.on_change_plot()
        sub.refresh_current_plot()
        if callable(change):
            change(page)
            for _ in range(600):  # a server scan job is polled per frame
                _frames(app, area, 1)
                if getattr(page, "_job", None) is None:
                    break
                time.sleep(0.05)
        elif change:
            model = page.settings_model()
            for attr, value in change.items():
                setattr(model, attr, value)
            page.update()
        sub.show_plot_settings()
        for _ in range(8):
            _frames(app, area, 1)
            sub.plot_settings.host.repaint()
        main_window.grab().save(str(OUT / name))
        print("wrote", name, flush=True)
    os._exit(0)


if __name__ == "__main__":
    main(sys.argv[1])
