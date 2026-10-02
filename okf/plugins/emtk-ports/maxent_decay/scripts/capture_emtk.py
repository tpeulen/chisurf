"""Populated emtk app (stub fit, MEM run and L-curve done in process) at both sizes. Usage: <out_dir> <prefix>. Temp HOME/settings."""
import test.gui.emtk_port_parity  # noqa (first: the stdlib "test" must not win)
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from stub_fit import stub_fit
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.fluorescence_decay.maxent_decay.gui.app import make_app
from chisurf.plugins.fluorescence_decay.maxent_decay.gui.model import execute_job
out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
for size in [(1200, 800), (800, 600)]:
    a = make_app(); m = a.model
    m.load_fit(stub_fit()); m.settings.tau_max = 8.0; m.settings.tau_bins = 64
    m.run(); m.lcurve = execute_job({"kind": "lcurve", "snapshot": m.snapshot()})
    for _ in range(4): a.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
