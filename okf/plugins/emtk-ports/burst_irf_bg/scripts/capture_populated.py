"""Populated captures: the IRF demo measurement (IRF at 2.0 ns, identical non-burst streams) computed.

usage: capture_populated.py <out_dir> qt|emtk <prefix> [<qt_head dir>]   (run from the repo root)
qt = the committed Qt tool (HEAD gui/tool.py over HEAD gui/app.py, gui/view_model.py, gui/sections.py, via qt_head).
"""
import pathlib, sys, tempfile, time

out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.burst.burst_irf_bg.test.demo_data import build

path = build(pathlib.Path(tempfile.mkdtemp()) / "measurement")
DETECTORS = {"green": {"chs": [0, 8], "micro_time_ranges": [[0, 4096]]},
             "red": {"chs": [1, 9], "micro_time_ranges": [[0, 4096]]}}

if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("burst_irf_bg", ("view_model", "sections", "app"))
    w = klass()
    w.model.channels_provider = lambda: DETECTORS
    w.model.add_files([str(path)])
    w._compute()
    w.resize(1200, 800); w.show()
    for _ in range(30):
        app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", w.model.results_rows())
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.burst.burst_irf_bg.gui.app import create_app
    for size in [(1200, 800), (800, 600)]:
        a = create_app()
        a.controller.add_files([path])
        a.controller.run()
        while a.controller.running:
            time.sleep(0.05); a.draw(RecordingPainter(), 0, 0, *size)
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", a.model.results_rows(), a.controller.status)
        a.close()
