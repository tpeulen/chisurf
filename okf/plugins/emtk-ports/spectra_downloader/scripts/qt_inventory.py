"""before.json for the Spectra tool from the predecessor Qt tool (pre-upgrade/qt_tool.py.txt), every panel visited, populated."""
import json, os, sys, tempfile, time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
import test.gui
tmp = Path(tempfile.mkdtemp(prefix="spectraqtinv_"))
os.environ.update(HOME=str(tmp), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"))
import numpy as np
from qtpy import QtWidgets
from test.gui import migration_parity as mp
from test.gui.emtk_port_parity import normalize
out = Path(sys.argv[1])
mod = type(sys)("spectra_qt_tool"); exec(compile((out / "pre-upgrade" / "qt_tool.py.txt").read_text(), "qt_tool.py", "exec"), mod.__dict__)
from chisurf.plugins.spectra_downloader.mmfdb_adapter import FluorophoreDatabase
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
db = FluorophoreDatabase(tmp / "staging.db"); db.connect()
x = np.arange(400.0, 701.0, 5.0)
for name, prov, kind, c in (("EGFP", "fpbase", "fluorescent_protein", 509), ("Alexa Fluor 488", "atto", "organic_dye", 519), ("ET525/50m", "chroma", "bandpass", 525)):
    db.register_component(name=name, source=prov, kind=kind, properties={"em_max": c}, spectra={"emission": (x, np.exp(-0.5 * ((x - c) / 22.0) ** 2))})
w = mod.SpectraTool(db); w.resize(1180, 760); w.show()
def spin(n=20):
    for _ in range(n): app.processEvents(); time.sleep(0.01)
spin()
for i in range(4):
    w.nav_list.setCurrentRow(i); spin()
    if i == 1:
        b = next(c for c in w.findChildren(QtWidgets.QWidget) if type(c).__name__ == "SpectraBrowserWidget"); b._table.selectRow(0); spin()
inv = mp.control_inventory(w)
inv["entrypoint"] = "predecessor chisurf.plugins.spectra_downloader.gui.tool:SpectraTool (git history, pre-upgrade/qt_tool.py.txt)"
inv["size"] = [1180, 760]
inv["controls"] = sorted({normalize(c) for c in inv["controls"]} - {""})
(out / "before.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False))
print("before.json:", len(inv["controls"]), "controls")
