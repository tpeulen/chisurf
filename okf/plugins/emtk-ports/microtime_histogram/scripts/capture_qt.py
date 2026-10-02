"""Populated Qt baseline of the Histogram-Microtime wizard on test/data/tttr/BH/132/BH_SPC132.spc (green detector, defaults).

usage: capture_qt.py <out.png> [<tab index>]   (repo root; temp HOME / CHISURF_SETTINGS_DIR / MMFDB_* from the caller)
Prints the cumulative histogram's length, sum, the FWHM text and the dt box (the Qt tool shows dt 357.23 for a 3.3 ps bin: legacy defect).
"""
import pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity  # noqa: F401  (before the plugin import)
from qtpy import QtWidgets
app = QtWidgets.QApplication([])
from chisurf.plugins.tttr.microtime_histogram.wizard import MicrotimeHistogram
w = MicrotimeHistogram()
w.listWidget.add_paths(["test/data/tttr/BH/132/BH_SPC132.spc"])
w.lineEdit_5.setText(str(pathlib.Path(tempfile.mkdtemp()) / "decay.dat"))   # autosave target, never next to the data
w.compute_microtime_histogram()
w.resize(1200, 800)
w.tabWidget.setCurrentIndex(int(sys.argv[2]) if len(sys.argv) > 2 else 0)
w.show()
for sp in w.findChildren(QtWidgets.QSplitter):
    sp.setSizes([420, 380])
for _ in range(30):
    app.processEvents()
w.grab().save(sys.argv[1])
print("QT", len(w.cumulative_ps), int(w.cumulative_ps.sum()), w.lineEdit_fwhm.text(), w.lineEdit_4.text(), w.parallel_channels, w.perpendicular_channels)
