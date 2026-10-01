"""Drive the Qt Photon Table tool (host of the legacy emtk app) into populated states.

Usage: python capture_qt_populated.py <tempdir> <out dir>   (from the repo root)
Temporary settings only; the sample is a private copy.
"""
import json, os, pathlib, shutil, sys
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
os.environ["MMFDB_SETTINGS_DIR"] = str(T / "mmfdb")
os.environ["MMFDB_DATABASE_PATH"] = str(T / "mmfdb" / "db.sqlite")
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
src = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")
cp = T / "BH_SPC132.spc"; shutil.copy(src, cp)
for s in src.parent.glob("BH_SPC132*"):
    if s != src: shutil.copy(s, T / s.name)
from chisurf.plugins.tttr.photon_table.gui.tool import PhotonTableTool
w = PhotonTableTool(); w.resize(1200, 800); w.show()
def grab(name):
    for _ in range(30): app.processEvents()
    w.grab().save(str(O / name))
grab("before_populated_empty.png")
w.load_file(str(cp))
m = w._model
out = {"n_photons": m.n_photons, "channels": m.used_channels, "res": m.macro_resolution,
       "acq_s": m.acquisition_time_s(), "n_micro": m.n_micro_channels,
       "status": w.statusBar().currentMessage()}
out["page0"] = m.page(0, 5)
grab("before_populated.png")
w.channel_filter = m.used_channels[-1]; w.first_index = 0
out["filter_channel"] = w.channel_filter; out["filtered_count"] = m.filtered_count(w.channel_filter)
out["page_filtered"] = m.page(0, 5, w.channel_filter)
grab("before_populated_filtered.png")
w.channel_filter = -1; w.first_index = 100; w.rows_per_page = 50
grab("before_populated_page.png")
w.load_file(str(T / "missing.spc")); out["error_status"] = w.statusBar().currentMessage()
grab("before_populated_error.png")
print(json.dumps(out, indent=1, default=str)); (O / "before_populated.json").write_text(json.dumps(out, indent=1, default=str))
