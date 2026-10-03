"""Populated Qt baseline of the Spectra tool (the predecessor gui/tool.py of git HEAD at the emtk switch), temp HOME/DB.

python capture_qt_populated.py <outdir>   (from the repo root)
"""
import importlib.util, os, subprocess, sys, tempfile, time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
tmp = Path(tempfile.mkdtemp(prefix="spectraqt_"))
os.environ.update(HOME=str(tmp), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"),
                  MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"))
sys.path.insert(0, os.getcwd())
import numpy as np
from qtpy import QtWidgets
out = Path(sys.argv[1])
source = Path(out, "pre-upgrade", "qt_tool.py.txt").read_text()
spec = importlib.util.spec_from_loader("spectra_qt_tool", loader=None)
mod = importlib.util.module_from_spec(spec); exec(compile(source, "qt_tool.py", "exec"), mod.__dict__)
from chisurf.plugins.spectra_downloader.mmfdb_adapter import FluorophoreDatabase
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
db = FluorophoreDatabase(tmp / "staging.db"); db.connect()
x = np.arange(400.0, 701.0, 5.0)
for name, prov, kind, c in (("EGFP", "fpbase", "fluorescent_protein", 509), ("Alexa Fluor 488", "atto", "organic_dye", 519),
                            ("ET525/50m", "chroma", "bandpass", 525), ("DMLP550", "thorlabs", "dichroic", 550),
                            ("SPAD 650", "thorlabs", "apd", 650)):
    db.register_component(name=name, source=prov, kind=kind, properties={"em_max": c, "description": "Reference fixture"},
                          spectra={"emission": (x, np.exp(-0.5 * ((x - c) / 22.0) ** 2))})
w = mod.SpectraTool(db); w.resize(1180, 760); w.show()
def spin(n=25):
    for _ in range(n): app.processEvents(); time.sleep(0.01)
spin()
for i, name in enumerate(("overview", "browse", "download", "add_to_mmfdb")):
    w.nav_list.setCurrentRow(i); spin()
    if name == "browse":
        b = next(c for c in w.findChildren(QtWidgets.QWidget) if type(c).__name__ == "SpectraBrowserWidget")
        b.refresh(); b._table.selectRow(0); spin()
    w.grab().save(str(out / f"before_populated_{name}.png"))
w.resize(800, 600); spin(); w.nav_list.setCurrentRow(1); spin(); w.grab().save(str(out / "before_populated_browse_800x600.png")); 
btns = sorted({b.text() + " | " + b.toolTip() for b in w.findChildren((QtWidgets.QToolButton, QtWidgets.QPushButton))})
print("\n".join(btns))
