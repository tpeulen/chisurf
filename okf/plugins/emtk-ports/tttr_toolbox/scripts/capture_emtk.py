"""Populated emtk captures of the TTTR toolbox: python capture_emtk.py <outdir> <prefix> (temp HOME/settings)."""
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
import test.gui
tmp = Path(tempfile.mkdtemp(prefix="ttbemtk_"))
os.environ.update(HOME=str(tmp), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"),
                  MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"))
from chisurf.plugins.emtk_test_input import Driver
from chisurf.plugins.tttr.tttr_toolbox.gui.app import make_app
out, prefix = Path(sys.argv[1]), sys.argv[2]
app = make_app(); d = Driver(app)
app.filter = ""
for role in ("alex_creator", "count_rate"):
    app.select(role)
    for size in ((1200, 800), (800, 600)):
        d.resize(size); d.screenshot(out / f"{prefix}_{role}_{size[0]}x{size[1]}.png")
app.close()
