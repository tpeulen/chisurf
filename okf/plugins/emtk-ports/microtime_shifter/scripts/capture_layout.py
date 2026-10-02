"""After-upgrade captures of the micro-time shifter on the demo file: populated, idle, dialogs, tour, help, both sizes.

usage: capture_layout.py <out_dir> <prefix>   (run from the repo root; temp settings and HOME come from the caller)
"""
import pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity as pp  # before the plugin import (it shadows the repo's `test` package)
from emtk.testing import RecordingPainter
from chisurf.plugins.tttr.tttr_microtime_shifter.gui.app import create_app
from chisurf.plugins.tttr.tttr_microtime_shifter.tests.demo_data import build

out, prefix = pathlib.Path(sys.argv[1]), sys.argv[2]
path = build(pathlib.Path(tempfile.mkdtemp()) / "demo")


def settle(a, size):
    for _ in range(3):
        a.draw(RecordingPainter(), 0, 0, *size)
    end = time.monotonic() + 60
    while a.job.running:
        assert time.monotonic() < end
        time.sleep(0.05)
        a.draw(RecordingPainter(), 0, 0, *size)
    for _ in range(3):
        a.draw(RecordingPainter(), 0, 0, *size)


def shot(a, name, size):
    pp.emtk_screenshot(a, out / f"{prefix}_{name}_{size[0]}x{size[1]}.png", size)


for size in [(1200, 800), (800, 600)]:
    a = create_app(); settle(a, size); shot(a, "idle", size)
    a.on_paths_dropped([str(path)]); settle(a, size)
    shot(a, "loaded", size)
    a.auto_align(); settle(a, size); shot(a, "populated", size)
    a.save_dialog(); settle(a, size); shot(a, "save_dialog", size); a.dialog = None
    a.choose("TTTR folder", lambda p: None, mode="folder"); settle(a, size); shot(a, "folder_dialog", size); a.dialog = None
    a.new_sample(); settle(a, size); shot(a, "sample_dialog", size); a.cancel_sample()
    a.form.open = getattr(a.form, "open", None)
    step = next(i for i, s in enumerate(a.tour.steps) if s.get("target", {}).get("name") == "auto_align")
    a.tour.start(step); settle(a, size); shot(a, "guide", size); a.tour.stop()
    a.help.show(); settle(a, size); shot(a, "help", size)
    a.close()
