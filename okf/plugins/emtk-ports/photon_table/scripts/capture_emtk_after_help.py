"""The help window, the guided tour and the narrow window of the native app. Usage: <tempdir> <out>."""
import os, pathlib, shutil, sys, time
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from test.gui.emtk_port_parity import emtk_screenshot
from emtk.testing import RecordingPainter
from chisurf.plugins.tttr.photon_table.gui.app import make_app
shutil.copy("test/data/tttr/BH/132/BH_SPC132.spc", T / "BH_SPC132.spc")
app = make_app(); app.load_file(str(T / "BH_SPC132.spc"))
for _ in range(300):
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    if not app.job.busy: break
    time.sleep(0.02)
def shot(name, size=(1200, 800)):
    t0 = time.time(); emtk_screenshot(app, O / f"{name}_{size[0]}x{size[1]}.png", size); print(name, round(time.time() - t0, 1), flush=True)
shot("after_populated_narrow", (500, 500))
app.help_window.show(); shot("after_populated_help"); app.help_window.hide()
app.tour.start(0); shot("after_populated_guide")
