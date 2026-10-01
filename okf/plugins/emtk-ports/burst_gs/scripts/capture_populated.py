"""Populated captures: the tool's own simulation (k 3000 / 1000 /s, E 0.25 / 0.75, 200 bursts) fitted.

usage: capture_populated.py <out_dir> qt|emtk <prefix> [<qt_head dir>]   (run from the repo root)
qt = the committed Qt tool (HEAD gui/tool.py over HEAD gui/app.py and gui/view_model.py, via qt_head).
"""
import pathlib, sys, time

out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
from test.gui.emtk_port_parity import emtk_screenshot

if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("burst_gs", ("view_model", "app"))
    w = klass()
    w.model.use_simulation = True
    w._fitted(bool(w.model.compute()))
    w._refresh()
    w.resize(1200, 800); w.show()
    for _ in range(30):
        app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", w.statusBar().currentMessage())
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.burst.burst_gs.gui.app import create_app
    for size in [(1200, 800), (800, 600)]:
        a = create_app()
        a.model.use_simulation = True
        a.controller.run()
        while a.controller.running:
            time.sleep(0.05); a.draw(RecordingPainter(), 0, 0, *size)
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", a.controller.status)
        a.close()
