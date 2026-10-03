"""Run test.gui.emtk_port_parity (after/compare) with the plugin's default staging DB redirected to a temp copy-free DB.

``create_app()`` without a db opens the repository's spectra.db (and may write migration backups into the plugin folder), so
the harness is run with ``get_db`` pointing at an empty database in a temp folder: python run_parity.py after|compare <outdir>
"""
import os, runpy, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
import test.gui  # the repo's test package, not the stdlib one
tmp = Path(tempfile.mkdtemp(prefix="spectraparity_"))
os.environ.update(HOME=str(tmp), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"))
import chisurf.plugins.spectra_downloader as plugin
from chisurf.plugins.spectra_downloader.mmfdb_adapter import FluorophoreDatabase
def get_db():
    import numpy as np
    db = FluorophoreDatabase(tmp / "staging.db")
    db.connect()
    if not db.conn.execute("SELECT COUNT(*) FROM probes").fetchone()[0]:
        x = np.arange(400.0, 701.0, 5.0)
        for name, prov, kind, c in (("EGFP", "fpbase", "fluorescent_protein", 509), ("Alexa Fluor 488", "atto", "organic_dye", 519),
                                    ("ET525/50m", "chroma", "bandpass", 525)):
            db.register_component(name=name, source=prov, kind=kind, properties={"em_max": c, "description": "Reference fixture"},
                                  spectra={"emission": (x, np.exp(-0.5 * ((x - c) / 22.0) ** 2))})
    return db
plugin.get_db = get_db
import json, subprocess
from test.gui import emtk_port_parity as epp
phase, out = sys.argv[1], Path(sys.argv[2])
if phase == "after":
    # epp.after() also runs qt_free() in a fresh interpreter that would open the real spectra.db: do its steps here with
    # get_db redirected, and check Qt-freedom in a child that gets the same redirection.
    app = epp.build_emtk_app("spectra_downloader")
    for size in epp.SIZES:
        epp.emtk_screenshot(app, out / f"after_{size[0]}x{size[1]}.png", size)
    inv = None
    for panel in ("Overview", "Browse", "Download", "Add to MMFDB"):  # every panel, populated, merged into one inventory
        app.panel = panel
        if panel == "Browse":
            app.model.show(app.model.rows[0]["probe_id"])
        part = epp.emtk_inventory(app, epp.SIZES[0])
        if inv is None:
            inv = part
        else:
            inv["controls"] = sorted(set(inv["controls"]) | set(part["controls"]))
            inv["interactive"] += part["interactive"]
            inv["controls_without_tooltip"] = sorted(set(inv["controls_without_tooltip"]) | set(part["controls_without_tooltip"]))
    app.close()
    child = r"""
import importlib.abc, os, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6','pyqtgraph'} or fullname == 'chisurf.gui' or fullname.startswith('chisurf.gui.'):
            raise AssertionError('Qt import attempted: ' + fullname)
sys.meta_path.insert(0, Block())
from pathlib import Path
import chisurf.plugins.spectra_downloader as plugin
from chisurf.plugins.spectra_downloader.mmfdb_adapter import FluorophoreDatabase
plugin.get_db = lambda: FluorophoreDatabase(Path(os.environ['HOME']) / 'staging.db')
from emtk.testing import RecordingPainter
from chisurf.plugins.spectra_downloader.gui.app import create_app
a = create_app()
for panel in ('Overview', 'Browse', 'Download', 'Add to MMFDB'):
    a.panel = panel; a.draw(RecordingPainter(), 0, 0, 1200, 800)
a.close(); print('QT-FREE OK')
"""
    done = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=os.getcwd()))
    inv["qt_free"] = {"ok": done.returncode == 0, "output": (done.stdout + done.stderr)[-1500:]}
    (out / "after.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False))
    print("after:", len(inv["controls"]), "controls,", len(inv["controls_without_tooltip"]), "without tooltip, qt-free:", inv["qt_free"]["ok"])
else:
    print(epp.compare("spectra_downloader", out)["lost"])
