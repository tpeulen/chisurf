"""Draw the upgraded native generator into the states of the evidence screenshots. Usage: <tempdir> <out>."""
import os, pathlib, sys, time
import numpy as np
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from test.gui.emtk_port_parity import emtk_screenshot
from emtk.testing import RecordingPainter
from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.app import SyntheticDecayApp
app = SyntheticDecayApp(fit_sink=lambda g, p: None); m = app.model
def draw(size=(1200, 900)):
    for _ in range(3): app.draw(RecordingPainter(), 0, 0, *size)
def shot(name, size=(1200, 900)):
    t0 = time.time(); emtk_screenshot(app, O / f"{name}_{size[0]}x{size[1]}.png", size); print(name, round(time.time() - t0, 1), flush=True)
for size in ((1200, 900), (800, 600)): shot("after_empty", size)
m.generate()
for size in ((1200, 900), (800, 600)): shot("after_populated", size)
draw()
c = app.form.tables["spectrum_records"].control          # a cell edit, as a double click and Enter do
c.begin_edit(0, "tau"); c.editor.set_text("0.5"); c.commit_edit()
m.add_row(); m.update_spectrum(2, "amp", 0.25); m.update_spectrum(2, "tau", 9.0)
m.add_rotation_row(); m.shot_noise = True; m.photon_count = 200000.0; m.seed = 7
m.set_polarization("vv/vh"); m.g_factor, m.l1, m.l2 = 1.3, 0.02, 0.05; m.generate()
for size in ((1200, 900), (800, 600)): shot("after_populated_vvvh_noise", size)
t = np.arange(256) * 0.032; irf = T / "irf.txt"; np.savetxt(irf, np.exp(-0.5 * ((t - 1.0) / 0.1) ** 2))
m.set_polarization("vm"); m.shot_noise = False; m.irf_path = str(irf); m.generate(); shot("after_populated_irf")
m.irf_path = str(T / "missing_irf.txt"); m.generate(); shot("after_populated_bad_irf")
m.irf_path = ""; m.generate()
app.request_file("open", "Load lifetime spectrum", "", "Data files (*.csv *.txt *.dat)"); app.draw(RecordingPainter(), 0, 0, 1200, 900); shot("after_populated_file_dialog"); app.dialog = None
shot("after_populated_narrow", (500, 500))
app.help_window.show(); shot("after_populated_help"); app.help_window.hide()
app.tour.start(6); shot("after_populated_guide")
