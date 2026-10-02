"""Populated emtk app (trace loaded, fit and scan done) at both sizes. Usage: <out_dir> <prefix>. Temp HOME/settings."""
import test.gui.emtk_port_parity  # noqa (first: the stdlib "test" must not win)
import pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import chisurf.core.settings as st
st.chisurf_settings_path = pathlib.Path(tempfile.mkdtemp())
from make_data import make_trace
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.core.hmm.gui.app import make_app
out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
for size in [(1200, 800), (800, 600)]:
    a = make_app(); m = a.model
    m.set_traces([make_trace()[0]], ["trace.csv"]); m.n_states = 3; m.time_step = 0.001; m.max_states = 5
    m.run(); m.run_scan()
    for _ in range(4): a.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
