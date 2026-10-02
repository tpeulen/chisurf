"""emtk hub, every panel selected, both sizes. Usage: <out_dir> <prefix>. Temp HOME/settings."""
import test.gui.emtk_port_parity  # noqa (first: the stdlib "test" must not win)
import pathlib, sys, tempfile
import chisurf.core.settings as st
st.chisurf_settings_path = pathlib.Path(tempfile.mkdtemp())
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.app import make_app, PANELS
out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
for size in [(1200, 800), (800, 600)]:
    a = make_app()
    for i, (ident, *_r) in enumerate(PANELS, 1):
        a.select(ident)
        for _ in range(4): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{i}_{ident}_{size[0]}x{size[1]}.png", size)
    a.close()
