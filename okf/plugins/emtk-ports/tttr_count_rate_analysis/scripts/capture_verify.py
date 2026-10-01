"""Verification pass screenshots: drop, error on the status line, guide waiting for a press, populated."""
import pathlib, sys, tempfile
import tttrlib
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller import create_app

out = pathlib.Path(sys.argv[1])
ptu = pathlib.Path("test/data/clsm/Leica_SP5.ptu").resolve()
routing = [int(c) for c in tttrlib.TTTR(str(ptu)).get_used_routing_channels()]
channels = {"all": [{"detector_chs": routing, "micro_time_range": None, "window_range": None}]}

def shot(app, name, size=(1200, 800)):
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(app, out / f"{name}_{size[0]}x{size[1]}.png", size)

app = create_app()
t = app.tool
t.channels = lambda: channels
t._model.channels_provider = t.channels
shot(app, "verify_error_no_files")            # message after Calculate without files
t.calculate()
shot(app, "verify_error_no_files")
print("message:", t.message)
tmp = pathlib.Path(tempfile.mkdtemp()); (tmp / "notes.txt").write_text("x")
print("drop txt:", app.files_dropped([str(tmp / "notes.txt")]), "|", t.message)
print("drop file:", app.files_dropped([str(ptu)]), t._model.files)
t.calculate(); t.job.future.result(timeout=120); t.job.poll()
shot(app, "verify_populated"); shot(app, "verify_populated", (800, 600))
app.start_guide(); shot(app, "verify_guide_await_add_files")
app.count_rate_gui.tour.notify_used("add_files"); app.count_rate_gui.tour.next()
shot(app, "verify_guide_channels")
app.close()
