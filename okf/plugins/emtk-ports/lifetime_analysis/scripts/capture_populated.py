"""Hub with the G-factor tool populated (fast + slow reference loaded) and the MaxEnt tool after a run. Usage: <out_dir>. Temp settings."""
import test.gui.emtk_port_parity  # noqa (first: the stdlib "test" must not win)
import pathlib, sys, tempfile
sys.path.insert(0, "okf/plugins/emtk-ports/vv_vh_g_factor/scripts"); sys.path.insert(0, "okf/plugins/emtk-ports/maxent_decay/scripts")
import chisurf.core.settings as st
st.chisurf_settings_path = pathlib.Path(tempfile.mkdtemp())
from make_data import make_data
from stub_fit import stub_fit
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.app import make_app
out = pathlib.Path(sys.argv[1]); files = make_data(tempfile.mkdtemp())
for size in [(1200, 800), (800, 600)]:
    a = make_app()
    g = a.select("vv_vh_g_factor"); m = g.model; m.fp_dt_ns = 0.05; m.load(files["fast"]); m.load(files["slow"], slow=True); m.background = True; m.compute()
    for _ in range(4): a.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(a, out / f"after_populated_g_factor_{size[0]}x{size[1]}.png", size)
    x = a.select("maxent_decay"); x.model.load_fit(stub_fit()); x.model.settings.tau_bins = 32; x.model.settings.tau_max = 8.0; x.model.run()
    for _ in range(4): a.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(a, out / f"after_populated_maxent_{size[0]}x{size[1]}.png", size)
    a.close()
