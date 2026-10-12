"""Spectra tool, Förster calculator and MFD Prepare screenshots."""
import os, sys, pathlib, tempfile
# Scratch settings, set before chisurf reads them: a capture never touches the user's preferences.
os.environ.setdefault("CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="chisurf_grab_settings_"))
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
    """The Förster radius calculator (emtk dialog) on the seed MMFDB: Alexa488 -> Alexa594, n = 1.33 (guide 83)."""
    from emtk.app import ImApp
    from emtk.testing import Driver
    from PIL import Image, ImageChops

    from chisurf.core.fluorescence.fret.forster_calculator import ForsterCalculatorModel
    from chisurf.emtk.forster_calculator import ForsterCalculatorDialog

    model = ForsterCalculatorModel()
    donors = {name: pid for pid, name in model.donor_options()[1:]}
    acceptors = {name: pid for pid, name in model.acceptor_options()[1:]}
    model.set_donor(donors["Alexa488"])
    model.set_acceptor(acceptors["Alexa594"])
    model.refractive_index = 1.33
    model.changed()
    dialog = ForsterCalculatorDialog(on_close=lambda r0: None, model=model)
    size = (720, 330)
    holder = {}

    def gui() -> None:
        dialog.draw((0, 0, *size))
        holder["app"]._item_rects.update(dialog.rects)

    holder["app"] = ImApp(gui)
    driver = Driver(holder["app"], size)
    driver.frame(3)
    print("calc: R0", round(model.r0, 1), "QY", model.donor_qy, "eps", model.acceptor_emax, flush=True)
    print(model.spectra_text(), flush=True)
    target = FIG / "forster_calculator.png"
    driver.screenshot(target)
    image = Image.open(target).convert("RGB")
    box = ImageChops.difference(image, Image.new("RGB", image.size, image.getpixel((0, 0)))).getbbox()
    if box:
        pad = 6
        image.crop((max(box[0] - pad, 0), max(box[1] - pad, 0),
                    min(box[2] + pad, image.width), min(box[3] + pad, image.height))).save(target)
    print("wrote forster_calculator.png", flush=True)

def _grab_mfd_prepare():
    """The native MFD Prepare window after *Prepare* on the shipped sm-DNA burst folder (guide 85)."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from emtk.testing import Driver
    from emtk_shot import app_from, wait

    app = app_from("mfd_prepare")
    driver = Driver(app, (1400, 860))
    driver.frame(2)
    assert app.files_dropped([str(pathlib.Path(BURST).resolve())])
    app.start_prepare()
    wait(driver, lambda: not app.job.busy, timeout=600)
    print("mfd prepare:", app.panel.status_line, flush=True)
    driver.screenshot(FIG / "mfd_prepare_report.png")
    print("wrote mfd_prepare_report.png", flush=True)
    app.close()

if __name__ == "__main__":
    for name in sys.argv[1:]:
        globals()[name]()
