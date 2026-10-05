"""Qt baseline of the Intensity trace tool, populated: BH_SPC132.spc (a temp copy: Compute HMM writes beside the file),
10 ms bins, a 3-state HMM, both tabs and the four result windows. usage: capture_qt.py <out_dir>

Writes before_<state>.png and before.json (union of the control inventory over the states) and qt_values.json (the
numbers the native port must reproduce).
"""

import json
import os
import pathlib
import shutil
import sys
import tempfile
import time

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
work = pathlib.Path(tempfile.mkdtemp())
os.environ.update(CHISURF_SETTINGS_DIR=str(work / "s"), MMFDB_SETTINGS_DIR=str(work / "m"),
                  MMFDB_DATABASE_PATH=str(work / "m.sqlite"), HOME=str(work))
REPO = pathlib.Path(__file__).resolve().parents[5]
SPC = work / "BH_SPC132.spc"
shutil.copy(REPO / "test/data/tttr/BH/132/BH_SPC132.spc", SPC)
# the repo's test.gui first: a chisurf import loads the standard library's ``test`` package otherwise
from test.gui import migration_parity as mp  # noqa: E402, I001
from test.gui.emtk_port_parity import normalize  # noqa: E402
import numpy as np  # noqa: E402
from qtpy import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
import chisurf.plugins.tttr.intensity_trace as it  # noqa: E402


def pump(n=20):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


controls = set()


def grab(widget, name):
    widget.resize(1200, 800)
    widget.show()
    pump()
    widget.grab().save(str(out / f"before_{name}.png"))
    controls.update(normalize(c) for c in mp.control_inventory(widget)["controls"])
    print("captured", name)


win = it.IntensityTrace()
grab(win, "empty")
win.load_file(file_path=str(SPC))
pump()
tabs = win.findChild(QtWidgets.QTabWidget)
grab(win, "processing")
tabs.setCurrentIndex(1)
win.hmm_components_spinner.setValue(3)
win.perform_hmm()
pump()
grab(win, "hmm")
d = win.current_data
states = np.asarray(d["hmm_states"])
bics = it.compute_bic_curve(d["padded"], max_states=6)
dwell = it.compute_dwell_times(states, d["window_ms"] / 1000.0)
padded = d["padded"]
fret = padded[:, 0] / np.clip(padded.sum(axis=1), 1e-12, None)
grab(it.ElbowPlotWindow(bics), "bic_elbow")
grab(it.DwellTimeWindow(dwell), "dwell_times")
grab(it.TransitionMatrixWindow(d["transmat"]), "hmm_matrix")
grab(it.DistPlotWindow({s: fret[states == s] for s in range(int(states.max()) + 1)}), "fret_distributions")
(out / "before.json").write_text(json.dumps({"entrypoint": "chisurf.plugins.tttr.intensity_trace:IntensityTrace",
                                             "size": [1200, 800], "controls": sorted(controls - {""})}, indent=2,
                                            ensure_ascii=False))
values = {"channels": d["channels"], "n_bins": int(padded.shape[0]), "counts_sum": padded.sum(axis=0).tolist(),
          "window_ms": d["window_ms"], "state_counts": np.bincount(states).tolist(),
          "transmat": np.asarray(d["transmat"]).round(6).tolist(), "bic": [[float(v) for v in b] if isinstance(b, (tuple, list)) else float(b) for b in bics],
          "outputs": sorted(str(p.relative_to(work)) for p in work.rglob("*") if p.is_file() and "HMM#" in str(p))}
(out / "qt_values.json").write_text(json.dumps(values, indent=1))
print(values["channels"], values["n_bins"], values["state_counts"], len(values["outputs"]), "controls", len(controls))
