"""Draw the CURRENT (pre-upgrade) standalone emtk app: empty, populated, error. Usage: <tempdir> <out>."""
import os, pathlib, shutil, sys, time
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from test.gui.emtk_port_parity import emtk_screenshot
from emtk.testing import RecordingPainter
from chisurf.plugins.tttr.photon_table.gui.controller import PhotonTableController
shutil.copy("test/data/tttr/BH/132/BH_SPC132.spc", T / "BH_SPC132.spc")
c = PhotonTableController(); app = c.app
def settle():
    for _ in range(200):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
        if not c.job.running: break
        time.sleep(0.02)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
emtk_screenshot(app, O / "before_emtk_empty_1200x800.png", (1200, 800))
c.load_file(str(T / "BH_SPC132.spc")); settle()
emtk_screenshot(app, O / "before_emtk_populated_1200x800.png", (1200, 800))
c.load_file(str(T / "missing.spc")); settle()
emtk_screenshot(app, O / "before_emtk_error_1200x800.png", (1200, 800))
