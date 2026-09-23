"""Spectra tool, Förster calculator and MFD Prepare screenshots."""
import sys, pathlib
from qtpy.QtWidgets import QApplication, QListWidget
app = QApplication.instance() or QApplication([])
import chisurf.core.settings  # noqa
S = pathlib.Path(__import__("tempfile").mkdtemp(prefix="chisurf_grab_"))
FIG = pathlib.Path(__file__).resolve().parents[1] / "figures"
BURST = "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15"

def _grab(w, name):
    w.show(); QApplication.processEvents(); w.grab().save(str(FIG / name)); print("wrote", name)

def _nav(tool, text):
    for lw in tool.findChildren(QListWidget):
        for i in range(lw.count()):
            if text in lw.item(i).text():
                lw.setCurrentRow(i); QApplication.processEvents(); return True
    return False

def _grab_spectra_tool():
    # A copy of the staging DB: opening it migrates/backs it up, and the docs
    # must not mutate the user's reference database.
    from chisurf.plugins.spectra_downloader.mmfdb_adapter import FluorophoreDatabase
    from chisurf.plugins.spectra_downloader.gui.tool import SpectraTool
    import shutil

    from chisurf.plugins.spectra_downloader.mmfdb_adapter import DEFAULT_DATABASE_PATH

    shutil.copy2(DEFAULT_DATABASE_PATH, S / "spectra_copy.db")
    db = FluorophoreDatabase(S / "spectra_copy.db"); db.connect()
    tool = SpectraTool(db); tool.resize(1300, 820); tool.show(); QApplication.processEvents()
    _nav(tool, "Overview"); _grab(tool, "spectra_overview.png")
    _nav(tool, "Browse")
    from chisurf.plugins.spectra_downloader.browser import SpectraBrowserWidget
    br = tool.findChildren(SpectraBrowserWidget)[0]
    br._search.setText("ATTO-647N"); QApplication.processEvents()
    br._table.selectRow(0); QApplication.processEvents()
    _grab(tool, "spectra_browse.png")
    

def _grab_forster_calculator():
    from chisurf.gui.widgets.models.tcspc.forster_calculator_dialog import ForsterCalculatorWidget
    w = ForsterCalculatorWidget(); w.resize(720, 330)
    w.donor_combo.setCurrentIndex(w.donor_combo.findText("Alexa488"))
    w.acceptor_combo.setCurrentIndex(w.acceptor_combo.findText("Alexa594"))
    QApplication.processEvents(); w._compute(); QApplication.processEvents()
    print("calc:", w.result_label.text(), "QY", w._model.donor_qy, "eps", w._model.acceptor_emax)
    _grab(w, "forster_calculator.png")

def _grab_mfd_prepare():
    from chisurf.plugins.burst.mfd_prepare.gui.tool import MfdPrepareTool
    t = MfdPrepareTool(); t.resize(1400, 700)
    t._folder = str(pathlib.Path(BURST).resolve()); t.folder_label.setText(pathlib.Path(BURST).name)
    t._prepare(); QApplication.processEvents()
    _grab(t, "mfd_prepare_report.png")

if __name__ == "__main__":
    for name in sys.argv[1:]:
        globals()[name]()
