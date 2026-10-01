"""Re-draw the guide step after its hint was shortened. Usage: <tempdir> <out>."""
import os, pathlib, shutil, sys, time
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.core.tttr_to_pto.gui.app import make_app
app = make_app(); app.tour.start(1)
emtk_screenshot(app, O / "after_populated_guide_900x600.png", (900, 600))
