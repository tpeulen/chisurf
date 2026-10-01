"""Populated captures on test/data/clsm/Leica_SP5.ptu with one channel 'all' (every used routing channel).

qt:   CountRateAnalyzer as committed (HEAD tool.py + HEAD view_model.py), Count Rates and Results tabs
emtk: the current app (create_app)
"""
import sys, pathlib
from test.gui.emtk_port_parity import emtk_screenshot
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import tttrlib
out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
ptu = str(pathlib.Path("test/data/clsm/Leica_SP5.ptu").resolve())
routing = [int(c) for c in tttrlib.TTTR(ptu).get_used_routing_channels()]
channels = {"all": [{"detector_chs": routing, "micro_time_range": None, "window_range": None}]}
if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("tttr_count_rate_analysis", ("view_model",))
    w = klass(); w.resize(1200, 800); w.show()
    m = w.model
    m.add_files([ptu]); m.channels_provider = lambda: channels; m.compute(); m.notify("changed")
    for _ in range(20): app.processEvents()
    tabs = w.findChildren(QtWidgets.QTabWidget)[0]
    for i in range(tabs.count()):
        tabs.setCurrentIndex(i)
        for _ in range(10): app.processEvents()
        w.grab().save(str(out / f"{prefix}_tab_{tabs.tabText(i).replace(' ', '_')}.png"))
    print("qt rows", m.results_rows())
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller import create_app
    for size in [(1200, 800), (800, 600)]:
        a = create_app()
        m = a.tool._model
        m.add_files([ptu]); m.channels_provider = lambda: channels; m.compute(); m.notify("changed")
        for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        if size[0] == 1200: print("emtk rows", m.results_rows())
