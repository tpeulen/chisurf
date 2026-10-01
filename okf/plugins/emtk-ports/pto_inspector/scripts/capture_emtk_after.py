"""Draw the upgraded native PTO inspector into the states of the evidence screenshots. Usage: <tempdir> <out>."""
import os, pathlib, shutil, sys, time
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from test.gui.emtk_port_parity import emtk_screenshot
from emtk.testing import RecordingPainter
from chisurf.core.fio.pto import Measurement
from chisurf.plugins.core.pto_inspector.test.test_core import container, PTU
path = container.__wrapped__(T)
from chisurf.plugins.core.pto_inspector.gui.app import make_app
app = make_app()
def shot(name, size=(1200, 800)):
    t0 = time.time(); emtk_screenshot(app, O / f"{name}_{size[0]}x{size[1]}.png", size); print(name, round(time.time() - t0, 1), flush=True)
shot("after_empty")
app.files_dropped([str(path)])          # the host drop hook
for size in ((1200, 800), (800, 600)): shot("after_populated", size)
app.model.select_uid(next(i.uid for i in app.model.inspection.infos() if i.name == "lifetimes"))
shot("after_populated_lifetimes")
app.model.select_uid(next(i.uid for i in app.model.inspection.infos() if i.name == "bursts"))
shot("after_populated_bursts_tool")
app.verify(); shot("after_populated_verified")
shot("after_populated_narrow", (500, 500))
raw = T / "raw.ptu"; shutil.copy(PTU, raw); app.files_dropped([str(raw)]); app.draw(RecordingPainter(), 0, 0, 1200, 800)
shot("after_populated_pack_dialog"); app.vendor_paths = []
app.choose_file("open"); app.draw(RecordingPainter(), 0, 0, 1200, 800); shot("after_populated_file_dialog"); app.dialog = None; app.file_window = None
bad = T / "broken.pto"; bad.write_bytes(b"not a pto"); app.model.set_filename(str(bad)); shot("after_populated_error")
app.model.set_filename(str(path))
app.help.show(); shot("after_populated_help"); app.help.open = False
app.tour.start(1); shot("after_populated_guide")
