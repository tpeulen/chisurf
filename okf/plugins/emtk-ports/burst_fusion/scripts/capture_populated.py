"""Populated captures: the plugin's own demo (declared molecules and splits) loaded and estimated.

usage: capture_populated.py <out_dir> qt|emtk <prefix> [<qt_head dir>]   (run from the repo root)
qt = the committed Qt tool (HEAD gui/tool.py over HEAD gui/app.py, gui/view_model.py, gui/sections.py, via qt_head).
"""
import pathlib, sys, time

out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
from test.gui.emtk_port_parity import emtk_screenshot

if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("burst_fusion", ("view_model", "sections", "app"))
    w = klass()
    w.load_demo()
    w.model.analyze()
    w.resize(1200, 800); w.show()
    for _ in range(30):
        app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", w.model._status)
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.burst.burst_fusion.gui.app import create_app
    for size in [(1200, 800), (800, 600)]:
        a = create_app()
        for action in (a.controller.demo, a.controller.estimate):
            action()
            while a.controller.running:
                time.sleep(0.05); a.draw(RecordingPainter(), 0, 0, *size)
            a.draw(RecordingPainter(), 0, 0, *size)
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", a.model._status, a.controller.status)
        a.close()
