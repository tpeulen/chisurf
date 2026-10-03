"""The two figures of docs/guides/83_spectra_and_r0.md from the emtk app on a COPY of the staging database (the original is never opened)."""
import os, shutil, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
import test.gui
tmp = Path(tempfile.mkdtemp(prefix="spectradocs_"))
os.environ.update(HOME=str(tmp), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"))
from chisurf.plugins.emtk_test_input import Driver
from chisurf.plugins.spectra_downloader.gui.app import create_app
from chisurf.plugins.spectra_downloader.mmfdb_adapter import FluorophoreDatabase, DEFAULT_DATABASE_PATH
copy = tmp / "spectra.db"; shutil.copy(DEFAULT_DATABASE_PATH, copy)
db = FluorophoreDatabase(copy); db.connect()
app = create_app(db); d = Driver(app)
out = Path(sys.argv[1])
d.screenshot(out / "spectra_overview.png")
app.panel = "Browse"; app.model.search = "ATTO 647N"
rows = app.model.filtered(); print(len(rows), "rows")
if rows: app.model.show(rows[0]["probe_id"])
d.screenshot(out / "spectra_browse.png")
app.close(); db.close()
