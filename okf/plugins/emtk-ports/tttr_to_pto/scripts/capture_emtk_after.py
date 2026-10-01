"""Draw the upgraded native converter into the states of the evidence screenshots. Usage: <tempdir> <out>."""
import os, pathlib, shutil, sys, time
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from test.gui.emtk_port_parity import emtk_screenshot
from emtk.testing import RecordingPainter
DATA = pathlib.Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna")
for n in ("m000.spc", "m001.spc"): shutil.copy(DATA / n, T / n)
(T / "m000.set").write_bytes(b"BH settings kept byte for byte\r\n")
from chisurf.plugins.core.tttr_to_pto.gui.app import make_app
app = make_app()
def finish():
    while app.model.job.running or app.model.pending:
        app.draw(RecordingPainter(), 0, 0, 900, 600); time.sleep(0.02)
    app.draw(RecordingPainter(), 0, 0, 900, 600)
def shot(name, size=(900, 600)):
    t0 = time.time(); emtk_screenshot(app, O / f"{name}_{size[0]}x{size[1]}.png", size); print(name, round(time.time() - t0, 1), flush=True)
for size in ((900, 600), (800, 600)): shot("after_empty", size)
app.add_paths([str(T / "m001.spc"), str(T / "m000.spc")]); finish()
for size in ((900, 600), (800, 600)): shot("after_populated_packed", size)
for n in ("m000.spc", "m001.spc", "m000.set"): (T / n).rename(T / (n + ".saved"))
app.add_paths([str(T / "m000.pto")]); finish()
(T / "bad.pto").write_bytes(b"not a PTO"); app.add_paths([str(T / "bad.pto")]); finish()
(T / "alone.set").write_bytes(b"sidecar"); app.add_paths([str(T / "alone.set")])
for size in ((900, 600), (800, 600)): shot("after_populated", size)
shot("after_populated_narrow", (500, 500))
app.model.request_add(); app.draw(RecordingPainter(), 0, 0, 900, 600); shot("after_populated_file_dialog"); app.dialog = None
app.help_window.show(); shot("after_populated_help"); app.help_window.hide()
app.tour.start(1); shot("after_populated_guide")
