"""Drive the Qt Synthetic Decay Generator into populated states. Usage: <tempdir> <out dir> (repo root).

Temporary settings only; the IRF and spectrum files are written into the temp folder; the fit group goes
to a stub sink (no session).
"""
import json, os, pathlib, sys
import numpy as np
T = pathlib.Path(sys.argv[1]); O = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T / "settings")
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.tool import SyntheticDecayTool
w = SyntheticDecayTool(); w.resize(900, 900); w.show()
m = w.model
def grab(name):
    for _ in range(40): app.processEvents()
    w.grab().save(str(O / name))
sunk = []
m.fit_sink = lambda group, polarized: sunk.append((len(group), polarized))
out = {"initial_status": m.status_text(), "spectrum": m.spectrum_source(), "rotation": m.rotation_source()}
grab("before_populated_empty.png")
m.generate()
out["vm"] = {"status": m.status_text(), "n": len(m._y), "sum": float(np.sum(m._y)), "peak": float(np.max(m._y)), "r0": m._r[0], "r_last": m._r[-1],
             "series": [s["name"] for s in m.decay_series()], "aniso": [s["name"] for s in m.aniso_series()]}
grab("before_populated.png")
m.update_spectrum(0, "tau", 0.5); m.add_row(); m.update_spectrum(2, "amp", 0.25); m.update_spectrum(2, "tau", 9.0)
m.selected_row = 2; m.add_rotation_row(); m.shot_noise = True; m.photon_count = 200000.0; m.seed = 7
m.set_polarization("vv/vh"); m.g_factor, m.l1, m.l2 = 1.3, 0.02, 0.05
m.generate()
out["vvvh"] = {"status": m.status_text(), "n": len(m._vv), "vv_sum": float(np.sum(m._vv)), "vh_sum": float(np.sum(m._vh)),
               "series": [s["name"] for s in m.decay_series()], "metadata": m.aniso_metadata()}
grab("before_populated_vvvh_noise.png")
p = T / "pair.dat"; m.save(str(p)); out["vvvh_saved"] = {"status": m.status_text(), "size": p.stat().st_size, "head": p.read_text().splitlines()[:3], "tail": p.read_text().splitlines()[-4:]}
m.send_to_fit(); out["fit_sink"] = {"calls": sunk, "status": m.status_text()}
irf = T / "irf.txt"; t = np.arange(256) * 0.032; np.savetxt(irf, np.exp(-0.5 * ((t - 1.0) / 0.1) ** 2))
m.set_polarization("vm"); m.shot_noise = False; m.irf_path = str(irf); m.generate()
out["vm_irf"] = {"status": m.status_text(), "peak_bin": int(np.argmax(m._y)), "sum": float(np.sum(m._y))}
grab("before_populated_irf.png")
m.irf_path = str(T / "missing_irf.txt"); m.generate()
out["bad_irf"] = {"status": m.status_text(), "n": len(m._y)}
grab("before_populated_bad_irf.png")
m.irf_path = ""; spec = T / "spec.csv"; np.savetxt(spec, [[.3, 1.2], [.7, 4.0]], delimiter=",")
m.load_spectrum(str(spec)); out["loaded"] = {"status": m.status_text(), "rows": m.spectrum_source()}
(T / "bad.csv").write_text("a,b\nx,y\n"); m.load_spectrum(str(T / "bad.csv")); out["bad_load"] = m.status_text()
m.n_bins = 128; m.generate(); out["n128"] = len(m._y)
m2 = type(m)(); m2.save(str(T / "x.csv")); out["save_before_generate"] = m2.status_text()
m2.send_to_fit(); out["fit_before_generate"] = m2.status_text()
grab("before_populated_final.png")
print(json.dumps(out, indent=1, default=str)[:2500]); (O / "before_populated.json").write_text(json.dumps(out, indent=1, default=str))
