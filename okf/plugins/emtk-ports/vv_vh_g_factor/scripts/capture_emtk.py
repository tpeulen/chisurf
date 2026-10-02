"""Populated emtk app at both sizes. Usage: <out_dir> <prefix>. Temp settings only."""
import test.gui.emtk_port_parity  # noqa (first: the stdlib "test" must not win)
import pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from make_data import make_data
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.vv_vh_g_factor.gui.app import create_app
out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
files = make_data(tempfile.mkdtemp())
for size in [(1200, 800), (800, 600)]:
    a = create_app(); m = a.model
    m.fp_dt_ns = 0.05; m.load(files["fast"]); m.load(files["slow"], slow=True); m.background = True; m.compute()
    m.batch_files = [files["batch1"], files["batch2"]]; m.compute_batch()
    for _ in range(4): a.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
