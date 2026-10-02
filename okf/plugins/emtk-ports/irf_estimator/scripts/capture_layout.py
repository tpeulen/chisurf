"""After-upgrade captures of the IRF estimator on the measured donor decay: idle, loaded, estimated, range drag, dialogs, tour, help.

usage: capture_layout.py <out_dir> <prefix>   (repo root; temp HOME / CHISURF_SETTINGS_DIR / MMFDB_* from the caller)
"""
import pathlib, sys, time
sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity as pp  # before the plugin import
from emtk.testing import RecordingPainter
from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import IRFEstimatorApp
from chisurf.plugins.fluorescence_decay.irf_estimator.test.test_emtk_irf_estimator_clicks import DECAY

out, prefix = pathlib.Path(sys.argv[1]), sys.argv[2]


def settle(a, size):
    for _ in range(3):
        a.draw(RecordingPainter(), 0, 0, *size)
    while a.future is not None:
        time.sleep(0.02)
        a.draw(RecordingPainter(), 0, 0, *size)
    for _ in range(4):
        a.draw(RecordingPainter(), 0, 0, *size)


def shot(a, name, size):
    pp.emtk_screenshot(a, out / f"{prefix}_{name}_{size[0]}x{size[1]}.png", size)


for size in [(1200, 800), (800, 600)]:
    a = IRFEstimatorApp(); settle(a, size); shot(a, "idle", size)
    a.model.load_file(str(DECAY)); a.model.rl_iterations = 100; settle(a, size); shot(a, "loaded", size)
    a.model.use_range_selection = True; a.model.range_bounds = [60.0, 600.0]
    a.start_estimate(); settle(a, size); shot(a, "estimated", size)
    a.model.auto_update_enabled = True; settle(a, size); shot(a, "auto_update", size); a.model.auto_update_enabled = False
    a.choose_file(); a.dialog.directory = str(DECAY.parent); settle(a, size); shot(a, "file_dialog", size); a.dialog = None
    a.tour.start(2); settle(a, size); shot(a, "guide", size); a.tour.stop()
    a.help_window.show(); settle(a, size); shot(a, "help", size)
    a.close()
