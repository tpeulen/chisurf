"""Populated emtk captures of the Spectra tool: python capture_emtk.py <outdir> <prefix> (temp HOME/DB; no network)."""
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
import test.gui
tmp = Path(tempfile.mkdtemp(prefix="spectraemtk_"))
os.environ.update(HOME=str(tmp), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"),
                  MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"))
import numpy as np
from chisurf.plugins.emtk_test_input import Driver
from chisurf.plugins.spectra_downloader.gui.app import create_app
from chisurf.plugins.spectra_downloader.mmfdb_adapter import FluorophoreDatabase
out, prefix = Path(sys.argv[1]), sys.argv[2]
db = FluorophoreDatabase(tmp / "staging.db"); db.connect()
x = np.arange(400.0, 701.0, 5.0)
for name, prov, kind, c in (("EGFP", "fpbase", "fluorescent_protein", 509), ("Alexa Fluor 488", "atto", "organic_dye", 519),
                            ("ET525/50m", "chroma", "bandpass", 525), ("DMLP550", "thorlabs", "dichroic", 550),
                            ("SPAD 650", "thorlabs", "apd", 650)):
    db.register_component(name=name, source=prov, kind=kind, properties={"em_max": c, "description": "Reference fixture"},
                          spectra={"emission": (x, np.exp(-0.5 * ((x - c) / 22.0) ** 2))})
app = create_app(db); d = Driver(app)
for panel, key in (("Overview", "overview"), ("Browse", "browse"), ("Download", "download"), ("Add to MMFDB", "add_to_mmfdb")):
    app.panel = panel
    if panel == "Browse":
        app.model.refresh(); app.model.select(app.model.rows[0]["probe_id"])
    for size in ((1200, 800), (800, 600)):
        d.resize(size); d.screenshot(out / f"{prefix}_{key}_{size[0]}x{size[1]}.png")
app.close(); db.close()
