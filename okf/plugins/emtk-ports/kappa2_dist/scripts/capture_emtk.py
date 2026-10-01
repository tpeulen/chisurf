"""emtk κ² app after its construction compute, both sizes (Monte-Carlo: numbers vary by seed; seed 7 here)."""
import sys, pathlib, time
import numpy as np
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.calculator.kappa2_dist.gui.app import make_app
out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
for size in [(1200, 800), (800, 600)]:
    np.random.seed(7); a = make_app()
    for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
