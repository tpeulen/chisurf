"""emtk app in the same populated states as capture_qt.py.

Run: python okf/plugins/emtk-ports/vv_vh_anisotropy/scripts/capture_emtk.py <out-dir> <prefix> [size]
"""
import sys, tempfile, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from data import make
from chisurf.plugins.vv_vh_anisotropy.gui.app import create_app

out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
size = tuple(int(v) for v in (sys.argv[3] if len(sys.argv) > 3 else "1200x800").split("x"))
tmp = pathlib.Path(tempfile.mkdtemp())
a = make(tmp / "a.dat", seed=1); b = make(tmp / "b.dat", seed=2, rinf=0.08)
bad = tmp / "bad.dat"; bad.write_text("not numbers\n")

def shot(app, name, sz=size):
    for _ in range(1):
        app.draw(RecordingPainter(), 0, 0, *sz)
    emtk_screenshot(app, out / f"{prefix}_{name}_{sz[0]}x{sz[1]}.png", sz)

app = create_app(); m = app.model
shot(app, "empty")
m.load(a); m.g_factor = 1.05; m.bg_vv = 12.0; m.bg_vh = 9.0; m.shift = 1.5; m.compute()
shot(app, "populated")
print("r_inf:", m.r_infty, "region:", m.region_bounds)
app.files_dropped([str(bad)]); shot(app, "load_error"); print("message after bad drop:", m.message)
m.load(a)
m.open_batch(); m.batch_files = [str(a), str(b)]
shot(app, "batch_queued")
m.run_batch(); shot(app, "batch_results")
for r in m.batch_results: print("row", r)
m.batch_files.append(str(bad)); m.run_batch(); shot(app, "batch_bad_file")
m.request_load(); shot(app, "file_dialog")
# the guide waiting for a press, and the help window
m.batch_open = False; m.request = ""; app.dialog = None
app.tour.start(0); shot(app, "guide_await_load")
app.tour.notify_used("request_load"); app.tour.next(); shot(app, "guide_g_factor")
app.tour.stop(); app.help_window.show(); shot(app, "help")
