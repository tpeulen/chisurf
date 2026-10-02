"""Populated emtk app (stack loaded, beads detected, one fitted, all fitted) at both sizes. Usage: <out_dir> <prefix>. Temp HOME/settings."""
import test.gui.emtk_port_parity  # noqa (first: the stdlib "test" must not win)
import pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import chisurf.core.settings as st
st.chisurf_settings_path = pathlib.Path(tempfile.mkdtemp())
from make_data import make_stack
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.microscopy.psf_determination.gui.app import make_app
out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
for size in [(1200, 800), (800, 600)]:
    a = make_app(); m = a.model
    m.pixel_size_nm, m.z_step_nm = 100.0, 300.0
    m.set_stack(make_stack()); m.detect_beads(); m.selected_bead = (10, 20, 20); m.fit_selected(); m.fit_all(); m.selected_bead = (9, 20, 20); m.fit_selected()
    a.canvas.z = 10
    for _ in range(4): a.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
