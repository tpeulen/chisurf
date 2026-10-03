"""Populated Qt baseline of the Wizards hub (offscreen): each wizard selected. Usage: <out dir>."""
import sys, pathlib
from qtpy import QtWidgets, QtCore
from chisurf.plugins.core.wizards.gui.tool import WizardHub
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
w = WizardHub(); w.resize(1200, 800); w.show(); app.processEvents()
for row, name in enumerate(("anisotropy", "batch_analysis")):
    w._list.setCurrentRow(row); app.processEvents()
    w.grab().save(str(out / f"before_populated_{row+1}_{name}.png"))
