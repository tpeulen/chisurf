"""Populated captures of the Qt drift tool on a drifting TIFF stack and on the real photon stream. Usage: <out_dir>.

Everything on temporary settings. Writes before_populated_*.png, before_tab_*.png and qt_values.json (shifts, status messages, table
rows, the exported CSV and TIFF) -- the numbers the Qt window showed before the port.
"""
import json, os, pathlib, sys, tempfile, time

tmp = pathlib.Path(tempfile.mkdtemp())
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "s")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "m")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "m.sqlite")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from qtpy import QtCore, QtWidgets

out = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(out / "scripts"))
from make_data import drifting_stack  # noqa: E402
from chisurf.core.fio.image import imwrite, imread  # noqa: E402
from chisurf.plugins.microscopy.img_drift.gui import tool as tool_mod  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[5]
HT3 = REPO / "test/data/clsm/PQ_Olympus_MFIS.ht3"
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def settle(n=30):
    for _ in range(n):
        app.processEvents()


def wait():
    end = time.monotonic() + 120
    settle()
    while QtCore.QThreadPool.globalInstance().activeThreadCount() and time.monotonic() < end:
        app.processEvents(); time.sleep(0.02)
    settle(60)


w = tool_mod.ImgDriftTool()
w.resize(1200, 800)
w.show()
settle()


def grab(name):
    settle(); w.grab().save(str(out / f"{name}.png"))


def tab(text):
    for bar in w.findChildren(QtWidgets.QTabBar):
        for i in range(bar.count()):
            if bar.tabText(i) == text:
                bar.setCurrentIndex(i); settle(); return True
    return False


def state():
    m = w.model
    d = {"status": w.statusBar().currentMessage(), "model_status": m.status, "channel_names": m.channel_names, "channel": m.channel,
         "reference": m.reference, "mode": m.mode, "smooth": m.smooth, "subpixel": m.subpixel}
    if m.result is not None:
        r = m.result
        d.update(shifts=np.asarray(r.shifts).tolist(), total_drift=float(r.total_drift), n_frames=r.n_frames, kind=r.kind,
                 shift_rows=m.shift_rows(), drift_series=[{k: (np.asarray(v).tolist() if k in ("x", "y") else v) for k, v in s.items()} for s in m.drift_series()],
                 before_sum=float(np.asarray(m.before_image()).sum()), after_sum=float(np.asarray(m.after_image()).sum()),
                 before_std=float(np.asarray(m.before_image()).std()), after_std=float(np.asarray(m.after_image()).std()))
    return d


vals = {}
# 1. nothing loaded: Measure and both exports are silent in the Qt tool
w.run_with_progress(); grab("before_populated_empty_measure_pressed"); vals["empty_measure"] = state()
w._export_stack(); w._export_shifts(); vals["empty_exports"] = state()

# 2. a drifting TIFF: choosing it starts the measurement by itself ("file" event)
tif = tmp / "drift.tif"
imwrite(tif, drifting_stack())
w.model.set_filename(str(tif)); wait()
vals["tiff_default"] = state(); grab("before_populated_tiff_default")
for t in ("Drift trace", "Projection", "Shifts"):
    if tab(t):
        grab("before_tab_" + t.replace(" ", "_"))
tab("Drift trace")

# 3. options
m = w.model
m.reference = "previous"; m.mode = "constant"; m.smooth = 0.0; m.subpixel = True; w._refresh()
w.run_with_progress(); wait(); vals["tiff_previous_constant_subpixel"] = state(); grab("before_populated_tiff_options")
m.reference = "mean"; m.mode = "wrap"; m.smooth = 2.0; m.subpixel = False
w.run_with_progress(); wait(); vals["tiff_mean"] = state()
m.reference = "first"

# 4. exports (dialogs stubbed)
shifts_csv, stack_tif = tmp / "shifts.csv", tmp / "corrected.tif"
tool_mod.QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(shifts_csv), ""))
w.run_with_progress(); wait()
w._export_shifts(); settle(); vals["export_shifts"] = {"status": w.statusBar().currentMessage(), "csv": shifts_csv.read_text()}
tool_mod.QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(stack_tif), ""))
w._export_stack(); settle()
corrected = np.asarray(imread(str(stack_tif)))
vals["export_stack"] = {"status": w.statusBar().currentMessage(), "shape": list(corrected.shape), "sum": float(corrected.sum()),
                        "std_frame_to_frame": float(np.std([corrected[k] for k in range(corrected.shape[0])], axis=0).mean())}
(out / "qt_shifts.csv").write_text(shifts_csv.read_text())

# 5. the real photon stream: no measurable drift
w.model.reference = "first"
w.model.set_filename(str(HT3)); wait()
vals["photon_stream"] = state(); grab("before_populated_photon_stream")
tab("Projection"); grab("before_tab_Projection_photon")

# 6. errors: a corrupt file, a one-frame file, a missing file
(tmp / "bad.tif").write_bytes(b"not a tiff")
w.model.set_filename(str(tmp / "bad.tif")); wait(); vals["corrupt"] = state(); grab("before_populated_corrupt_file")
one = tmp / "one.tif"; imwrite(one, np.zeros((16, 16), dtype=np.float32))
w.model.set_filename(str(one)); wait(); vals["one_frame"] = state(); grab("before_populated_one_frame")
w.model.set_filename(str(tmp / "missing.tif")); wait(); vals["missing"] = state()
(out / "qt_values.json").write_text(json.dumps(vals, indent=1, default=str))
print(json.dumps({k: {a: b for a, b in v.items() if a in ("status", "model_status", "total_drift", "kind", "n_frames")} for k, v in vals.items() if isinstance(v, dict)}, default=str)[:2500])
