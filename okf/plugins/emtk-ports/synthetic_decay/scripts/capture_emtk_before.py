"""Draw the CURRENT (pre-upgrade) native generator: empty, VM, VV/VH with noise, bad IRF. Usage: <tempdir> <out>."""
import json, os, pathlib, sys, time
import numpy as np
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.app import SyntheticDecayApp
app = SyntheticDecayApp(fit_sink=lambda g, p: None); m = app.model
S = (1200, 900)
def shot(name):
    t0 = time.time(); emtk_screenshot(app, O / f"{name}_{S[0]}x{S[1]}.png", S); print(name, round(time.time() - t0, 1), flush=True)
shot("before_emtk_empty")
m.generate(); shot("before_emtk_populated")
m.update_spectrum(0, "tau", 0.5); m.add_row(); m.update_spectrum(2, "amp", 0.25); m.update_spectrum(2, "tau", 9.0)
m.add_rotation_row(); m.shot_noise = True; m.photon_count = 200000.0; m.seed = 7
m.set_polarization("vv/vh"); m.g_factor, m.l1, m.l2 = 1.3, 0.02, 0.05; m.generate()
shot("before_emtk_vvvh_noise")
m.irf_path = str(T / "missing_irf.txt"); m.set_polarization("vm"); m.generate()
shot("before_emtk_bad_irf")
print(m.status_text())
