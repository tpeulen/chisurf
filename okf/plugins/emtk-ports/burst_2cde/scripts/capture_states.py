"""A run in progress (progress bar) and the folder dialog, on the demo folder. usage: capture_states.py <out_dir>"""
import pathlib, sys, tempfile, threading
from test.gui.emtk_port_parity import emtk_screenshot
from emtk.testing import RecordingPainter
from chisurf.plugins.burst.burst_2cde.core import computation as core
from chisurf.plugins.burst.burst_2cde.gui.app import create_app
from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build

out = pathlib.Path(sys.argv[1])
folder = build(pathlib.Path(tempfile.mkdtemp()) / "measurement")
gate, reached = threading.Event(), threading.Event()
original = core.compute_2cde


def held(*a, progress_window=None, **k):
    progress_window.set_value(24)
    reached.set()
    gate.wait(30)
    return original(*a, progress_window=progress_window, **k)


core.compute_2cde = held
a = create_app()
a.model.donor_channels_text, a.model.acceptor_channels_text = "0", "1"
a.model.set_folder(folder)
a.controller.run()
reached.wait(30)
for _ in range(2):
    a.draw(RecordingPainter(), 0, 0, 1200, 800)
emtk_screenshot(a, out / "after_running_1200x800.png", (1200, 800))
gate.set()
a.close()

b = create_app()
b.controller.browse()
for _ in range(2):
    b.draw(RecordingPainter(), 0, 0, 1200, 800)
emtk_screenshot(b, out / "after_folder_dialog_1200x800.png", (1200, 800))
b.close()
