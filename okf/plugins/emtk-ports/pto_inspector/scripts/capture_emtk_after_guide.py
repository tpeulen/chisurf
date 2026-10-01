"""Re-draw the guide step after its hint was shortened. Usage: <tempdir> <out>."""
import os, pathlib, sys
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.core.pto_inspector.test.test_core import container
path = container.__wrapped__(T)
from chisurf.plugins.core.pto_inspector.gui.app import make_app
app = make_app(); app.files_dropped([str(path)]); app.tour.start(1)
emtk_screenshot(app, O / "after_populated_guide_1200x800.png", (1200, 800))
