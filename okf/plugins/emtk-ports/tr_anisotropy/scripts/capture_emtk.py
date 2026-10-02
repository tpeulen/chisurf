"""Populated emtk app, every step, both sizes. Usage: <out_dir> <prefix> (before_emtk | after_populated). Temp settings only."""
import pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from make_data import make_data
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.app import make_app
out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
files = make_data(pathlib.Path(tempfile.mkdtemp()) / "data")
for size in [(1200, 800), (800, 600)]:
    a = make_app(); m = a.model
    for k, p in files.items():
        setattr(m, k + "_path", p)
    m.load_data(); m.g_factor, m.l1, m.l2 = 1.1, 0.02, 0.01
    for step in range(6):
        a.select_step(step)
        for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{step + 1}_{size[0]}x{size[1]}.png", size)
