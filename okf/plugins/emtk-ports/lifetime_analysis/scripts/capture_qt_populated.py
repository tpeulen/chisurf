"""Qt hub baseline: every panel selected in turn, G-factor panel with data, search filter. Usage: <out_dir>. Temp HOME/settings/QSettings."""
import pathlib, sys, tempfile
from qtpy import QtCore, QtWidgets
tmp = pathlib.Path(tempfile.mkdtemp())
QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, str(tmp / "qt"))
out = pathlib.Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.tool import LifetimeAnalysisTool
w = LifetimeAnalysisTool(); w.resize(1180, 760); w.show()
def shot(name):
    for _ in range(40): app.processEvents()
    w.grab().save(str(out / f"before_populated_{name}.png"))
shot("0_default")
lst = w.findChildren(QtWidgets.QListWidget)[0]
for i in range(lst.count()):
    lst.setCurrentRow(i); shot(f"{i + 1}_" + lst.item(i).text().split(". ")[-1].replace(" ", "_").replace("/", "_"))
search = w.findChildren(QtWidgets.QLineEdit)[0]; search.setText("lazy"); shot("6_search_lazy")
print("items", [lst.item(i).text() for i in range(lst.count())])
