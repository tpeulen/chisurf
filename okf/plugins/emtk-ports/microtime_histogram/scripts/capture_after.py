"""After-upgrade captures of the micro-time histogram on BH_SPC132.spc (SPC-130, green detector), both sizes.

usage: capture_after.py <out_dir> <prefix>   (repo root; temp HOME / CHISURF_SETTINGS_DIR / MMFDB_* from the caller)
"""
import pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity as pp  # before the plugin import
from emtk.testing import RecordingPainter
from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app
from chisurf.plugins.tttr.microtime_histogram.tests.test_emtk_histogram_clicks import SETUP, SPC

out, prefix = pathlib.Path(sys.argv[1]), sys.argv[2]
work = pathlib.Path(tempfile.mkdtemp())


def settle(a, size):
    for _ in range(3):
        a.draw(RecordingPainter(), 0, 0, *size)
    while a.job.running:
        time.sleep(0.05)
        a.draw(RecordingPainter(), 0, 0, *size)
    for _ in range(4):
        a.draw(RecordingPainter(), 0, 0, *size)


def shot(a, name, size):
    pp.emtk_screenshot(a, out / f"{prefix}_{name}_{size[0]}x{size[1]}.png", size)


for size in [(1200, 800), (800, 600)]:
    a = create_app(); a.definition_changed(SETUP); settle(a, size); shot(a, "idle", size)
    a.model.filetype = "SPC-130"; a.add_files([str(SPC)]); a.model.output = str(work / "decay.dat"); a.model.auto_save = False
    settle(a, size); shot(a, "queued", size)
    a.compute(); settle(a, size); shot(a, "populated", size)
    a.model.vv_shift = 12; a.model.update_timeshifts(); settle(a, size); shot(a, "shifted", size)
    a.model.vv_shift = 0; a.model.update_timeshifts()
    a.choose("TTTR inputs", a.add_files, multiple=True); settle(a, size); shot(a, "file_dialog", size); a.dialog = None
    a.docks.focus("setup"); settle(a, size); shot(a, "detector_tab", size); a.docks.focus("inputs")
    a.tour.start(4); settle(a, size); shot(a, "guide", size); a.tour.stop()
    a.help.show(); settle(a, size); shot(a, "help", size)
    a.close()
