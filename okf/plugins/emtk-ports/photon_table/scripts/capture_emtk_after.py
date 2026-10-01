"""Draw the upgraded native app into the states of the evidence screenshots. Usage: <tempdir> <out>."""
import os, pathlib, shutil, sys, time
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from test.gui.emtk_port_parity import emtk_screenshot
from emtk.testing import RecordingPainter
from chisurf.plugins.tttr.photon_table.gui.app import make_app
shutil.copy("test/data/tttr/BH/132/BH_SPC132.spc", T / "BH_SPC132.spc")
app = make_app(); m = app.model
def settle(size=(1200, 800)):
    for _ in range(300):
        app.draw(RecordingPainter(), 0, 0, *size)
        if not app.job.busy: break
        time.sleep(0.02)
    app.draw(RecordingPainter(), 0, 0, *size)
def shot(name, size=(1200, 800)):
    emtk_screenshot(app, O / f"{name}_{size[0]}x{size[1]}.png", size)
for size in ((1200, 800), (800, 600)): shot("after_empty", size)
app.load_file(str(T / "missing.spc")); settle(); shot("after_populated_error_missing")
app.load_file(str(T / "BH_SPC132.spc")); settle()
for size in ((1200, 800), (800, 600)): shot("after_populated", size)
m.set_channel(9)
for size in ((1200, 800), (800, 600)): shot("after_populated_filtered", size)
m.set_channel(-1); m.set_rows(50); m.set_first(100); shot("after_populated_page")
m.go_last(); shot("after_populated_last")
(T / "broken.ptu").write_text("not a TTTR file")
app.load_file(str(T / "broken.ptu")); settle(); shot("after_populated_error_unreadable")
m.set_rows(200); m.set_first(0)
m.request_open(); app.draw(RecordingPainter(), 0, 0, 1200, 800); shot("after_populated_file_dialog"); app.dialog = None
app.help_window.show(); shot("after_populated_help"); app.help_window.hide()
app.tour.start(0); shot("after_populated_guide"); app.tour.stop()
shot("after_populated_narrow", (500, 500))
