"""Populated captures of the Qt tool (every tab) and the committed emtk app.  usage: capture_before.py <out_dir>"""
import pathlib, sys
out = pathlib.Path(sys.argv[1])
from qtpy import QtWidgets
from test.gui.emtk_port_parity import emtk_screenshot
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.calculator.fcs_saturation_calc.gui.tool import SaturationCalculatorTool
w = SaturationCalculatorTool()
w.resize(1300, 850); w.show()
tabs = w.findChildren(QtWidgets.QTabWidget)
print("tabwidgets", [(t.count(), [t.tabText(i) for i in range(t.count())]) for t in tabs])
def spin():
    for _ in range(40):
        app.processEvents()
spin()
w.grab().save(str(out / "before_populated.png"))
for t in tabs:
    for i in range(t.count()):
        t.setCurrentIndex(i); spin()
        w.grab().save(str(out / f"before_populated_{t.tabText(i).replace(' ', '_').replace('&','and').replace('(','').replace(')','')}.png"))
from chisurf.plugins.calculator.fcs_saturation_calc.gui.app import make_app
for size in [(1200, 800), (800, 600)]:
    a = make_app(restore=False)
    emtk_screenshot(a, out / f"before_emtk_populated_{size[0]}x{size[1]}.png", size)
