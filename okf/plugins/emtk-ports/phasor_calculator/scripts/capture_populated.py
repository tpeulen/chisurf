"""Populated captures: FRET trajectory, component line, mixing region and cursor all switched on.

usage: capture_populated.py <out_dir> qt|emtk <prefix> [<qt_head dir>]   (run from the repo root)
qt = the committed Qt tool (HEAD gui/tool.py, model inline at HEAD, via qt_head).
"""
import pathlib, sys

out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
from test.gui.emtk_port_parity import emtk_screenshot

ON = {"show_fret": True, "show_component": True, "show_mixing": True, "show_cursor": True, "show_polar_grid": True}

if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("phasor_calculator")
    w = klass()
    for k, v in ON.items():
        setattr(w._model, k, v)
    w._form.sync_fields(); w._form.refresh_plots()
    w.resize(1200, 800); w.show()
    for _ in range(20):
        app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    from qtpy import QtWidgets as Q
    tabs = w.findChildren(Q.QTabBar)
    for bar in tabs:   # the plot lives in its own tab
        for i in range(bar.count()):
            if "lot" in bar.tabText(i):
                bar.setCurrentIndex(i)
    for _ in range(20):
        app.processEvents()
    w.grab().save(str(out / f"{prefix}_plot_tab.png"))
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.calculator.phasor_calculator.gui.app import make_app
    for size in [(1200, 800), (800, 600)]:
        a = make_app()
        for k, v in ON.items():
            setattr(a.tool._model, k, v)
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
